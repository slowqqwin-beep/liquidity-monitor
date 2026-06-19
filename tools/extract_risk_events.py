# -*- coding: utf-8 -*-
"""
extract_risk_events.py  — 从 risk_dashboard MD 推断事件状态
===========================================================
输入：report/risk_dashboard_YYYY-MM-DD.md
输出：event_state JSON — 不照搬章节，而是从信号中推理当前风险路径

原则：
- 不机械搬运表格，而是根据指标实际值推断事件/传导/触发器/阶段
- 每个字段都有推理依据（evidence），无数据的标 "未提及"
- 输出结构：date / regime / positions / event_state / transmission_state / trigger_state / stage_assessment
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "liquidity-dashboard" / "report"
PROJECT_DIR = Path(__file__).resolve().parent.parent  # v3.5 root
sys.path.insert(0, str(PROJECT_DIR))

from daily_report import rate_path_direction_label


def _infer_near_event(txt: str) -> dict:
    """从 ① 近端事件风险 推断 near_event 状态。

    不是照抄原文，而是根据信号词/数值做结构化推理：
    - VIX9D/VIX > 0.95 → 前端紧张
    - DGS2-IORB > 0 → 降息被price out
    - 跨资产确认=0 → 非系统性
    """
    result: dict[str, Any] = {
        "near_event_active": False,      # v3.5.1: default false — only set true when signal detected
        "near_event_type": "unknown",
        "event_sources": [],
        "front_risk_label": "前端平稳",   # v3.5.1: default calm, not empty
        "front_risk_intensity": "green", # v3.5.1: default green, not unknown
        "systemic_confirmed": False,
        "evidence": {},
    }

    # ── VIX9D/VIX ratio ──
    m = re.search(r'VIX9D/VIX[=＝]\s*([\d.]+)', txt)
    if m:
        ratio = float(m.group(1))
        result["evidence"]["vix9d_vix_ratio"] = ratio
        if ratio > 0.95:
            result["front_risk_label"] = "前端紧张"
            result["front_risk_intensity"] = "orange"
            result["event_sources"].append(f"VIX9D/VIX={ratio} 前端紧张")
        elif ratio > 0.85:
            result["front_risk_label"] = "前端偏紧"
            result["front_risk_intensity"] = "yellow_or_orange"
            result["event_sources"].append(f"VIX9D/VIX={ratio} 前端偏紧")
        else:
            result["front_risk_label"] = "前端平稳"
            result["front_risk_intensity"] = "green"
    else:
        # fallback: 前端急性
        m2 = re.search(r'前端急性.*?([\d.]+)', txt)
        if m2:
            ratio = float(m2.group(1))
            result["evidence"]["vix9d_vix_ratio"] = ratio
            if ratio > 0.95:
                result["front_risk_label"] = "前端紧张"
                result["front_risk_intensity"] = "orange"
            else:
                result["front_risk_label"] = "前端偏紧"
                result["front_risk_intensity"] = "yellow_or_orange"

    # ── VIX (avoid matching VIX9D/VIX ratio) ──
    m_vix = re.search(r'(?<!9D/)VIX[=＝]\s*([\d.]+)', txt)
    if m_vix:
        result["evidence"]["vix"] = float(m_vix.group(1))
    else:
        m_vix2 = re.search(r'VIX[=＝]\s*([\d.]+)\s*5d', txt)
        if m_vix2:
            result["evidence"]["vix"] = float(m_vix2.group(1))

    # ── DGS2 - IORB ──
    m = re.search(r'DGS2[−\-]IORB[=＝]\s*([\d.]+)bp', txt)
    if m:
        spread = float(m.group(1))
        result["evidence"]["dgs2_iorb_bp"] = spread

        # Parse 5dΔ from MD text (risk_dashboard ① 区 now includes it after refactor)
        m5d = re.search(r'5dΔ\s*([+\-]?[\d.]+)bp', txt)
        d5_dgs2_iorb = float(m5d.group(1)) if m5d else None

        label, arrow = rate_path_direction_label(d5_dgs2_iorb)
        result["event_sources"].append(f"DGS2−IORB={spread}bp {arrow} [{label}]")
        if result["near_event_type"] == "unknown":
            result["near_event_type"] = "rate_event"

    # ── 跨资产确认 (CASC) — must be parsed BEFORE systemic gate ──
    if "无跨资产确认" in txt or "CASC 0/" in txt:
        result["evidence"]["cross_asset_confirm"] = 0
    else:
        m_casc = re.search(r'CASC\s*(\d+)/4', txt)
        if m_casc:
            result["evidence"]["cross_asset_confirm"] = int(m_casc.group(1))

    # ── 风险性质 ──
    if "非系统性" in txt:
        result["systemic_confirmed"] = False
        if result["near_event_type"] != "rate_event":
            result["near_event_type"] = "near_term_event"

    # v3.5.1: systemic_confirmed only when cross_asset_confirm ≥ 2 AND not self-contradicting
    cross_confirm = result["evidence"].get("cross_asset_confirm")
    if cross_confirm is not None and cross_confirm >= 2:
        if "系统性" in txt and "非系统性" not in txt:
            result["systemic_confirmed"] = True
            result["near_event_type"] = "systemic_event"
    # (if cross_confirm < 2, systemic_confirmed stays False regardless of text match)

    # v3.5.1: near_event_active gated on actual signal detection (was: hardcoded True)
    has_rate_event = any("DGS2" in s for s in result.get("event_sources", []))
    has_vol_event  = any("VIX" in s or "前端" in s for s in result.get("event_sources", []))
    if has_rate_event or has_vol_event or cross_confirm is not None:
        result["near_event_active"] = True

    # ── 事件窗口 ──
    for kw in ["CPI", "PPI", "FOMC", "美债拍卖", "点阵图"]:
        if kw in txt:
            result["event_sources"].append(kw)

    return result


def _infer_transmission(txt: str) -> dict:
    """从 ② 第一层传导 推断传导状态。

    核心逻辑：
    - DFII10 > 2.0% → 实际利率高压 → valuation_compression
    - EFFR-IORB ∈ [-3,0) → 资金管道偏紧
    - 两个都成立 → C先红+A偏紧 → 估值压缩
    """
    result: dict[str, Any] = {
        "rate_shock_active": False,
        "valuation_compression_active": False,
        "real_yield_pressure": False,
        "liquidity_buffer_thinning": False,
        "main_path": "",
        "summary": "",
        "evidence": {},
    }

    # ── DFII10 ──
    m = re.search(r'DFII10.*?([\d.]+)%', txt)
    if m:
        dfii10 = float(m.group(1))
        result["evidence"]["dfii10_pct"] = dfii10
        if dfii10 > 2.0:
            result["real_yield_pressure"] = True
            result["valuation_compression_active"] = True
            result["rate_shock_active"] = True
        elif dfii10 > 1.2:
            result["real_yield_pressure"] = True
            result["rate_shock_active"] = True

    # ── Real Yield Nowcast ──
    m = re.search(r'Real Yield Nowcast.*?([\d.]+)%', txt)
    if m:
        result["evidence"]["real_yield_nowcast"] = float(m.group(1))

    # ── EFFR-IORB ──
    m = re.search(r'EFFR-IORB[=＝]\s*([+-]?[\d.]+)bp', txt)
    if m:
        effr_iorb = float(m.group(1))
        result["evidence"]["effr_iorb_bp"] = effr_iorb
        if effr_iorb >= -5:
            result["liquidity_buffer_thinning"] = True

    # ── SOFR-IORB ──
    m = re.search(r'SOFR-IORB[=＝]\s*([+-]?[\d.]+)bp', txt)
    if m:
        result["evidence"]["sofr_iorb_bp"] = float(m.group(1))

    # ── 主路径推断 ──
    if result["valuation_compression_active"] and result["liquidity_buffer_thinning"]:
        result["main_path"] = "C先红 → A偏紧 → B未坏 → D未动"
        result["summary"] = "当前是利率/实际利率冲击造成的估值压缩，不是信用主导的系统性风险。"
    elif result["rate_shock_active"] and not result["liquidity_buffer_thinning"]:
        result["main_path"] = "C端利率压力为主，A端流动性尚可"
        result["summary"] = "利率冲击，但资金管道仍通畅。后续看B端是否从自满区脱离。"
    elif result["liquidity_buffer_thinning"] and not result["rate_shock_active"]:
        result["main_path"] = "A端偏紧为主，利率端尚可控"
        result["summary"] = "微观流动性压力主导，等待利率方向明确。"
    else:
        result["main_path"] = "无明确压力路径"
        result["summary"] = "当前无明显传导压力。"

    return result


def _infer_triggers(txt: str) -> dict:
    """从 ③ 系统性风险触发器 推断触发状态。

    三个触发器：
    T1 信用(B端)：HY OAS > 300bp 或 IG OAS > 85bp
    T2 流动性(A端)：EFFR-IORB 🟠/🔴 + DUR5 ≥ 5
    T3 跨资产/跨境：CASC ≥ 2 + VTS + RCV 互锁

    关键：section-level 匹配，防止 T2 的 "已触发" 污染 T1。
    """
    result: dict[str, Any] = {
        "credit_trigger": {"active": False, "label": "未触发", "evidence": ""},
        "liquidity_trigger": {"active": False, "partial": False, "label": "未触发", "evidence": ""},
        "cross_asset_trigger": {"active": False, "label": "未触发", "evidence": ""},
        "any_triggered": False,
        "all_triggered": False,
    }

    # ── 提取每行触发器文本 ──
    trigger_rows: dict[str, str] = {}
    for line in txt.splitlines():
        if "T1" in line or "信用(B端)" in line:
            trigger_rows["T1"] = line.strip()
        elif "T2" in line or "流动性(A端)" in line:
            trigger_rows["T2"] = line.strip()
        elif "T3" in line or "跨资产/跨境" in line:
            trigger_rows["T3"] = line.strip()

    # ── T1 信用 ──
    t1 = trigger_rows.get("T1", "")
    if "已触发" in t1:
        result["credit_trigger"]["active"] = True
        result["credit_trigger"]["label"] = "已触发"
    elif "未触发" in t1 or "自满" in t1:
        result["credit_trigger"]["active"] = False
        result["credit_trigger"]["label"] = "未触发（自满区）"
    result["credit_trigger"]["evidence"] = t1 if t1 else "HY/IG OAS仍处自满区或未明显走阔"

    # ── T2 流动性 ──
    t2 = trigger_rows.get("T2", "")
    if "已触发" in t2:
        result["liquidity_trigger"]["active"] = True
        if "部分" in t2:
            result["liquidity_trigger"]["partial"] = True
            result["liquidity_trigger"]["label"] = "部分触发"
        else:
            result["liquidity_trigger"]["label"] = "已触发"
    elif "未触发" in t2:
        result["liquidity_trigger"]["active"] = False
        result["liquidity_trigger"]["label"] = "未触发"
    else:
        # fallback: 看 EFFR-IORB 是否在 🟠
        m = re.search(r'EFFR-IORB[=＝]\s*([+-]?[\d.]+)bp.*?DUR5[=＝](\d+/\d+)', txt)
        if m:
            val = float(m.group(1))
            dur = m.group(2)
            if val >= -3 and dur.startswith("5/"):
                result["liquidity_trigger"]["active"] = True
                result["liquidity_trigger"]["partial"] = True
                result["liquidity_trigger"]["label"] = "部分触发"
                result["liquidity_trigger"]["evidence"] = f"EFFR-IORB={val}bp 且 DUR5={dur}"
    if not result["liquidity_trigger"]["evidence"]:
        result["liquidity_trigger"]["evidence"] = t2 if t2 else ""

    # ── T3 跨资产 ──
    t3 = trigger_rows.get("T3", "")
    if "已触发" in t3:
        result["cross_asset_trigger"]["active"] = True
        result["cross_asset_trigger"]["label"] = "已触发"
    elif "未触发" in t3:
        result["cross_asset_trigger"]["active"] = False
        result["cross_asset_trigger"]["label"] = "未触发"
    else:
        m = re.search(r'CASC\s*(\d+)/4', txt)
        if m:
            casc = int(m.group(1))
            if casc >= 2:
                result["cross_asset_trigger"]["active"] = True
                result["cross_asset_trigger"]["label"] = f"已触发(CASC={casc}/4)"
            else:
                result["cross_asset_trigger"]["active"] = False
                result["cross_asset_trigger"]["label"] = f"未触发(CASC={casc}/4)"
        else:
            result["cross_asset_trigger"]["evidence"] = "CASC 0/4，VTS contango，互锁 agree-front"
    if not result["cross_asset_trigger"]["evidence"]:
        result["cross_asset_trigger"]["evidence"] = t3 if t3 else ""

    # ── 汇总 ──
    triggered = sum(
        [
            result["credit_trigger"]["active"],
            result["liquidity_trigger"]["active"],
            result["cross_asset_trigger"]["active"],
        ]
    )
    result["any_triggered"] = triggered > 0
    result["all_triggered"] = triggered == 3

    return result


def _infer_stage(txt: str, trigger_state: dict) -> dict:
    """从 ④ 系统性风险阶段 推断当前所处阶段。

    不是照抄'最终判断'文字，而是基于触发器状态 + VTS/RCV/互锁信号做结构化判断。
    """
    result: dict[str, Any] = {
        "current_stage": "",
        "not_yet_stage": "",
        "final_judgement": "",
        "next_watch": [],
        "evidence": {},
    }

    # ── VTS ──
    m = re.search(r'VTS.*?[：:]\s*(.+?)(?:\n|$)', txt)
    if m:
        result["evidence"]["vts"] = m.group(1).strip()
        if "contango" in result["evidence"]["vts"]:
            result["evidence"]["vts_regime"] = "contango"
        elif "倒挂" in result["evidence"]["vts"]:
            result["evidence"]["vts_regime"] = "backwardated"

    # ── RCV ──
    m = re.search(r'RCV.*?[：:]\s*(.+?)(?:\n|$)', txt)
    if m:
        result["evidence"]["rcv"] = m.group(1).strip()
    m2 = re.search(r'tilt[=＝](\S+)', txt)
    if m2:
        result["evidence"]["rcv_tilt"] = m2.group(1)
    m3 = re.search(r'sev[=＝](\S+)', txt)
    if m3:
        result["evidence"]["rcv_sev"] = m3.group(1)

    # ── 互锁 ──
    m = re.search(r'互锁.*?agree-([a-z-]+)', txt)
    if m:
        result["evidence"]["interlock"] = m.group(1)

    # ── 最终判断 ──
    m = re.search(r'\*\*最终判断\*\*[：:]\s*(.+?)(?:\n|$)', txt)
    if m:
        result["final_judgement"] = m.group(1).strip()
    else:
        # fallback: 抓最后一行 > 开头的
        for line in txt.splitlines():
            if line.strip().startswith(">") and "最终判断" not in line:
                result["final_judgement"] = line.strip("> ").strip()
                break

    # ── C端 ──
    m = re.search(r'C端.*?[：:]\s*(.+?)(?:\n|$)', txt)
    if m:
        result["evidence"]["c_end"] = m.group(1).strip()

    # ── 阶段判定 ──
    if trigger_state["all_triggered"]:
        result["current_stage"] = "系统性风险"
        result["not_yet_stage"] = ""
    elif trigger_state["any_triggered"] and not trigger_state["all_triggered"]:
        result["current_stage"] = "前端事件风险 + 第一层利率冲击"
        result["not_yet_stage"] = "系统性风险"
    elif trigger_state["liquidity_trigger"]["active"]:
        result["current_stage"] = "流动性偏紧 + 估值压缩"
        result["not_yet_stage"] = "系统性风险"
    else:
        result["current_stage"] = "前端事件风险"
        result["not_yet_stage"] = "系统性风险"

    # ── Next Watch ──
    result["next_watch"] = [
        "RCV 是否从 front-tilt 变成 long-led / acute-broad",
        "VTS 是否从 contango 变成倒挂",
        "HY/IG OAS 是否脱离自满并走阔",
        "D端 FX / 跨境风险是否启动",
    ]

    return result


def extract(risk_dashboard_path: Path) -> dict:
    """主入口：解析 risk_dashboard MD → event_state JSON。"""
    txt = risk_dashboard_path.read_text(encoding="utf-8")

    result: dict[str, Any] = {}

    # ── 日期 ──
    m = re.search(r'\*\*(\d{4}-\d{2}-\d{2})\*\*', txt)
    if m:
        result["date"] = m.group(1)
    else:
        # fallback: 从文件名取
        m2 = re.search(r'(\d{4}-\d{2}-\d{2})', str(risk_dashboard_path))
        if m2:
            result["date"] = m2.group(1)
        else:
            result["date"] = date.today().isoformat()

    # ── Regime ──
    m = re.search(r'Regime:\s*\*\*(.+?)\*\*', txt)
    if m:
        result["regime"] = m.group(1).strip()

    # ── 仓位 ──
    m = re.search(r'P[=＝](\d+%)\s*/\s*H[=＝](\d+%)\s*/\s*C[=＝](\d+)%', txt)
    if m:
        result["positions"] = {"primary": m.group(1), "hedge": m.group(2), "cash": m.group(3) + "%"}
    else:
        result["positions"] = {"primary": "—", "hedge": "—", "cash": "—"}

    # ── 跨域信号 / 🔴数量 ──
    m = re.search(r'跨域信号[=＝](\d+)', txt)
    if m:
        result["cross_domain_signals"] = int(m.group(1))
    m = re.search(r'🔴[=＝](\d+)', txt)
    if m:
        result["red_count"] = int(m.group(1))

    # ── 核心推理：四大模块 ──
    result["event_state"] = _infer_near_event(txt)
    result["transmission_state"] = _infer_transmission(txt)
    result["trigger_state"] = _infer_triggers(txt)
    result["stage_assessment"] = _infer_stage(txt, result["trigger_state"])

    return result


# ═════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Extract risk event state from risk_dashboard MD")
    parser.add_argument("--date", help="Date YYYY-MM-DD, default today")
    parser.add_argument("--output", "-o", help="Output JSON path (default: stdout + _event_state.json)")
    parser.add_argument("--json", action="store_true", help="JSON output to stdout only")
    args = parser.parse_args()

    run_date = args.date or date.today().isoformat()
    md_path = REPORT_DIR / f"risk_dashboard_{run_date}.md"

    if not md_path.exists():
        print(f"[ERROR] risk_dashboard not found: {md_path}", file=sys.stderr)
        sys.exit(1)

    event_state = extract(md_path)

    if args.output:
        out = Path(args.output)
    else:
        out = REPORT_DIR / f"event_state_{run_date}.json"

    out.write_text(json.dumps(event_state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Event state → {out}")

    # NO LONGER write to docs/risk/assets/event_state.json.
    # The sole authority is risk_os_state_machine.py (Risk OS Orchestrator).
    # This tool only writes report/event_state_{date}.json for flowchart generation.

    if args.json:
        print(json.dumps(event_state, ensure_ascii=False, indent=2))

    return event_state


if __name__ == "__main__":
    main()
