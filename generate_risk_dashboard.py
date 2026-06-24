"""
§0.7+ 前端风险→系统性风险 可视化看板
从 daily_report 计算管线读取数据，生成四模块文字表格 + PNG。
Usage: python v3.5/generate_risk_dashboard.py [--date 2026-06-10]
"""
from __future__ import annotations
import argparse, json, sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from daily_report import (
    load_data, compute_vintages, compute_v35_triggers,
    compute_abcd_signals, compute_casc, compute_vts, compute_rcv,
    compute_vts_rcv_interlock, apply_casc_gate, compute_position,
    compute_rate_path_proxy, compute_trigger_proximity,
    compute_real_yield_nowcast,
)

DATA_DIR   = Path(__file__).resolve().parent / "data"
REPORT_DIR = Path(__file__).resolve().parent / "report"

def _light_color(l: str) -> str:
    m = {"🔴":"red","🟠":"orange","🟡":"yellow","🟢":"green","⚠️":"yellow"}
    return m.get(l, "gray")

# ═══════════════════════════════════════════════════════════════════════════
# Verdict 映射 — 唯一入口，与 compute_vts_rcv_interlock() 的 state 全集保持覆盖
# ═══════════════════════════════════════════════════════════════════════════

VERDICTS = {
    "systemic":     "[!] SYSTEMIC CONFIRMED -- VTS inversion + RCV long/acute-broad. Defend. Role B triggered.",
    "pre-systemic": "Front stress accumulating, NOT systemic yet. Watch RCV→long-led or acute-broad + VTS inverted → upgrade.",
    "front":        "Non-systemic front event. Await CPI/Fed → front will either fade or spread. Key flip: RCV→long-led/acute-broad + VTS inverted.",
    "divergent":    "VTS hot · RCV calm → single-asset technical. No dual-probe resonance, no extra systemic position action.",
    "calm":         "Low risk. Dual probes calm. Maintain baseline.",
    "N/A":          "VTS/RCV data missing — cannot confirm or refute systemic. Watch for data return.",
}

def map_lock_to_verdict(lock_state: str, vts_structure: str) -> str:
    """将互锁 state 映射为 verdict 字符串。stg_key 枚举全集：
    systemic / pre-systemic / front / divergent / N/A / calm

    缺键时返回可见告警 fallback（不返回空串，防 PNG 空白）。
    """
    if lock_state == "agree-systemic":
        stg_key = "systemic"
    elif vts_structure in ("倒挂", "倒挂·急性"):
        stg_key = "pre-systemic"
    elif lock_state == "agree-front":
        stg_key = "front"
    elif lock_state == "divergent":
        stg_key = "divergent"
    elif lock_state in ("N/A", "vts_missing"):
        stg_key = "N/A"
    else:
        stg_key = "calm"
    fallback = f"[!] VERDICT KEY MISSING: stg_key='{stg_key}' lock_state='{lock_state}' — report bug"
    return VERDICTS.get(stg_key, fallback)

# ═══════════════════════════════════════════════════════════════════════════
# Markdown Dashboard
# ═══════════════════════════════════════════════════════════════════════════
def format_dashboard_md(data_date, run_date, abcd, pos, v35, casc, vts, rcv, lock, rate_path, *, nowcast=None):
    a,b,c,d = abcd["A"],abcd["B"],abcd["C"],abcd["D"]
    cross, red_n = abcd["cross_domain_count"], abcd["red_domain_count"]
    reg, reg_key = pos["label"], pos["regime_key"]
    a_effr = a["details"].get("EFFR-IORB",{})
    effr_v, effr_l, dur5_e = a_effr.get("value_bp",0) or 0, a_effr.get("light","N/A"), a_effr.get("dur5",0)
    c_dfii = c["details"].get("DFII10",{})
    dur5_d = c_dfii.get("dur5",0)
    vix_leg = casc["legs"]["VIX"]
    move_leg = casc["legs"]["MOVE"]
    casc_conf, casc_label = casc["confirmation_count"], casc.get("c_label","—")
    lock_state = lock.get("state","N/A")
    vix9d_r = vts.get("ratio_vix9d_vix")
    vix9d_r_str = f"{vix9d_r:.3f}" if vix9d_r is not None else "N/A"
    rp_gap, rp_label = rate_path.get("gap_bp"), rate_path.get("level_label","N/A")
    rp_5d = rate_path.get("gap_5d_chg")

    # Systemic stage — describes systemic-risk dimension only; never outputs position advice
    # v3.5.1: VTS=N/A explicitly gated (not folded into calm). stage_l emoji removed (stage_c provides it).
    if lock_state == "agree-systemic":
        stage, stage_l, stage_c = "systemic", "已进入系统性 — §0.7 Role B", "🔴"
    elif lock_state in ("N/A", "vts_missing"):
        # lock_state detail already contains the probe-specific reason
        lock_detail = lock.get("state_label", "无法判定")
        stage, stage_l, stage_c = "N/A", f"{lock_detail} · 无法判定", "⚪"
    elif vts.get("structure","") in ("倒挂","倒挂·急性"):
        stage, stage_l, stage_c = "pre-systemic", "前端积聚·系统性前兆", "🟠"
    elif lock_state == "agree-front":
        stage, stage_l, stage_c = "front", "双探针前端一致·近端事件·非系统性", "🟡"
    elif lock_state == "divergent":
        # VTS hot but RCV calm → single-asset technical, no systemic resonance
        vts_front = vts.get("front_structure", "")
        if vts_front in ("前端急性", "前端紧张"):
            stage, stage_l, stage_c = "divergent", f"单资产技术性·{vts_front}·无双探针共振", "🟡"
        else:
            stage, stage_l, stage_c = "divergent", "单资产技术性·无双探针共振", "🟡"
    else:
        stage, stage_l, stage_c = "calm", "无双探针共振·前端事件未扩散", "🟢"

    # Verdict — systemic-risk dimension; 仓位归 §0.6 瀑布管
    verdicts = {
        "systemic": "系统已进入系统性风险阶段。VTS倒挂+RCV长端/全曲线→Role B确认触发。激进降风险。",
        "pre-systemic": "前端压力积聚，未进系统性。等RCV翻long-led或acute-broad叠VTS倒挂→升档。",
        "front": "双探针前端一致·近端事件非系统性。等CPI/Fed落地看前端是fade还是扩散。要盯的翻转点：RCV→long-led/acute-broad叠VTS倒挂→agree-systemic。",
        "divergent": "VTS热·RCV平→单资产技术性。无双探针共振，不触发额外系统性仓位动作。",
        "calm": "双端平静·无双探针共振。系统性风险维度=低，不触发额外动作。",
    }

    lines = []
    lines.append(f"# 🛡️ 前端风险 → 系统性风险 演化看板\n")
    lines.append(f"> **{run_date}** | Regime: **{reg}** | P={pos['Primary']}% / H={pos['Hedge']}% / C={pos['Cash']}% | 跨域信号={cross} | 🔴={red_n}\n")

    # ① Near-term event risk
    lines.append("---\n## ① 近端事件风险\n")
    evt = []; nxt = ""
    if vts.get("front_structure") in ("前端急性","前端紧张"): evt.append(f"VIX9D/VIX={vix9d_r_str} **{vts['front_structure']}**")
    elif vix9d_r: evt.append(f"VIX9D/VIX={vix9d_r_str} 前端平静")
    vix_d5 = vix_leg.get("delta_5d")
    if vix_d5 is not None: evt.append(f"VIX={vix_leg['value']:.1f} 5dΔ{vix_d5:+.1f}")
    lines.append(f"| 维度 | 信号 |")
    lines.append(f"|------|------|")
    if lock_state == "agree-front": nxt = "**非系统性**·近端事件"
    elif lock_state == "agree-systemic": nxt = "**⚠️ 系统性**·双端确认"
    elif lock_state == "divergent": nxt = "单资产技术性·CASC守卫"
    elif lock_state == "vts_missing": nxt = "平静（单探针·VTS缺数据）"
    elif lock_state == "N/A": nxt = "平静（数据不足）"
    else: nxt = "平静"
    lines.append(f"| 事件窗 | {' | '.join(evt) if evt else '无近端事件'} |")
    lines.append(f"| 风险性质 | {nxt} |")

    sig = []
    if vix_leg.get("mutated"): sig.append("VIX突变✅")
    if move_leg.get("mutated"): sig.append("MOVE突变✅")
    if casc.get("legs",{}).get("HY OAS 20dΔ",{}).get("confirmed"): sig.append("信用确认✅")
    if casc.get("legs",{}).get("FX",{}).get("mutated"): sig.append("FX突变✅")
    lines.append(f"| 市场信号 | {'·'.join(sig) if sig else '无跨资产确认'} |")
    rp_gap_str = f"{rp_gap:.1f}" if rp_gap is not None else "N/A"
    lines.append(f"| 利率路径 | US02Y−IORB={rp_gap_str}bp {rp_label}{' 5dΔ'+str(rp_5d)+'bp' if rp_5d else ''} |\n")

    # ② First-layer transmission
    lines.append("---\n## ② 第一层传导\n")
    lines.append(f"| 端 | 指标 | 当前值 | 灯 | DUR5 | 状态 |")
    lines.append(f"|----|------|--------|------|------|------|")
    dfii_pct = c_dfii.get("value_pct")
    dfii_str = f"{dfii_pct:.2f}%" if dfii_pct is not None else "N/A"
    lines.append(f"| C 长端利率 | DFII10 | {dfii_str} | {c.get('light','N/A')} | {dur5_d}/5 {'✅' if dur5_d>=5 else ''} | 贴现率压力 |")
    # C_RealYield_Nowcast row (if available)
    if nowcast and nowcast.get("real_yield_nowcast") is not None:
        nc_ryn = nowcast["real_yield_nowcast"]
        nc_lvl = nowcast.get("nowcast_level_light", "N/A")
        nc_dir = nowcast.get("nowcast_direction", "N/A")
        nc_label = nowcast.get("nowcast_level_label", "")
        lines.append(f"| C Nowcast | Real Yield Nowcast | {nc_ryn:.2f}% | {nc_lvl} | — | 官方DFII10滞后修正・{nc_label} 方向：{nc_dir} |")
    lines.append(f"| A 资金管道 | EFFR-IORB | {effr_v}bp | {effr_l} | {dur5_e}/5 {'✅' if dur5_e>=5 else ''} | 资金管道偏紧 |")
    a_sofr = a["details"].get("SOFR-IORB",{})
    sofr_v = a_sofr.get("value_bp",0) or 0
    lines.append(f"| A 拆借 | SOFR-IORB | {sofr_v}bp | {a_sofr.get('light','N/A')} | — | 拆借市场 |\n")

    # ③ Systemic triggers
    lines.append("---\n## ③ 系统性风险触发器\n")
    b_light = b.get("light","N/A")
    t_a = "🟢"; t_b = "🟢"; t_c = "🟢"
    if b_light in ("🟡","🟠","🔴"): t_a = b_light
    if effr_l in ("🟠","🔴") and dur5_e>=5: t_b = "🟠"
    if casc_conf >= 3: t_c = "🔴"
    elif casc_conf >= 2: t_c = "🟠"
    if vts.get("structure","") in ("倒挂","倒挂·急性"): t_c = "🔴"
    if lock_state == "agree-systemic": t_c = "🔴"

    # T1/T2/T3 = 触发器序号，非 ABCD 端。条件中触发端名保留框架定义
    lines.append(f"| 触发器 | 条件 | 当前状态 |")
    lines.append(f"|--------|------|---------|")
    lines.append(f"| **T1 信用(B端)** | HY/IG OAS走阔脱离自满 | {t_a} {'已触发' if t_a in ('🟠','🔴') else '未触发'} (HY/IG ⚠️自满) |")
    # T2: 🟠=条件已满足(不是预警) → 已触发·部分压力
    t_b_txt = f"{t_b} {'已触发·部分压力' if t_b=='🟠' else '已触发' if t_b=='🔴' else '未触发'}"
    lines.append(f"| **T2 流动性(A端)** | EFFR-IORB 🟠/🔴+DUR5≥5 | {t_b_txt} (EFFR-IORB={effr_v}bp DUR5={dur5_e}/5) |")
    t_c_txt = f"{t_c} {'已触发' if t_c=='🔴' else '需关注' if t_c=='🟠' else '未触发'}"
    vts_display = vts.get('structure','N/A')
    vts_missing_note = "⚠️缺数据" if vts_display == "N/A" else ""
    lines.append(f"| **T3 跨资产/跨境** | CASC≥2+VTS+RCV互锁 | {t_c_txt} (CASC{casc_conf}/4·VTS={vts_display}{vts_missing_note}·互锁={lock_state}) |\n")

    # ④ Final judgment
    lines.append("---\n## ④ 系统性风险阶段与最终判断\n")
    lines.append(f"| 项目 | 状态 |")
    lines.append(f"|------|------|")
    lines.append(f"| 当前阶段 | {stage_c} **{stage_l}** |")
    lines.append(f"| Regime | **{reg}**({reg_key}) · 跨域={cross} · 🔴={red_n} |")
    lines.append(f"| 仓位 | P={pos['Primary']}% / H={pos['Hedge']}% / C={pos['Cash']}% |")
    lines.append(f"| VTS | {vts.get('structure','N/A')} · 前端={vts.get('front_structure','N/A')} |")
    rcv_ratio = rcv.get('ratio_2y_30y')
    rcv_zratio = rcv.get('z_ratio')
    rcv_extra = ""
    if rcv_ratio is not None:
        rcv_extra = f" · 2y/30y={rcv_ratio:.3f}"
        if rcv_zratio is not None:
            rcv_note = ""
            if rcv.get('tilt') == 'N/A' and abs(rcv_zratio) > 1.0:
                rcv_note = " (形态偏离但vol不高·不触发tilt)"
            rcv_extra += f" z={rcv_zratio:.1f}{rcv_note}"
    lines.append(f"| RCV | {rcv.get('character','N/A')} · sev={rcv.get('severity','N/A')} · tilt={rcv.get('tilt','N/A')}{rcv_extra} |")
    lines.append(f"| 互锁 | {lock_state} — {lock.get('state_label','N/A')} |")
    lines.append(f"| C端 | {casc_label} |")
    # C_RealYield_Nowcast insight line
    if nowcast and nowcast.get("real_yield_nowcast") is not None:
        nc_level = nowcast.get("nowcast_level_label", "")
        nc_dir = nowcast.get("nowcast_direction", "N/A")
        nc_dfii = nowcast.get("dfii10_official")
        nc_warming = nowcast.get("nowcast_delta_1d_warming", False)
        nc_d_meaningful = not nc_warming and nc_dir != "N/A"
        if nc_d_meaningful and nc_dfii is not None and nc_dfii >= 2.00 and nc_dir in ("明显回落", "小幅回落"):
            lines.append(f"| C Nowcast | 官方{nowcast['nowcast_level_light']}红灯·Nowcast边际回落 → 估值压力边际缓和 |")
        elif nc_d_meaningful and nc_dir in ("明显上行", "小幅上行"):
            lines.append(f"| C Nowcast | 官方确认与Nowcast同步走高·{nc_level} → 估值压力继续强化 |")
        elif nc_warming:
            lines.append(f"| C Nowcast | {nowcast['nowcast_level_light']} {nc_level} · 方向数据累积中(<5d历史) |")
        else:
            lines.append(f"| C Nowcast | {nowcast['nowcast_level_light']} {nc_level} · 方向{nc_dir} |")
    lines.append(f"\n> **最终判断**：{verdicts.get(stage,'')}\n")

    lines.append(f"---\n*ABCD v3.5.1 风险演化看板 | {run_date} | FRED+Yahoo*")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# PNG Dashboard
# ═══════════════════════════════════════════════════════════════════════════
def generate_png(data_date, run_date, abcd, pos, casc, vts, rcv, lock, rate_path, out_path):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties

    for f in ["Microsoft YaHei","SimHei","WenQuanYi Micro Hei","Noto Sans CJK SC","sans-serif"]:
        try: FontProperties(family=f); plt.rcParams["font.family"] = f; break
        except: continue
    plt.rcParams["axes.unicode_minus"] = False

    a,b,c,d = abcd["A"],abcd["B"],abcd["C"],abcd["D"]
    cross, red_n = abcd["cross_domain_count"], abcd["red_domain_count"]
    reg, reg_key = pos["label"], pos["regime_key"]
    a_effr = a["details"].get("EFFR-IORB",{})
    effr_v, effr_l, dur5_e = a_effr.get("value_bp",0) or 0, a_effr.get("light","N/A"), a_effr.get("dur5",0)
    c_dfii = c["details"].get("DFII10",{})
    dur5_d = c_dfii.get("dur5",0)
    vix_leg = casc["legs"]["VIX"]
    move_leg = casc["legs"]["MOVE"]
    casc_conf, casc_label = casc["confirmation_count"], casc.get("c_label","—")
    lock_state = lock.get("state","N/A")
    vix_val = vix_leg.get("value",0) or 0
    move_val = move_leg.get("value",0) or 0
    rp_gap = rate_path.get("gap_bp")
    rp_gap_str = f"{rp_gap:.1f}" if rp_gap is not None else "N/A"
    b_light = b.get("light","N/A")

    # Stage
    if lock_state == "agree-systemic": stage_s, stage_t = "#DC143C","[!] SYSTEMIC  |  Role B Triggered"
    elif vts.get("structure","") in ("倒挂","倒挂·急性"): stage_s, stage_t = "#FF8C00","PRE-SYSTEMIC · VTS Inverted"
    elif lock_state == "agree-front": stage_s, stage_t = "#FFD700","FRONT-EVENT · Non-Systemic"
    elif lock_state == "divergent": stage_s, stage_t = "#FFD700","DIVERGENT · Single-Asset Technical"
    elif lock_state in ("N/A", "vts_missing"): stage_s, stage_t = "#6E7681","N/A · DATA MISSING"
    else: stage_s, stage_t = "#2E8B57","CALM · No Probe Resonance"

    fig = plt.figure(figsize=(10.55, 14.91), dpi=120, facecolor="#0D1117")
    gs = fig.add_gridspec(5,1,height_ratios=[0.6,0.9,1.0,1.2,1.3],hspace=0.32,top=0.97,bottom=0.03,left=0.06,right=0.94)
    tc_dark, tc_mid, tc_dim = "#C9D1D9", "#8B949E", "#484F58"
    blue = "#58A6FF"
    def box(ax,x,y,w,h,fc,ec,alpha=0.12): ax.add_patch(plt.Rectangle((x,y),w,h,facecolor=fc,alpha=alpha,edgecolor=ec,linewidth=1.5))
    def txt(ax,x,y,s,sz=10,c=tc_dark,b=False,ha="left"): ax.text(x,y,s,fontsize=sz,color=c,fontweight="bold" if b else "normal",ha=ha)
    def pad(): return 0.25

    # 0: Header
    ax0 = fig.add_subplot(gs[0],facecolor="#161B22"); ax0.set_xlim(0,10); ax0.set_ylim(0,6); ax0.axis("off")
    txt(ax0,0.3,5.2,f"FRONT-RISK → SYSTEMIC-RISK EVOLUTION DASHBOARD",14,blue,True)
    txt(ax0,0.3,3.8,f"{run_date}  |  Regime: {reg} ({reg_key})  |  P={pos['Primary']}% / H={pos['Hedge']}% / C={pos['Cash']}%  |  Cross={cross}  |  RED={red_n}",10.5,tc_dim)
    txt(ax0,0.3,2.5,f"Data: FRED(T-0) + Yahoo(T-1)  |  CASC v3.5 + VTS x RCV Interlock",9,tc_dim)
    ax0.add_patch(plt.Rectangle((0.3,0.2),9.4,0.06,facecolor="#FF8C00",alpha=0.4))

    # ① Event Risk
    ax1 = fig.add_subplot(gs[1],facecolor="#161B22"); ax1.set_xlim(0,10); ax1.set_ylim(0,9); ax1.axis("off")
    txt(ax1,0.3,8.3,"① NEAR-TERM EVENT RISK",13,blue,True)
    front_s = vts.get("front_structure","N/A"); vix9d = vts.get("ratio_vix9d_vix"); vts_r_raw = vts.get("ratio_vix_vix3m")
    vts_r_str = f"{vts_r_raw:.3f}" if vts_r_raw is not None else "N/A"
    vix9d_str = f"{vix9d:.3f}" if vix9d is not None else "N/A"
    txt(ax1,0.3,7.0,f"Event: VIX9D/VIX={vix9d_str} * {front_s}  |  VIX={vix_val:.1f}(5dD{vix_leg.get('delta_5d',0):+.1f})  |  MOVE={move_val:.0f}  |  Rate: US02Y-IORB={rp_gap_str}bp",9.5,tc_mid)
    # CASC confirmation badgelist
    mks=[]
    if vix_leg.get("mutated"): mks.append("VIX")
    if move_leg.get("mutated"): mks.append("MOVE")
    if casc.get("legs",{}).get("HY OAS 20dΔ",{}).get("confirmed"): mks.append("HY")
    if casc.get("legs",{}).get("FX",{}).get("mutated"): mks.append("FX")
    txt(ax1,0.3,5.8,f"CASC confirmation: {casc_conf}/4 {'+'.join(mks) if mks else '- none -'}",9.5,tc_mid)

    lock_badge = {"agree-systemic":"#DC143C","agree-front":"#FF8C00","divergent":"#6E7681","calm":"#2E8B57"}.get(lock_state,"#6E7681")
    box(ax1,0.3,3.2,9.4,1.8,lock_badge,lock_badge)
    txt(ax1,0.6,4.4,f"RISK CHARACTER: {lock.get('state_label',lock_state)}",12,lock_badge,True)
    nature_m = {"agree-front":"Non-systemic front-event · Await CPI/Fed to confirm fade or spread",
                "agree-systemic":"[!] SYSTEMIC  |  VTS+RCV dual-probe confirmed  |  Role B triggered",
                "divergent":"Single-asset technical · CASC gate active",
                "calm":"Low risk · Dual-probe calm"}
    txt(ax1,0.6,3.7,nature_m.get(lock_state,""),9,tc_dim)

    # ② Transmission
    ax2 = fig.add_subplot(gs[2],facecolor="#161B22"); ax2.set_xlim(0,10); ax2.set_ylim(0,10); ax2.axis("off")
    txt(ax2,0.3,9.3,"② FIRST-LAYER TRANSMISSION",13,blue,True)
    c_lc = {"🔴":"#DC143C","🟠":"#FF8C00","🟡":"#FFD700","🟢":"#2E8B57","⚠️":"#FFD700"}.get(c.get("light",""),"#6E7681")
    a_lc = {"🔴":"#DC143C","🟠":"#FF8C00","🟡":"#FFD700","🟢":"#2E8B57"}.get(a.get("light",""),"#6E7681")
    box(ax2,0.3,5.3,4.3,3.5,c_lc,c_lc); box(ax2,5.2,5.3,4.3,3.5,a_lc,a_lc)
    txt(ax2,0.6,8.1,"C: LONG RATE",11,c_lc,True)
    c_td_label = {"🔴":"RED","🟠":"ORANGE","🟡":"YELLOW","🟢":"GREEN","⚠️":"COMPLACENT"}.get(c.get("light",""),c.get("light",""))
    a_td_label = {"🔴":"RED","🟠":"ORANGE","🟡":"YELLOW","🟢":"GREEN"}.get(a.get("light",""),a.get("light",""))
    txt(ax2,0.6,7.3,f"DFII10  TD={c_td_label}  DUR5={dur5_d}/5",10,tc_dark)
    txt(ax2,0.6,6.5,f"DUR5={'CONFIRMED OK' if dur5_d>=5 else f'{dur5_d}/5'}  *  Discount rate pressure",9,tc_dim)
    txt(ax2,0.6,5.8,f"{casc_label}" if casc_label else "—",8.5,tc_dim)
    txt(ax2,5.5,8.1,"A: LIQUIDITY PIPE",11,a_lc,True)
    txt(ax2,5.5,7.3,f"EFFR-IORB={effr_v}bp  TD={a_td_label}  DUR5={dur5_e}/5",10,tc_dark)
    txt(ax2,5.5,6.5,f"DUR5={'CONFIRMED OK' if dur5_e>=5 else f'{dur5_e}/5'}  *  Micro-liquidity strained",9,tc_dim)
    txt(ax2,5.5,5.8,f"SOFR-IORB={a.get('details',{}).get('SOFR-IORB',{}).get('value_bp','N/A')}bp",8.5,tc_dim)
    ax2.annotate("",xy=(5.0,7.0),xytext=(4.5,7.0),arrowprops=dict(arrowstyle="->",color="#FF8C00",lw=2.5))
    txt(ax2,4.2,7.3,"C->A",9,"#FF8C00",ha="center")

    # ③ Triggers
    ax3 = fig.add_subplot(gs[3],facecolor="#161B22"); ax3.set_xlim(0,10); ax3.set_ylim(0,12); ax3.axis("off")
    txt(ax3,0.3,11.3,"③ SYSTEMIC RISK TRIGGERS",13,blue,True)

    t_a_c = "#DC143C" if b_light in ("🟠","🔴") else "#FF8C00" if b_light=="🟡" else "#2E8B57"
    t_b_c = "#DC143C" if (effr_l in ("🟠","🔴") and dur5_e>=5) else "#FF8C00" if effr_l=="🟠" else "#2E8B57"
    t_c_c = "#DC143C" if lock_state=="agree-systemic" else "#FF8C00" if casc_conf>=2 else "#2E8B57"

    box(ax3,0.3,7.0,3.0,3.5,t_a_c,t_a_c); box(ax3,3.6,7.0,3.0,3.5,t_b_c,t_b_c); box(ax3,6.9,7.0,3.0,3.5,t_c_c,t_c_c)
    for i,(lb,lc,cv,detail) in enumerate([
        ("T1: CREDIT (B)",t_a_c, "NOT TRIGGERED" if t_a_c=="#2E8B57" else "PARTIAL" if t_a_c=="#FF8C00" else "TRIGGERED", "HY/IG OAS complacent"),
        ("T2: LIQUIDITY (A)",t_b_c, "PARTIAL" if t_b_c=="#FF8C00" else "TRIGGERED" if t_b_c=="#DC143C" else "NOT TRIGGERED", f"EFFR-IORB={effr_v}bp DUR5={dur5_e}/5"),
        ("T3: CROSS-ASSET (C)",t_c_c, "TRIGGERED" if t_c_c=="#DC143C" else "MONITOR" if t_c_c=="#FF8C00" else "NOT TRIGGERED", f"CASC{casc_conf}/4·VTS={vts.get('structure','N/A')}"),
    ]):
        x0 = 0.3 + i*3.3
        txt(ax3,x0+0.3,9.7,lb,10,lc,True); txt(ax3,x0+0.3,9.0,detail,9,tc_dim); txt(ax3,x0+0.3,7.5,cv,9,lc,True)

    # ④ Final
    ax4 = fig.add_subplot(gs[4],facecolor="#161B22"); ax4.set_xlim(0,10); ax4.set_ylim(0,13); ax4.axis("off")
    txt(ax4,0.3,12.3,"④ SYSTEMIC RISK STAGE & VERDICT",13,blue,True)

    # big stage badge
    box(ax4,0.3,9.5,9.4,2.5,stage_s,stage_s,0.18)
    txt(ax4,5.0,11.3,stage_t,14,stage_s,True,ha="center")

    # Key metrics grid
    y0 = 8.5
    metrics = [
        (f"Regime: {reg} ({reg_key})", f"Cross={cross} * RED={red_n}"),
        (f"Position: P={pos['Primary']}% / H={pos['Hedge']}% / C={pos['Cash']}%", f"Baseline: R2=55/25/20"),
        (f"VTS: {vts.get('structure','N/A')} · Front={vts.get('front_structure','N/A')}", f"VIX/VIX3M={vts_r_str}"),
        (f"RCV: {rcv.get('character','N/A')} · 2y/30y={rcv.get('ratio_2y_30y','N/A')}", f"sev={rcv.get('severity','N/A')} tilt={rcv.get('tilt','N/A')}"),
        (f"Interlock: {lock_state}", lock.get('state_label','N/A')),
        (f"C-end: {casc_label[:60]}", f"CASC {casc_conf}/4"),
    ]
    for i,(l,r) in enumerate(metrics):
        txt(ax4,0.6,y0-i*1.05,l,9.5,tc_dark); txt(ax4,6.0,y0-i*1.05,r,9,tc_dim)

    # Verdict — 统一入口 map_lock_to_verdict()，枚举全集覆盖，缺键高亮告警
    verdict_text = map_lock_to_verdict(lock_state, vts.get("structure",""))
    box(ax4,0.3,1.5,9.4,1.8,stage_s,stage_s,0.1)
    txt(ax4,0.6,2.8,f"VERDICT: {verdict_text}",10,tc_dark,True)

    # Footer
    txt(ax4,0.3,0.3,f"ABCD v3.5.1 Risk Evolution Dashboard · {run_date} · FRED + Yahoo",8,tc_dim)

    fig.savefig(out_path, dpi=120, facecolor="#0D1117", bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    print(f"[Dashboard PNG saved to {out_path}]")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Override run date (YYYY-MM-DD)")
    args = parser.parse_args()

    raw = load_data()
    from daily_report import _clamp_weekday, last_date, HY_OAS_ID
    data_date_raw = last_date(raw.get(HY_OAS_ID, [])) or date.today().isoformat()
    data_date = _clamp_weekday(date.fromisoformat(data_date_raw)).isoformat()
    run_date = args.date or date.today().isoformat()

    vintages = compute_vintages(raw)
    v35 = compute_v35_triggers(raw)
    abcd = compute_abcd_signals(raw)
    casc = compute_casc(raw, v35, abcd)
    abcd = apply_casc_gate(abcd, casc)
    pos = compute_position(abcd, v35, casc=casc)
    rate_path = compute_rate_path_proxy(raw)

    vts = casc.get("vts", compute_vts(raw))
    rcv = casc.get("rcv", compute_rcv(raw))
    lock = casc.get("vts_rcv_lock", compute_vts_rcv_interlock(vts, rcv))
    nowcast = compute_real_yield_nowcast(raw)

    # 1) Markdown
    md = format_dashboard_md(data_date, run_date, abcd, pos, v35, casc, vts, rcv, lock, rate_path, nowcast=nowcast)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORT_DIR / f"risk_dashboard_{run_date}.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"[Dashboard MD saved to {md_path}]")

    # 2) PNG
    png_path = REPORT_DIR / f"risk_dashboard_{run_date}.png"
    generate_png(data_date, run_date, abcd, pos, casc, vts, rcv, lock, rate_path, str(png_path))

    print("Done: risk dashboard generated (MD + PNG)")


if __name__ == "__main__":
    sys.exit(main())
