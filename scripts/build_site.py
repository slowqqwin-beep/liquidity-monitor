"""
build_site.py — 生成 GitHub Pages 静态站点

1. 从 fed_reaction_dashboard.md + pipeline_result.json → docs/index.html (Fed Reaction)
2. 从 risk_dashboard_latest.md + mm_calendar.json → docs/risk/index.html (Risk Dashboard)
3. Risk Dashboard 页面嵌入 MM 财经日历 Google Calendar embed

Usage:
  python scripts/build_site.py
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Paths ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DOCS_DIR = PROJECT_DIR / "docs"
RISK_DIR = DOCS_DIR / "risk"
ASSETS_DIR = DOCS_DIR / "assets"
RISK_ASSETS_DIR = RISK_DIR / "assets"

FED_MD = PROJECT_DIR / "fed_reaction_dashboard.md"
PIPELINE_JSON = PROJECT_DIR / "data" / "pipeline_result.json"
RISK_MD = PROJECT_DIR / "risk_dashboard_latest.md"
MM_CALENDAR_JSON = PROJECT_DIR / "data" / "mm_calendar.json"

FED_INDEX = DOCS_DIR / "index.html"
RISK_INDEX = RISK_DIR / "index.html"

CST = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════════════
# CSS (shared)
# ═══════════════════════════════════════════════════

SHARED_CSS = """/* ── Reset & Base ── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0b0f19;--card:#131a2b;--border:#1e2d4a;
  --text:#c8d6e5;--muted:#6b7d99;--accent:#4da6ff;
  --red:#ff4757;--orange:#ff9f43;--yellow:#feca57;
  --green:#2ed573;--cyan:#1dd1a1;
  --radius:10px;--shadow:0 2px 12px rgba(0,0,0,.3);
}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;
  min-height:100vh}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

/* ── Shell ── */
.app-shell{max-width:1200px;margin:0 auto;padding:16px 20px 40px}
header.hero{text-align:center;padding:28px 0 20px;position:relative}
.hero h1{font-size:2rem;font-weight:700;letter-spacing:-.01em;
  background:linear-gradient(135deg,#e0e7ff,#8eb8ff);-webkit-background-clip:text;
  -webkit-text-fill-color:transparent;background-clip:text}
.hero .sub{color:var(--muted);font-size:.9rem;margin-top:6px}
.hero .timestamp{font-size:.75rem;color:var(--muted);margin-top:4px}
.nav-links{margin-top:12px;display:flex;gap:16px;justify-content:center;flex-wrap:wrap}
.nav-links a{padding:6px 16px;border-radius:20px;border:1px solid var(--border);
  font-size:.85rem;transition:all .2s}
.nav-links a:hover,.nav-links a.active{background:var(--accent);color:#fff;
  border-color:var(--accent);text-decoration:none}

/* ── Cards ── */
.card{background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:18px 20px;box-shadow:var(--shadow)}
.card-title{font-size:.85rem;text-transform:uppercase;letter-spacing:.06em;
  color:var(--accent);margin-bottom:10px;font-weight:600}

/* ── Tables ── */
table{width:100%;border-collapse:collapse;font-size:.88rem}
th{text-align:left;color:var(--muted);font-weight:500;padding:8px 10px 6px;
  border-bottom:1px solid var(--border);font-size:.78rem;text-transform:uppercase}
td{padding:8px 10px;border-bottom:1px solid rgba(30,45,74,.5)}
tr:last-child td{border-bottom:none}

/* ── Traffic Lights ── */
.light{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.light-red{background:var(--red);box-shadow:0 0 8px var(--red)}
.light-orange{background:var(--orange);box-shadow:0 0 8px var(--orange)}
.light-yellow{background:var(--yellow);box-shadow:0 0 8px var(--yellow)}
.light-green{background:var(--green);box-shadow:0 0 8px var(--green)}

/* ── Status Badges ── */
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.78rem;font-weight:600}
.badge-red{background:rgba(255,71,87,.15);color:var(--red)}
.badge-orange{background:rgba(255,159,67,.15);color:var(--orange)}
.badge-yellow{background:rgba(254,202,87,.15);color:var(--yellow)}
.badge-green{background:rgba(46,213,115,.15);color:var(--green)}

/* ── Grids ── */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.grid-4{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
section{margin-bottom:20px}
.section-head{margin-bottom:14px}
.section-head h2{font-size:1.2rem;color:#e0e7ff}

/* ── Event Window ── */
.event-card{border-left:3px solid var(--accent);padding:12px 16px;
  background:rgba(77,166,255,.05);border-radius:0 var(--radius) var(--radius) 0}
.event-main{font-size:1.05rem;font-weight:600;color:#e0e7ff}
.event-meta{font-size:.82rem;color:var(--muted);margin-top:4px}
.dense-events{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.dense-event{padding:3px 10px;background:rgba(255,159,67,.1);color:var(--orange);
  border-radius:6px;font-size:.8rem}

/* ── Calendar Embed ── */
.calendar-embed{margin-top:20px;border:1px solid var(--border);
  border-radius:var(--radius);overflow:hidden}
.calendar-embed iframe{width:100%;height:500px;border:none}

/* ── Signal Row ── */
.signal-grid{display:grid;grid-template-columns:120px 1fr;gap:6px 16px;
  align-items:baseline}
.signal-label{color:var(--muted);font-size:.82rem;text-align:right}
.signal-value{font-size:.92rem}

/* ── Footer ── */
footer{text-align:center;padding:24px 0 12px;color:var(--muted);font-size:.75rem}

@media(max-width:768px){
  .grid-2,.grid-3,.grid-4{grid-template-columns:1fr}
  .signal-grid{grid-template-columns:80px 1fr}
}
"""


# ═══════════════════════════════════════════════════
# Risk Dashboard HTML Template
# ═══════════════════════════════════════════════════

RISK_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Risk Dashboard — ABCD v3.5</title>
<link rel="stylesheet" href="assets/style.css"/>
</head>
<body>
<div class="app-shell">
<header class="hero">
  <h1>🛡️ Risk Evolution Dashboard</h1>
  <div class="sub">ABCD v3.5 · 前端风险 → 系统性风险演化看板</div>
  <div class="timestamp">__TIMESTAMP__</div>
  <nav class="nav-links">
    <a href="../">Fed Reaction Dashboard</a>
    <a href="./" class="active">Risk Dashboard</a>
  </nav>
</header>

<main>
  <!-- ① Near-Term Event Risk -->
  <section>
    <div class="section-head"><h2>① 近端事件风险</h2></div>
    <div class="card signal-grid">
      __SIGNAL_ROWS__
    </div>
  </section>

  <!-- ② First-Layer Conduction -->
  <section>
    <div class="section-head"><h2>② 第一层传导</h2></div>
    <div class="card">
      __TABLE_CONDUCTION__
    </div>
  </section>

  <!-- ③ Systemic Triggers -->
  <section>
    <div class="section-head"><h2>③ 系统性风险触发器</h2></div>
    <div class="card">
      __TABLE_TRIGGERS__
    </div>
  </section>

  <!-- ④ Phase & Final Judgment -->
  <section>
    <div class="section-head"><h2>④ 系统性风险阶段与最终判断</h2></div>
    <div class="card">
      __TABLE_JUDGMENT__
    </div>
  </section>

  <!-- MM Calendar Embed -->
  <section>
    <div class="section-head"><h2>MM 财经日历</h2></div>
    <div class="calendar-embed">
      <iframe src="https://calendar.google.com/calendar/embed?src=c_c040a8d14375de55799b6fdd8ece2ee2f32aa85fd0e5b39d14b1e07f90df424e%40group.calendar.google.com&ctz=Asia%2FTaipei"
              style="border:0" width="100%" height="500" frameborder="0" scrolling="no"></iframe>
    </div>
  </section>
</main>

<footer>
  ABCD v3.5 Risk Evolution Dashboard · Auto-generated by GitHub Actions
  · <a href="https://github.com">View on GitHub</a>
</footer>
</div>
</body>
</html>"""


FED_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Fed Reaction Dashboard v2</title>
<link rel="stylesheet" href="assets/style.css"/>
</head>
<body>
<div class="app-shell">
<header class="hero">
  <h1>Fed Reaction Dashboard v2</h1>
  <div class="sub">State Machine · Driver Attribution · Five-Module Scores</div>
  <div class="timestamp">__TIMESTAMP__</div>
  <nav class="nav-links">
    <a href="./" class="active">Fed Reaction Dashboard</a>
    <a href="risk/">Risk Dashboard</a>
  </nav>
</header>
<main>
  __FED_CONTENT__
</main>
<footer>
  Fed Reaction Dashboard v2 · Auto-generated by GitHub Actions
  · <a href="https://github.com">View on GitHub</a>
</footer>
</div>
</body>
</html>"""


# ═══════════════════════════════════════════════════
# Markdown → HTML helpers
# ═══════════════════════════════════════════════════

def md_table_to_html(md: str) -> str:
    """Convert a markdown table block to HTML table."""
    lines = [l.strip() for l in md.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        return f"<pre>{md}</pre>"

    # Parse header row
    header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
    # Skip separator row (line 1)
    data_rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if cells:
            data_rows.append(cells)

    html = "<table><thead><tr>"
    for h in header_cells:
        html += f"<th>{escape_html(h)}</th>"
    html += "</tr></thead><tbody>"

    for row in data_rows:
        html += "<tr>"
        for i, cell in enumerate(row):
            # Add light indicators for signal columns
            cell_html = inline_formatting(cell)
            html += f"<td>{cell_html}</td>"
        html += "</tr>"

    html += "</tbody></table>"
    return html


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_formatting(text: str) -> str:
    """Apply inline markdown formatting (bold, light indicators) to HTML."""
    t = escape_html(text)
    # Bold
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    # Light indicators
    t = t.replace("🔴", '<span class="light light-red"></span>🔴')
    t = t.replace("🟠", '<span class="light light-orange"></span>🟠')
    t = t.replace("🟡", '<span class="light light-yellow"></span>🟡')
    t = t.replace("🟢", '<span class="light light-green"></span>🟢')
    t = t.replace("⚠️", "⚠️")
    return t


def extract_md_section(md: str, section_header: str) -> str:
    """Extract a markdown section by its ## header."""
    pattern = rf"## {re.escape(section_header)}\n\n(.*?)(?=\n## |\n---\n\*|\Z)"
    m = re.search(pattern, md, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def extract_md_table(md: str, section_header: str) -> str:
    """Extract the first table from a markdown section."""
    section = extract_md_section(md, section_header)
    # Find table: lines between |---|---|... and the next blank line or section
    lines = section.splitlines()
    table_lines = []
    in_table = False
    for line in lines:
        if line.startswith("|"):
            table_lines.append(line)
            in_table = True
        elif in_table and not line.strip():
            break
        elif in_table and line.startswith("##"):
            break
    return "\n".join(table_lines)


def extract_signal_grid(md: str) -> list[tuple[str, str]]:
    """Extract signal rows from ① section as (label, value) pairs."""
    table = extract_md_table(md, "① 近端事件风险")
    lines = [l.strip() for l in table.splitlines() if l.strip()]
    rows = []
    for line in lines[2:]:  # skip header + separator
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) >= 2:
            rows.append((cells[0], cells[1]))
    return rows


# ═══════════════════════════════════════════════════
# Fed Reaction Dashboard builder (from pipeline_result.json)
# ═══════════════════════════════════════════════════

def build_fed_content() -> str:
    """Build Fed Reaction content from pipeline_result.json."""
    if not PIPELINE_JSON.exists():
        return '<div class="card"><p>pipeline_result.json not found — run fed_dashboard.py first.</p></div>'

    p = json.loads(PIPELINE_JSON.read_text(encoding="utf-8"))
    html_parts = []

    # State block
    st = p.get("state", {})
    state_val = st.get("state", "UNKNOWN")
    state_days = st.get("state_days", 0)
    reason = st.get("reason", "--")
    needs = st.get("upgrade_needs", [])

    state_cls_map = {
        "ACTIONABLE": "badge-green", "CANDIDATE": "badge-yellow",
        "OBSERVE": "badge-green", "ABSTAIN": "badge-red",
    }
    state_cls = state_cls_map.get(state_val, "badge-yellow")

    html_parts.append('<section class="card">')
    html_parts.append(f'<div class="card-title">State Machine</div>')
    html_parts.append(f'<span class="badge {state_cls}">{state_val}</span> '
                      f'<strong>Day {state_days}</strong> — {escape_html(reason)}')
    if needs:
        html_parts.append(f'<p style="margin-top:8px;color:var(--muted)">Upgrade needs: {", ".join(needs)}</p>')
    html_parts.append('</section>')

    # Attribution
    attr = p.get("attribution", {})
    if attr:
        html_parts.append('<section class="card">')
        html_parts.append('<div class="card-title">Driver Attribution</div>')
        html_parts.append(f'<p><strong>{escape_html(attr.get("label",""))}</strong></p>')
        detail = attr.get("detail", "")
        if detail:
            html_parts.append(f'<p style="color:var(--muted)">{escape_html(detail)}</p>')
        html_parts.append('</section>')

    # Gates
    gates = p.get("gates", {})
    if gates:
        html_parts.append('<section><div class="section-head"><h2>Gates</h2></div>')
        html_parts.append('<div class="grid-3">')
        for gk in ["vix_contango", "casc", "credit"]:
            gv = gates.get(gk, {})
            if isinstance(gv, dict):
                ok = gv.get("pass", False)
                cls = "badge-green" if ok else "badge-red"
                detail = gv.get("detail", "")
                html_parts.append(
                    f'<div class="card"><span class="badge {cls}">{"PASS" if ok else "CLOSED"}</span>'
                    f'<strong> {gk}</strong><p style="color:var(--muted);font-size:.82rem">{escape_html(detail)}</p></div>'
                )
        html_parts.append('</div></section>')

    # Scores
    scores = p.get("scores", {})
    if scores:
        html_parts.append('<section><div class="section-head"><h2>Five-Module Scores</h2></div>')
        html_parts.append('<div class="grid-3">')
        for k in ["hawkish", "dovish", "liquidity", "inflation", "growth"]:
            m = scores.get(k, {})
            label = m.get("label", k)
            score = m.get("score", 0)
            mx = m.get("max", 4)
            pct = min(100, int(score / mx * 100)) if mx else 0
            cls = "badge-red" if score >= 3 else ("badge-orange" if score >= 2 else "badge-green")
            html_parts.append(
                f'<div class="card"><span class="badge {cls}">{score}/{mx}</span>'
                f'<strong style="margin-left:8px">{escape_html(label)}</strong></div>'
            )
        html_parts.append('</div></section>')

    # Cross validation
    cv = p.get("cross_validation", {})
    if cv:
        html_parts.append('<section class="card">')
        html_parts.append('<div class="card-title">ABCD Cross-Validation</div>')
        for r in cv.get("rows", []):
            tool = r.get("tool", "")
            abcd = r.get("abcd", "")
            match = r.get("match", "")
            html_parts.append(
                f'<p><strong>{escape_html(tool)}</strong>: {escape_html(abcd)} — {escape_html(match)}</p>'
            )
        html_parts.append('</section>')

    return "\n".join(html_parts)


# ═══════════════════════════════════════════════════
# Risk Dashboard builder (from risk_dashboard_latest.md)
# ═══════════════════════════════════════════════════

def build_risk_html() -> str:
    """Build Risk Dashboard HTML from risk_dashboard_latest.md."""
    if not RISK_MD.exists():
        return RISK_HTML_TEMPLATE.replace("__TIMESTAMP__", now_str()).replace(
            "__SIGNAL_ROWS__", "<p>risk_dashboard_latest.md not found</p>"
        ).replace("__TABLE_CONDUCTION__", "").replace(
            "__TABLE_TRIGGERS__", ""
        ).replace("__TABLE_JUDGMENT__", "")

    md = RISK_MD.read_text(encoding="utf-8")

    # Extract header line
    header_match = re.search(r"^> \*\*(.+?)\*\*", md)
    header_date = header_match.group(1) if header_match else ""

    # Signal rows from ①
    signal_rows = extract_signal_grid(md)
    signal_html = ""
    for label, value in signal_rows:
        value_html = inline_formatting(value)
        signal_html += (
            f'<div class="signal-label">{escape_html(label)}</div>'
            f'<div class="signal-value">{value_html}</div>\n'
        )
    if not signal_html:
        signal_html = "<p>暂无近端事件数据</p>"

    # Tables from ②③④
    conduction_table = md_table_to_html(extract_md_table(md, "② 第一层传导"))
    triggers_table = md_table_to_html(extract_md_table(md, "③ 系统性风险触发器"))
    judgment_table = md_table_to_html(extract_md_table(md, "④ 系统性风险阶段与最终判断"))

    # Final judgment text
    final_match = re.search(r"> \*\*最终判断\*\*：(.*?)(?:\n|$)", md)
    final_text = final_match.group(1) if final_match else ""

    html = RISK_HTML_TEMPLATE
    ts = f"{now_str()} · {header_date}" if header_date else now_str()
    html = html.replace("__TIMESTAMP__", ts)
    html = html.replace("__SIGNAL_ROWS__", signal_html)
    html = html.replace("__TABLE_CONDUCTION__", conduction_table)
    html = html.replace("__TABLE_TRIGGERS__", triggers_table)
    html = html.replace("__TABLE_JUDGMENT__", judgment_table)

    if final_text:
        html = html.replace("</main>",
            f'<section class="card"><div class="card-title">最终判断</div>'
            f'<p>{escape_html(final_text)}</p></section>\n</main>')

    return html


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def now_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S · GitHub Actions")


def write_assets():
    """Write shared CSS and minimal JS to docs/assets/ and docs/risk/assets/."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    RISK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    (ASSETS_DIR / "style.css").write_text(SHARED_CSS, encoding="utf-8")
    (RISK_ASSETS_DIR / "style.css").write_text(SHARED_CSS, encoding="utf-8")

    # Minimal JS
    js = 'console.log("ABCD v3.5 Dashboard loaded");\n'
    (ASSETS_DIR / "app.js").write_text(js, encoding="utf-8")
    (RISK_ASSETS_DIR / "app.js").write_text(js, encoding="utf-8")


def main():
    print("[build_site] Generating GitHub Pages...")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    RISK_DIR.mkdir(parents=True, exist_ok=True)
    write_assets()

    # ── Fed Reaction Dashboard ──
    print("[build_site] Building Fed Reaction Dashboard...")
    fed_content = build_fed_content()
    fed_html = FED_HTML_TEMPLATE.replace("__TIMESTAMP__", now_str())
    fed_html = fed_html.replace("__FED_CONTENT__", fed_content)
    FED_INDEX.write_text(fed_html, encoding="utf-8")
    print(f"  → {FED_INDEX} ({FED_INDEX.stat().st_size} bytes)")

    # ── Risk Dashboard ──
    print("[build_site] Building Risk Dashboard...")
    risk_html = build_risk_html()
    RISK_INDEX.write_text(risk_html, encoding="utf-8")
    print(f"  → {RISK_INDEX} ({RISK_INDEX.stat().st_size} bytes)")

    # Timestamp files
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ\n")
    (DOCS_DIR / "build_timestamp.txt").write_text(ts, encoding="utf-8")
    (RISK_DIR / "build_timestamp.txt").write_text(ts, encoding="utf-8")

    print("[build_site] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
