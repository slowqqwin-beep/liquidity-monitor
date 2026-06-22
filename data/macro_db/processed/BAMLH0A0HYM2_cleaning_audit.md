# BAMLH0A0HYM2 Cleaning Audit

**Generated**: 2026-06-21 19:53
**Cleaning script**: `scripts/macro_db/_clean_master.py`

## Files Produced

| File | Rows | Description |
|------|------|-------------|
| `BAMLH0A0HYM2_master_raw.csv` | 7694 | Original + quality_flag column |
| `BAMLH0A0HYM2_master_clean_for_backtest.csv` | 7560 | Weekends removed, synthetic fill stripped |

## Actions Taken

### 1. Weekend Removal
- **100 rows** removed (all month-end weekends: Saturday/Sunday)
- These likely originated from monthly panel data or fill logic
- HY OAS is daily close, weekend data is not valid for daily backtest

### 2. Deliberate GAP: SVB Period (2023-03-06 ~ 2023-04-20)
- **34 trading days** stripped from clean version — deliberate, not a source failure
- **FRED**: BAMLH0A0HYM2 `observation_start=2023-06-19` — the series did not exist during SVB
- **Wayback seed**: contains linear interpolation (4.179→4.167, 3dp) that is **directionally false** — it shows credit *narrowing* during a banking crisis when OAS actually spiked to ~5%+
- **Decision (2026-06-22)**: GAP, not interpolate. An honest N/A is more correct than a directionally-wrong pseudo-value. A reader seeing "unavailable" knows to suspend judgement; a reader seeing 4.16 in March 2023 concludes "credit was fine" — which is the opposite of truth.
- **Post-crisis truth preserved**: 2023-04-21 = 4.46 (+29bp jump) is genuine FRED data and correctly triggers malign classification

### 3. Quality Flag Legend

| Flag | Meaning | Action |
|------|---------|--------|
| `ok` | Genuine data, no issues | Use in backtest |
| `weekend_month_end` | Month-end weekend row | Exclude from daily backtest |
| `synthetic_or_filled` | Linear interpolation artifact (legacy) | EXCLUDE from daily backtest |
| `weekend+synthetic` | Both issues | EXCLUDE |

## Boundary After Cleaning

- **Last pre-SVB**: 2023-03-03 = 4.18
- **SVB GAP**: 2023-03-06 → 2023-04-20 (deliberate; no interpolated values)
- **First post-SVB**: 2023-04-21 = 4.46

## Recommendations

1. ✅ `master_raw` → use as historical reference, full audit trail
2. ✅ `master_clean_for_backtest` → use for daily-frequency backtest
   - 2023-03-06 ~ 2023-04-20 is a deliberate **void** in the clean series
   - Any strategy that depends on this window must note data unavailability
   - Consider marking this gap in visualization/charts
3. 🔴 Do NOT use raw for daily backtest without filtering
4. 📊 For monthly-frequency analysis, consider building a separate EOM table

## Verdict

**Rating**: B after cleaning
**Usable for**: Long-term quantile, regime classification, macro overlay
**NOT suitable for**: SVB-window event studies at daily precision (data gap, not quality issue)
