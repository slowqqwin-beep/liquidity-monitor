"""
fetch_mm_calendar.py — MacroMicro 财经日历 iCal 订阅源自动抓取

每次运行重新 requests.get(URL) 下载最新 basic.ics → 解析 VEVENT →
筛选未来 10 天美国/宏观事件 → 按权重 + 天距评分 → 输出 data/mm_calendar.json

URL 优先级：
  1. 环境变量 MM_CALENDAR_ICS_URL
  2. 默认 Google Calendar iCal 订阅源

Usage:
  python scripts/fetch_mm_calendar.py
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from icalendar import Calendar

# ── Paths ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_PATH = DATA_DIR / "mm_calendar.json"

# ── iCal URL ──
DEFAULT_ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "c_c040a8d14375de55799b6fdd8ece2ee2f32aa85fd0e5b39d14b1e07f90df424e"
    "%40group.calendar.google.com/public/basic.ics"
)


def normalize_ics_url(url: str) -> str:
    """Convert Google Calendar embed/event URLs to the raw ical ICS URL.

    embed format (returns HTML):  https://calendar.google.com/calendar/embed?src=CAL_ID...
    ical format (returns ICS):    https://calendar.google.com/calendar/ical/CAL_ID/public/basic.ics
    """
    if not url:
        return url

    # Already correct ical/ path
    if "/calendar/ical/" in url:
        return url

    # embed?src=... → extract the calendar ID and rebuild
    embed_match = re.search(r"[/&?]src=([^&]+)", url)
    if embed_match:
        cal_id = embed_match.group(1)
        # URL-decode if needed (e.g. %40 → @)
        from urllib.parse import unquote
        cal_id = unquote(cal_id)
        # If cal_id doesn't end with @group.calendar.google.com, append it
        if "@group.calendar.google.com" not in cal_id and not cal_id.endswith(".ics"):
            cal_id = cal_id + "@group.calendar.google.com"
        fixed = f"https://calendar.google.com/calendar/ical/{cal_id}/public/basic.ics"
        print(f"[fetch_mm_calendar] Auto-converted embed URL → ical URL")
        return fixed

    # event?src=... similar pattern
    if "/calendar/event?" in url and "src=" in url:
        return normalize_ics_url(url)  # recurse with same src= extraction

    return url


def is_html_response(text: str) -> bool:
    """Detect if response is HTML instead of valid iCalendar data."""
    stripped = text.strip().lower()
    return stripped.startswith("<!doctype") or stripped.startswith("<html")


def get_ics_url() -> str:
    url = os.getenv("MM_CALENDAR_ICS_URL", "").strip()
    if url:
        normalized = normalize_ics_url(url)
        if normalized != url:
            print(f"[fetch_mm_calendar] WARNING: env var URL was embed format, "
                  f"auto-converted to ical")
        return normalized
    return DEFAULT_ICS_URL


# ── Timezone ──
try:
    from zoneinfo import ZoneInfo
    SG_TZ = ZoneInfo("Asia/Singapore")
except ImportError:
    import pytz
    SG_TZ = pytz.timezone("Asia/Singapore")

UTC = timezone.utc


# ── Filters ──
US_KEYWORDS = [
    "美国", "美联储", "Powell", "鲍威尔", "FOMC", "Fed",
    "非农", "CPI", "PCE", "PPI", "ISM",
    "失业率", "初次申请失业救济金", "密大消费者信心",
    "会议纪要", "利率决策", "零售销售",
]


# Non-US country prefixes to exclude even if keyword matches
NON_US_PREFIXES = [
    "英国", "日本", "欧元区", "德国", "法国", "意大利", "加拿大",
    "澳大利亚", "新西兰", "瑞士", "瑞典", "挪威", "韩国",
    "中国", "台湾", "香港", "印度", "巴西", "墨西哥",
    "新加坡", "马来西亚", "印尼", "泰国", "越南", "菲律宾",
    "南非", "俄罗斯", "土耳其", "沙特",
]


def is_us_event(summary: str) -> bool:
    """Check if event summary is a US event.

    Two-pass filter:
    1. Exclude events with non-US country prefix (e.g. "英国-CPI")
    2. Include events matching US keywords
    """
    s = summary or ""
    # Pass 1: exclude non-US country prefixes
    for prefix in NON_US_PREFIXES:
        if s.startswith(prefix) or s.startswith(f"{prefix}-") or s.startswith(f"{prefix} "):
            return False
    # Pass 2: include if US keyword matches
    for kw in US_KEYWORDS:
        if kw.lower() in s.lower():
            return True
    return False


# ── Weight Map ──
def compute_weight(summary: str) -> int:
    """Assign base weight based on event type."""
    s = (summary or "").lower()
    # Highest priority
    if any(k in s for k in ["利率决策", "fomc", "fed rate decision"]):
        return 100
    if any(k in s for k in ["core cpi", "核心 cpi", "核心cpi"]):
        return 95
    if any(k in s for k in ["cpi", "消费者物价指数", "消费者物价"]):
        return 95
    if any(k in s for k in ["core pce", "核心 pce", "核心pce"]):
        return 90
    if any(k in s for k in ["pce", "个人消费支出"]):
        return 90
    if any(k in s for k in ["非农", "nfp", "nonfarm payroll", "nonfarm"]):
        return 85
    if any(k in s for k in ["失业率"]):
        return 85
    if any(k in s for k in ["powell", "鲍威尔"]):
        return 80
    if any(k in s for k in ["ppi", "生产者物价指数"]):
        return 70
    if "ism" in s:
        return 65
    if "零售" in s:
        return 60
    if "会议纪要" in s:
        return 50
    if "初次申请失业救济金" in s:
        return 45
    if "密大消费者信心" in s or "通胀预期" in s:
        return 45
    return 20


# ── Parse DESCRIPTION ──
def parse_description(desc: str) -> dict:
    """Extract forecast / previous / actual / link from DESCRIPTION field."""
    result = {"forecast": "", "previous": "", "actual": "", "link": ""}
    if not desc:
        return result

    for line in desc.splitlines():
        line = line.strip()

        # MM图表连结 / MM图表连结:
        m = re.search(r"MM图表连结:?\s*(https?://\S+)", line)
        if m:
            result["link"] = m.group(1)
            continue

        # 市场预期:
        m = re.search(r"市场预期:\s*(.+)", line)
        if m:
            result["forecast"] = m.group(1).strip()
            continue

        # 前值:
        m = re.search(r"前值:\s*(.+)", line)
        if m:
            result["previous"] = m.group(1).strip()
            continue

        # 实际值:
        m = re.search(r"实际值:\s*(.+)", line)
        if m:
            result["actual"] = m.group(1).strip()
            continue

    return result


# ── Main ──
def fetch_and_parse() -> list[dict]:
    """Download ICS, parse events, filter future 10 days US events, score them."""
    url = get_ics_url()
    # Normalize webcal:// → https://
    if url.startswith("webcal://"):
        url = url.replace("webcal://", "https://", 1)

    print(f"[fetch_mm_calendar] Fetching: {url[:80]}...")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.text
    print(f"[fetch_mm_calendar] Downloaded {len(raw):,} bytes")

    # Detect HTML responses (wrong URL format, e.g. embed instead of ical)
    if is_html_response(raw):
        if url == DEFAULT_ICS_URL:
            raise RuntimeError(
                "DEFAULT_ICS_URL returned HTML instead of ICS — "
                "Google Calendar public ICS feed may be unavailable or require auth. "
                f"First 200 chars: {raw[:200]}"
            )
        # Try fallback to DEFAULT_ICS_URL
        print("[fetch_mm_calendar] Response is HTML, not ICS — "
              "falling back to DEFAULT_ICS_URL")
        fallback_resp = requests.get(DEFAULT_ICS_URL, timeout=30)
        fallback_resp.raise_for_status()
        raw = fallback_resp.text
        print(f"[fetch_mm_calendar] Fallback downloaded {len(raw):,} bytes")
        if is_html_response(raw):
            raise RuntimeError(
                "Both env-provided URL and DEFAULT_ICS_URL returned HTML — "
                "Google Calendar ICS feed may be down. "
                f"First 200 chars: {raw[:200]}"
            )

    cal = Calendar.from_ical(raw)
    today = date.today()
    cutoff = today + timedelta(days=10)

    events: list[dict] = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("SUMMARY", ""))
        if not is_us_event(summary):
            continue

        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue

        # Convert to datetime
        dt = dtstart.dt
        if isinstance(dt, date) and not isinstance(dt, datetime):
            # All-day event → treat as midnight UTC
            dt = datetime(dt.year, dt.month, dt.day, tzinfo=UTC)
        elif dt.tzinfo is None:
            # Naive datetime → assume UTC
            dt = dt.replace(tzinfo=UTC)

        event_date = dt.date()

        # Only future 10 days
        if event_date < today or event_date > cutoff:
            continue

        days_to = (event_date - today).days

        # Parse description
        desc_raw = str(component.get("DESCRIPTION", ""))
        parsed = parse_description(desc_raw)

        weight = compute_weight(summary)
        score = weight - days_to * 5

        # Determine country
        country = "US"
        s_lower = summary.lower()

        # Time strings
        time_utc_str = dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        dt_sg = dt.astimezone(SG_TZ)
        time_sg_str = dt_sg.strftime("%Y-%m-%dT%H:%M:%S+08:00")

        uid = str(component.get("UID", ""))

        event = {
            "uid": uid,
            "date": event_date.isoformat(),
            "time_utc": time_utc_str,
            "time_sg": time_sg_str,
            "country": country,
            "event": summary.strip(),
            "summary": summary.strip(),
            "forecast": parsed["forecast"],
            "previous": parsed["previous"],
            "actual": parsed["actual"],
            "link": parsed["link"],
            "source": "MacroMicro",
            "weight": weight,
            "days_to_event": days_to,
            "score": score,
        }
        events.append(event)

    # Sort by score descending
    events.sort(key=lambda e: e["score"], reverse=True)

    print(f"[fetch_mm_calendar] Found {len(events)} US events in next 10 days")
    for e in events[:5]:
        print(f"  score={e['score']:3d}  weight={e['weight']:3d}  "
              f"T-{e['days_to_event']:d}  {e['event'][:60]}")

    return events


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    events = fetch_and_parse()
    OUTPUT_PATH.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[fetch_mm_calendar] Saved {len(events)} events → {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
