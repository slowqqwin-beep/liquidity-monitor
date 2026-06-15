"""
v3.5 Daily Workflow Orchestrator
=================================
One command to run the full daily pipeline in correct order:

  Step 1: Yahoo local fetch → yahoo_series.json
  Step 2: FRED + Yahoo live fetch → series.json (fallback to yahoo_series.json)
  Step 3: Daily report + paper_trade → markdown

Usage:
    python v3.5/run_daily.py                  # full pipeline
    python v3.5/run_daily.py --skip-fetch     # skip data fetch, only report
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# FRED API key — 传递给子进程
os.environ.setdefault("FRED_API_KEY", "6b3a6e4c44a2e709c6e60feb17ef3401")

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
YAHOO_SCRIPT = SCRIPT_DIR / "fetch_yahoo_local.py"
FRED_SCRIPT = SCRIPT_DIR / "fetch_data.py"
REPORT_SCRIPT = SCRIPT_DIR / "daily_report.py"


def run_step(label: str, script: Path, args: list[str] | None = None) -> bool:
    """Run a Python script via uv run, return True if OK."""
    cmd = ["uv", "run", "python", str(script)] + (args or [])
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[{ts}] STEP: {label}")
    print(f"[{ts}] CMD:  {' '.join(cmd)}")
    print(f"{'='*60}")
    sys.stdout.flush()

    try:
        result = subprocess.run(cmd, cwd=str(WORKSPACE), check=False)
        ok = result.returncode == 0
        status = "OK" if ok else f"FAIL (exit={result.returncode})"
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {label}: {status}")
        return ok
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {label}: ERROR ({e})")
        return False


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="v3.5 Daily Workflow Orchestrator")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip data fetching, only generate report")
    parser.add_argument("--report-only", action="store_true",
                        help="Same as --skip-fetch")
    args = parser.parse_args()

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] v3.5 Daily Pipeline START")
    errors = []

    if not (args.skip_fetch or args.report_only):
        # ── Step 1: Yahoo local ──
        if not run_step("Yahoo Local (FXY/HYG/SPY)", YAHOO_SCRIPT):
            errors.append("Yahoo local fetch")
            # Continue anyway — fetch_data.py has live Yahoo fallback

        # ── Step 2: FRED + Yahoo live + derived → series.json ──
        if not run_step("FRED + Yahoo (series.json)", FRED_SCRIPT):
            errors.append("FRED data fetch")
            # If series.json is stale/absent, Step 3 will fail on its own

    # ── Step 3: Daily Report + Paper Trade ──
    if not run_step("Daily Report (daily + paper_trade)", REPORT_SCRIPT, ["--md"]):
        errors.append("Daily report generation")

    print(f"\n{'='*60}")
    if errors:
        print(f"[FAIL] {len(errors)} step(s) failed: {', '.join(errors)}")
        return 1
    else:
        print(f"[DONE] All steps OK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
