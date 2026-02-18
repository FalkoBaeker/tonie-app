# MVP Ops Runbook

## Purpose
Daily maintenance for the MVP backend to keep market/pricing data current and track operational health.

## Command (daily)

```bash
cd backend
./.venv/bin/python scripts/run_mvp_daily_maintenance.py
```

## Dry-run / smoke

```bash
cd backend
./.venv/bin/python scripts/run_mvp_daily_maintenance.py --dry-run-only
```

## What the script orchestrates
1. **Market refresh** (`run_refresh_now`) to update `market_listings` and persist a `refresh_runs` record.
2. **Gap pipeline** (`scripts/run_gap_pipeline.py`) to process remaining coverage gaps.
3. **Coverage report** (`scripts/generate_coverage_report.py`) to regenerate a markdown snapshot.
4. **refresh_runs audit** (latest entries) included in summary output.

## Expected outputs
- `backend/outputs/mvp_daily_maintenance_summary.md`
- `backend/outputs/mvp_daily_coverage_report.md`
- Updated DB tables (especially `market_listings`, `refresh_runs`)
- Console lines:
  - `SUMMARY_FILE ...`
  - `STEP <name> OK|FAILED :: ...`

## Troubleshooting
- `refresh already running`
  - Another refresh lock is active. Wait and rerun.
- Step marked `FAILED`
  - Inspect `mvp_daily_maintenance_summary.md` details for failing command.
  - Re-run the failing command manually.
- Missing dependencies
  - Activate backend venv and install requirements:
    - `cd backend && ./.venv/bin/pip install -r requirements.txt`
- Empty or stale coverage
  - Verify data freshness/ingestion and rerun refresh before report generation.

## Operational notes
- Use `--dry-run-only` for CI/smoke validation (no live fetch).
- Keep summary file under version control if daily ops trace is desired.
