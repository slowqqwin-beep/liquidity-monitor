"""
sync_historical_data.py — series.json → 历史数据 CSV + fred_live，自动化日常增量同步
==============================================================================
读取 data/series.json (CI 每日 fetch_data.py 产出)，将新日期追加到：
  - data/历史数据/*.csv  (DGS10, DFII10, DGS2, EFFR, DFEDTARU, T10YIE, DFEDTARL)
  - data/macro_db/raw/BAMLH0A0HYM2/fred_live/BAMLH0A0HYM2_fred_live.csv
  - data/历史数据/BAMLH0A0HYM2_master_clean_for_backtest.csv

幂等：已存在日期自动跳过。

不处理 SR3（用户手工维护 sofr_sr3.csv → append_sr3_daily.py）。
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERIES_JSON = PROJECT_ROOT / "data" / "series.json"
HIST_DIR = PROJECT_ROOT / "data" / "历史数据"

# ── FRED 利率序列 → 历史数据 CSV ──
# format: observation_date, <series_id>
FRED_HIST_TARGETS: dict[str, Path] = {
    "DGS10":    HIST_DIR / "DGS10.csv",
    "DFII10":   HIST_DIR / "DFII10.csv",
    "DGS2":     HIST_DIR / "DGS2.csv",
    "EFFR":     HIST_DIR / "EFFR.csv",
    "DFEDTARU": HIST_DIR / "DFEDTARU.csv",
    "T10YIE":   HIST_DIR / "T10YIE.csv",
    "DFEDTARL": HIST_DIR / "DFEDTARL.csv",
}

# ── HY OAS 专用目标 ──
# fred_live 格式: observation_date, value
FRED_LIVE_PATH = (
    PROJECT_ROOT / "data" / "macro_db" / "raw" / "BAMLH0A0HYM2"
    / "fred_live" / "BAMLH0A0HYM2_fred_live.csv"
)
# master_clean 格式: date, series_id, value, source_layer, source_file, quality_flag, flag_detail
HY_MASTER_PATH = HIST_DIR / "BAMLH0A0HYM2_master_clean_for_backtest.csv"


def append_to_csv(target: Path, new_rows: list[dict], sort_col: str) -> int:
    """Append new rows to an existing CSV. Returns number of appended rows."""
    existing = pd.read_csv(target)
    existing[sort_col] = pd.to_datetime(existing[sort_col])
    existing_dates = set(existing[sort_col].dt.strftime("%Y-%m-%d"))

    fresh = [r for r in new_rows if r[sort_col] not in existing_dates]
    if not fresh:
        print(f"  {target.name}: up to date ({len(existing):,} rows)")
        return 0

    fresh_df = pd.DataFrame(fresh)
    fresh_df[sort_col] = pd.to_datetime(fresh_df[sort_col])
    combined = pd.concat([existing, fresh_df], ignore_index=True)
    combined = combined.sort_values(sort_col).drop_duplicates(
        subset=[sort_col], keep="last"
    )
    combined.to_csv(target, index=False)
    print(f"  {target.name}: +{len(fresh)} rows → {len(combined):,} rows")
    return len(fresh)


def main() -> int:
    if not SERIES_JSON.exists():
        print(f"[ERROR] series.json not found at {SERIES_JSON}", file=sys.stderr)
        return 1

    with open(SERIES_JSON, "r", encoding="utf-8") as f:
        series = json.load(f)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[Sync] {today_str} — series.json has {len(series)} keys")
    total_new = 0

    # ── 1. FRED 历史 CSV ──
    for sid, target_path in FRED_HIST_TARGETS.items():
        if sid not in series or not series[sid]:
            print(f"  {sid}: missing/empty in series.json, skipped")
            continue
        new_rows = [
            {"observation_date": row["date"], sid: row["value"]}
            for row in series[sid]
        ]
        total_new += append_to_csv(target_path, new_rows, "observation_date")

    # ── 2. HY OAS fred_live ──
    if "BAMLH0A0HYM2" in series and series["BAMLH0A0HYM2"]:
        new_rows = [
            {"observation_date": row["date"], "value": row["value"]}
            for row in series["BAMLH0A0HYM2"]
        ]
        total_new += append_to_csv(FRED_LIVE_PATH, new_rows, "observation_date")
    else:
        print("  BAMLH0A0HYM2: missing in series.json, skipped fred_live")

    # ── 3. HY OAS master_clean_for_backtest ──
    if "BAMLH0A0HYM2" in series and series["BAMLH0A0HYM2"]:
        new_rows = []
        for row in series["BAMLH0A0HYM2"]:
            new_rows.append({
                "date": row["date"],
                "series_id": "BAMLH0A0HYM2",
                "value": row["value"],
                "source_layer": "fred_live_rolling_3y",
                "source_file": "FRED",
                "quality_flag": "ok",
                "flag_detail": "",
            })
        total_new += append_to_csv(HY_MASTER_PATH, new_rows, "date")
    else:
        print("  HY master_clean: skipped (no BAMLH0A0HYM2 data)")

    print(f"[Sync] Done — {total_new} new rows appended total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
