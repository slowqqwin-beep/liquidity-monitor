#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone SR3 Repair Watch Dashboard builder.

Boundary rules:
- Research-only.
- Standalone path: docs/sr3-watch/
- Does NOT connect to Risk OS.
- Does NOT modify run_all.py.
- Does NOT affect position sizing.
- SR3 deceleration / mixed_repair is NOT a buy signal.

Inputs, searched in order:
- sr3_repair_watch_latest.md
- docs/sr3-watch/data/sr3_repair_watch_latest.md

Optional TradingView curve input, searched in order:
- 100-CME_DL_SR3H2027, 1D.csv
- data/100-CME_DL_SR3H2027, 1D.csv
- docs/sr3-watch/data/100-CME_DL_SR3H2027, 1D.csv
- CME_DL_SR3H2027, 1D.csv
- data/CME_DL_SR3H2027, 1D.csv
- docs/sr3-watch/data/CME_DL_SR3H2027, 1D.csv

Outputs:
- docs/sr3-watch/data/sr3_repair_watch_latest.md
- docs/sr3-watch/data/sr3_repair_watch_latest.json
- docs/sr3-watch/data/sr3_curve_z26_h27_m27.csv

Curve rule:
- The page displays daily Z26-H27-M27 implied-rate forward curves from 2026-06-16 onward.
- If input is 100-SR3, values are already implied rates.
- If input is SR3 price, implied rate = 100 - price.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _treasury_yields import fetch_history

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "sr3-watch" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2026-06-16"

MD_CANDIDATES = [
    ROOT / "_sr3_watch.md",
    ROOT / "docs/sr3-watch/data/sr3_repair_watch_latest.md",
    ROOT / "sr3_repair_watch_latest.md",
]

CSV_CANDIDATES = [
    ROOT / "data" / "历史数据" / "100-CME_DL_SR3M2026, 1D.csv",
    ROOT / "data" / "历史数据" / "100-CME_DL_SR3H2027, 1D.csv",
    ROOT / "100-CME_DL_SR3M2026, 1D.csv",
    ROOT / "100-CME_DL_SR3H2027, 1D.csv",
]

TWOS10S_CANDIDATES = [
    ROOT / "data" / "历史数据" / "TVC_US10Y, 1D.csv",
    ROOT / "TVC_US10Y, 1D.csv",
    ROOT / "2s10s.csv",
    ROOT / "twos10s.csv",
    ROOT / "data/2s10s.csv",
    ROOT / "data/twos10s.csv",
    ROOT / "US10Y-US02Y, 1D.csv",
    ROOT / "TVC_US10Y-US02Y, 1D.csv",
    ROOT / "TVC_US10Y-TVC_US02Y, 1D.csv",
    ROOT / "docs/sr3-watch/data/2s10s.csv",
]


def first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


def clean(value: Any) -> str:
    return "" if value is None else str(value).replace("\ufeff", "").strip()


def strip_md(value: Any) -> str:
    return re.sub(r"[*`]", "", clean(value)).strip()


def to_float(value: Any) -> Optional[float]:
    text = strip_md(value)
    if text == "" or text.upper() in {"N/A", "NA", "NULL", "NONE", "-"}:
        return None
    text = text.replace("%", "").replace("bp", "").replace(",", "")
    text = re.sub(r"[^\d.\-+]", "", text)
    if text in {"", ".", "-", "+"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_bool_cn(value: Any) -> Optional[bool]:
    text = strip_md(value)
    if any(x in text for x in ["是", "✅", "true", "True", "YES", "yes"]):
        return True
    if any(x in text for x in ["否", "❌", "false", "False", "NO", "no"]):
        return False
    return None


def parse_md_table(md: str, heading_keyword: str) -> List[Dict[str, str]]:
    lines = md.splitlines()
    start = None
    # Prefer actual markdown headings so metadata lines such as "参考峰值: ..." do not steal the match.
    for i, line in enumerate(lines):
        if line.strip().startswith("#") and heading_keyword in line:
            start = i
            break
    if start is None:
        for i, line in enumerate(lines):
            if heading_keyword in line:
                start = i
                break
    if start is None:
        return []

    table_lines: List[str] = []
    in_table = False
    for line in lines[start + 1:]:
        s = line.strip()
        if s.startswith("|"):
            in_table = True
            table_lines.append(s)
        elif in_table:
            break

    if len(table_lines) < 2:
        return []

    headers = [x.strip() for x in table_lines[0].strip("|").split("|")]
    rows = []
    for line in table_lines[2:]:
        cells = [x.strip() for x in line.strip("|").split("|")]
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        rows.append(dict(zip(headers, cells)))
    return rows


def parse_key_value_table(md: str, heading_keyword: str) -> Dict[str, str]:
    rows = parse_md_table(md, heading_keyword)
    out: Dict[str, str] = {}
    for row in rows:
        keys = list(row.keys())
        if len(keys) >= 2:
            out[strip_md(row.get(keys[0]))] = strip_md(row.get(keys[1]))
    return out


def parse_report_md(md: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "generated_at": None,
        "data_date": None,
        "reference_peak": None,
        "status": "Research-Only",
        "state": None,
        "state_title": None,
        "state_note": None,
        "hawkish_impulse": None,
        "deceleration": None,
        "deceleration_since": None,
        "level_repair": None,
        "classification": None,
        "classification_reason": None,
        "repair": None,
        "near_rate": None,
        "drawdown_from_peak_bp": None,
        "daily_change_bp": None,
        "five_day_change_bp": None,
        "high_plateau": None,
        "hy_oas": None,
        "dgs10": None,
        "real_yield_nowcast": None,
        "repair_start_date": None,
        "repair_magnitude_bp": None,
        "reference_peaks": [],
        "signal_matrix": [],
        "field_warnings": [],
        "mixed_repair_warning": "mixed_repair 不是买入信号；它只表示 SR3 冲击已钝化但尚未完成 level repair，且 benign repair 条件未完全满足。",
        "research_note": "Research-Only；不接 Risk OS / dashboard / run_all.py；不影响仓位；SR3 deceleration ≠ buy signal。",
        "constraints": {
            "research_only": True,
            "standalone_sr3_watch": True,
            "no_risk_os": True,
            "no_existing_dashboard_merge": True,
            "no_run_all": True,
            "no_position_impact": True,
            "deceleration_not_buy_signal": True,
        },
    }

    # Header meta can be split across two blockquote lines.
    m = re.search(r"生成时间\*\*:\s*([0-9T:\-]+).*?数据日\*\*:\s*([0-9\-]+)", md, re.S)
    if m:
        data["generated_at"] = strip_md(m.group(1))
        data["data_date"] = strip_md(m.group(2))
    m = re.search(r"参考峰值\*\*:\s*([^|\n]+?)\s*\|\s*\*\*状态\*\*:\s*([^\n]+)", md)
    if m:
        data["reference_peak"] = strip_md(m.group(1))
        data["status"] = strip_md(m.group(2))

    m = re.search(r"##\s*[🟡🔴🟢⚪⚠️\s]*([^:\n]+:\s*[^\n]+)", md)
    if m:
        data["state"] = strip_md(m.group(1))
        data["state_title"] = strip_md(m.group(1))

    m = re.search(r">\s*短端预期：([^\n]+)", md)
    if m:
        data["state_note"] = strip_md(m.group(1))

    for row in parse_md_table(md, "四个关键问题"):
        question = strip_md(row.get("问题"))
        answer = strip_md(row.get("答案"))
        if "hawkish impulse" in question:
            data["hawkish_impulse"] = parse_bool_cn(answer)
        elif "deceleration" in question:
            data["deceleration"] = parse_bool_cn(answer)
            m2 = re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", answer)
            if m2:
                data["deceleration_since"] = m2.group(1)
        elif "level repair" in question:
            data["level_repair"] = parse_bool_cn(answer)
        elif "修复分类" in question:
            data["classification"] = strip_md(answer)

    ref_peaks = []
    for row in parse_md_table(md, "参考峰值"):
        if "来源" not in row:
            continue
        ref_peaks.append({
            "source": strip_md(row.get("来源")),
            "date": strip_md(row.get("日期")),
            "distance": strip_md(row.get("距今")),
            "near_rate": to_float(row.get("near_rate")),
            "height": strip_md(row.get("高度")),
        })
    data["reference_peaks"] = ref_peaks

    m = re.search(r"当前使用:\s*\*\*([^*]+)\*\*", md)
    if m:
        data["reference_peak"] = strip_md(m.group(1))

    snap = parse_key_value_table(md, "当前快照")
    data["near_rate"] = to_float(snap.get("near_rate"))
    data["drawdown_from_peak_bp"] = to_float(snap.get("较参考峰回落"))
    data["daily_change_bp"] = to_float(snap.get("当日变动"))
    data["five_day_change_bp"] = to_float(snap.get("5d 累计"))
    data["high_plateau"] = parse_bool_cn(snap.get("高台 (>3.5%)"))
    data["hy_oas"] = to_float(snap.get("HY OAS"))
    data["dgs10"] = to_float(snap.get("DGS10"))
    data["real_yield_nowcast"] = to_float(snap.get("Real Yield Nowcast"))

    details = parse_key_value_table(md, "分类详情")
    if details.get("分类"):
        data["classification"] = strip_md(details.get("分类"))
    data["classification_reason"] = strip_md(details.get("原因"))
    if details.get("level_repair"):
        data["level_repair"] = parse_bool_cn(details.get("level_repair"))
    data["repair"] = parse_bool_cn(details.get("repair"))
    data["repair_start_date"] = details.get("修复起始日") or data.get("deceleration_since")
    data["repair_magnitude_bp"] = to_float(details.get("修复幅度"))

    signal_matrix = []
    for row in parse_md_table(md, "信号组合速查"):
        if "条件" in row and "信号含义" in row:
            signal_matrix.append({
                "condition": strip_md(row.get("条件")),
                "meaning": strip_md(row.get("信号含义")),
            })
    data["signal_matrix"] = signal_matrix

    required = ["generated_at", "data_date", "state", "classification", "near_rate"]
    for key in required:
        if data.get(key) in [None, "", []]:
            data["field_warnings"].append(f"字段缺失: {key}")

    return data


def parse_trade_date(value: Any) -> Optional[str]:
    raw = clean(value)
    if not raw:
        return None

    # Direct YYYY-MM-DD or ISO
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.year >= 2000:
            return dt.date().isoformat()
    except Exception:
        pass

    # Unix timestamp seconds
    try:
        ts = float(raw)
        if ts > 1_000_000_000:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            # CME daily export can appear at 22:00 UTC, mapped to next trade date.
            return (dt + timedelta(days=1)).date().isoformat()
    except Exception:
        return None
    return None


def detect_col(headers: List[str], contract: str, source: Path) -> Optional[str]:
    # Prefer explicit 100-SR3 columns.
    for h in headers:
        if f"100-{contract}" in h:
            return h
    # Then explicit SR3 price columns.
    for h in headers:
        if contract in h:
            return h
    # Primary close column for H27 when file is exported from SR3H2027 / 100-SR3H2027.
    if contract == "SR3H2027" and "H2027" in source.name and "close" in headers:
        return "close"
    return None


def is_implied_rate_column(col: str, source: Path) -> bool:
    return col.startswith("100-SR3") or "100-SR3" in col or (col == "close" and source.name.startswith("100-"))


def parse_curve_csv(source: Optional[Path]) -> Dict[str, Any]:
    contracts = [
        {"code": "Z26", "label": "Dec-26", "contract": "SR3Z2026"},
        {"code": "H27", "label": "Mar-27", "contract": "SR3H2027"},
        {"code": "M27", "label": "Jun-27", "contract": "SR3M2027"},
    ]

    result: Dict[str, Any] = {
        "curve_start_date": START_DATE,
        "curve_source_file": source.name if source else None,
        "curve_contracts": contracts,
        "curve_comparison": [],
        "curve_bp_changes": [],
        "curve_warning": None,
    }

    if source is None or not source.exists():
        result["curve_warning"] = "未找到 TradingView SR3 曲线 CSV，Z26-H27-M27 远期曲线图将降级为空数据。"
        write_curve_audit_csv([])
        return result

    with source.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    if "time" not in headers:
        result["curve_warning"] = "CSV 缺少 time 列。"
        write_curve_audit_csv([])
        return result

    col_map: Dict[str, Tuple[str, bool]] = {}
    missing = []
    for item in contracts:
        col = detect_col(headers, item["contract"], source)
        if not col:
            missing.append(item["code"])
        else:
            col_map[item["code"]] = (col, is_implied_rate_column(col, source))

    if missing:
        result["curve_warning"] = "CSV 缺少合约列: " + ", ".join(missing)

    curve_rows = []
    for row in rows:
        d = parse_trade_date(row.get("time"))
        if not d or d < START_DATE:
            continue

        rates: Dict[str, Optional[float]] = {}
        for item in contracts:
            code = item["code"]
            if code not in col_map:
                rates[code] = None
                continue
            col, is_rate = col_map[code]
            raw_value = to_float(row.get(col))
            if raw_value is None:
                rates[code] = None
            else:
                rates[code] = round(raw_value if is_rate else 100.0 - raw_value, 4)

        if any(v is not None for v in rates.values()):
            label = d
            if d == "2026-06-16":
                label = "6/16 讲话前"
            elif d == "2026-06-17":
                label = "6/17 讲话后"
            elif d == "2026-06-18":
                label = "6/18 确认日"
            curve_rows.append({"date": d, "label": label, "rates": rates})

    curve_rows.sort(key=lambda x: x["date"])
    result["curve_comparison"] = curve_rows

    if curve_rows:
        base = curve_rows[0]
        last = curve_rows[-1]
        bp_changes = []
        for item in contracts:
            code = item["code"]
            b = base["rates"].get(code)
            l = last["rates"].get(code)
            bp_changes.append({
                "code": code,
                "label": item["label"],
                "from_date": base["date"],
                "to_date": last["date"],
                "bp_change": None if b is None or l is None else round((l - b) * 100, 2),
            })
        result["curve_bp_changes"] = bp_changes

    write_curve_audit_csv(curve_rows)
    return result


def write_curve_audit_csv(curve_rows: List[Dict[str, Any]]) -> None:
    out = OUT_DIR / "sr3_curve_z26_h27_m27.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "label", "Z26_Dec26", "H27_Mar27", "M27_Jun27"])
        for row in curve_rows:
            rates = row.get("rates", {})
            writer.writerow([row.get("date"), row.get("label"), rates.get("Z26"), rates.get("H27"), rates.get("M27")])




def derive_current_event_repair(curve_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Derive current post-FOMC price-over / hike-over repair from Z26-H27-M27 curve.

    Vocabulary:
    - This is NOT just "price-out cuts".
    - If the FOMC/Warsh shock lifts the forward curve above the pre-event baseline,
      the dashboard treats it as "price-over hikes / hike-over premium".
    - Repair start means the hike-over premium starts to retreat from the event peak.
    - Full level repair means the curve returns to the pre-event baseline, not just
      a one-day pullback from the peak.
    """
    out = {
        "event_baseline_date": None,
        "event_baseline_avg_rate": None,
        "hike_over_peak_date": None,
        "hike_over_peak_avg_rate": None,
        "current_event_peak_date": None,
        "current_event_peak_avg_rate": None,
        "current_event_repair_start_date": None,
        "hike_over_shock_bp": None,
        "hike_over_repair_magnitude_bp": None,
        "hike_over_repair_ratio": None,
        "hike_over_remaining_bp": None,
        "event_avg_level_repair": False,
        "event_strict_level_repair": False,
        "event_level_repair_date": None,
        "current_event_state": "N/A",
        "current_event_note": "缺少 Z26-H27-M27 曲线，无法计算当前事件修复。",
    }

    if not curve_rows:
        return out

    rows = []
    for row in curve_rows:
        rates = row.get("rates", {})
        vals = [rates.get("Z26"), rates.get("H27"), rates.get("M27")]
        vals = [float(v) for v in vals if v is not None]
        if vals:
            rows.append({"date": row.get("date"), "avg_rate": sum(vals) / len(vals), "rates": rates})

    if len(rows) < 2:
        out["current_event_note"] = "曲线样本不足，无法确认当前事件修复。"
        return out

    baseline = rows[0]
    latest = rows[-1]
    peak_idx = max(range(len(rows)), key=lambda i: rows[i]["avg_rate"])
    peak = rows[peak_idx]

    out["event_baseline_date"] = baseline["date"]
    out["event_baseline_avg_rate"] = round(baseline["avg_rate"], 4)
    out["hike_over_peak_date"] = peak["date"]
    out["hike_over_peak_avg_rate"] = round(peak["avg_rate"], 4)

    # Backward-compatible aliases
    out["current_event_peak_date"] = peak["date"]
    out["current_event_peak_avg_rate"] = round(peak["avg_rate"], 4)

    shock_bp = round((peak["avg_rate"] - baseline["avg_rate"]) * 100, 2)
    repaired_bp = round(max(0.0, peak["avg_rate"] - latest["avg_rate"]) * 100, 2)
    remaining_bp = round(max(0.0, latest["avg_rate"] - baseline["avg_rate"]) * 100, 2)
    ratio = None if shock_bp <= 0 else round(repaired_bp / shock_bp, 4)

    out["hike_over_shock_bp"] = shock_bp
    out["hike_over_repair_magnitude_bp"] = repaired_bp
    out["hike_over_remaining_bp"] = remaining_bp
    out["hike_over_repair_ratio"] = ratio

    # Backward-compatible fields
    out["current_event_repair_magnitude_bp"] = repaired_bp
    out["current_event_drawdown_from_peak_bp"] = round((latest["avg_rate"] - peak["avg_rate"]) * 100, 2)

    if len(rows) - 1 <= peak_idx:
        out["current_event_state"] = "at_hike_over_peak_or_no_repair"
        out["current_event_note"] = "最新曲线仍在 price-over / hike-over 峰值附近，尚未出现当前事件修复起点。"
    else:
        start_date = None
        for i in range(peak_idx + 1, len(rows)):
            if rows[i]["avg_rate"] < rows[i - 1]["avg_rate"]:
                start_date = rows[i]["date"]
                break
        out["current_event_repair_start_date"] = start_date
        if start_date:
            out["current_event_state"] = "hike_over_repair_started"
        else:
            out["current_event_state"] = "post_peak_but_not_confirmed"

    # Level repair definitions.
    tolerance_bp = 2.0
    out["event_level_repair_tolerance_bp"] = tolerance_bp
    out["event_avg_level_repair"] = latest["avg_rate"] <= baseline["avg_rate"] + tolerance_bp / 100.0

    strict_ok = True
    for code in ["Z26", "H27", "M27"]:
        b = baseline["rates"].get(code)
        l = latest["rates"].get(code)
        if b is None or l is None or float(l) > float(b) + tolerance_bp / 100.0:
            strict_ok = False
            break
    out["event_strict_level_repair"] = strict_ok

    # First date that satisfies strict level repair after peak.
    level_date = None
    for row in rows[peak_idx + 1:]:
        avg_ok = row["avg_rate"] <= baseline["avg_rate"] + tolerance_bp / 100.0
        strict = True
        for code in ["Z26", "H27", "M27"]:
            b = baseline["rates"].get(code)
            l = row["rates"].get(code)
            if b is None or l is None or float(l) > float(b) + tolerance_bp / 100.0:
                strict = False
                break
        if avg_ok and strict:
            level_date = row["date"]
            break
    out["event_level_repair_date"] = level_date

    ratio_pct = "N/A" if ratio is None else f"{ratio * 100:.1f}%"
    out["current_event_note"] = (
        f"本轮不是简单 price-out 降息，而是 FOMC/沃什后曲线 price-over / hike-over。"
        f"事件前基准 {baseline['date']}，hike-over 峰值 {peak['date']}，"
        f"冲击约 +{shock_bp:.1f}bp；当前已修复约 {repaired_bp:.1f}bp（{ratio_pct}），"
        f"距离事件前基准仍约 +{remaining_bp:.1f}bp。"
        f"当前事件修复启动不等于 level repair，也不是买入信号。"
    )

    return out


def find_twos10s_source() -> Optional[Path]:
    direct = first_existing(TWOS10S_CANDIDATES)
    if direct:
        return direct
    keywords = ("2s10s", "twos10s", "us10y-us02y", "us10y_us02y", "us10y-us2y", "us10y_us2y")
    for folder in [ROOT, ROOT / "data", ROOT / "docs/sr3-watch/data"]:
        if not folder.exists():
            continue
        for p in folder.glob("*.csv"):
            name = p.name.lower().replace(" ", "")
            if any(k in name for k in keywords):
                return p
    return None


def detect_twos10s_columns(headers: List[str], source: Path) -> Dict[str, Optional[str]]:
    lower_map = {h: h.lower().replace(" ", "") for h in headers}
    out = {"spread": None, "ten": None, "two": None}
    for h, low in lower_map.items():
        if any(k in low for k in ["2s10s", "twos10s", "us10y-us02y", "us10y-us2y", "10y-2y", "10yminus2y"]):
            out["spread"] = h
            break
    for h, low in lower_map.items():
        if ("us02y" in low or "us2y" in low or "dgs2" in low or "2y" in low):
            out["two"] = h
            break
    # TVC_US10Y file: "close" is US10Y, "US02Y · TVC: close" is US02Y
    fname = source.name.lower().replace(" ", "")
    if out["two"] is not None:
        if "close" in headers:
            out["ten"] = "close"
    else:
        for h, low in lower_map.items():
            if ("us10y" in low or "dgs10" in low or "10y" in low) and "close" in low:
                out["ten"] = h
                break
    if out["ten"] is None and "close" in headers and ("us10y" in fname or "10y" in fname):
        out["ten"] = "close"
    if out["ten"] is None and out["two"] is not None and "close" in headers:
        out["ten"] = "close"
    # Only treat close as spread for dedicated spread files, not TVC_US10Y
    if out["spread"] is None and "close" in headers and any(k in fname for k in ["2s10s", "twos10s", "us10y-us02y", "us10y-us2y"]):
        out["spread"] = "close"
    return out


def spread_to_bp(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value * 100, 2) if abs(value) < 20 else round(value, 2)


def classify_curve_structure(series: List[Dict[str, Any]]) -> Dict[str, Any]:
    empty = {
        "latest_spread_bp": None,
        "change_1d_bp": None,
        "change_5d_bp": None,
        "d10_1d_bp": None,
        "d2_1d_bp": None,
        "widening_state": "N/A",
        "structure": "N/A",
        "structure_note": "未提供 2s10s 数据。",
        "latest_date": None,
        "has_yields": False,
    }
    if not series:
        return empty

    latest = series[-1]
    prev = series[-2] if len(series) >= 2 else None
    latest_bp = latest.get("spread_bp")
    prev_bp = prev.get("spread_bp") if prev else None
    change_1d = None if latest_bp is None or prev_bp is None else round(latest_bp - prev_bp, 2)

    idx_5d = max(0, len(series) - 6)
    base_5d = series[idx_5d]
    base_bp = base_5d.get("spread_bp")
    change_5d = None if latest_bp is None or base_bp is None else round(latest_bp - base_bp, 2)

    widening_state = "N/A"
    if change_1d is not None:
        if change_1d > 1:
            widening_state = "阔开 / Steepening"
        elif change_1d < -1:
            widening_state = "缩窄 / Flattening"
        else:
            widening_state = "稳定 / Stable"

    structure = "仅利差"
    note = "当前只识别到 2s10s 利差：下方利差轴可判断阔开/缩窄；若同时提供 2Y 与 10Y，顶部会显示两条利率曲线并进一步识别熊平/熊陡/牛平/牛陡。"
    if change_1d is not None:
        if change_1d > 1:
            structure = "Steepening / 变陡"
            note = "2s10s 走阔，曲线变陡；需要看上方 2Y/10Y 两条线的方向，判断是熊陡还是牛陡。"
        elif change_1d < -1:
            structure = "Flattening / 变平"
            note = "2s10s 收窄，曲线变平；需要看上方 2Y/10Y 两条线的方向，判断是熊平还是牛平。"
        else:
            structure = "Stable / 稳定"
            note = "2s10s 日度变化较小，曲线结构暂未给出强确认。"

    ten = latest.get("ten_y")
    two = latest.get("two_y")
    has_yields = ten is not None and two is not None
    d10 = None
    d2 = None

    if prev and has_yields and prev.get("ten_y") is not None and prev.get("two_y") is not None:
        d10 = round((ten - prev["ten_y"]) * 100, 2)
        d2 = round((two - prev["two_y"]) * 100, 2)
        ds = change_1d

        if d10 > 0 and d2 > 0 and ds is not None and ds > 0:
            structure = "熊陡"
            note = "10Y 和 2Y 同上，但 10Y 上得更多，2s10s 阔开：长期利率/期限溢价压力更大，对长久期资产更不友好。"
        elif d10 > 0 and d2 > 0 and ds is not None and ds < 0:
            structure = "熊平"
            note = "10Y 和 2Y 同上，但 2Y 上得更多，2s10s 缩窄：主要是短端 Fed 鹰派重定价。"
        elif d10 < 0 and d2 < 0 and ds is not None and ds > 0:
            structure = "牛陡"
            note = "10Y 和 2Y 同下，但 2Y 下得更多，2s10s 阔开：市场在交易降息/增长压力。"
        elif d10 < 0 and d2 < 0 and ds is not None and ds < 0:
            structure = "牛平"
            note = "10Y 和 2Y 同下，但 10Y 下得更多，2s10s 缩窄：避险或增长担忧更强。"
        else:
            structure = "Mixed / 混合"
            note = "2Y 与 10Y 方向不一致，曲线结构需结合 SR3、real yield 和信用利差再判断。"

    return {
        "latest_spread_bp": latest_bp,
        "change_1d_bp": change_1d,
        "change_5d_bp": change_5d,
        "d10_1d_bp": d10,
        "d2_1d_bp": d2,
        "widening_state": widening_state,
        "structure": structure,
        "structure_note": note,
        "latest_date": latest.get("date"),
        "has_yields": has_yields,
    }


def parse_twos10s_csv(source: Optional[Path]) -> Dict[str, Any]:
    result: Dict[str, Any] = {"twos10s_source_file": source.name if source else None, "twos10s_series": [], "twos10s_latest": classify_curve_structure([]), "twos10s_warning": None}
    if source is None or not source.exists():
        result["twos10s_warning"] = "未找到 2s10s TradingView CSV。请把每日下载文件放到根目录，命名为 2s10s.csv 或 US10Y-US02Y, 1D.csv。"
        write_twos10s_audit_csv([])
        return result
    with source.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)
    if "time" not in headers:
        result["twos10s_warning"] = "2s10s CSV 缺少 time 列。"
        write_twos10s_audit_csv([])
        return result
    cols = detect_twos10s_columns(headers, source)
    if not cols.get("spread") and not (cols.get("ten") and cols.get("two")):
        result["twos10s_warning"] = "2s10s CSV 未识别到 spread close，或同时缺少 10Y/2Y close 列。"
        write_twos10s_audit_csv([])
        return result
    series = []
    for row in rows:
        d = parse_trade_date(row.get("time"))
        if not d:
            continue
        ten = to_float(row.get(cols["ten"])) if cols.get("ten") else None
        two = to_float(row.get(cols["two"])) if cols.get("two") else None
        if ten is not None and two is not None:
            spread_bp = round((ten - two) * 100, 2)
        elif cols.get("spread"):
            raw_spread = to_float(row.get(cols["spread"]))
            spread_bp = spread_to_bp(raw_spread)
        elif False:
            spread_bp = round((ten - two) * 100, 2)
        else:
            spread_bp = None
        if spread_bp is not None:
            series.append({"date": d, "spread_bp": spread_bp, "ten_y": ten, "two_y": two})
    dedup = {row["date"]: row for row in series}
    series = [dedup[k] for k in sorted(dedup)]
    result["twos10s_series"] = series
    result["twos10s_latest"] = classify_curve_structure(series)
    write_twos10s_audit_csv(series)
    return result


def write_twos10s_audit_csv(series: List[Dict[str, Any]]) -> None:
    out = OUT_DIR / "twos10s_history.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "spread_bp", "ten_y", "two_y"])
        for row in series:
            writer.writerow([row.get("date"), row.get("spread_bp"), row.get("ten_y"), row.get("two_y")])

def build() -> None:
    # Step 1: Load base data from sr3_repair_watch.py output (preserves contract_diffs and state fields)
    base_json = ROOT / "data" / "macro_backtest" / "research" / "sr3_repair_watch_latest.json"
    if base_json.exists():
        data = json.loads(base_json.read_text(encoding="utf-8"))
        data["field_warnings"] = []
        # Flatten nested fields from sr3_repair_watch.py into top-level for JS consumption
        current = data.get("current", {})
        if "us10y" not in data:
            data["us10y"] = current.get("us10y_pct")
        if "t10yie" not in data:
            data["t10yie"] = current.get("t10yie_pct")
        if "real_yield_nowcast" not in data:
            data["real_yield_nowcast"] = current.get("real_yield_pct")
    else:
        data = parse_report_md("")
        data["field_warnings"] = ["sr3_repair_watch.json 缺失，先跑 sr3_repair_watch.py"]

    # Step 2: Overlay md parsing for classification / state freshness
    md_path = first_existing(MD_CANDIDATES)
    if md_path:
        md = md_path.read_text(encoding="utf-8")
        shutil.copy2(md_path, OUT_DIR / "sr3_repair_watch_latest.md")
        md_data = parse_report_md(md)
        for key in md_data:
            if md_data[key] is not None and key not in ("curve_comparison", "curve_bp_changes",
                "curve_warning", "twos10s_series", "twos10s_latest", "twos10s_warning",
                "us10y", "t10yie", "real_yield_nowcast"):
                data[key] = md_data[key]

    # Step 3: Curve comparison + current event repair (derive from curve data, dynamic each day)
    csv_path = first_existing(CSV_CANDIDATES)
    data.update(parse_curve_csv(csv_path))
    data.update(derive_current_event_repair(data.get("curve_comparison") or []))

    # Step 4: 2s10s curve structure (yfinance, no local CSV needed)
    hist = fetch_history(400)
    twos10s_series = [{"date": r["date"], "spread_bp": r["spread_bp"],
                        "ten_y": r.get("ten_y"), "two_y": r.get("two_y")} for r in hist]
    twos10s_latest = classify_curve_structure(twos10s_series)
    data["twos10s_series"] = twos10s_series
    data["twos10s_latest"] = twos10s_latest
    data["twos10s_source_file"] = "yfinance (^TNX + ZT=F)"
    # Sync us10y from 2s10s cache (same source, consistent with table)
    if twos10s_series:
        last = twos10s_series[-1]
        data["us10y"] = last.get("ten_y")
    data["twos10s_warning"] = None if twos10s_series else "yfinance 抓取失败"

    # Write outputs
    out_json = OUT_DIR / "sr3_repair_watch_latest.json"
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Also write embedded JS for file:// CORS bypass
    js_path = OUT_DIR / "sr3_data.js"
    js_path.write_text("window.SR3_DATA = " + json.dumps(data, ensure_ascii=False, indent=2, default=str) + ";", encoding="utf-8")

    print(f"[SR3 Watch] wrote {out_json.relative_to(ROOT)}")
    print(f"[SR3 Watch] wrote {js_path.relative_to(ROOT)}")
    print(f"[SR3 Watch] wrote {(OUT_DIR / 'sr3_repair_watch_latest.md').relative_to(ROOT)}")
    print(f"[SR3 Watch] wrote {(OUT_DIR / 'sr3_curve_z26_h27_m27.csv').relative_to(ROOT)}")
    print(f"[SR3 Watch] curve source: {csv_path.relative_to(ROOT) if csv_path else 'N/A'}")
    print(f"[SR3 Watch] 2s10s source: yfinance (^TNX + ZT=F)")

    warnings = data.get("field_warnings") or []
    if warnings:
        print("[SR3 Watch] warnings:")
        for w in warnings:
            print(f"  - {w}")
    if data.get("curve_warning"):
        print(f"[SR3 Watch] curve warning: {data['curve_warning']}")
    if data.get("twos10s_warning"):
        print(f"[SR3 Watch] 2s10s warning: {data['twos10s_warning']}")


if __name__ == "__main__":
    build()
