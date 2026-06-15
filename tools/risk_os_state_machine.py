# -*- coding: utf-8 -*-
"""
Risk OS State Machine — 唯一状态裁决层 (Single Source of Truth)
================================================================
从 data/series.json 读取 FRED+Yahoo 信号，直接输出权威 event_state.json。
所有其他系统（Fed reaction、ABCD）降级为 signal provider，不得输出结论。

规则：
- R1 正常 / R2 观察 / R3 警惕 / R4 风险释放
- SYSTEMIC = T1+T2+T3 全亮
- 否则 NON-SYSTEMIC 或 WATCH

Usage:
  python tools/risk_os_state_machine.py [--date 2026-06-15]
"""
from __future__ import annotations
import argparse, json, sys
from datetime import date
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
    r = {"active": False, "type": "unknown", "sources": [], "intensity": "green",
         "label": "前端平稳", "evidence": {"vix": round(vix, 1) if vix else None,
         "dgs2_iorb_bp": d2_io}}
    if d2_io and d2_io > 0:
        r["active"], r["type"] = True, "rate_event"
        r["sources"].append(f"DGS2−IORB={d2_io}bp 降息被price out")
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
    # DUR5 on derived EFFR_IORB series (in bp), threshold ≥ -3bp
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
    t1_l = "已触发" if t1_a else "未触发（自满区）"
    t1_e = f"HY OAS={hy_bp:.0f}bp，{'已脱离自满' if t1_a else '仍在自满区'}" if hy_bp else "—"

    # T2: EFFR-IORB ≥ -3bp AND DUR5 ≥ 3 (user spec)
    t2_a = ei is not None and ei >= -3 and d5e >= 3
    t2_partial = ei is not None and ei >= -3 and not t2_a
    t2_l = "已触发" if t2_a else ("部分触发" if t2_partial else "未触发")
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
    return {"credit": {"active": t1_a, "label": t1_l, "evidence": t1_e},
            "liquidity": {"active": t2_a, "partial": t2_partial,
                          "credit_partial": t2_a and not t1_a,
                          "label": t2_l, "evidence": t2_e},
            "cross_asset": {"active": t3_a, "label": t3_l, "evidence": t3_e},
            "any_triggered": any_t, "all_triggered": t1_a and t2_a and t3_a, "casc_count": casc}

# ══════════════════════════════════════════════════════════════════════
#  STATE MACHINE
# ══════════════════════════════════════════════════════════════════════

def run_state_machine(fe, rs, tx, tg):
    """R1-R4 + SYSTEMIC/NON-SYSTEMIC"""
    # red: confirmed systemic-level signals
    red = sum([tx.get("real_yield_pressure", False),
               tg["liquidity"]["active"],       # full trigger (DUR5≥3)
               tg["credit"]["active"],
               tg["cross_asset"]["active"]])
    # orange: warning / early-stage signals
    orange = sum([fe.get("active", False),
                  rs.get("active", False),
                  tg["liquidity"].get("partial", False),  # near-trigger (DUR5<3)
                  tg["liquidity"].get("credit_partial", False)])  # active but credit missing
    cross = red + (1 if orange > 0 else 0)

    if red >= 3: rk, rl = "R4", "R4 风险释放"
    elif red >= 1 or (orange >= 1 and fe.get("active")):
        rk, rl = "R3", "R3 警惕"
    elif orange >= 1: rk, rl = "R2", "R2 观察"
    else: rk, rl = "R1", "R1 正常"

    systemic = "SYSTEMIC" if tg["all_triggered"] else ("WATCH" if tg["any_triggered"] else "NON-SYSTEMIC")

    if tg["all_triggered"]: cs, ny = "系统性风险", ""
    elif tg["any_triggered"]: cs, ny = "前端事件风险 + 第一层利率冲击", "系统性风险"
    elif fe.get("active"): cs, ny = "前端事件风险", "系统性风险"
    else: cs, ny = "无显著风险事件", "—"

    pos = {"R1": ("75%", "5%", "20%"), "R2": ("55%", "25%", "20%"),
           "R3": ("35%", "35%", "30%"), "R4": ("30%", "40%", "30%")}.get(rk, ("55%", "25%", "20%"))

    if systemic == "SYSTEMIC":
        fj = "三重触发器全亮：信用走阔 + 流动性压力持续 + 跨资产共振。系统已进入系统性风险。激进降风险。"
    elif systemic == "WATCH":
        fj = "双探针前端一致·近端事件非系统性。等CPI/Fed落地看前端是fade还是扩散。要盯的翻转点：RCV→long-led/acute-broad叠VTS倒挂→agree-systemic。"
    else:
        fj = "无系统性风险信号。四端平静。"

    return {"regime": rl, "regime_key": rk, "systemic_classification": systemic,
            "positions": {"primary": pos[0], "hedge": pos[1], "cash": pos[2]},
            "cross_domain_signals": cross, "red_count": red,
            "current_stage": cs, "not_yet_stage": ny, "final_judgement": fj,
            "systemic_upgrade_conditions": {
                "credit_widening": tg["credit"]["active"],
                "liquidity_sustained": tg["liquidity"]["active"],
                "cross_asset_resonance": tg["cross_asset"]["active"],
                "all_met": tg["all_triggered"]},
            "next_watch": [
                "RCV 是否从 front-tilt 变成 long-led / acute-broad",
                "VTS 是否从 contango 变成倒挂",
                "HY/IG OAS 是否脱离自满并走阔",
                "D端 FX / 跨境风险是否启动",
            ]}

def detect_conflicts(fe, state):
    c = []
    if fe.get("active") and state["regime_key"] == "R1":
        c.append({"type": "regime_risk_mismatch", "detail": "近端事件活跃但regime=R1"})
    if state["systemic_classification"] == "NON-SYSTEMIC" and state["regime_key"] == "R3":
        pass  # expected
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
    sm = run_state_machine(fe, rs, tx, tg)
    cf = detect_conflicts(fe, sm)

    return {
        "date": run_date,
        "source": "Risk OS State Machine v1.0 — Single Source of Truth",
        "_note": "此为唯一权威状态输出。Fed reaction/ABCD 仅作信号输入层，不得输出最终结论。",

        "regime": sm["regime"],
        "regime_key": sm["regime_key"],
        "systemic_classification": sm["systemic_classification"],
        "positions": sm["positions"],
        "cross_domain_signals": sm["cross_domain_signals"],
        "red_count": sm["red_count"],

        "front_event_risk": fe,
        "rate_shock": rs,
        "first_layer_transmission": tx,
        "systemic_triggers": tg,

        "stage_assessment": {
            "current_stage": sm["current_stage"],
            "not_yet_stage": sm["not_yet_stage"],
            "final_judgement": sm["final_judgement"],
            "systemic_upgrade_conditions": sm["systemic_upgrade_conditions"],
            "next_watch": sm["next_watch"],
        },
        "signal_conflicts": cf,
    }

def main():
    p = argparse.ArgumentParser(description="Risk OS State Machine")
    p.add_argument("--date", help="YYYY-MM-DD", default=date.today().isoformat())
    args = p.parse_args()

    es = assemble(args.date)
    DOCS_ASSETS.mkdir(parents=True, exist_ok=True)
    out = DOCS_ASSETS / "event_state.json"
    out.write_text(json.dumps(es, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Risk OS] State written → {out}")
    print(f"  Regime: {es['regime']} ({es['regime_key']})")
    print(f"  Systemic: {es['systemic_classification']}")
    print(f"  Stage: {es['stage_assessment']['current_stage']}")
    print(f"  Triggers: any={es['systemic_triggers']['any_triggered']} all={es['systemic_triggers']['all_triggered']}")
    if es["signal_conflicts"]:
        print(f"  ⚠️ Conflicts: {len(es['signal_conflicts'])}")
        for c in es["signal_conflicts"]: print(f"    - {c['detail']}")
    return es

if __name__ == "__main__":
    main()
