"""Check generated output files for banned patterns (§39/§40).

Usage:
    python _check_banned_patterns.py          # standalone
    from _check_banned_patterns import check   # import into pipeline
"""
import re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / "report"

# Patterns that MUST NOT appear in output
BANNED = [
    # Position percentages
    (r'P\s*=\s*\d+\s*%[^A-Z]*H\s*=\s*\d+\s*%[^A-Z]*C\s*=\s*\d+\s*%',
     "P/H/C percentage pattern"),
    # Banned mechanism keywords — EXCEPT when in "permanently banned" disclaimer
    (r'\bSSoT\s*(?:唯一|权威)(?!.*(?:禁入|已禁用|permanently))', "SSoT active in output"),
    (r'仓位动作', "仓位动作 section header"),
    (r'\|\s*仓位\s*\|.*P=.*H=.*C=', "仓位 row with P/H/C"),
    # DUR5 with confirmation markers
    (r'DUR5\s*=\s*5/5\s*✅.*已确认.*→R', "DUR5→R arrow pattern"),
    # Signal #2 wrong name
    (r'HYG 5d\s*<\s*-?1\.5%', "HYG 5d as trigger (should be HY OAS 5d)"),
]

def check_file(filepath):
    """Return list of banned patterns found."""
    hits = []
    text = filepath.read_text(encoding="utf-8")
    for pattern, desc in BANNED:
        matches = re.findall(pattern, text)
        if matches:
            line_nums = []
            for i, line in enumerate(text.split('\n'), 1):
                if re.search(pattern, line):
                    line_nums.append(str(i))
            hits.append(f"  BANNED [{desc}]: {filepath.name}:{','.join(line_nums[:3])}")
    return hits

def main(block_on_detection=True):
    daily_md = sorted(REPORT.glob("daily_*.md"), reverse=True)
    risk_md = sorted(REPORT.glob("risk_dashboard_*.md"), reverse=True)
    
    all_hits = []
    for fp in (daily_md[:1] + risk_md[:1]):
        if fp.exists():
            all_hits.extend(check_file(fp))
    
    if all_hits:
        print("[BANNED PATTERN CHECK] FAILED:")
        for h in all_hits:
            print(h)
        if block_on_detection:
            print("  → BLOCKED: banned patterns in output. Fix before presenting.")
            sys.exit(1)
        else:
            print("  → WARNING only (non-blocking mode)")
    else:
        print("[BANNED PATTERN CHECK] PASSED")

if __name__ == "__main__":
    main(block_on_detection=True)
