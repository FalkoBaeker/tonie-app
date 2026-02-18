#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.market_ingestion import (  # noqa: E402
    apply_time_window,
    build_ebay_search_queries,
    fetch_ebay_sold_listings_multi_query,
    fetch_kleinanzeigen_listings_multi_query,
)
from app.services.persistence import (  # noqa: E402
    get_market_coverage_report,
    init_db,
    prune_old_market_listings,
    save_market_listings,
)
from app.services.tonie_resolver import get_resolver  # noqa: E402


def _full_coverage_snapshot(
    *,
    resolver,
    fresh_minutes: int,
    min_effective_samples: float,
) -> dict:
    raw = get_market_coverage_report(
        fresh_minutes=max(1, int(fresh_minutes)),
        min_effective_samples=max(0.1, float(min_effective_samples)),
    )

    rows_by_id = {str(row.get("tonie_id")): row for row in (raw.get("items") or [])}
    full_items: list[dict] = []

    for item in resolver.catalog:
        tonie_id = str(item.get("id"))
        row = rows_by_id.get(tonie_id) or {}
        effective = float(row.get("effective_samples") or 0.0)

        full_items.append(
            {
                "tonie_id": tonie_id,
                "title": str(item.get("title") or ""),
                "raw_samples": int(row.get("raw_samples") or 0),
                "effective_samples": effective,
                "meets_target": effective >= float(min_effective_samples),
            }
        )

    full_items.sort(key=lambda r: (r["effective_samples"], r["raw_samples"], r["tonie_id"]))
    covered = sum(1 for row in full_items if row["meets_target"])

    return {
        "covered_tonies": covered,
        "total_tonies": len(full_items),
        "items": full_items,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh lowest-coverage Tonies first (coverage-driven market cache fill)."
    )
    parser.add_argument("--batch-size", type=int, default=40, help="How many uncovered IDs to refresh per pass")
    parser.add_argument("--passes", type=int, default=1, help="Number of passes to run")
    parser.add_argument(
        "--until-covered",
        action="store_true",
        help="Keep running passes until all resolver entries meet target",
    )
    parser.add_argument("--fresh-minutes", type=int, default=360, help="Coverage freshness window")
    parser.add_argument(
        "--min-effective-samples",
        type=float,
        default=12.0,
        help="Coverage target used to define uncovered IDs",
    )
    parser.add_argument("--delay-ms", type=int, default=200, help="Delay between refreshed tonies (per worker)")
    parser.add_argument("--max-items", type=int, default=80, help="Max sold listings per tonie")
    parser.add_argument(
        "--query-limit",
        type=int,
        default=8,
        help="Max query variants per tonie title",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of Tonies to refresh concurrently",
    )
    parser.add_argument(
        "--sources",
        choices=["ebay", "offers", "both"],
        default="both",
        help="Data sources to ingest per Tonie (default: both = ebay sold + classifieds offers)",
    )
    parser.add_argument(
        "--priority",
        choices=["lowest", "closest"],
        default="closest",
        help="lowest = start from worst coverage; closest = finish near-target IDs first",
    )
    parser.add_argument(
        "--cooldown-on-no-progress-minutes",
        type=int,
        default=0,
        help="Sleep between passes when no new rows were saved (useful under temporary anti-bot blocks)",
    )
    parser.add_argument(
        "--max-no-progress-passes",
        type=int,
        default=0,
        help="Stop after N consecutive no-progress passes (0 = unlimited)",
    )
    return parser.parse_args()


async def _refresh_one(
    *,
    tonie_id: str,
    item: dict,
    query_limit: int,
    max_items: int,
    delay_ms: int,
    sources: str,
    sem: asyncio.Semaphore,
) -> dict:
    async with sem:
        try:
            queries = build_ebay_search_queries(
                title=str(item.get("title") or ""),
                aliases=item.get("aliases") or [],
                series=item.get("series"),
                limit=max(1, int(query_limit)),
            )

            source_mode = (sources or "both").strip().lower()
            use_ebay = source_mode in {"ebay", "both"}
            use_offers = source_mode in {"offers", "both"}

            ebay_result = []
            offers_result = []
            errors: list[str] = []

            if use_ebay and use_offers:
                ebay_out, offer_out = await asyncio.gather(
                    fetch_ebay_sold_listings_multi_query(
                        queries=queries,
                        max_items=max(10, int(max_items)),
                    ),
                    fetch_kleinanzeigen_listings_multi_query(
                        queries=queries,
                        max_items=max(10, min(60, int(max_items))),
                    ),
                    return_exceptions=True,
                )

                if isinstance(ebay_out, Exception):
                    errors.append(f"ebay: {ebay_out}")
                else:
                    ebay_result = apply_time_window(ebay_out, days=90)

                if isinstance(offer_out, Exception):
                    errors.append(f"offers: {offer_out}")
                else:
                    offers_result = apply_time_window(offer_out, days=90)
            elif use_ebay:
                try:
                    ebay_result = await fetch_ebay_sold_listings_multi_query(
                        queries=queries,
                        max_items=max(10, int(max_items)),
                    )
                    ebay_result = apply_time_window(ebay_result, days=90)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"ebay: {exc}")
            elif use_offers:
                try:
                    offers_result = await fetch_kleinanzeigen_listings_multi_query(
                        queries=queries,
                        max_items=max(10, min(60, int(max_items))),
                    )
                    offers_result = apply_time_window(offers_result, days=90)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"offers: {exc}")

            ebay_records = [
                {
                    "title": row.title,
                    "price_eur": row.price_eur,
                    "url": row.url,
                    "sold_at": row.sold_at,
                }
                for row in ebay_result
                if row.price_eur > 0
            ]
            offers_records = [
                {
                    "title": row.title,
                    "price_eur": row.price_eur,
                    "url": row.url,
                    "sold_at": row.sold_at,
                }
                for row in offers_result
                if row.price_eur > 0
            ]

            saved = 0
            if ebay_records:
                saved += int(
                    save_market_listings(
                        tonie_id=tonie_id,
                        source="ebay_sold",
                        listings=ebay_records,
                    )
                )
            if offers_records:
                saved += int(
                    save_market_listings(
                        tonie_id=tonie_id,
                        source="kleinanzeigen_offer",
                        listings=offers_records,
                    )
                )

            return {
                "tonie_id": tonie_id,
                "queries": len(queries),
                "fetched": len(ebay_records) + len(offers_records),
                "fetched_ebay": len(ebay_records),
                "fetched_offers": len(offers_records),
                "saved": int(saved),
                "error": "; ".join(errors) if errors else None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "tonie_id": tonie_id,
                "queries": 0,
                "fetched": 0,
                "fetched_ebay": 0,
                "fetched_offers": 0,
                "saved": 0,
                "error": str(exc),
            }
        finally:
            if delay_ms > 0:
                await asyncio.sleep(max(0, int(delay_ms)) / 1000)


async def run(args: argparse.Namespace) -> int:
    init_db()

    resolver = get_resolver()
    by_id = {str(item["id"]): item for item in resolver.catalog}

    total_processed = 0
    total_saved = 0
    total_errors = 0
    pass_idx = 0
    no_progress_passes = 0

    while True:
        pass_idx += 1

        before = _full_coverage_snapshot(
            resolver=resolver,
            fresh_minutes=max(1, int(args.fresh_minutes)),
            min_effective_samples=max(0.1, float(args.min_effective_samples)),
        )
        uncovered = [row for row in (before.get("items") or []) if not row.get("meets_target")]

        if not uncovered:
            print("No uncovered tonies found. Nothing to refresh.")
            break

        target_value = max(0.1, float(args.min_effective_samples))

        if args.priority == "closest":
            uncovered.sort(
                key=lambda row: (
                    max(0.0, target_value - float(row.get("effective_samples") or 0.0)),
                    -int(row.get("raw_samples") or 0),
                    str(row.get("tonie_id") or ""),
                )
            )
        else:
            uncovered.sort(
                key=lambda row: (
                    float(row.get("effective_samples") or 0.0),
                    int(row.get("raw_samples") or 0),
                    str(row.get("tonie_id") or ""),
                )
            )

        target_ids = [
            str(row.get("tonie_id"))
            for row in uncovered[: max(1, int(args.batch_size))]
            if row.get("tonie_id")
        ]

        if not target_ids:
            print("No refresh targets selected. Stopping.")
            break

        print(
            f"Pass {pass_idx}: coverage {before.get('covered_tonies')} / {before.get('total_tonies')} | "
            f"refreshing {len(target_ids)} IDs | concurrency={max(1, int(args.concurrency))} | "
            f"priority={args.priority} | sources={args.sources}"
        )

        sem = asyncio.Semaphore(max(1, int(args.concurrency)))
        tasks = []
        for tonie_id in target_ids:
            item = by_id.get(tonie_id)
            if not item:
                continue
            tasks.append(
                asyncio.create_task(
                    _refresh_one(
                        tonie_id=tonie_id,
                        item=item,
                        query_limit=max(1, int(args.query_limit)),
                        max_items=max(10, int(args.max_items)),
                        delay_ms=max(0, int(args.delay_ms)),
                        sources=str(args.sources),
                        sem=sem,
                    )
                )
            )

        processed_this_pass = 0
        saved_this_pass = 0
        errors_this_pass = 0

        for fut in asyncio.as_completed(tasks):
            result = await fut
            processed_this_pass += 1
            total_processed += 1
            saved_this_pass += int(result["saved"])
            total_saved += int(result["saved"])

            if result.get("error"):
                errors_this_pass += 1
                total_errors += 1
                print(
                    f"[{processed_this_pass:03d}/{len(tasks):03d}] {result['tonie_id']} | ERROR: {result['error']}"
                )
            else:
                print(
                    f"[{processed_this_pass:03d}/{len(tasks):03d}] {result['tonie_id']} | "
                    f"queries={result['queries']} fetched={result['fetched']} "
                    f"(ebay={result.get('fetched_ebay', 0)}, offers={result.get('fetched_offers', 0)}) "
                    f"saved={result['saved']}"
                )

        pruned = prune_old_market_listings()

        after = _full_coverage_snapshot(
            resolver=resolver,
            fresh_minutes=max(1, int(args.fresh_minutes)),
            min_effective_samples=max(0.1, float(args.min_effective_samples)),
        )

        print("---")
        print(f"Pass {pass_idx} processed: {processed_this_pass}")
        print(f"Pass {pass_idx} rows saved/upserted: {saved_this_pass}")
        print(f"Pass {pass_idx} errors: {errors_this_pass}")
        print(f"Old rows pruned: {pruned}")
        print(
            f"Coverage after pass {pass_idx}: {after.get('covered_tonies')} / {after.get('total_tonies')} "
            f"(delta {int(after.get('covered_tonies', 0)) - int(before.get('covered_tonies', 0)):+d})"
        )
        print("===")

        if saved_this_pass <= 0:
            no_progress_passes += 1
            if max(0, int(args.cooldown_on_no_progress_minutes)) > 0:
                cooldown_minutes = max(0, int(args.cooldown_on_no_progress_minutes))
                print(
                    f"No progress in pass {pass_idx}; cooling down for {cooldown_minutes} min before next pass..."
                )
                await asyncio.sleep(cooldown_minutes * 60)
        else:
            no_progress_passes = 0

        max_no_progress = max(0, int(args.max_no_progress_passes))
        if max_no_progress > 0 and no_progress_passes >= max_no_progress:
            print(
                f"Stopping after {no_progress_passes} consecutive no-progress passes (max={max_no_progress})."
            )
            break

        if args.until_covered:
            continue

        if pass_idx >= max(1, int(args.passes)):
            break

    print("FINAL SUMMARY")
    print(f"Total processed: {total_processed}")
    print(f"Total rows saved/upserted: {total_saved}")
    print(f"Total errors: {total_errors}")

    final_snapshot = _full_coverage_snapshot(
        resolver=resolver,
        fresh_minutes=max(1, int(args.fresh_minutes)),
        min_effective_samples=max(0.1, float(args.min_effective_samples)),
    )
    print(f"Final coverage: {final_snapshot.get('covered_tonies')} / {final_snapshot.get('total_tonies')}")

    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
