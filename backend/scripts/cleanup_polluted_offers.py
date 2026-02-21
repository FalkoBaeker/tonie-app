#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.market_ingestion import is_relevant_offer_title_for_tonie
from app.services.persistence import delete_market_listings_by_ids, list_market_listings_for_source
from app.services.tonie_resolver import get_resolver


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review and optionally delete polluted kleinanzeigen_offer rows "
            "that fail Tonie relevance filtering."
        )
    )
    parser.add_argument("--tonie-id", type=str, default="", help="Only process one tonie_id (default: all).")
    parser.add_argument("--limit", type=int, default=2000, help="Max rows to inspect.")
    parser.add_argument(
        "--max-delete",
        type=int,
        default=250,
        help="Safety cap: max rows to delete in one apply run.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete matched polluted rows. Default is dry-run preview only.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    resolver = get_resolver()
    by_id = {str(row.get("id")): row for row in resolver.catalog}

    rows = list_market_listings_for_source(
        source="kleinanzeigen_offer",
        tonie_id=args.tonie_id.strip() or None,
        limit=max(1, int(args.limit)),
    )
    if not rows:
        print("No kleinanzeigen_offer rows found for scope.")
        return 0

    polluted: list[dict] = []
    for row in rows:
        tonie_id = str(row.get("tonie_id") or "")
        title = str(row.get("title") or "")
        item = by_id.get(tonie_id)
        if not item:
            continue

        if not is_relevant_offer_title_for_tonie(
            offer_title=title,
            tonie_title=str(item.get("title") or ""),
            aliases=[str(a) for a in (item.get("aliases") or [])],
            series=str(item.get("series") or "").strip() or None,
        ):
            polluted.append(row)

    print("=== POLLUTED OFFERS REVIEW ===")
    print(f"Scope rows inspected: {len(rows)}")
    print(f"Rows flagged as polluted: {len(polluted)}")
    if polluted:
        print("\nExamples:")
        for row in polluted[:10]:
            print(f"- id={row['id']} tonie_id={row['tonie_id']} price={row['price_eur']:.2f} title={row['title']}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to delete flagged rows (capped by --max-delete).")
        return 0

    delete_cap = max(1, int(args.max_delete))
    delete_ids = [int(row["id"]) for row in polluted[:delete_cap]]
    deleted = delete_market_listings_by_ids(ids=delete_ids, source="kleinanzeigen_offer")
    print(f"\nDeleted rows: {deleted} (cap={delete_cap})")
    if len(polluted) > delete_cap:
        print(f"Remaining flagged rows not deleted in this run: {len(polluted) - delete_cap}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
