#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.market_refresh import run_refresh_now  # noqa: E402
from app.services.persistence import init_db, list_refresh_runs  # noqa: E402


@dataclass
class StepResult:
    name: str
    ok: bool
    details: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MVP daily maintenance: refresh, gap pipeline, coverage report, refresh-runs check."
    )
    parser.add_argument("--dry-run-only", action="store_true", help="Skip network/external work and only simulate steps")
    parser.add_argument("--refresh-limit", type=int, default=0, help="Refresh first N tonies (0 = all)")
    parser.add_argument("--refresh-delay-ms", type=int, default=200, help="Delay between refresh requests")
    parser.add_argument("--refresh-max-items", type=int, default=80, help="Max listings per refresh query")
    parser.add_argument("--gap-fresh-minutes", type=int, default=43200)
    parser.add_argument("--gap-min-effective-samples", type=float, default=3.0)
    parser.add_argument(
        "--summary-file",
        type=str,
        default="outputs/mvp_daily_maintenance_summary.md",
        help="Markdown summary output path",
    )
    return parser.parse_args(argv)


def _run_subprocess(cmd: list[str], *, dry_run_only: bool) -> tuple[bool, str]:
    if dry_run_only:
        return True, f"DRY-RUN skipped: {' '.join(cmd)}"

    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode == 0, text.strip()


async def _run_refresh_step(args: argparse.Namespace) -> tuple[bool, str]:
    if args.dry_run_only:
        return True, "DRY-RUN skipped live refresh"

    try:
        summary = await run_refresh_now(
            limit=args.refresh_limit if args.refresh_limit > 0 else None,
            delay_ms=max(0, args.refresh_delay_ms),
            max_items=max(10, args.refresh_max_items),
        )
    except RuntimeError as exc:
        return False, str(exc)

    status = str(summary.get("status") or "unknown")
    run_id = str(summary.get("run_id") or "-")
    processed = int(summary.get("processed") or 0)
    total = int(summary.get("total") or 0)
    failed = int(summary.get("failed") or 0)
    return failed == 0, f"run_id={run_id} status={status} processed={processed}/{total} failed={failed}"


def _write_summary(
    *,
    path: Path,
    started_at: datetime,
    ended_at: datetime,
    dry_run_only: bool,
    steps: list[StepResult],
    refresh_runs_after: list[dict],
) -> None:
    lines: list[str] = []
    lines.append("# MVP Daily Maintenance Summary")
    lines.append("")
    lines.append(f"- started_at: {started_at.isoformat()}")
    lines.append(f"- ended_at: {ended_at.isoformat()}")
    lines.append(f"- dry_run_only: {str(dry_run_only).lower()}")
    lines.append("")
    lines.append("## Steps")

    for step in steps:
        state = "OK" if step.ok else "FAILED"
        lines.append(f"- {step.name}: {state} — {step.details}")

    lines.append("")
    lines.append("## refresh_runs (latest)")
    if not refresh_runs_after:
        lines.append("- none")
    else:
        for row in refresh_runs_after[:5]:
            lines.append(
                "- run_id={run_id} status={status} processed={processed}/{total} failed={failed} started_at={started_at}".format(
                    run_id=row.get("run_id"),
                    status=row.get("status"),
                    processed=row.get("processed"),
                    total=row.get("total"),
                    failed=row.get("failed"),
                    started_at=row.get("started_at"),
                )
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    init_db()
    started_at = datetime.now(UTC)
    steps: list[StepResult] = []

    refresh_ok, refresh_details = await _run_refresh_step(args)
    steps.append(StepResult(name="refresh_market_cache", ok=refresh_ok, details=refresh_details))

    gap_cmd = [
        sys.executable,
        "scripts/run_gap_pipeline.py",
        "--fresh-minutes",
        str(max(1, args.gap_fresh_minutes)),
        "--min-effective-samples",
        str(max(0.1, args.gap_min_effective_samples)),
    ]
    if args.dry_run_only:
        gap_cmd.append("--dry-run-only")

    gap_ok, gap_details = _run_subprocess(gap_cmd, dry_run_only=args.dry_run_only)
    steps.append(StepResult(name="run_gap_pipeline", ok=gap_ok, details=gap_details))

    coverage_cmd = [
        sys.executable,
        "scripts/generate_coverage_report.py",
        "--fresh-minutes",
        str(max(1, args.gap_fresh_minutes)),
        "--min-effective-samples",
        str(max(0.1, args.gap_min_effective_samples)),
        "--output",
        "outputs/mvp_daily_coverage_report.md",
    ]
    coverage_ok, coverage_details = _run_subprocess(coverage_cmd, dry_run_only=args.dry_run_only)
    steps.append(StepResult(name="generate_coverage_report", ok=coverage_ok, details=coverage_details))

    refresh_runs_after = list_refresh_runs(limit=5)

    ended_at = datetime.now(UTC)
    summary_path = Path(args.summary_file)
    if not summary_path.is_absolute():
        summary_path = (ROOT / summary_path).resolve()

    _write_summary(
        path=summary_path,
        started_at=started_at,
        ended_at=ended_at,
        dry_run_only=args.dry_run_only,
        steps=steps,
        refresh_runs_after=refresh_runs_after,
    )

    print(f"SUMMARY_FILE {summary_path}")
    for step in steps:
        print(f"STEP {step.name} {'OK' if step.ok else 'FAILED'} :: {step.details}")

    return 0 if all(step.ok for step in steps) else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
