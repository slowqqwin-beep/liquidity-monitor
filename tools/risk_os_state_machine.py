# -*- coding: utf-8 -*-
"""
Risk OS Orchestrator v2.0 — 三系统融合唯一裁决层 (Single Source of Truth)
==========================================================================
从 data/series.json 读取信号，输出权威 event_state.json。

三套输入系统（均为信号提供层，不得输出结论）：
  Fed Reaction   → 市场价格反应层（hawkish/dovish/liquidity/growth/inflation）
  ABCD / daily   → 结构风险层（A资金管道/B信用/C利率/D跨境）
  risk_dashboard → 前端风险演化层（近端事件/传导/T1-T2-T3/RCV/VTS/CASC）

Risk OS Orchestrator = 唯一融合裁决层，输出 risk_os_final。

关键分离：
  - Regime (R1-R4) = 仓位防御等级，由结构信号驱动
  - Systemic classification = 系统性风险确认，严格 T1+T2+T3
  - R4 防御 ≠ SYSTEMIC CONFIRMED

Usage:
  python tools/risk_os_state_machine.py [--date 2026-06-16]
"""
from __future__ import annotations
import argparse, json, sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERIES_PATH = PROJECT_ROOT / "data" / "series.json"
DOCS_ASSETS = PROJECT_ROOT / "docs" / "risk" / "assets"

# ── Helpers ──
def _load_data():
    if not SERIES_PATH.exists():
        raise FileNotFoundError(f"{SERIES_PATH} 不存在，先运行 fetch_data.py")
    with SERIES_PATH.open() as f: return json.load(f)

def _lv(s): return s[-1]["value"] if s else None
def _ld(s): return s[-1]["date"] if s else None
def _n_ago(s, n):
    if not s or len(s) < n + 1: return None
    return s[-n - 1]["value"]
def _n_chg(s, n):
    c, a = _lv(s), _n_ago(s, n)
    return c - a if (c is not None and a is not None) else None
def _dur5(s, lo, hi, mn=5):
    if not s: return 0
    cnt = 0
    for d in reversed(s):
        v = d["value"]
        if lo <= v < hi or (hi == float("inf") and v >= lo):
            cnt += 1
            if cnt >= mn: return mn
        else: break
    return cnt


# ═══ 数据质量评估 ═══
def assess_data_quality(raw, run_date: str) -> dict:
    """Check Yahoo/Market data staleness → degrade confidence for systemic confirmation."""
    r = {"stale": False, "stale_series": [], "confidence": "high", "impact": "",
         "note": "数据质量正常"}

    # Yahoo-sourced series check
    yahoo_keys = {"^VIX", "^VIX3M", "^VIX9D", "FXY", "HYG", "SPY", "^TNX"}
    today = None
    try:
        today = datetime.strptime(run_date, "%Y-%m-%d").date()
    except: pass

    for k in yahoo_keys:
        s = raw.get(k, [])
        if s:
            ld = _ld(s)
            if ld and today:
                try: d = datetime.strptime(ld, "%Y-%m-%d").date()
                except: continue
                age = (today - d).days
                if age > 5:
                    r["stale"] = True
                    r["stale_series"].append(f"{k} (last: {ld}, {age}d stale)")

    if r["stale"]:
        r["confidence"] = "low"
        r["impact"] = ("Yahoo数据滞后>5天，VTS/CASC/双探针互锁不能用于系统性确认。"
                       "systemic_confirmed严格为false，等fetch_data重抓。")
        r["note"] = f"⚠️ 数据质量降级：{'; '.join(r['stale_series'][:4])}"

    return r


# ── 1. DFII10 Nowcast ──
def compute_nowcast(raw):
    dgs10, t10yie, dfii = [raw.get(k, []) for k in ("DGS10", "T10YIE", "DFII10")]
    d10, bie, dof = _lv(dgs10), _lv(t10yie), _lv(dfii)
    r = {"dfii10_official": round(dof, 2) if dof else None,
         "dfii10_nowcast": None, "gap_bp": None, "direction": "N/A",
         "method": "DGS10 − 10Y BEI",
         "quality": "官方DFII10滞后修正，Nowcast更实时"}
    if d10 and bie:
        nc = round(d10 - bie, 2)
        r["dfii10_nowcast"] = nc
        if dof:
            g = round((nc - dof) * 100, 0)
            r["gap_bp"] = int(g)
            r["direction"] = "基本持平" if abs(g) <= 5 else (
                "小幅上行" if 0 < g <= 15 else "明显上行" if g > 15 else
                "小幅回落" if g >= -15 else "明显回落")
    return r


# ── 2. 近端事件风险 ──
def compute_front_event(raw):
    vix = _lv(raw.get("VIXCLS", []))
    d2, io = _lv(raw.get("DGS2", [])), _lv(raw.get("IORB", []))
    d2_io = round((d2 - io) * 100, 1) if (d2 and io) else None
    # 5d delta for direction context (avoid static template mislabeling)
    d2_5d = _n_chg(raw.get("DGS2", []), 5)
    d2_5d_bp = round(d2_5d * 100, 1) if d2_5d is not None else None
    r = {"active": False, "type": "unknown", "sources": [], "intensity": "green",
         "label": "前端平稳", "evidence": {"vix": round(vix, 1) if vix else None,
         "dgs2_iorb_bp": d2_io}}
    if d2_io and d2_io > 0:
        r["active"], r["type"] = True, "rate_event"
        # v3.5.1: include direction (level vs change) — avoids "降息被price out" static template
        # when 5d delta is moving dovish (negative)
        dir_note = ""
        if d2_5d_bp is not None:
            dir_note = f" · 5d{d2_5d_bp:+.1f}bp" + ("(方向背离：短期下行)" if d2_5d_bp < 0 else "(方向一致：短期上行)")
        r["sources"].append(f"DGS2−IORB={d2_io}bp 前端利率事件{dir_note}")
    if vix and vix > 20:
        r["active"] = True
        r["type"] = "mixed_event" if r["type"] == "rate_event" else "vol_event"
        r["sources"].append(f"VIX={vix:.1f}")
    if r["active"]:
        r["intensity"] = "red" if (d2_io and d2_io >= 20) else "orange"
        r["label"] = "前端急性" if r["intensity"] == "red" else "前端紧张"
    return r


# ── 3. 实际利率/估值挤压 ──
def compute_rate_shock(raw, nc):
    dof, now, dfii_s = nc.get("dfii10_official"), nc.get("dfii10_nowcast"), raw.get("DFII10", [])
    oe = dof is not None and dof >= 2.00
    ne = now is not None and now >= 2.00
    d5 = _dur5(dfii_s, 2.00, float("inf"))
    r = {"active": oe or ne, "dfii10_official": dof, "dfii10_nowcast": now,
         "gap_bp": nc.get("gap_bp"), "direction": nc.get("direction", "N/A"),
         "method": nc.get("method"), "quality_note": nc.get("quality"),
         "dur5_dfii": d5, "dur5_confirmed": d5 >= 5,
         "level_label": "", "level_light": ""}
    if dof is not None:
        r["level_label"] = "高压·估值压缩" if dof >= 2.00 else ("偏紧·接近阈值" if dof >= 1.20 else "正常区间")
        r["level_light"] = "🔴" if dof >= 2.00 else ("🟠" if dof >= 1.20 else "🟢")
    return r


# ── 4. 第一层传导 ──
def compute_transmission(raw, rs):
    e, io, sf, ei_derived = [raw.get(k, []) for k in ("EFFR", "IORB", "SOFR", "EFFR_IORB")]
    ev, iov = _lv(e), _lv(io)
    ei = round((ev - iov) * 100, 1) if (ev and iov) else None
    si = round((_lv(sf) - iov) * 100, 1) if (_lv(sf) and iov) else None
    d5 = _dur5(ei_derived, -3, float("inf"), mn=3) if ei_derived else 0
    ls = ei is not None and ei >= -3
    ra = rs.get("active", False)
    r = {"active": ra or ls, "real_yield_pressure": ra,
         "liquidity_buffer_thinning": ls, "effr_iorb_bp": ei,
         "sofr_iorb_bp": si, "dur5_effr_iorb": d5,
         "dur5_confirmed": d5 >= 3}
    if ra and ls: r["main_path"], r["summary"] = "C先红 → A偏紧 → B未坏 → D未动", "利率/实际利率冲击致估值压缩，非信用主导系统性风险。"
    elif ra: r["main_path"], r["summary"] = "C端利率压力为主", "利率冲击但资金管道通畅，看B端是否脱离自满。"
    elif ls: r["main_path"], r["summary"] = "A端偏紧为主", "微观流动性压力主导。"
    else: r["main_path"], r["summary"] = "无明确压力", "四端无显著传导。"
    return r


# ── 5. 系统性风险触发器 ──
def compute_triggers(raw, tx):
    hy, ig = _lv(raw.get("BAMLH0A0HYM2", [])), _lv(raw.get("BAMLC0A0CM", []))
    ei, d5e = tx.get("effr_iorb_bp"), tx.get("dur5_effr_iorb", 0)
    hy_bp = hy * 100 if hy else None

    t1_a = hy_bp is not None and hy_bp >= 300
    t1_l = "已触发" if t1_a else "未触发"
    t1_e = f"HY OAS={hy_bp:.0f}bp，{'已脱离自满' if t1_a else '仍在自满区'}" if hy_bp else "—"

    # T2: EFFR-IORB ≥ -3bp AND DUR5 ≥ 3
    t2_a = ei is not None and ei >= -3 and d5e >= 3
    t2_partial = ei is not None and ei >= -3 and not t2_a
    t2_l = "已触发·部分压力" if (t2_a and (t2_partial or not t1_a)) else ("已触发" if t2_a else ("部分触发" if t2_partial else "未触发"))
    t2_e = f"EFFR-IORB={ei}bp DUR5={d5e}/3" if ei else "—"

    vi, mv = _lv(raw.get("VIXCLS", [])), _lv(raw.get("MOVE", []))
    hy20d = _n_chg(raw.get("BAMLH0A0HYM2", []), 20)
    fxy = raw.get("FXY", [])
    f5r = None
    if fxy and len(fxy) >= 6:
        fc, fa = _lv(fxy), _n_ago(fxy, 5)
        if fc and fa and fa != 0: f5r = (fc - fa) / fa * 100

    casc = 0
    casc_parts = []
    if vi and vi > 25: casc += 1; casc_parts.append(f"VIX={vi:.1f}>25")
    if mv and mv > 120: casc += 1; casc_parts.append(f"MOVE={mv:.0f}>120")
    if hy20d and hy20d > 0.20: casc += 1; casc_parts.append(f"HY 20dΔ={hy20d*100:.0f}bp")
    if f5r and abs(f5r) > 2.5: casc += 1; casc_parts.append(f"FXY 5d={f5r:+.1f}%")
    t3_a = casc >= 2
    t3_l = f"{'已触发' if t3_a else '未触发'} (CASC{casc}/4)"
    t3_e = f"CASC {casc}/4（{'，'.join(casc_parts)}）" if casc_parts else f"CASC {casc}/4，无跨资产压力"

    any_t = t1_a or t2_a or t3_a
    all_t = t1_a and t2_a and t3_a
    return {"credit": {"active": t1_a, "label": t1_l, "evidence": t1_e},
            "liquidity": {"active": t2_a, "partial": t2_partial,
                          "credit_partial": t2_a and not t1_a,
                          "label": t2_l, "evidence": t2_e},
            "cross_asset": {"active": t3_a, "label": t3_l, "evidence": t3_e},
            "any_triggered": any_t, "all_triggered": all_t, "casc_count": casc}


# ══════════════════════════════════════════════════════════════════════
#  RISK OS ORCHESTRATOR — 三系统融合唯一裁决
# ══════════════════════════════════════════════════════════════════════

def run_orchestrator(raw, fe, rs, tx, tg, dq):
    """
    唯一裁决层。

    输入：
      fe = 前端事件风险 (来自 risk_dashboard / 利率+VIX事件层)
      rs = 实际利率压力 (来自 ABCD / C端 结构层)
      tx = 第一层传导   (来自 ABCD / A端 流动性层)
      tg = 三重触发器   (T1信用 / T2流动性 / T3跨资产)
      dq = 数据质量评估

    输出：
      risk_os_final — 最终裁决，下游只能读取，不得重算。
    """
    # ──── RED count: 已确认的系统级信号 ────
    # real_yield_pressure (DFII10≥2.00% DUR5≥5)   = C端确认
    # T2 liquidity full trigger (DUR5≥3)           = A端确认
    # T1 credit active                             = B端确认
    # T3 cross_asset active                        = D端确认
    red_c = tx.get("real_yield_pressure", False)
    red_a = tg["liquidity"]["active"]
    red_b = tg["credit"]["active"]
    red_d = tg["cross_asset"]["active"]
    red_count = sum([red_c, red_a, red_b, red_d])

    # ──── ORANGE count: 预警/早期信号 ────
    orange_count = sum([fe.get("active", False),
                        rs.get("active", False),
                        tg["liquidity"].get("partial", False)])

    # ──── REGIME: 仓位防御等级 (R1→R4) ────
    # v2.0: red≥2 → R4（A+C双红即为防御模式，不要求系统性确认）
    if red_count >= 3:
        regime_key, regime_label = "R4", "R4 防御"
    elif red_count >= 2:
        regime_key, regime_label = "R4", "R4 防御"
    elif red_count >= 1 or (orange_count >= 1 and fe.get("active")):
        regime_key, regime_label = "R3", "R3 警惕"
    elif orange_count >= 1:
        regime_key, regime_label = "R2", "R2 观察"
    else:
        regime_key, regime_label = "R1", "R1 正常"

    # ──── SYSTEMIC CLASSIFICATION ────
    # 严格四档：NON-SYSTEMIC / NON-SYSTEMIC WATCH / SYSTEMIC WATCH / SYSTEMIC CONFIRMED
    # systemic_confirmed = true ONLY IF T1+T2+T3 all active
    t1_active = tg["credit"]["active"]
    t2_active = tg["liquidity"]["active"]
    t3_active = tg["cross_asset"]["active"]
    any_trigger = tg["any_triggered"]
    all_trigger = tg["all_triggered"]

    if all_trigger:
        systemic_class = "SYSTEMIC CONFIRMED"
        systemic_confirmed = True
    elif t1_active and t2_active and not t3_active:
        # credit + liquidity without cross-asset: close to systemic
        systemic_class = "SYSTEMIC WATCH"
        systemic_confirmed = False
    elif any_trigger:
        systemic_class = "NON-SYSTEMIC WATCH"
        systemic_confirmed = False
    else:
        systemic_class = "NON-SYSTEMIC"
        systemic_confirmed = False

    # Data quality override: stale → systemic_confirmed must be false
    if dq.get("stale", False) and systemic_confirmed:
        systemic_confirmed = False
        systemic_class = "NON-SYSTEMIC WATCH"
        dq["impact"] = (dq.get("impact", "") +
                        " 系统性确认被数据质量降级强制置为false。")

    # ──── POSITIONS ────
    pos_map = {
        "R1": ("75%", "5%", "20%"),
        "R2": ("55%", "25%", "20%"),
        "R3": ("35%", "35%", "30%"),
        "R4": ("25%", "45%", "30%"),  # 对齐 ABCD 的 R4 仓位
    }
    pos = pos_map.get(regime_key, ("55%", "25%", "20%"))

    # ──── HERO / JUDGEMENT ────
    red_parts = []
    if red_c: red_parts.append("C(实际利率)")
    if red_a: red_parts.append("A(流动性)")
    if red_b: red_parts.append("B(信用)")
    if red_d: red_parts.append("D(跨境)")

    hero = f"{regime_label} · {systemic_class}"
    if red_count >= 2 and not systemic_confirmed:
        hero += f" — {'+'.join(red_parts)}双红→防御仓位，但系统性能确认未达成"

    if systemic_confirmed:
        judgement = ("三重触发器全亮：信用走阔+流动性压力持续+跨资产共振。"
                     "系统已进入系统性风险。激进降风险。")
    elif systemic_class == "SYSTEMIC WATCH":
        judgement = ("T1信用+T2流动性已触发，但T3跨资产未共振。"
                     "信用已走阔、流动性持续承压，距离系统性仅一步之遥。"
                     "需紧盯CASC/VTS/RCV是否从divergent转为agree-systemic。")
    elif systemic_class == "NON-SYSTEMIC WATCH":
        if red_c and red_a and not red_b:
            t2_detail = "已触发·部分压力" if tg["liquidity"].get("credit_partial") else "已触发"
            judgement = (f"A/C双红→{regime_label}模式；"
                         f"T2流动性{t2_detail}（{tg['liquidity'].get('evidence','')}）、"
                         f"但T1信用未触发、T3跨资产未触发，"
                         f"不满足系统性风险三端共振定义。"
                         f"实际利率高压+流动性部分压力使仓位进入防御，"
                         f"但信用未坏、跨境未扩散→仍为非系统性观察。")
        else:
            judgement = (f"部分触发信号存在但T1信用/T3跨资产未共振，"
                         f"不符合系统性风险确认条件。")
    else:
        judgement = "无系统性风险信号。四端平静。"

    # Data quality note in judgement
    if dq.get("stale", False):
        judgement += (" ⚠️数据质量降级：Yahoo数据滞后，CASC/VTS/双探针互锁"
                      "不能用于系统性确认。结论置信度打折，需重抓fetch_data。")

    # ──── STAGE ────
    if systemic_confirmed:
        current_stage, not_yet_stage = "系统性风险", ""
    elif any_trigger:
        current_stage, not_yet_stage = "前端事件风险 + 第一层利率冲击", "系统性风险"
    elif fe.get("active"):
        current_stage, not_yet_stage = "前端事件风险", "系统性风险"
    else:
        current_stage, not_yet_stage = "无显著风险事件", "—"

    # ──── SOURCE VOTES ────
    source_votes = {
        "fed_reaction": _infer_fed_reaction_signal(raw, fe, tg),
        "abcd": _infer_abcd_signal(red_c, red_a, red_b, red_d, tg, tx),
        "risk_dashboard": _infer_dashboard_signal(fe, rs, tx, tg),
    }

    return {
        "risk_os_final": {
            "date": "",  # filled by assemble()
            "final_regime": regime_label,
            "final_regime_key": regime_key,
            "final_systemic_classification": systemic_class,
            "systemic_confirmed": systemic_confirmed,
            "final_position": {"primary": pos[0], "hedge": pos[1], "cash": pos[2]},
            "final_hero": hero,
            "final_judgement": judgement,
            "confidence": dq.get("confidence", "high"),
            "data_quality": {"stale": dq.get("stale", False),
                             "stale_series": dq.get("stale_series", []),
                             "impact": dq.get("impact", "")},
            "source_votes": source_votes,
        },
        # detail layers (inputs, NOT final)
        "red_count": red_count,
        "orange_count": orange_count,
        "cross_domain_signals": red_count + (1 if orange_count > 0 else 0),
        "current_stage": current_stage,
        "not_yet_stage": not_yet_stage,
    }


def _infer_fed_reaction_signal(raw, fe, tg):
    """从 raw 数据推断 Fed Reaction 会给出的信号（模拟层，实际应读 Fed Reaction 输出）。"""
    d2, io = _lv(raw.get("DGS2", [])), _lv(raw.get("IORB", []))
    d2_io = round((d2 - io) * 100, 1) if (d2 and io) else None
    vix = _lv(raw.get("VIXCLS", []))
    hy = _lv(raw.get("BAMLH0A0HYM2", []))
    hy_bp = hy * 100 if hy else None

    parts = []
    if d2_io and d2_io >= 20:
        parts.append("hawkish pressure (DGS2-IORB high)")
    elif d2_io and d2_io >= 0:
        parts.append("rate normalization bias")
    if vix and vix < 20:
        parts.append("vol calm")
    if hy_bp and hy_bp < 300:
        parts.append("credit gate: complacent/improving")
    else:
        parts.append("credit gate: deterioration signal")

    if not parts:
        parts.append("insufficient data")
    return " | ".join(parts)


def _infer_abcd_signal(red_c, red_a, red_b, red_d, tg, tx):
    """ABCD 结构信号。—— A端用实际 EFFR-IORB 值映射 ABCD 阈值灯色，而非 T2 触发器。"""
    # ABCD A端灯色阈值：🟢<-7 | 🟡-7~-3 | 🟠-3~0 | 🔴≥0
    ei = tx.get("effr_iorb_bp")
    if ei is not None and ei >= 0:
        a_color = "🔴"
    elif ei is not None and ei >= -3:
        a_color = "🟠"
    elif ei is not None and ei >= -7:
        a_color = "🟡"
    else:
        a_color = "🟢" if ei is not None else "?端"
    parts = []
    parts.append(f"C端={'🔴' if red_c else '🟢'}")
    parts.append(f"A端={a_color}")
    parts.append(f"B端={'🔴' if red_b else '🟢'}")
    parts.append(f"D端={'🔴' if red_d else '🟢'}")
    regime_hint = ""
    a_red_abcd = (ei is not None and ei >= 0)
    c_red_abcd = red_c  # DFII10 >= 2.00%
    if c_red_abcd and a_red_abcd and not red_b:
        regime_hint = " → A/C双红→R4防御模式"
    elif c_red_abcd or a_red_abcd:
        regime_hint = " → R3警惕"
    return " ".join(parts) + regime_hint


def _infer_dashboard_signal(fe, rs, tx, tg):
    """前端风险演化信号。"""
    parts = []
    if fe.get("active"):
        parts.append(f"前端事件:{fe.get('intensity','?')}")
    if rs.get("active"):
        parts.append("实际利率高压")
    if tx.get("liquidity_buffer_thinning"):
        parts.append("流动性缓冲变薄")
    if tg["any_triggered"] and not tg["all_triggered"]:
        parts.append("部分触发·非系统性")
    elif tg["all_triggered"]:
        parts.append("全触发·系统性")
    else:
        parts.append("无触发")
    return " | ".join(parts) if parts else "insufficient"


def detect_conflicts(fe, final, tg):
    """检测输入信号与最终裁决之间的冲突。"""
    c = []
    if fe.get("active") and final["risk_os_final"]["final_regime_key"] == "R1":
        c.append({"type": "regime_risk_mismatch",
                  "detail": "近端事件活跃但regime=R1",
                  "resolution": "检查前端事件是否应升级regime"})
    if tg["all_triggered"] and not final["risk_os_final"]["systemic_confirmed"]:
        c.append({"type": "trigger_vs_systemic",
                  "detail": "三重触发器全亮但systemic_confirmed=false",
                  "resolution": "数据质量降级导致，需重抓数据后复核"})
    # Fed Reaction conflict: credit gate deteriorate but ABCD credit complacent
    if tg["credit"]["active"] and tg["liquidity"].get("credit_partial"):
        pass  # expected: credit triggers and liquidity with missing credit → this IS the WATCH case
    return c


# ══════════════════════════════════════════════════════════════════════
#  MAIN — assemble & output
# ══════════════════════════════════════════════════════════════════════

def assemble(run_date: str) -> dict:
    raw = _load_data()
    nc = compute_nowcast(raw)
    fe = compute_front_event(raw)
    rs = compute_rate_shock(raw, nc)
    tx = compute_transmission(raw, rs)
    tg = compute_triggers(raw, tx)
    dq = assess_data_quality(raw, run_date)
    orch = run_orchestrator(raw, fe, rs, tx, tg, dq)
    cf = detect_conflicts(fe, orch, tg)

    # Fill date in risk_os_final
    orch["risk_os_final"]["date"] = run_date
    orch["risk_os_final"]["data_quality"]["note"] = dq.get("note", "")

    result = {
        "generated_at": run_date,
        "generator": "Risk OS Orchestrator v2.0 — SSoT",
        "_version": "v2.0",
        "_note": (
            "⚠️ 唯一权威状态输出。三套输入系统(Fed Reaction/ABCD/risk_dashboard) "
            "降级为信号提供层，不得输出最终结论。下游只能读取 risk_os_final，不得重算。"
        ),

        # ── COMPAT: top-level aliases (for dashboard.js v2 compat) ──
        "date": run_date,
        "regime": orch["risk_os_final"]["final_regime"],
        "regime_key": orch["risk_os_final"]["final_regime_key"],
        "systemic_classification": orch["risk_os_final"]["final_systemic_classification"],
        "systemic_confirmed": orch["risk_os_final"]["systemic_confirmed"],
        "positions": orch["risk_os_final"]["final_position"],
        "cross_domain_signals": orch["cross_domain_signals"],
        "red_count": orch["red_count"],

        # ── THE authority: risk_os_final ──
        "risk_os_final": orch["risk_os_final"],

        # ── Detail layers (inputs to the orchestrator) ──
        "_detail_inputs": {
            "front_event_risk": fe,
            "rate_shock": rs,
            "first_layer_transmission": tx,
            "systemic_triggers": tg,
        },

        # Stage assessment
        "stage_assessment": {
            "current_stage": orch["current_stage"],
            "not_yet_stage": orch["not_yet_stage"],
            "final_judgement": orch["risk_os_final"]["final_judgement"],
            "systemic_upgrade_conditions": {
                "credit_widening": tg["credit"]["active"],
                "liquidity_sustained": tg["liquidity"]["active"],
                "cross_asset_resonance": tg["cross_asset"]["active"],
                "all_met": tg["all_triggered"],
            },
            "next_watch": [
                "T1信用: HY/IG OAS是否脱离自满并走阔 (>300bp)",
                "T2流动性: EFFR-IORB是否持续≥-3bp DUR5≥3",
                "T3跨资产: CASC是否≥2/4 · VTS+RCV是否从divergent→agree-systemic",
                "D端: FX/跨境风险是否启动",
            ],
        },
        "signal_conflicts": cf,
    }
    return result


def main():
    p = argparse.ArgumentParser(description="Risk OS Orchestrator v2.0")
    p.add_argument("--date", help="YYYY-MM-DD", default=date.today().isoformat())
    args = p.parse_args()

    es = assemble(args.date)
    DOCS_ASSETS.mkdir(parents=True, exist_ok=True)
    out = DOCS_ASSETS / "event_state.json"
    out.write_text(json.dumps(es, ensure_ascii=False, indent=2), encoding="utf-8")
    rf = es["risk_os_final"]
    print(f"[Risk OS v2.0] State written → {out}")
    print(f"  Final Regime:    {rf['final_regime']} ({rf['final_regime_key']})")
    print(f"  Systemic:        {rf['final_systemic_classification']}")
    print(f"  Systemic Confirmed: {rf['systemic_confirmed']}")
    print(f"  Position:        P{rf['final_position']['primary']} H{rf['final_position']['hedge']} C{rf['final_position']['cash']}")
    print(f"  Confidence:      {rf['confidence']}")
    print(f"  Data Quality:    {'[STALE]' if rf['data_quality']['stale'] else 'OK'}")
    print(f"  Hero: {rf['final_hero']}")
    if es["signal_conflicts"]:
        print(f"  [WARN] Conflicts: {len(es['signal_conflicts'])}")
        for c in es["signal_conflicts"]: print(f"    - {c['detail']}")
    return es


if __name__ == "__main__":
    main()
