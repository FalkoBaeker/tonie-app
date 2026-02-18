#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import math
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
    save_market_listings,
)
from app.services.tonie_resolver import get_resolver  # noqa: E402

FRESH_MINUTES = 43200
MIN_EFFECTIVE = 3.0
BLOCK_SIZE = 5


def _coverage_snapshot() -> tuple[dict, set[str], dict[str, dict]]:
    report = get_market_coverage_report(
        fresh_minutes=FRESH_MINUTES,
        min_effective_samples=MIN_EFFECTIVE,
    )
    items = {str(item.get("tonie_id")): item for item in (report.get("items") or [])}
    covered = {str(item.get("tonie_id")) for item in (report.get("items") or []) if bool(item.get("meets_target"))}
    return report, covered, items


def _load_remaining_ids(path: Path, all_catalog_ids: set[str], covered: set[str]) -> list[str]:
    if path.exists():
        out: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            token = (line.split("\t", 1)[0] or "").strip()
            if token and token in all_catalog_ids and token not in covered:
                out.append(token)
        # de-dup preserving order
        seen = set()
        unique = []
        for tid in out:
            if tid in seen:
                continue
            seen.add(tid)
            unique.append(tid)
        if unique:
            return unique

    # fallback from live snapshot
    return sorted(tid for tid in all_catalog_ids if tid not in covered)


async def _process_one(tonie_id: str, item: dict) -> dict:
    title = str(item.get("title") or tonie_id)
    queries = build_ebay_search_queries(
        title=title,
        aliases=item.get("aliases") or [],
        series=item.get("series"),
        limit=8,
    )

    ebay_out, offers_out = await asyncio.gather(
        fetch_ebay_sold_listings_multi_query(queries=queries, max_items=80),
        fetch_kleinanzeigen_listings_multi_query(queries=queries, max_items=60),
        return_exceptions=True,
    )

    errors: list[str] = []
    ebay_rows = []
    offers_rows = []

    if isinstance(ebay_out, Exception):
        errors.append(f"ebay_error={ebay_out}")
    else:
        ebay_rows = apply_time_window(ebay_out, days=90)

    if isinstance(offers_out, Exception):
        errors.append(f"offers_error={offers_out}")
    else:
        offers_rows = apply_time_window(offers_out, days=90)

    ebay_records = [
        {
            "title": row.title,
            "price_eur": row.price_eur,
            "url": row.url,
            "sold_at": row.sold_at,
        }
        for row in ebay_rows
        if row.price_eur > 0
    ]
    offers_records = [
        {
            "title": row.title,
            "price_eur": row.price_eur,
            "url": row.url,
            "sold_at": row.sold_at,
        }
        for row in offers_rows
        if row.price_eur > 0
    ]

    saved = 0
    if ebay_records:
        saved += int(save_market_listings(tonie_id=tonie_id, source="ebay_sold", listings=ebay_records))
    if offers_records:
        saved += int(
            save_market_listings(tonie_id=tonie_id, source="kleinanzeigen_offer", listings=offers_records)
        )

    return {
        "tonie_id": tonie_id,
        "title": title,
        "queries": len(queries),
        "fetched_ebay": len(ebay_records),
        "fetched_offers": len(offers_records),
        "fetched_total": len(ebay_records) + len(offers_records),
        "saved": saved,
        "errors": errors,
    }


def _reason_for_unresolved(result: dict) -> str:
    title = str(result.get("title") or "")
    errors = result.get("errors") or []
    fetched_ebay = int(result.get("fetched_ebay") or 0)
    fetched_offers = int(result.get("fetched_offers") or 0)
    fetched_total = int(result.get("fetched_total") or 0)
    saved = int(result.get("saved") or 0)

    if errors:
        return "fetch_error"

    if fetched_total == 0:
        if any(tag in title for tag in ("[EN]", "[FR]", "[ES]", "[IT]")):
            return "keine Treffer (möglicher Sprach-/Locale-Mismatch)"
        return "keine Treffer"

    if saved == 0:
        return "nur Duplikate/gefilterte Treffer"

    if fetched_ebay == 0 and fetched_offers > 0:
        return "nur Angebotspreise, effektive Samples < 3"

    return "zu wenige effektive Samples (<3)"


def _chunks(items: list[str], size: int) -> list[list[str]]:
    out: list[list[str]] = []
    for i in range(0, len(items), max(1, size)):
        out.append(items[i : i + max(1, size)])
    return out


async def main() -> int:
    init_db()
    resolver = get_resolver()
    by_id = {str(item["id"]): item for item in resolver.catalog}

    report_before, covered_before, _ = _coverage_snapshot()
    total_catalog = len(resolver.catalog)

    remaining_file = Path("outputs/remaining_gap_me3_30d.txt")
    remaining_ids = _load_remaining_ids(remaining_file, set(by_id.keys()), covered_before)

    print(
        f"START covered={report_before.get('covered_tonies')}/{total_catalog} "
        f"remaining={len(remaining_ids)}"
    )

    unresolved_reasons: dict[str, str] = {}

    block_no = 0
    for block in _chunks(remaining_ids, BLOCK_SIZE):
        block_no += 1
        print(f"BLOCK {block_no} start ids={','.join(block)}")

        results: list[dict] = []
        for tid in block:
            item = by_id.get(tid)
            if not item:
                result = {
                    "tonie_id": tid,
                    "title": tid,
                    "queries": 0,
                    "fetched_ebay": 0,
                    "fetched_offers": 0,
                    "fetched_total": 0,
                    "saved": 0,
                    "errors": ["missing_catalog_item"],
                }
            else:
                result = await _process_one(tid, item)

            results.append(result)
            print(
                f"  {tid} | queries={result['queries']} fetched={result['fetched_total']} "
                f"(ebay={result['fetched_ebay']}, offers={result['fetched_offers']}) saved={result['saved']}"
            )

        report_after, covered_after, _items_after = _coverage_snapshot()

        fixed_ids = [tid for tid in block if tid in covered_after]
        still_missing_global = [tid for tid in remaining_ids if tid not in covered_after]
        unresolved_in_block = [tid for tid in block if tid not in covered_after]

        for tid in unresolved_in_block:
            result = next((r for r in results if str(r.get("tonie_id")) == tid), None)
            if result is None:
                unresolved_reasons[tid] = "unknown"
            else:
                unresolved_reasons[tid] = _reason_for_unresolved(result)

        print(
            f"CHECKPOINT block={block_no} covered={report_after.get('covered_tonies')}/{total_catalog} "
            f"fixed={','.join(fixed_ids) if fixed_ids else '-'} "
            f"remaining={len(still_missing_global)}"
        )
        if unresolved_in_block:
            for tid in unresolved_in_block:
                print(f"  unresolved {tid}: {unresolved_reasons.get(tid, 'unknown')}")

    final_report, final_covered, _ = _coverage_snapshot()
    final_missing = [tid for tid in sorted(by_id.keys()) if tid not in final_covered]

    remaining_file.parent.mkdir(parents=True, exist_ok=True)
    with remaining_file.open("w", encoding="utf-8") as f:
        for tid in final_missing:
            title = str(by_id.get(tid, {}).get("title") or tid)
            f.write(f"{tid}\t{title}\n")

    reasons_file = Path("outputs/remaining_gap_me3_30d_reasons.txt")
    with reasons_file.open("w", encoding="utf-8") as f:
        for tid in final_missing:
            reason = unresolved_reasons.get(tid, "not_processed_in_this_run")
            title = str(by_id.get(tid, {}).get("title") or tid)
            f.write(f"{tid}\t{title}\t{reason}\n")

    print(
        f"FINAL covered={final_report.get('covered_tonies')}/{total_catalog} "
        f"remaining={len(final_missing)}"
    )
    print(f"UPDATED_FILE {remaining_file.resolve()}")
    print(f"REASONS_FILE {reasons_file.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
