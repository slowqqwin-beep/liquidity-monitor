#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Treasury yield fetcher — Yahoo API + Treasury CSV. No local file dependency."""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "treasury_yields_cache.json"


def _yahoo_chart(ticker: str, period: str = "5d") -> list:
    """Fetch chart data from Yahoo Finance API."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={period}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            r = json.loads(resp.read())
        result = r["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        out = []
        for ts, cl in zip(timestamps, closes):
            if cl is not None:
                d = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                out.append({"date": d, "close": float(cl)})
        return out
    except Exception:
        return []


def _treasury_2y() -> Optional[float]:
    """Fetch latest 2Y Treasury yield from US Treasury CSV."""
    try:
        url = ("https://home.treasury.gov/resource-center/data-chart-center/"
               "interest-rates/daily-treasury-rates.csv/all/2026?"
               "type=daily_treasury_yield_curve&field_tdr_date_value=2026&_format=csv")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode()
        reader = csv.DictReader(io.StringIO(data))
        last = None
        for row in reader:
            val = row.get("2 Yr", "").strip()
            if val:
                last = float(val)
        return round(last, 3) if last else None
    except Exception:
        return None


def fetch_latest_yields() -> Tuple[Optional[float], Optional[float]]:
    """Return (us10y_pct, us2y_pct) from Yahoo API + Treasury."""
    us10y = None
    tnx_data = _yahoo_chart("%5ETNX", "2d")
    if tnx_data:
        us10y = round(tnx_data[-1]["close"], 2)
    us2y = _treasury_2y()
    return us10y, us2y


def fetch_t10yie() -> Optional[float]:
    """Fetch latest T10YIE from FRED web."""
    try:
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10YIE"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read().decode()
        reader = csv.reader(io.StringIO(data))
        next(reader)
        last_val = None
        for row in reader:
            if len(row) >= 2 and row[1].strip():
                last_val = float(row[1])
        return round(last_val, 3) if last_val else None
    except Exception:
        return None


def fetch_history(days: int = 400) -> list:
    """30min cache + Yahoo/Treasury API. No CSV dependency."""
    now = datetime.now()

    # Fresh cache: return immediately
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            cache_ts = datetime.fromisoformat(cache.get("fetched_at", "2000-01-01"))
            if (now - cache_ts).total_seconds() < 1800:
                series = cache.get("series", [])
                return series[-days:] if len(series) > days else series
        except Exception:
            pass

    # Load existing cache as base
    existing: dict[str, dict] = {}
    if CACHE_PATH.exists():
        try:
            for s in json.loads(CACHE_PATH.read_text(encoding="utf-8")).get("series", []):
                existing[s["date"]] = s
        except Exception:
            pass

    # Overlay Yahoo ^TNX (2d) + ZT=F (5d) + Treasury CSV for 2Y
    try:
        tnx_data = _yahoo_chart("%5ETNX", "2d")
        zt_data = _yahoo_chart("ZT=F", "5d")
        zt_by = {r["date"]: r["close"] for r in (zt_data or [])}
        t_2y = _treasury_2y()
        if tnx_data:
            for r in tnx_data:
                d = r["date"]
                ten = round(r["close"], 3)
                two = existing.get(d, {}).get("two_y") if d in existing else None
                if two is None and d in zt_by:
                    two = round(100.0 - zt_by[d], 3)
                if two is None and t_2y is not None:
                    two = t_2y
                if two is not None:
                    existing[d] = {"date": d, "ten_y": ten, "two_y": two,
                                   "spread_bp": round((ten - two) * 100, 1)}
    except Exception:
        pass

    series = [existing[k] for k in sorted(existing)][-days:]

    # Recalculate spreads
    for s in series:
        if s.get("ten_y") and s.get("two_y"):
            s["spread_bp"] = round((s["ten_y"] - s["two_y"]) * 100, 1)

    if series:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps({
            "fetched_at": now.isoformat(), "series": series,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    return series


def _fallback_csv() -> list:
    """Legacy: kept for build_sr3_watch_dashboard compatibility (twos10s audit)."""
    return []
