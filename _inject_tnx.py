"""One-shot: inject ^TNX from yahoo_series.json into series.json."""
import json
from pathlib import Path

YAHOO = Path("D:/liquidity-dashboard/liquidity-dashboard/data/yahoo_series.json")
SERIES = Path("D:/liquidity-dashboard/liquidity-dashboard/data/series.json")

yh = json.loads(YAHOO.read_text())
s = json.loads(SERIES.read_text())

if "^TNX" in yh:
    s["^TNX"] = yh["^TNX"]
    print(f"Injected ^TNX: {len(yh['^TNX'])} rows, last={yh['^TNX'][-1]}")
else:
    print("^TNX not found in yahoo_series.json")
    exit(1)

SERIES.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
print("Done. series.json updated.")
