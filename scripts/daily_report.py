"""
Thin wrapper — delegates to v3.5/daily_report.py (single source of truth).

Previously this was an independent 1251-line copy with its own
POSITION_MATRIX and compute_position() that had drifted from the
production version (missing CASC gate §0.7, stale step labels).

Now all logic lives in one place: the root daily_report.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the production daily_report importable from scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_report import main

if __name__ == "__main__":
    sys.exit(main())
