# -*- coding: utf-8 -*-
"""
generate_flowchart_png.py  — 白底风险演化流程图 PNG
=====================================================
输入：event_state JSON（由 extract_risk_events.py 产出）
输出：白底 4 层信号流程图 PNG

设计原则：
- 白底，结构化 4 层布局，非表格搬运
- 每层从 event_state 推理渲染，标注当前值 + 判定
- 层间箭头连接，颜色编码：橙=近端事件 / 黄=传导 / 红=系统
- 使用 matplotlib + 中文字体
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties

PROJECT_DIR = Path(__file__).resolve().parent.parent  # v3.5 root
REPORT_DIR = PROJECT_DIR / "report"
ARCHIVE_DIR = PROJECT_DIR / "daily_archive"

# ── 颜色方案 ──
C_ORANGE = "#f06a25"
C_ORANGE_LIGHT = "#fef0ea"
C_ORANGE_BORDER = "#fad4c4"
C_YELLOW = "#f8a81d"
C_YELLOW_LIGHT = "#fffaf0"
C_RED = "#da3832"
C_RED_LIGHT = "#fbecec"
C_GREEN = "#3ab54a"
C_GREEN_LIGHT = "#eaf6eb"
C_BLUE = "#2457a6"
C_BLUE_LIGHT = "#eaf1fa"
C_GRAY = "#888888"
C_BG = "#ffffff"
C_TEXT = "#222222"
C_TEXT_SUB = "#555555"
C_BORDER = "#e0e0e0"


def _get_chinese_font() -> FontProperties:
    """Find available Chinese font."""
    candidates = [
        "Microsoft YaHei", "SimHei", "PingFang SC",
        "Noto Sans CJK SC", "WenQuanYi Micro Hei", "STHeiti",
        "sans-serif",
    ]
    for name in candidates:
        try:
            fp = FontProperties(family=name)
            # Test if font is actually available
            fig, _ = plt.subplots(figsize=(1, 1))
            fig.text(0.5, 0.5, "测试", fontproperties=fp, fontsize=10)
            plt.close(fig)
            return fp
        except Exception:
            continue
    return FontProperties(family="sans-serif")


FONT = _get_chinese_font()
FONT_BOLD = FontProperties(family=FONT.get_family(), weight="bold", size=10)
FONT_TITLE = FontProperties(family=FONT.get_family(), weight="bold", size=13)
FONT_SECTION = FontProperties(family=FONT.get_family(), weight="bold", size=11)
FONT_SMALL = FontProperties(family=FONT.get_family(), size=9)
FONT_MEDIUM = FontProperties(family=FONT.get_family(), size=10)


def _color_for_intensity(intensity: str) -> str:
    return {"orange": C_ORANGE, "yellow_or_orange": C_YELLOW,
            "green": C_GREEN, "red": C_RED}.get(intensity, C_GRAY)


def _light_icon(active: bool, partial: bool = False) -> str:
    if active and not partial:
        return "[!] 已触发"
    elif active and partial:
        return "[~] 部分触发"
    return "[ ] 未触发"


def _box(ax, x, y, w, h, facecolor=C_BG, edgecolor=C_BORDER, linewidth=1.5,
         corner_radius=0.08, zorder=2):
    """Draw a rounded rectangle box."""
    from matplotlib.patches import FancyBboxPatch
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad={corner_radius}",
        facecolor=facecolor, edgecolor=edgecolor,
        linewidth=linewidth, zorder=zorder,
    )
    ax.add_patch(box)
    return box


def draw_flowchart(event_state: dict, output_path: Path):
    """主绘图函数。"""
    es = event_state.get("event_state", {})
    ts = event_state.get("transmission_state", {})
    tgs = event_state.get("trigger_state", {})
    sa = event_state.get("stage_assessment", {})

    evidence_es = es.get("evidence", {})
    evidence_ts = ts.get("evidence", {})
    evidence_sa = sa.get("evidence", {})
    regime = event_state.get("regime", "—")
    pos = event_state.get("positions", {})

    # ── Figure ──
    fig = plt.figure(figsize=(14, 20), facecolor=C_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 20)
    ax.axis("off")

    y = 18.8

    # ══════════════════════════════════════════════
    #  HEADER
    # ══════════════════════════════════════════════
    ax.text(7, y + 0.4, "前端风险 → 系统性风险 演化流程",
            fontproperties=FONT_TITLE, ha="center", va="center",
            fontsize=16, color="#111")
    y -= 0.5
    date_str = event_state.get("date", "—")
    p_str = f"{pos.get('primary', '—')}/{pos.get('hedge', '—')}/{pos.get('cash', '—')}"
    header_line = f"{date_str}  |  {regime}  |  P/H/C = {p_str}"
    ax.text(7, y, header_line,
            fontproperties=FONT_MEDIUM, ha="center", va="center",
            fontsize=10, color=C_TEXT_SUB)
    y -= 0.25
    # SSoT authority note — flowchart reads MD-derived event_state, not the authoritative SSoT JSON
    ax.text(7, y, "显示用 · 权威裁决以 Risk Dashboard (risk_os_state_machine SSoT) 为准",
            fontproperties=FONT_SMALL, ha="center", va="center",
            fontsize=7, color=C_GRAY)
    y -= 0.65

    # ══════════════════════════════════════════════
    #  LAYER 1: 近端事件风险
    # ══════════════════════════════════════════════
    intensity = es.get("front_risk_intensity", "unknown")
    l1_color = _color_for_intensity(intensity)
    _box(ax, 0.5, y - 4.5, 13, 4.8, edgecolor=l1_color, linewidth=2.5)

    # Section badge
    _box(ax, 0.7, y - 0.5, 2.2, 0.6, facecolor=l1_color, edgecolor=l1_color)
    ax.text(1.8, y - 0.2, "① 近端事件风险",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=11, color="white")

    near_label = es.get("front_risk_label", "评估中")
    ax.text(3.3, y - 0.2, f"当前状态：{near_label}",
            fontproperties=FONT_MEDIUM, ha="left", va="center",
            fontsize=10, color=C_TEXT)
    y -= 0.9

    # Left: event sources
    _box(ax, 0.7, y - 3.0, 6.2, 3.3, facecolor=C_ORANGE_LIGHT,
         edgecolor=C_ORANGE_BORDER, linewidth=1.2)
    ax.text(3.8, y - 0.4, "事件信号源",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=10, color=C_ORANGE)
    src_y = y - 0.85
    for src in es.get("event_sources", [])[:5]:
        ax.text(1.0, src_y, f"• {src}",
                fontproperties=FONT_SMALL, ha="left", va="center",
                fontsize=9, color=C_TEXT)
        src_y -= 0.45

    # Right: evidence box
    _box(ax, 7.1, y - 3.0, 6.2, 3.3, facecolor=C_RED_LIGHT,
         edgecolor="#f3c2c0", linewidth=1.2)
    ax.text(10.2, y - 0.4, "量化证据",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=10, color=C_RED)
    ev_y = y - 0.85
    vix = evidence_es.get("vix", "—")
    ratio = evidence_es.get("vix9d_vix_ratio")
    dgs2 = evidence_es.get("dgs2_iorb_bp")
    items = []
    if ratio is not None:
        items.append(f"VIX9D/VIX = {ratio}")
    if vix != "—":
        items.append(f"VIX = {vix}")
    if dgs2 is not None:
        items.append(f"DGS2−IORB = {dgs2}bp")
    items.append(f"跨资产确认 = {evidence_es.get('cross_asset_confirm', 0)}/4")
    for item in items:
        ax.text(7.4, ev_y, f"• {item}",
                fontproperties=FONT_SMALL, ha="left", va="center",
                fontsize=9, color=C_TEXT)
        ev_y -= 0.45

    # Bottom tag
    event_type = es.get("near_event_type", "unknown")
    type_label = {"rate_event": "利率事件", "near_term_event": "近端事件",
                  "soft_landing_event": "软着陆事件", "systemic_event": "系统性事件"}.get(event_type, event_type)
    sys_confirm = "非系统性" if not es.get("systemic_confirmed", False) else "已扩散至系统性"
    tag_text = f"性质：{type_label} · {sys_confirm}"
    _box(ax, 3.5, y - 3.55, 7, 0.45, facecolor=l1_color, edgecolor=l1_color)
    ax.text(7, y - 3.32, tag_text,
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=9, color="white")
    y -= 4.5

    # ══════════════════════════════════════════════
    #  ARROW 1→2
    # ══════════════════════════════════════════════
    arrow_y = y - 0.15
    ax.annotate("", xy=(7, arrow_y - 0.6), xytext=(7, arrow_y),
                arrowprops=dict(arrowstyle="->", color=C_ORANGE, lw=3))
    ax.text(7, arrow_y - 0.1, "▼ 第一层传导",
            fontproperties=FONT_SMALL, ha="center", va="center",
            fontsize=9, color=C_ORANGE)
    y -= 1.0

    # ══════════════════════════════════════════════
    #  LAYER 2: 第一层传导
    # ══════════════════════════════════════════════
    _box(ax, 0.5, y - 3.2, 13, 3.6, edgecolor=C_YELLOW, linewidth=2.5)
    _box(ax, 0.7, y - 0.5, 2.6, 0.6, facecolor=C_YELLOW, edgecolor=C_YELLOW)
    ax.text(2.0, y - 0.2, "② 第一层传导",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=11, color="white")

    main_path = ts.get("main_path", "")
    ax.text(6.0, y - 0.2, f"主路径：{main_path}",
            fontproperties=FONT_MEDIUM, ha="left", va="center",
            fontsize=10, color=C_TEXT)
    y -= 0.9

    # C端 box
    dfii10 = evidence_ts.get("dfii10_pct")
    ryn = evidence_ts.get("real_yield_nowcast")
    c_active = ts.get("real_yield_pressure", False)
    c_box_color = C_RED_LIGHT if c_active else C_GREEN_LIGHT
    c_border = C_RED if c_active else C_GREEN
    _box(ax, 0.7, y - 2.1, 6.2, 2.5, facecolor=c_box_color, edgecolor=c_border, linewidth=1.5)
    c_label = "[!] 实际利率高压" if c_active else "[ ] 实际利率正常"
    ax.text(3.8, y - 0.4, f"C 端：长端利率定价  {c_label}",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=10, color=c_border)
    c_lines = []
    if dfii10 is not None:
        c_lines.append(f"DFII10 = {dfii10}%")
    if ryn is not None:
        c_lines.append(f"Real Yield Nowcast = {ryn}%")
    c_lines.append(f"估值压缩 = {'是' if ts.get('valuation_compression_active') else '否'}")
    cy = y - 0.85
    for cl in c_lines:
        ax.text(1.0, cy, f"• {cl}", fontproperties=FONT_SMALL, ha="left", va="center",
                fontsize=9, color=C_TEXT)
        cy -= 0.5

    # A端 box
    effr = evidence_ts.get("effr_iorb_bp")
    sofr = evidence_ts.get("sofr_iorb_bp")
    a_active = ts.get("liquidity_buffer_thinning", False)
    a_box_color = C_ORANGE_LIGHT if a_active else C_GREEN_LIGHT
    a_border = C_ORANGE if a_active else C_GREEN
    _box(ax, 7.1, y - 2.1, 6.2, 2.5, facecolor=a_box_color, edgecolor=a_border, linewidth=1.5)
    a_label = "[!] 资金管道偏紧" if a_active else "[ ] 资金管道正常"
    ax.text(10.2, y - 0.4, f"A 端：美元资金管道  {a_label}",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=10, color=a_border)
    a_lines = []
    if effr is not None:
        a_lines.append(f"EFFR−IORB = {effr}bp")
    if sofr is not None:
        a_lines.append(f"SOFR−IORB = {sofr}bp")
    ay = y - 0.85
    for al in a_lines:
        ax.text(7.4, ay, f"• {al}", fontproperties=FONT_SMALL, ha="left", va="center",
                fontsize=9, color=C_TEXT)
        ay -= 0.5

    # Summary
    summary = ts.get("summary", "")
    if summary:
        _box(ax, 2.0, y - 2.65, 10, 0.45, facecolor=C_YELLOW_LIGHT, edgecolor=C_YELLOW)
        ax.text(7, y - 2.42, summary,
                fontproperties=FONT_SMALL, ha="center", va="center",
                fontsize=9, color="#886514")
    y -= 3.2

    # ══════════════════════════════════════════════
    #  ARROW 2→3
    # ══════════════════════════════════════════════
    arrow_y2 = y - 0.15
    ax.annotate("", xy=(7, arrow_y2 - 0.6), xytext=(7, arrow_y2),
                arrowprops=dict(arrowstyle="->", color=C_YELLOW, lw=3))
    ax.text(7, arrow_y2 - 0.1, "▼ 三重触发器判定",
            fontproperties=FONT_SMALL, ha="center", va="center",
            fontsize=9, color=C_YELLOW)
    y -= 1.0

    # ══════════════════════════════════════════════
    #  LAYER 3: 系统性风险触发器
    # ══════════════════════════════════════════════
    _box(ax, 0.5, y - 3.8, 13, 4.2, edgecolor="#d68700", linewidth=2.5)
    _box(ax, 0.7, y - 0.5, 3.2, 0.6, facecolor="#d68700", edgecolor="#d68700")
    ax.text(2.3, y - 0.2, "③ 系统性风险触发器",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=11, color="white")

    triggered_count = sum([
        tgs["credit_trigger"]["active"],
        tgs["liquidity_trigger"]["active"],
        tgs["cross_asset_trigger"]["active"],
    ])
    ax.text(7.5, y - 0.2, f"触发进度：{triggered_count}/3",
            fontproperties=FONT_MEDIUM, ha="left", va="center",
            fontsize=10, color=C_TEXT)
    y -= 0.9

    # Three trigger boxes
    triggers = [
        ("T1 信用(B端)", tgs.get("credit_trigger", {}),
         ["HY OAS > 300bp", "IG OAS > 85bp", "信用利差脱离自满"],
         C_RED),
        ("T2 流动性(A端)", tgs.get("liquidity_trigger", {}),
         ["EFFR−IORB 继续上行", "SOFR−IORB → 0bp", "A端从偏紧→压力"],
         C_ORANGE),
        ("T3 跨资产/跨境", tgs.get("cross_asset_trigger", {}),
         ["FXY 5d > +2.5%", "CASC ≥ 2/4", "风险扩散至多资产"],
         C_BLUE),
    ]

    for i, (t_name, t_data, t_conditions, t_color) in enumerate(triggers):
        tx = 0.7 + i * 4.2
        t_active = t_data.get("active", False)
        t_box_color = "#fbecec" if t_active else "#f6f6f6"
        t_border = t_color if t_active else C_BORDER
        _box(ax, tx, y - 2.7, 3.9, 3.1, facecolor=t_box_color, edgecolor=t_border, linewidth=1.5)

        status_text = _light_icon(t_active, t_data.get("partial", False))
        ax.text(tx + 1.95, y - 0.4, f"{t_name}",
                fontproperties=FONT_BOLD, ha="center", va="center",
                fontsize=10, color=t_color)
        ax.text(tx + 1.95, y - 0.8, status_text,
                fontproperties=FONT_BOLD, ha="center", va="center",
                fontsize=9, color=t_color if t_active else C_GRAY)

        cy2 = y - 1.3
        for cond in t_conditions:
            ax.text(tx + 0.3, cy2, f"• {cond}",
                    fontproperties=FONT_SMALL, ha="left", va="center",
                    fontsize=8, color=C_TEXT_SUB)
            cy2 -= 0.45

    y -= 3.75

    # ══════════════════════════════════════════════
    #  ARROW 3→4
    # ══════════════════════════════════════════════
    arrow_y3 = y - 0.15
    ax.annotate("", xy=(7, arrow_y3 - 0.6), xytext=(7, arrow_y3),
                arrowprops=dict(arrowstyle="->", color=C_RED, lw=3))
    ax.text(7, arrow_y3 - 0.1, "▼ 阶段判定",
            fontproperties=FONT_SMALL, ha="center", va="center",
            fontsize=9, color=C_RED)
    y -= 1.0

    # ══════════════════════════════════════════════
    #  LAYER 4: 系统性风险阶段与最终判断
    # ══════════════════════════════════════════════
    sys_triggered = tgs.get("all_triggered", False)
    l4_edge = C_RED if sys_triggered else "#da3832"
    _box(ax, 0.5, y - 4.0, 13, 4.4, edgecolor=l4_edge, linewidth=2.5)

    _box(ax, 0.7, y - 0.5, 3.2, 0.6, facecolor=C_RED, edgecolor=C_RED)
    stage_label = "④ 系统性风险阶段" if sys_triggered else "④ 当前阶段判定"
    ax.text(2.3, y - 0.2, stage_label,
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=11, color="white")

    current_stage = sa.get("current_stage", "—")
    not_yet = sa.get("not_yet_stage", "")
    ax.text(7, y - 0.2, f"当前：{current_stage} {'| 尚未进入：' + not_yet if not_yet else ''}",
            fontproperties=FONT_MEDIUM, ha="center", va="center",
            fontsize=10, color=C_RED)
    y -= 0.9

    # Left: VTS / RCV / Interlock
    _box(ax, 0.7, y - 2.8, 6.2, 3.2, facecolor=C_BLUE_LIGHT, edgecolor=C_BLUE, linewidth=1.5)
    ax.text(3.8, y - 0.4, "双探针信号",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=10, color=C_BLUE)
    probe_y = y - 0.85
    for key, label in [("vts_regime", "VTS"), ("rcv_tilt", "RCV tilt"),
                        ("rcv_sev", "RCV severity"), ("interlock", "互锁")]:
        val = evidence_sa.get(key, "—")
        ax.text(1.0, probe_y, f"• {label} = {val}",
                fontproperties=FONT_SMALL, ha="left", va="center",
                fontsize=9, color=C_TEXT)
        probe_y -= 0.45

    # Right: Final judgement
    _box(ax, 7.1, y - 2.8, 6.2, 3.2, facecolor="#fff9f6", edgecolor=C_RED, linewidth=1.5)
    ax.text(10.2, y - 0.4, "最终判断",
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=10, color=C_RED)
    judgement = sa.get("final_judgement", "—")
    # Text wrap
    import textwrap
    wrapped = textwrap.fill(judgement, width=24)
    lines = wrapped.split("\n")[:4]
    fj_y = y - 0.85
    for line in lines:
        ax.text(7.4, fj_y, line,
                fontproperties=FONT_SMALL, ha="left", va="center",
                fontsize=9, color=C_TEXT)
        fj_y -= 0.45

    # ── 底部横幅 ──
    _box(ax, 0.5, 0.3, 13, 0.7, facecolor=C_BLUE, edgecolor=C_BLUE)
    if sys_triggered:
        banner = "⚠ 当前已进入系统性风险阶段 —— 需高度关注 B/A/D 端同步恶化信号"
    else:
        banner = f">> 当前处于 {regime} · 非危机模式 · 等待触发器进一步演化"
    ax.text(7, 0.65, banner,
            fontproperties=FONT_BOLD, ha="center", va="center",
            fontsize=10, color="white")

    # ── Footer ──
    ax.text(7, 0.15, f"ABCD v3.5 风险演化看板 · {event_state.get('date', '—')} · FRED + Yahoo Finance",
            fontproperties=FONT_SMALL, ha="center", va="center",
            fontsize=8, color=C_GRAY)

    # ── Save ──
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight",
                facecolor=C_BG, edgecolor="none", pad_inches=0.3)
    plt.close(fig)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate white-background risk flowchart PNG")
    parser.add_argument("--date", help="Date YYYY-MM-DD, default today")
    parser.add_argument("--input", "-i", help="Event state JSON path (default: auto-find)")
    parser.add_argument("--output", "-o", help="Output PNG path")
    args = parser.parse_args()

    run_date = args.date or date.today().isoformat()

    if args.input:
        json_path = Path(args.input)
    else:
        json_path = REPORT_DIR / f"event_state_{run_date}.json"

    if not json_path.exists():
        print(f"[ERROR] Event state not found: {json_path}", file=sys.stderr)
        print("  Run extract_risk_events.py first.", file=sys.stderr)
        sys.exit(1)

    event_state = json.loads(json_path.read_text(encoding="utf-8"))

    if args.output:
        out_path = Path(args.output)
    else:
        month = run_date[:7]
        out_dir = ARCHIVE_DIR / month
        out_path = out_dir / f"risk_flowchart_{run_date}.png"

    result = draw_flowchart(event_state, out_path)
    print(f"[OK] Flowchart PNG → {result}  ({result.stat().st_size / 1024:.0f} KB)")

    return result


if __name__ == "__main__":
    main()
