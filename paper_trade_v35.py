"""
Clean v3.5 paper trade — only the 5 validated signals from v3.0 backtest.
No CASC, VTS, RCV, SSoT, DUR5, DFII10, 5Y5Y, EFFR-IORB threshold triggers.
"""
import json, csv, pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
SERIES = ROOT / "data" / "series.json"
LEDGER = ROOT / "paper_trade_v3_5_clean.csv"

# Load FRED data
data = json.loads(SERIES.read_text("utf-8"))

def last_val(key, idx=-1):
    items = data.get(key, [])
    return items[idx]["value"] if items and abs(idx) <= len(items) else None

def n_day_chg(key, n, as_of_idx=-1):
    """n-day change. as_of_idx=-1 means latest data, -2 means second-to-last, etc.
    This makes historical backfills deterministic — same as_of_idx always gives same result."""
    items = data.get(key, [])
    if len(items) < n + 1:
        return None
    return items[as_of_idx]["value"] - items[as_of_idx - n]["value"]

def pct_5d(key, as_of_idx=-1):
    items = data.get(key, [])
    if len(items) < 6:
        return None
    return (items[as_of_idx]["value"] / items[as_of_idx - 5]["value"] - 1) * 100

def hy_5d(key):
    items = data.get(key, [])
    if len(items) < 6:
        return None
    return (items[-1]["value"] / items[-6]["value"] - 1) * 100

def spy_200ma():
    spy = data.get("SPY", [])  # actual key, not "SP500"
    if len(spy) < 200:
        return None, None
    spy_val = spy[-1]["value"]
    ma200 = sum(x["value"] for x in spy[-200:]) / 200
    return spy_val, ma200

# ── 5 Signals (§40 locked definitions) ──
hy_oas_20d = n_day_chg("BAMLH0A0HYM2", 20)  # in % points, *100 for bp
hy_oas_5d = n_day_chg("BAMLH0A0HYM2", 5)
hyg_5d = hy_5d("HYG")
fxy_5d = hy_5d("FXY")
spy_val, ma200 = spy_200ma()
sofr_iorb = (last_val("SOFR") or 0) - (last_val("IORB") or 0)
vix = last_val("VIXCLS")

today = datetime.now().strftime("%Y-%m-%d")
today_dt = datetime.now()
# Non-trading day guard: skip only if NO new data exists (weekend runs with stale data are fine
# when catching up on missed days — the data itself is from the last trading day)
# We check if the FRED date has advanced since the last row in the ledger
fred_date = data.get("BAMLH0A0HYM2", [{}])[-1].get("date", "N/A")

last_ledger_date = None
if LEDGER.exists():
    import csv as _csv
    rows = list(_csv.reader(open(LEDGER, "r", encoding="utf-8")))
    if len(rows) > 1:
        last_ledger_date = rows[-1][0]  # date column

if last_ledger_date and fred_date <= last_ledger_date:
    print(f"[SKIP] No new FRED data since ledger last date {last_ledger_date} (FRED: {fred_date})")
    exit(0)

# Signal evaluations
signals = {}
# #1: HY OAS 20dΔ > +20bp (★★★ drawdown warning)
signals["HY_OAS_20d_bp"] = round(hy_oas_20d * 100, 1) if hy_oas_20d else None
signals["HY_OAS_trigger"] = hy_oas_20d > 0.20 if hy_oas_20d else False

# #2: HY OAS 5dΔ > +15bp (★ short-term supplement) — BAML direct, NOT HYG
signals["HY_OAS_5d_bp"] = round(hy_oas_5d * 100, 1) if hy_oas_5d is not None else None
signals["HY_OAS_5d_trigger"] = (hy_oas_5d > 0.15) if hy_oas_5d is not None else False

# HYG 5d — diagnostic only, NOT a trigger (proxy for 20d when BAML missing, §40)
hyg_5d = pct_5d("HYG")

# #3: FXY 5d > +2.5% (★★ D-end cross-border)
signals["FXY_5d_pct"] = round(fxy_5d, 1) if fxy_5d else None
signals["FXY_trigger"] = fxy_5d > 2.5 if fxy_5d else False

# #4: SPY < 200MA (technical baseline)
spy_below_200 = spy_val < ma200 if spy_val and ma200 else False
signals["SPY_200MA"] = f"{spy_val:.0f}" if spy_val else "N/A"
signals["SPY_trigger"] = spy_below_200

# #5: Extreme Meltdown circuit breaker
signals["VIX"] = vix
signals["SOFR_IORB_bp"] = round(sofr_iorb * 100, 1) if sofr_iorb else None
meltdown = (vix or 0) > 35 and (sofr_iorb or 0) * 100 > 5
signals["Meltdown_trigger"] = meltdown

trigger_count = sum([
    signals["HY_OAS_trigger"],
    signals["HY_OAS_5d_trigger"],
    signals["FXY_trigger"],
    signals["SPY_trigger"],
    signals["Meltdown_trigger"],
])

# Position: baseline 55/25/20, no drawdown = no change
if trigger_count >= 3 and signals["Meltdown_trigger"]:
    pos = "30/30/40"  # circuit breaker
    note = "熔断: ≥3 信号触发且 Extreme Meltdown"
elif trigger_count >= 2:
    pos = "45/30/25"
    note = "防御: ≥2 信号触发"
elif trigger_count >= 1:
    pos = "55/25/20"
    note = "基线: 1 信号触发，维持观察"
else:
    pos = "55/25/20"
    note = "important null: 0 信号触发，市场平静"

# ── Write ledger ──
row = {
    "date": today,
    "fred_date": fred_date,
    "HY_OAS_20d_bp": signals["HY_OAS_20d_bp"],
    "HY_OAS_20d_trigger": signals["HY_OAS_trigger"],
    "HY_OAS_5d_bp": signals["HY_OAS_5d_bp"],
    "HY_OAS_5d_trigger": signals["HY_OAS_5d_trigger"],
    # TODO: align field names to §40 — add _delta suffix (HY_OAS_20d_delta_bp etc)
    "FXY_5d_pct": signals["FXY_5d_pct"],
    "FXY_trigger": signals["FXY_trigger"],
    "SPY_vs_200MA": "Y" if spy_below_200 else "N",
    "SPY_trigger": signals["SPY_trigger"],
    "VIX": signals["VIX"],
    "SOFR_IORB_bp": signals["SOFR_IORB_bp"],
    "Meltdown_trigger": meltdown,
    "trigger_count": trigger_count,
    "hypothetical_position": pos,
    "important_null_note": note,
}

# ── Known structural gaps (reference only, see KNOWN_GAPS.md for details) ──
row["important_null_note"] = row["important_null_note"] + ". 已知缺口记录见KNOWN_GAPS.md v1"

file_exists = LEDGER.exists()
with open(LEDGER, "a", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(row.keys()))
    if not file_exists:
        w.writeheader()
    w.writerow(row)

print(f"[v3.5 Paper Trade] {today} | FRED: {fred_date}")
print(f"  #1 HY OAS 20d: {signals['HY_OAS_20d_bp']}bp {'⚠️' if signals['HY_OAS_trigger'] else 'OK'}")
print(f"  #2 HY OAS 5d: {signals['HY_OAS_5d_bp']}bp {'⚠️' if signals['HY_OAS_5d_trigger'] else 'OK'}")
print(f"  #3 FXY 5d: {signals['FXY_5d_pct']}% {'⚠️' if signals['FXY_trigger'] else 'OK'}")
print(f"  #4 SPY vs 200MA: {signals['SPY_200MA']} {'⚠️' if spy_below_200 else 'OK'}")
print(f"  #5 Meltdown: VIX={signals['VIX']}, SOFR-IORB={signals['SOFR_IORB_bp']}bp {'⚠️' if meltdown else 'OK'}")
if hyg_5d is not None:
    print(f"  HYG 5d (diagnostic): {hyg_5d:.1f}%")
else:
    print("  HYG 5d: N/A")
    print(f"  Triggers: {trigger_count}/5")
print(f"  Triggers: {trigger_count}/5")
print(f"  Position: P={pos.split('/')[0]}% H={pos.split('/')[1]}% C={pos.split('/')[2]}%")
print(f"  Note: {note}")
print(f"  Saved to {LEDGER}")
