#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.market_refresh import run_refresh_now


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh Tonie market cache from eBay sold listings.")
    parser.add_argument("--limit", type=int, default=0, help="Only refresh first N catalog entries (0 = all)")
    parser.add_argument("--delay-ms", type=int, default=200, help="Delay between requests in milliseconds")
    parser.add_argument("--max-items", type=int, default=80, help="Max scraped items per Tonie query")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    summary = await run_refresh_now(
        limit=args.limit if args.limit > 0 else None,
        delay_ms=max(0, args.delay_ms),
        max_items=max(10, args.max_items),
    )

    print("\n=== REFRESH SUMMARY ===")
    print(f"Run ID: {summary.get('run_id')}")
    print(f"Status: {summary.get('status')}")
    print(f"Processed: {summary.get('processed')} / {summary.get('total')}")
    print(f"Successful: {summary.get('successful')}")
    print(f"Failures: {summary.get('failed')}")
    print(f"Rows saved/upserted: {summary.get('saved_rows')}")
    print(f"Old rows pruned: {summary.get('pruned_rows')}")

    failures = summary.get("failures") or []
    if failures:
        print("\nFailed tonies:")
        for row in failures[:20]:
            print(f"- {row}")

    return 0 if summary.get("failed", 0) == 0 else 1


def main() -> int:
    args = parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
