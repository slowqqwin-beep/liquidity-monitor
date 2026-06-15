# -*- coding: utf-8 -*-
"""
generate_risk_flowchart.py  (v4 — HTML 精修版)
=================================================
从 daily_{date}.md 提取 ABCD 四端框架 + 仓位动作 + 信号快照，
生成「前端风险 → 系统性风险演化流程图」HTML。
输出: daily_archive/{YYYY-MM}/risk_flowchart_{date}.html

v4 升级：新版 CSS 配色体系 · clip-path 箭头 · badge/check-list · 底部动态横幅
"""

import argparse
import io
import re
import sys
from datetime import date
from pathlib import Path

import markdown
import pandas as pd
from bs4 import BeautifulSoup

REPORT_DIR  = Path(__file__).resolve().parent.parent / "liquidity-dashboard" / "report"
ARCHIVE_DIR = Path(__file__).resolve().parent / "daily_archive"

# ── CSS (self-contained, v4 精修版) ──
CSS = """
:root {
    --text-main: #222;  --text-sub: #555;  --bg-page: #f4f6f9;
    --c-orange: #f06a25;  --c-orange-light: #fef0ea;  --c-orange-border: #fad4c4;
    --c-yellow: #f8a81d;  --c-yellow-light: #fffaf0;  --c-yellow-border: #fce1ad;
    --c-red: #da3832;  --c-red-light: #fbecec;  --c-red-border: #f3c2c0;
    --c-blue: #2457a6;  --c-blue-light: #eaf1fa;  --c-green: #3ab54a;  --c-green-light: #eaf6eb;
}
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
    background-color: var(--bg-page); color: var(--text-main); margin: 0; padding: 40px 20px; display: flex; justify-content: center;
}
.container { width: 100%; max-width: 960px; background: #fff; padding: 40px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); }
.header { text-align: center; margin-bottom: 30px; }
.header h1 { font-size: 32px; font-weight: 800; color: #111; margin: 0 0 12px 0; letter-spacing: 1px; }
.header p { font-size: 15px; color: var(--text-sub); margin: 0; font-weight: 500; }
.section { border-radius: 10px; padding: 24px; margin-bottom: 0; position: relative; background: #fff; }
.section-title { display: flex; align-items: center; font-size: 20px; font-weight: 800; margin-bottom: 20px; letter-spacing: .5px; }
.circle-num { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 50%; color: white; margin-right: 12px; font-size: 18px; font-weight: bold; }
.block-arrow { width: 30px; height: 35px; margin: 15px auto; clip-path: polygon(30% 0%, 70% 0%, 70% 55%, 100% 55%, 50% 100%, 0% 55%, 30% 55%); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.box { background: white; border-radius: 8px; overflow: hidden; border: 2px solid; }
.box-header { text-align: center; padding: 10px; font-weight: bold; font-size: 16px; border-bottom: 2px solid; }
.box-content { padding: 16px 20px; font-size: 15px; line-height: 1.6; font-weight: 500; }
.box-content ul { margin: 0; padding-left: 20px; }
.box-content li { margin-bottom: 6px; }
.border-orange-thick { border: 3px solid var(--c-orange); }
.text-orange { color: var(--c-orange); }
.bg-orange { background-color: var(--c-orange); }
.box.theme-orange { border-color: var(--c-orange-border); }
.box.theme-orange .box-header { background: var(--c-orange-light); border-bottom-color: var(--c-orange-border); color: var(--c-orange); }
.box.theme-red { border-color: var(--c-red-border); }
.box.theme-red .box-header { background: var(--c-red-light); border-bottom-color: var(--c-red-border); color: var(--c-red); }
.border-red-thick { border: 3px solid var(--c-red); }
.text-red { color: var(--c-red); }
.bg-red { background-color: var(--c-red); }
.border-blue-thick { border: 3px solid var(--c-blue); background: var(--c-blue-light); }
.text-blue { color: var(--c-blue); }
.bg-blue { background-color: var(--c-blue); }
.border-yellow-thick { border: 3px solid var(--c-yellow); background: var(--c-yellow-light); }
.text-yellow { color: #d68700; }
.bg-yellow { background-color: var(--c-yellow); }
.box-3 { background: white; border: 2px solid var(--c-yellow-border); border-radius: 8px; padding: 16px; font-size: 14px; font-weight: 500; }
.box-3-header { font-weight: bold; font-size: 15px; color: var(--c-orange); margin-bottom: 12px; border-bottom: 2px solid #eee; padding-bottom: 8px; }
.box-3 ul { margin: 0 0 15px 0; padding-left: 18px; line-height: 1.6; }
.box-3 li { margin-bottom: 5px; }
.tag-center { display: flex; justify-content: center; align-items: center; margin: 20px auto 0 auto; padding: 8px 24px; border-radius: 30px; font-size: 15px; font-weight: bold; width: fit-content; }
.tag-orange { background: var(--c-orange-light); color: var(--c-orange); border: 2px solid var(--c-orange); }
.tag-red { background: var(--c-red); color: white; border: 2px solid var(--c-red); }
.tag-neutral { background: #fff9f6; color: #444; border: 1px solid #e0e0e0; }
.status-badge { display: block; padding: 8px; border-radius: 6px; font-size: 13px; font-weight: bold; text-align: center; width: 100%; }
.badge-green { background: var(--c-green-light); color: var(--c-green); border: 1px solid #bce8c1; }
.badge-orange { background: var(--c-orange-light); color: var(--c-orange); border: 1px solid var(--c-orange-border); }
.badge-red { background: var(--c-red-light); color: var(--c-red); border: 1px solid var(--c-red-border); }
.footer-note { text-align: center; font-size: 15px; font-weight: bold; margin-top: 20px; padding-top: 15px; border-top: 2px dashed #e0e0e0; color: #886514; }
.step-4-container { display: grid; grid-template-columns: 1fr 1.2fr; gap: 24px; margin-top: 25px; }
.bottom-banner { background: var(--c-blue); color: white; padding: 16px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 18px; margin-top: 25px; letter-spacing: .5px; box-shadow: 0 4px 10px rgba(36,87,166,.2); }
.check-list { font-size: 15px; line-height: 2.2; list-style: none; padding-left: 0; font-weight: 600; color: #111; }
.check-list li { display: flex; align-items: flex-start; }
.check-list li::before { content: '\\2714'; color: white; background: var(--c-blue); border-radius: 50%; width: 20px; height: 20px; display: inline-flex; justify-content: center; align-items: center; font-size: 12px; margin-right: 10px; margin-top: 6px; flex-shrink: 0; }
"""


# ═════════════════════════════════════════════════════════════════════
#  MD 解析
# ═════════════════════════════════════════════════════════════════════

def parse_md(md_path: Path) -> dict:
    """从 daily .md 提取流程图所需全部字段。"""
    txt = md_path.read_text(encoding="utf-8")
    html = markdown.markdown(txt, extensions=["tables"])
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    data = {}

    # ── ABCD 四端框架 (Table 1) ──
    if tables:
        df_abcd = pd.read_html(io.StringIO(str(tables[0])))[0]
        nodes = {}
        for _, row in df_abcd.iterrows():
            end_raw = str(row.iloc[0]).strip()
            light  = str(row.iloc[1]).strip()
            desc   = str(row.iloc[2]).strip()
            m = re.match(r'([A-D])', end_raw)
            key = m.group(1) if m else end_raw
            nodes[key] = {"light": light, "desc": desc}
        data["nodes"] = nodes

    # ── 仓位动作 ──
    for t in tables:
        ht = str(t)
        if "Primary" in ht and "Hedge" in ht and "Cash" in ht:
            df_pos = pd.read_html(io.StringIO(ht))[0]
            latest = df_pos.iloc[-1]
            def _clean(v): return str(v).replace("*", "").replace("%", "").strip()
            data["positions"] = {
                "Primary": _clean(latest.iloc[2]),
                "Hedge":   _clean(latest.iloc[3]),
                "Cash":    _clean(latest.iloc[4]),
            }
            break

    # ── 核心诊断表 (含 DUR 状态) ──
    for t in tables:
        ht = str(t)
        if "DUR" in ht and "仓位消费" in ht:
            df_diag = pd.read_html(io.StringIO(ht))[0]
            dur_map = {}
            for _, row in df_diag.iterrows():
                end_raw = str(row.iloc[0]).strip()
                m = re.match(r'([A-D])', end_raw)
                key = m.group(1) if m else end_raw
                dur_val = str(row.iloc[2]).strip() if len(row) > 2 else ""
                dur_map[key] = dur_val
            data["dur"] = dur_map
            break

    # ── 四端快照表 (含具体指标值) ──
    for t in tables:
        ht = str(t)
        if "指标" in ht and "当前值" in ht and "20d" in ht:
            df_snap = pd.read_html(io.StringIO(ht))[0]
            snapshot = {}
            for _, row in df_snap.iterrows():
                indicator = str(row.iloc[1]).strip()
                val = str(row.iloc[2]).strip()
                snapshot[indicator] = val
            data["snapshot"] = snapshot
            break

    # ── v3.5 信号检查表 ──
    for t in tables:
        ht = str(t)
        if "Drawdown Warning" in ht and "HYG 5d" in ht:
            df_sig = pd.read_html(io.StringIO(ht))[0]
            sigs = {}
            for _, row in df_sig.iterrows():
                sig_name = str(row.iloc[0]).strip()
                sig_status = str(row.iloc[1]).strip()
                sig_detail = str(row.iloc[2]).strip()
                sigs[sig_name] = {"status": sig_status, "detail": sig_detail}
            data["signals"] = sigs
            break

    # ── CASC ──
    m = re.search(r'\[CASC 确认 (\d+)/4', txt)
    if m:
        data["casc"] = int(m.group(1))

    # ── VTS ──
    m = re.search(r'VTS §0\.8.*?期限结构=(\S+)\(([\d.]+)\).*?前端=(\S+)\(([\d.]+)\)', txt)
    if m:
        data["vts_back_label"] = m.group(1)
        data["vts_back_ratio"] = m.group(2)
        data["vts_front_label"] = m.group(3)
        data["vts_front_ratio"] = m.group(4)
    else:
        m = re.search(r'VTS §0\.8.*?前端=(\S+)', txt)
        if m:
            data["vts_front"] = m.group(1)
    m = re.search(r'VIX9D.*?VIX.*?[=＝]\s*([\d.]+)', txt)
    if not m:
        m = re.search(r'前端急性\(([\d.]+)\)', txt)
    if m:
        data["vix9d_ratio"] = m.group(1)

    # ── RCV ──
    m = re.search(r'RCV §0\.9.*?tilt=(\S+)', txt)
    if m:
        data["rcv_tilt"] = m.group(1)
    m = re.search(r'RCV §0\.9.*?sev=(\S+)', txt)
    if m:
        data["rcv_sev"] = m.group(1)

    # ── 双探针 ──
    m = re.search(r'双探针.*?agree-(\S+)', txt)
    if m:
        data["probe"] = m.group(1)
    m = re.search(r'双探针.*?([^·]+(?:近端事件风险|非系统性)[^·]*)', txt)
    if m:
        data["probe_text"] = m.group(1).strip()

    # ── 文本字段 ──
    m = re.search(r'\*\*综合判定\*\*[：:]\s*(.+?)(?:\n|$)', txt)
    if m: data["verdict"] = m.group(1).strip()

    m = re.search(r'\*\*Regime\*\*[：:]\s*(.+)', txt)
    if m:
        raw = m.group(1).strip().replace('**', '').replace('*', '').strip()
        data["regime"] = raw

    m = re.search(r'背离[：:]\s*(.+?)(?:\n|$)', txt)
    if m: data["diverge"] = m.group(1).strip()

    m = re.search(r'\*\*今日一句话\*\*[：:]\s*(.+?)(?:\n|$)', txt)
    if m: data["oneliner"] = m.group(1).strip()

    # ── Layer 1 (ON RRP) ──
    m = re.search(r'ON RRP.*?\$([\d.]+[BMT])', txt)
    if m: data["on_rrp"] = m.group(1).strip()

    return data


# ═════════════════════════════════════════════════════════════════════
#  辅助函数 & HTML 生成
# ═════════════════════════════════════════════════════════════════════

def _light_label(light: str) -> str:
    if "🔴" in light: return "🔴"
    if "🟠" in light: return "🟠"
    if "🟡" in light: return "🟡"
    if "🟢" in light: return "🟢"
    return "?"


def _clean_dur(dur_val: str) -> str:
    """去掉 DUR 值的 'DUR5=' 前缀，避免 'DUR5 = DUR5=5/5' 重复。"""
    if not dur_val or dur_val == "—":
        return "—"
    v = re.sub(r'^DUR\d*[=＝]\s*', '', dur_val)
    v = v.replace('✅ ✅', '✅')
    return v.strip()


def build_html(data: dict, run_date: str) -> str:
    nodes    = data.get("nodes", {})
    pos      = data.get("positions", {})
    dur      = data.get("dur", {})
    snap     = data.get("snapshot", {})
    sigs     = data.get("signals", {})
    casc     = data.get("casc", 0)
    regime   = data.get("regime", "")
    verdict  = data.get("verdict", "")
    oneliner = data.get("oneliner", "")
    vix9d_ratio  = data.get("vix9d_ratio", "—")
    rcv_tilt     = data.get("rcv_tilt", "—")
    probe        = data.get("probe", "")
    probe_text   = data.get("probe_text", "")
    vts_back_label = data.get("vts_back_label", "")
    vts_back_ratio = data.get("vts_back_ratio", "")
    vts_front_label = data.get("vts_front_label", "")
    vts_front_ratio = data.get("vts_front_ratio", "")

    def p(k): return pos.get(k, "—")
    def s(k): return snap.get(k, "—")

    # ── Step 1 市场信号 ──
    move_val = s("MOVE")
    vix9d_display = vix9d_ratio if vix9d_ratio != "—" else "—"
    rcv_display = f"MOVE={move_val} / RCV={rcv_tilt}" if rcv_tilt != "—" else f"MOVE={move_val}"
    # VTS 双比率显示：背端 contango + 前端 backwardation
    if vts_back_ratio and vts_front_ratio:
        vts_display = f"VTS 背端={vts_back_label}({vts_back_ratio}) · 前端={vts_front_label}({vts_front_ratio})"
    elif vix9d_display != "—":
        vts_display = f"VIX9D/VIX = {vix9d_display} → 前端急性"
    else:
        vts_display = "VTS 待计算"

    if probe == "front" and probe_text:
        step1_conclusion = probe_text.split("·")[-1].strip().rstrip("]") if "·" in probe_text else probe_text.strip().rstrip("]")
    elif "近端" in probe_text:
        step1_conclusion = "近端利率事件风险"
    else:
        step1_conclusion = "评估中"

    # ── Step 2: C端 & A端 ──
    c_light = nodes.get("C", {}).get("light", "?")
    a_light = nodes.get("A", {}).get("light", "?")
    c_dur = _clean_dur(dur.get("C", "—"))
    a_dur = _clean_dur(dur.get("A", "—"))
    dfii10 = s("DFII10")
    effr_iorb = s("EFFR-IORB")

    # ── Step 3 triggers ──
    hy_oas = s("HY OAS")
    ig_oas = s("IG OAS")
    fxy_5d = s("FXY 5d")
    b_light = nodes.get("B", {}).get("light", "?")
    d_light = nodes.get("D", {}).get("light", "?")

    def _to_num(v):
        try: return float(v.replace("bp", "").replace("%", "").strip())
        except: return None
    hy_bp = _to_num(hy_oas) or 0
    ig_bp = _to_num(ig_oas) or 0
    trig_t1 = hy_bp >= 300 or ig_bp >= 85
    trig_t1_text = f"当前：{'已触发' if trig_t1 else '未触发'} (HY {hy_oas} / IG {ig_oas})"
    trig_t1_cls = "badge-red" if trig_t1 else "badge-green"

    trig_t2_text = "当前：部分压力，但未到系统性阈值"
    trig_t2_cls = "badge-orange"

    fxy_pct = _to_num(fxy_5d) or 0
    trig_c = fxy_pct > 2.5 or casc >= 1
    trig_t3_text = f"当前：{'已触发' if trig_c else '未触发'} (D端 {d_light} / CASC {casc}/4)"
    trig_t3_cls = "badge-red" if trig_c else "badge-green"

    # ── Step 4 ──
    b_bad = any(c in b_light for c in ("🟡","🟠","🔴"))
    a_bad = "🔴" in a_light
    d_bad = any(c in d_light for c in ("🟡","🟠","🔴"))
    systemic = b_bad and a_bad and d_bad
    step4_label = "系统性风险阶段 (已触发)" if systemic else "系统性风险阶段 (未到)"
    step4_tag = "这时才从「近端风险」升级为「系统性风险」" if not systemic else "⚠ 当前已进入系统性风险阶段"

    # ── 🔴 域 & 跨域信号计数 (底部横幅) ──
    triggered_domains = sum(1 for v in sigs.values() if "TRIGGERED" in v.get("status","").upper())
    red_count = sum(1 for k in "ABCD" if "🔴" in nodes.get(k,{}).get("light",""))

    # 底部横幅
    regime_clean = regime.replace('⚡','').strip()
    if "R1" in regime or "R2" in regime:
        bottom = "💡 当前处于前风险阶段，关注近端信号演化。"
    else:
        bottom = f"💡 {regime_clean}，跨域信号={triggered_domains}，🔴={red_count}个域"

    # ── 当前判断 checklist ──
    s_map = {"🔴":"红","🟠":"橙","🟡":"黄","🟢":"绿"}
    a_s = s_map.get(_light_label(a_light), _light_label(a_light))
    b_s = s_map.get(_light_label(b_light), _light_label(b_light))
    c_s = s_map.get(_light_label(c_light), _light_label(c_light))
    d_s = s_map.get(_light_label(d_light), _light_label(d_light))

    v_short = (verdict[:70] if verdict else "评估中").rstrip('。').rstrip('.')
    pos_short = f"{p('Primary')}% Pri · {p('Hedge')}% Hdg · {p('Cash')}% Cash"
    position_str = f"{p('Primary')}% Primary · {p('Hedge')}% Hedge · {p('Cash')}% Cash"

    check_html = f"""                <ul class="check-list">
                    <li>A{a_s} / B{b_s} / C{c_s} / D{d_s} — {v_short}。</li>
                    <li>仓位：{pos_short}，等待事件出清与触发器变化</li>
                    <li>因此当前仍是：<span style="color: var(--c-red); font-weight: 800;">{regime}</span>，而非危机模式</li>
                    <li>{'B 端、A 端、D 端尚未同时恶化' if not systemic else 'B/A/D 端已现同步恶化信号，需高度关注'}</li>
                </ul>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>前端风险与系统性风险演化流程</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">

    <div class="header">
        <h1>前端风险会如何演化成系统性风险？</h1>
        <p>基于 {run_date} ABCD 日报 · 当前结论：{regime} / 仓位 {position_str}</p>
    </div>

    <!-- ====== Step 1 ====== -->
    <div class="section border-orange-thick">
        <div class="section-title text-orange">
            <span class="circle-num bg-orange">1</span> 近端事件风险（当前已确认）
        </div>
        <div class="grid-2">
            <div class="box theme-orange">
                <div class="box-header">事件窗</div>
                <div class="box-content"><ul>
                    <li>CPI / PPI</li>
                    <li>10Y / 30Y 美债拍卖</li>
                    <li>FOMC / 点阵图</li>
                </ul></div>
            </div>
            <div class="box theme-red">
                <div class="box-header">市场信号</div>
                <div class="box-content"><ul>
                    <li>{vts_display}</li>
                    <li>{rcv_display} = front-tilt</li>
                    <li>结论：{step1_conclusion}</li>
                </ul></div>
            </div>
        </div>
        <div class="tag-center tag-orange">当前性质：事件驱动，尚非系统性</div>
    </div>

    <div class="block-arrow bg-orange"></div>

    <!-- ====== Step 2 ====== -->
    <div class="section border-orange-thick">
        <div class="section-title text-orange">
            <span class="circle-num bg-orange">2</span> 第一层传导：估值压缩 / 利率冲击
        </div>
        <div class="grid-2">
            <div class="box theme-red" style="border: 2px solid var(--c-orange);">
                <div class="box-header" style="background:#fff;color:var(--c-red);border-bottom:2px solid var(--c-orange);">
                    C 端：长端利率定价
                </div>
                <div class="box-content"><ul>
                    <li>DFII10 = {dfii10}</li>
                    <li>状态：{c_light}</li>
                    <li>DUR5 = {c_dur}</li>
                </ul></div>
            </div>
            <div class="box theme-orange" style="border: 2px solid var(--c-orange);">
                <div class="box-header" style="background:#fff;border-bottom:2px solid var(--c-orange);">
                    A 端：资金管道
                </div>
                <div class="box-content"><ul>
                    <li>EFFR-IORB = {effr_iorb}</li>
                    <li>状态：{a_light}</li>
                    <li>DUR5 = {a_dur}</li>
                </ul></div>
            </div>
        </div>
        <div class="tag-center tag-neutral">
            含义：先压估值、伤久期、增波动；但此时仍可能只是「利率冲击」。
        </div>
    </div>

    <div class="block-arrow bg-yellow"></div>

    <!-- ====== Step 3 ====== -->
    <div class="section border-yellow-thick">
        <div class="section-title text-yellow">
            <span class="circle-num bg-yellow">3</span> 是否升级为系统性风险？看 3 个触发器
        </div>
        <div class="grid-3">
            <div class="box-3">
                <div class="box-3-header">触发器 T1：信用开始恶化</div>
                <ul>
                    <li>HY OAS 脱离自满区: &gt; 300bp</li>
                    <li>IG OAS 脱离自满区: &gt; 85bp</li>
                    <li>若继续走阔 → B 端转坏</li>
                </ul>
                <div class="status-badge {trig_t1_cls}">{trig_t1_text}</div>
            </div>
            <div class="box-3">
                <div class="box-3-header">触发器 T2：流动性继续收紧</div>
                <ul>
                    <li>EFFR-IORB 继续上行至 🔴</li>
                    <li>SOFR-IORB 接近或升破 0bp</li>
                    <li>A 端从偏紧走向真正压力</li>
                </ul>
                <div class="status-badge {trig_t2_cls}">{trig_t2_text}</div>
            </div>
            <div class="box-3">
                <div class="box-3-header">触发器 T3：跨资产 / 跨境扩散</div>
                <ul>
                    <li>D 端启动 (如 FXY 5d &gt; +2.5%)</li>
                    <li>CASC 从 0/4 升至 1/4 以上</li>
                    <li>风险从利率扩散到外汇与多资产</li>
                </ul>
                <div class="status-badge {trig_t3_cls}">{trig_t3_text}</div>
            </div>
        </div>
        <div class="footer-note">
            只有当信用恶化 + 流动性恶化 + 跨资产扩散逐步出现，前端风险才可能演化成系统性风险。
        </div>
    </div>

    <!-- ====== Step 4 ====== -->
    <div class="step-4-container">
        <div class="section border-red-thick">
            <div class="section-title text-red">
                <span class="circle-num bg-red">4</span> {step4_label}
            </div>
            <ul style="font-size:15px;line-height:1.8;font-weight:500;margin-bottom:25px;">
                <li><b>B 端转坏</b>：信用利差明显走阔</li>
                <li><b>A 端红灯</b>：资金管道受压</li>
                <li><b>D 端启动</b>：跨境 / FX 风险扩散</li>
                <li style="color:var(--c-red);font-weight:bold;margin-top:10px;">市场结果：去杠杆、全面相关性上升、系统性下跌</li>
            </ul>
            <div class="tag-center tag-red" style="width:100%;">{step4_tag}</div>
        </div>

        <div class="section border-blue-thick" style="padding:0;">
            <div style="background:var(--c-blue);color:white;padding:12px;font-size:18px;font-weight:bold;text-align:center;border-radius:6px 6px 0 0;">
                📋 当前判断
            </div>
            <div style="padding:20px;">
{check_html}
            </div>
        </div>
    </div>

    <div class="bottom-banner">
        {bottom}
    </div>

</div>
</body>
</html>"""
    return html


# ═════════════════════════════════════════════════════════════════════
#  main
# ═════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate Risk Evolution Flowchart (HTML)")
    parser.add_argument("--date", help="Date YYYY-MM-DD, default today")
    args = parser.parse_args()
    run_date = args.date or date.today().isoformat()

    md_path = REPORT_DIR / f"daily_{run_date}.md"
    if not md_path.exists():
        print(f"[ERROR] Daily report not found: {md_path}")
        sys.exit(1)

    data = parse_md(md_path)
    month = run_date[:7]
    out_dir = ARCHIVE_DIR / month
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"risk_flowchart_{run_date}.html"

    html = build_html(data, run_date)
    out_path.write_text(html, encoding="utf-8")
    print(f"[OK] {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")

    return out_path


if __name__ == "__main__":
    main()
