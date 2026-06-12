"""
local_auto_push.py — 本地文件监听自动 git push

监听项目源文件变动，自动 add + commit + push。
主要用于手动修改 Markdown / JSON 后的自动同步。

MM 日历更新优先由 GitHub Actions schedule 完成，
本脚本用于本地手动修改后的快速 push。

Usage:
  python scripts/local_auto_push.py
  python scripts/local_auto_push.py --once   # 单次检查后退出
"""

import os
import subprocess
import sys
import time
from pathlib import Path

# ── Config ──
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

WATCH_PATTERNS = [
    "fed_reaction_dashboard.md",
    "risk_dashboard_latest.md",
    "data/latest.json",
    "data/history.csv",
    "data/mm_calendar.json",
    "data/mm_calendar.ics",
]

IGNORE_PATTERNS = [
    "docs/",
    ".git/",
    ".venv/",
    "__pycache__/",
    "*.pyc",
]

DEBOUNCE_SECONDS = 10  # Wait after last change before committing


def run_git(args: list[str]) -> tuple[int, str, str]:
    """Run git command in PROJECT_DIR, return (code, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", "git not found"


def has_changes() -> bool:
    """Check if any watched files have uncommitted changes."""
    code, out, _ = run_git(["status", "--porcelain"])
    if code != 0:
        return False

    for line in out.splitlines():
        if not line.strip():
            continue
        # line format: " M path" or "?? path"
        path = line[3:].strip()
        # Check if path matches any watch pattern
        for pat in WATCH_PATTERNS:
            if path.endswith(pat) or pat in path:
                # Make sure it's not in ignore list
                ignored = False
                for ign in IGNORE_PATTERNS:
                    if ign.rstrip("/") in path or path.startswith(ign):
                        ignored = True
                        break
                if not ignored:
                    return True
    return False


def commit_and_push() -> bool:
    """Stage watched files, commit, and push."""
    # Stage watched files
    for pat in WATCH_PATTERNS:
        target = PROJECT_DIR / pat
        if target.exists():
            run_git(["add", str(target.relative_to(PROJECT_DIR))])

    # Check if anything staged
    code, out, _ = run_git(["diff", "--staged", "--quiet"])
    if code == 0:
        print("[local_auto_push] No staged changes — skipping commit")
        return True

    # Commit
    ts = time.strftime("%Y-%m-%d %H:%M")
    code, _, err = run_git(["commit", "-m", f"auto: local update {ts}"])
    if code != 0:
        print(f"[local_auto_push] Commit failed: {err}")
        return False

    # Push
    code, _, err = run_git(["push"])
    if code != 0:
        print(f"[local_auto_push] Push failed: {err}")
        return False

    print(f"[local_auto_push] Pushed successfully at {ts}")
    return True


def watch_loop():
    """Main watch loop with debounce."""
    print("[local_auto_push] Watching for changes...")
    print(f"  Project: {PROJECT_DIR}")
    print(f"  Patterns: {WATCH_PATTERNS}")
    print(f"  Press Ctrl+C to stop")

    last_change = 0.0
    while True:
        try:
            if has_changes():
                now = time.time()
                if now - last_change > DEBOUNCE_SECONDS:
                    print(f"\n[local_auto_push] Changes detected — committing...")
                    commit_and_push()
                    last_change = now
                else:
                    # Debouncing — wait
                    pass
            else:
                last_change = 0.0

            time.sleep(3)
        except KeyboardInterrupt:
            print("\n[local_auto_push] Stopped.")
            break
        except Exception as e:
            print(f"[local_auto_push] Error: {e}")
            time.sleep(10)


def main():
    if "--once" in sys.argv:
        if has_changes():
            commit_and_push()
        else:
            print("[local_auto_push] No changes.")
        return 0

    watch_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
