"""
update_event_window.py — 自动改写 risk_dashboard_latest.md §① 近端事件风险

读取 data/mm_calendar.json → 选 score 最高事件 → 检测密集窗 →
读取现有看板信号（VIX9D/VIX, CASC, VTS, RCV） → 生成四维信号行 →
替换 ## ① 近端事件风险 整段（不破坏后续内容）

Usage:
  python scripts/update_event_window.py
"""

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ── Paths ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
CALENDAR_PATH = DATA_DIR / "mm_calendar.json"
DASHBOARD_PATH = PROJECT_DIR / "risk_dashboard_latest.md"
REPORT_DIR = PROJECT_DIR / "report"


# ── Helpers ──
def load_calendar() -> list[dict]:
    if not CALENDAR_PATH.exists():
        print(f"[update_event_window] {CALENDAR_PATH} not found")
        return []
    return json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))


def load_dashboard() -> str:
    """Read the current risk_dashboard_latest.md, or fall back to latest dated version."""
    if DASHBOARD_PATH.exists():
        return DASHBOARD_PATH.read_text(encoding="utf-8")

    # Fallback: find latest risk_dashboard_*.md in report/
    if REPORT_DIR.exists():
        candidates = sorted(REPORT_DIR.glob("risk_dashboard_*.md"), reverse=True)
        if candidates:
            print(f"[update_event_window] Using fallback: {candidates[0].name}")
            return candidates[0].read_text(encoding="utf-8")

    print("[update_event_window] No dashboard found — creating minimal template")
    today = date.today().isoformat()
    return f"""# 🛡️ 前端风险 → 系统性风险 演化看板

> **{today}** | Regime: **R3 警惕** | P=35% / H=35% / C=30% | 跨域信号=2 | 🔴=1

---

## ① 近端事件风险

| 维度 | 信号 |
|------|------|
| 事件窗 | 暂无高权重宏观事件窗 |
| 风险性质 | 待确认 |
| 市场信号 | 待确认 |
| 利率路径 | 待确认 |

---

## ② 第一层传导

| 端 | 指标 | 当前值 | 灯 | DUR5 | 状态 |
|----|------|--------|------|------|------|

---

## ③ 系统性风险触发器

| 触发器 | 条件 | 当前状态 |
|--------|------|---------|

---

## ④ 系统性风险阶段与最终判断

| 项目 | 状态 |
|------|------|

---
*ABCD v3.5 风险演化看板 | {today} | FRED+Yahoo*
"""


def extract_dashboard_signals(md: str) -> dict:
    """Extract key signal values from existing dashboard markdown."""
    signals: dict = {}

    # VIX9D/VIX ratio
    m = re.search(r"VIX9D/VIX\s*=\s*([\d.]+)", md)
    if m:
        signals["vix9d_vix"] = float(m.group(1))

    # VIX value
    m = re.search(r"VIX\s*=\s*([\d.]+)", md)
    if m:
        signals["vix"] = float(m.group(1))

    # CASC
    m = re.search(r"CASC\s*(\d+)/4", md)
    if m:
        signals["casc"] = int(m.group(1))
    else:
        m = re.search(r"CASC确认\s*(\d+)/4", md)
        if m:
            signals["casc"] = int(m.group(1))

    # VTS contango/backwardation
    if "VTS=contango" in md or "VTS = contango" in md or "期限结构=contango" in md:
        signals["vts_contango"] = True
    elif "VTS=backwardation" in md or "VTS = backwardation" in md or "期限结构=backwardation" in md:
        signals["vts_contango"] = False
    else:
        # Try neutral
        m = re.search(r"期限结构\s*=\s*(\w+)", md)
        if m:
            signals["vts_contango"] = m.group(1) not in ("backwardation", "倒挂")

    # DGS2-IORB
    m = re.search(r"DGS2[−\\-]IORB\s*=\s*([\d.]+)bp", md)
    if m:
        signals["dgs2_iorb"] = float(m.group(1))

    # 5dΔ for DGS2-IORB
    m = re.search(r"5dΔ\s*([+\-]?[\d.]+)bp", md)
    if m:
        signals["dgs2_iorb_5d"] = float(m.group(1))

    # Interlock
    if "agree-front" in md:
        signals["interlock"] = "agree-front"
    elif "agree-systemic" in md:
        signals["interlock"] = "agree-systemic"

    # RCV
    m = re.search(r"RCV\s*=\s*([\w\-]+)", md)
    if m:
        signals["rcv"] = m.group(1)

    return signals


def classify_risk_nature(event_summary: str) -> str:
    """Map event type to risk nature label."""
    s = event_summary.lower()
    if any(k in s for k in ["利率决策", "fomc", "fed rate decision"]):
        return "Fed事件 · 近端事件"
    if any(k in s for k in ["cpi", "pce", "ppi", "消费者物价", "个人消费支出", "生产者物价"]):
        return "通胀事件 · 近端事件"
    if any(k in s for k in ["非农", "nfp", "失业率", "初次申请"]):
        return "就业事件 · 近端事件"
    if any(k in s for k in ["powell", "鲍威尔", "会议纪要"]):
        return "Fed沟通事件 · 近端事件"
    if any(k in s for k in ["ism", "零售"]):
        return "增长数据事件 · 近端事件"
    return "宏观事件 · 近端事件"


def build_event_window(events: list[dict], signals: dict) -> str:
    """Build the 事件窗 cell value."""
    if not events:
        return "暂无高权重宏观事件窗"

    # Check if dense event window (3d, multiple weight>=70)
    today = date.today()
    dense_events = [
        e for e in events
        if e["days_to_event"] <= 3 and e["weight"] >= 70
    ]

    vix_note = ""
    if signals.get("vix9d_vix"):
        ratio = signals["vix9d_vix"]
        if ratio > 1.10:
            vix_note = f" · VIX9D/VIX={ratio:.3f} 前端高度急性"
        elif ratio > 1.05:
            vix_note = f" · VIX9D/VIX={ratio:.3f} 前端急性"
        else:
            vix_note = f" · VIX9D/VIX={ratio:.3f}"

    if len(dense_events) >= 2:
        names = " / ".join(e["event"][:30] for e in dense_events[:4])
        return f"**密集事件窗**：{names}{vix_note}"

    # Single main event
    main = events[0]
    d = main["days_to_event"]
    t = main["time_sg"]
    # Extract just HH:MM from Singapore time
    time_match = re.search(r"T(\d{2}:\d{2})", t)
    sg_time = time_match.group(1) if time_match else t
    event_date = main["date"]
    return (
        f"{main['event']} T-{d} · "
        f"新加坡时间 {event_date} {sg_time}"
        f"{vix_note}"
    )


def build_risk_nature(events: list[dict], signals: dict) -> str:
    """Build the 风险性质 cell value."""
    if not events:
        return "待确认"

    main = events[0]
    nature = classify_risk_nature(main["event"])

    # Systemic supplement
    casc = signals.get("casc", 0)
    vts_ok = signals.get("vts_contango", True)

    if casc >= 2 or not vts_ok:
        nature += " · 有扩散风险"
    elif casc < 2 and (vts_ok or vts_ok is None):
        nature += " · 非系统性"
    else:
        nature += " · 待确认"

    return nature


def build_market_signal(signals: dict) -> str:
    """Build the 市场信号 cell value."""
    parts = []

    vix9d_vix = signals.get("vix9d_vix")
    if vix9d_vix is not None:
        if vix9d_vix > 1.10:
            parts.append("前端高度急性，市场正在为近端事件付溢价")
        elif vix9d_vix > 1.05:
            parts.append("前端急性，市场开始为近端事件付溢价")
        elif vix9d_vix <= 1.00:
            parts.append("前端未明显定价")
        else:
            parts.append(f"VIX9D/VIX={vix9d_vix:.3f}")

    casc = signals.get("casc")
    if casc is not None:
        if casc >= 2:
            parts.append("出现跨资产确认，需警惕扩散")
        elif casc < 2:
            parts.append("暂无跨资产确认")

    if not parts:
        # Try to extract VIX info from signal dict
        vix = signals.get("vix")
        if vix:
            parts.append(f"VIX={vix}")

    return "；".join(parts) if parts else "待确认"


def build_rate_path(md: str, signals: dict) -> str:
    """Build the 利率路径 cell value, preserving existing content if available."""
    # Try to extract existing DGS2-IORB info from the dashboard
    existing = ""
    m = re.search(
        r"利率路径\s*\|\s*(.+?)(?:\||$)",
        md,
    )
    if m:
        existing = m.group(1).strip()
        if existing and existing != "待确认" and existing != "自动生成":
            return existing

    # Build from signals
    dgs2_iorb = signals.get("dgs2_iorb")
    dgs2_5d = signals.get("dgs2_iorb_5d")

    if dgs2_iorb is not None:
        parts = [f"DGS2−IORB={dgs2_iorb:.1f}bp"]
        if dgs2_5d is not None:
            delta_sign = "▲" if dgs2_5d > 0 else ("▼" if dgs2_5d < 0 else "→")
            parts.append(f"5dΔ{dgs2_5d:+.1f}bp {delta_sign}")
        if dgs2_iorb > 15:
            parts.append("降息被price out / 加息风险")
        return " ".join(parts)

    return "待确认"


def build_section_1(events: list[dict], md: str) -> str:
    """Generate the complete ① 近端事件风险 section."""
    signals = extract_dashboard_signals(md)

    event_win = build_event_window(events, signals)
    risk_nat = build_risk_nature(events, signals)
    market_sig = build_market_signal(signals)
    rate_path = build_rate_path(md, signals)

    return f"""## ① 近端事件风险

| 维度 | 信号 |
|------|------|
| 事件窗 | {event_win} |
| 风险性质 | {risk_nat} |
| 市场信号 | {market_sig} |
| 利率路径 | {rate_path} |

"""


def replace_section_1(md: str, new_section: str) -> str:
    """Replace the ## ① 近端事件风险 section, preserving everything else."""
    # Match ## ① 近端事件风险 through the next --- or ## section
    pattern = r"(## ① 近端事件风险\n\n)(.*?)(\n---\n## ②|\n## ②)"
    replacement = r"\1__NEW_SECTION__\3"

    if re.search(pattern, md, flags=re.DOTALL):
        # Multiple variants possible
        # Simpler approach: find start and end markers
        start = md.find("## ① 近端事件风险")
        if start == -1:
            print("[update_event_window] Section ① not found — prepending")
            return new_section + md

        # Find next ## section after ① (with or without --- separator)
        rest = md[start:]
        # Prefer "\n---\n## ②" over "\n## ②" to preserve separator
        next_section = re.search(r"\n---\n(## [^①])", rest)
        if next_section:
            end = start + next_section.start()
            return md[:start] + new_section.strip() + "\n" + md[end:].lstrip()
        next_section = re.search(r"\n(## [^①])", rest)
        if next_section:
            end = start + next_section.start()
            return md[:start] + new_section.strip() + "\n\n---\n" + md[end:].lstrip()

        # No next section — replace to end
        return md[:start] + new_section.strip() + "\n"

    # Fallback: insert after header line
    header_end = md.find("\n---\n")
    if header_end != -1:
        return md[:header_end + 5] + new_section + md[header_end + 5:]

    return new_section + md


# ── Main ──
def main():
    print("[update_event_window] Loading calendar...")
    events = load_calendar()

    print("[update_event_window] Loading dashboard...")
    md = load_dashboard()

    print("[update_event_window] Building §①...")
    section = build_section_1(events, md)

    print("[update_event_window] Updating dashboard...")
    updated = replace_section_1(md, section)

    DASHBOARD_PATH.write_text(updated, encoding="utf-8")
    print(f"[update_event_window] Saved → {DASHBOARD_PATH}")

    # Print the new section for verification
    print("\n--- New §① ---")
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
