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

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "sr3-watch" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START_DATE = "2026-06-16"

MD_CANDIDATES = [
    ROOT / "data" / "macro_backtest" / "research" / "sr3_repair_watch_latest.md",
    ROOT / "sr3_repair_watch_latest.md",
    ROOT / "docs" / "sr3-watch" / "data" / "sr3_repair_watch_latest.md",
]

CSV_CANDIDATES = [
    # CSV bundled in docs/sr3-watch/data/ (ZIP or manual copy)
    ROOT / "docs" / "sr3-watch" / "data" / "100-CME_DL_SR3H2027, 1D.csv",
    ROOT / "docs" / "sr3-watch" / "data" / "CME_DL_SR3H2027, 1D.csv",
    # Historical data directory
    ROOT / "data" / "历史数据" / "100-CME_DL_SR3H2027, 1D.csv",
    ROOT / "data" / "历史数据" / "CME_DL_SR3H2027, 1D.csv",
    # Root-level candidates
    ROOT / "100-CME_DL_SR3H2027, 1D.csv",
    ROOT / "CME_DL_SR3H2027, 1D.csv",
    ROOT / "data" / "100-CME_DL_SR3H2027, 1D.csv",
    ROOT / "data" / "CME_DL_SR3H2027, 1D.csv",
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
    # Prefer an actual markdown heading, so metadata lines such as "参考峰值: ..." do not steal the match.
    for i, line in enumerate(lines):
        if line.strip().startswith("#") and heading_keyword in line:
            start = i
            break
    # Fallback for less formal reports.
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


def build() -> None:
    md_path = first_existing(MD_CANDIDATES)
    if md_path:
        md = md_path.read_text(encoding="utf-8")
        shutil.copy2(md_path, OUT_DIR / "sr3_repair_watch_latest.md")
        data = parse_report_md(md)
    else:
        data = parse_report_md("")
        data["field_warnings"].append("未找到 sr3_repair_watch_latest.md，当前为 fallback/降级展示。")

    csv_path = first_existing(CSV_CANDIDATES)
    data.update(parse_curve_csv(csv_path))

    out_json = OUT_DIR / "sr3_repair_watch_latest.json"
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[SR3 Watch] wrote {out_json.relative_to(ROOT)}")
    print(f"[SR3 Watch] wrote {(OUT_DIR / 'sr3_repair_watch_latest.md').relative_to(ROOT)}")
    print(f"[SR3 Watch] wrote {(OUT_DIR / 'sr3_curve_z26_h27_m27.csv').relative_to(ROOT)}")
    print(f"[SR3 Watch] curve source: {csv_path.relative_to(ROOT) if csv_path else 'N/A'}")

    warnings = data.get("field_warnings") or []
    if warnings:
        print("[SR3 Watch] warnings:")
        for w in warnings:
            print(f"  - {w}")
    if data.get("curve_warning"):
        print(f"[SR3 Watch] curve warning: {data['curve_warning']}")


if __name__ == "__main__":
    build()
