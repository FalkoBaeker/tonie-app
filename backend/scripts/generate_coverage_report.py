#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.persistence import get_market_coverage_report
from app.services.tonie_resolver import get_resolver


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Tonie coverage markdown report.")
    parser.add_argument(
        "--fresh-minutes",
        type=int,
        default=360,
        help="Freshness window in minutes (default: 360)",
    )
    parser.add_argument(
        "--min-effective-samples",
        type=float,
        default=12.0,
        help="Target minimum effective samples per tonie (default: 12)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="../COVERAGE_REPORT.md",
        help="Output markdown file path (default: ../COVERAGE_REPORT.md)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    cov = get_market_coverage_report(
        fresh_minutes=max(1, int(args.fresh_minutes)),
        min_effective_samples=max(0.1, float(args.min_effective_samples)),
    )
    items_by_id = {item["tonie_id"]: item for item in cov.get("items") or []}

    resolver = get_resolver()
    full_rows: list[dict] = []

    for item in resolver.catalog:
        tonie_id = str(item["id"])
        row = items_by_id.get(
            tonie_id,
            {
                "raw_samples": 0,
                "effective_samples": 0.0,
                "meets_target": False,
            },
        )

        full_rows.append(
            {
                "tonie_id": tonie_id,
                "title": str(item["title"]),
                "raw_samples": int(row.get("raw_samples") or 0),
                "effective_samples": float(row.get("effective_samples") or 0.0),
                "meets_target": bool(row.get("meets_target", False)),
            }
        )

    target = max(0.1, float(args.min_effective_samples))
    covered = sum(1 for row in full_rows if row["meets_target"])

    uncovered = sorted(
        (row for row in full_rows if not row["meets_target"]),
        key=lambda row: (row["effective_samples"], row["raw_samples"], row["tonie_id"]),
    )

    lines: list[str] = []
    lines.append("# Coverage Report — Tonie Finder")
    lines.append("")
    lines.append(f"- Generated at: {datetime.now(UTC).isoformat()}")
    lines.append(f"- Fresh window: {int(args.fresh_minutes)} minutes")
    lines.append(
        f"- Effective sample target: >= {int(target) if float(target).is_integer() else target}"
    )
    lines.append("")
    lines.append("## Snapshot")
    lines.append(f"- Total tonies in seed: **{len(full_rows)}**")
    lines.append(f"- Tonies meeting effective-sample target: **{covered} / {len(full_rows)}**")
    lines.append(f"- Tonies below target: **{len(uncovered)}**")
    lines.append("")

    lines.append("## Uncovered tonies (effective samples < 12)")
    if not uncovered:
        lines.append("- None — all tonies currently meet target.")
    else:
        for row in uncovered:
            lines.append(
                f"- `{row['tonie_id']}` — {row['title']}: raw={row['raw_samples']}, effective={row['effective_samples']:.2f}"
            )

    lines.append("")
    lines.append("## Top 5 priorities to improve accuracy")
    if not uncovered:
        lines.append("1. None — all tonies currently at/above target.")
    else:
        for idx, row in enumerate(uncovered[:5], start=1):
            gap = max(0.0, target - row["effective_samples"])
            lines.append(
                f"{idx}. `{row['tonie_id']}` — {row['title']} (effective {row['effective_samples']:.2f}, gap {gap:.2f})"
            )

    lines.append("")
    lines.append("## Notes")
    lines.append(
        f"- Coverage endpoint currently reports tonies with >=1 fresh listing; this report expands to full seed coverage ({len(full_rows)} entries)."
    )
    lines.append(
        "- Multi-query sold-listing ingestion is active (title + aliases + tonie-context variants)."
    )

    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Report written: {out_path}")
    print(f"Coverage: {covered}/{len(full_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
