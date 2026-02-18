from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RunMvpDailyMaintenanceSmokeTests(unittest.TestCase):
    def test_dry_run_only_smoke(self) -> None:
        backend_dir = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            summary_path = tmp_dir / "summary.md"
            sqlite_path = tmp_dir / "ops_smoke.db"

            env = os.environ.copy()
            env["SQLITE_PATH"] = str(sqlite_path)

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_mvp_daily_maintenance.py",
                    "--dry-run-only",
                    "--summary-file",
                    str(summary_path),
                ],
                cwd=backend_dir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stdout + "\n" + proc.stderr)
            self.assertIn("DRY-RUN", proc.stdout)
            self.assertTrue(summary_path.exists())

            content = summary_path.read_text(encoding="utf-8")
            self.assertIn("dry_run_only: true", content)
            self.assertIn("refresh_market_cache", content)
            self.assertIn("run_gap_pipeline", content)
            self.assertIn("generate_coverage_report", content)


if __name__ == "__main__":
    unittest.main()
