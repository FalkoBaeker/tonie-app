#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.services.persistence import (
    get_market_cache_status,
    get_market_coverage_report,
    get_pricing_quality_status,
    list_refresh_runs,
)


def build_report(*, fresh_minutes: int, quality_hours: int, fallback_limit: int) -> dict:
    cache_status = get_market_cache_status(fresh_minutes=fresh_minutes)
    quality = get_pricing_quality_status(
        window_hours=quality_hours,
        fallback_limit=fallback_limit,
    )
    coverage = get_market_coverage_report(
        fresh_minutes=fresh_minutes,
        min_effective_samples=settings.market_min_effective_samples,
    )
    refresh_runs = list_refresh_runs(limit=5)

    latest_run = refresh_runs[0] if refresh_runs else None

    total_tonies = int(coverage.get("total_tonies") or 0)
    covered_tonies = int(coverage.get("covered_tonies") or 0)
    coverage_rate = round((covered_tonies / total_tonies) * 100.0, 2) if total_tonies > 0 else 0.0

    coverage_items = coverage.get("items") or []
    top_gaps = [row for row in coverage_items if isinstance(row, dict) and not row.get("meets_target")][:10]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "refresh_policy_minutes": int(settings.market_auto_refresh_interval_minutes),
        "cache_status": cache_status,
        "quality_status": quality,
        "coverage_summary": {
            "total_tonies": total_tonies,
            "covered_tonies": covered_tonies,
            "coverage_rate_percent": coverage_rate,
            "effective_target": float(coverage.get("min_effective_samples") or 0.0),
            "top_gaps": top_gaps,
        },
        "latest_refresh_run": latest_run,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ops quality report from local SQLite state")
    parser.add_argument("--fresh-minutes", type=int, default=max(60, int(settings.market_cache_ttl_minutes)))
    parser.add_argument("--quality-hours", type=int, default=24)
    parser.add_argument("--fallback-limit", type=int, default=10)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    report = build_report(
        fresh_minutes=max(1, int(args.fresh_minutes)),
        quality_hours=max(1, int(args.quality_hours)),
        fallback_limit=max(1, int(args.fallback_limit)),
    )

    if args.pretty:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
