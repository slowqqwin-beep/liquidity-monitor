"""
find_external_hy_oas_seed.py — BAMLH0A0HYM2 外部 seed 搜寻脚本
独立模块，不依赖 Risk OS。
"""
import os, sys, json, requests, time, traceback
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_hy_oas_candidate import validate_candidate, SERIES_ID

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "macro_db"
RAW_DIR = DATA_DIR / "raw" / SERIES_ID
EXTERNAL_DIR = RAW_DIR / "external_candidates"
MANUAL_DIR = EXTERNAL_DIR / "manual_drop"
FRED_LIVE_DIR = RAW_DIR / "fred_live"
AUDIT_DIR = DATA_DIR / "audit"
METADATA_DIR = DATA_DIR / "metadata"
FRED_LIVE_PATH = FRED_LIVE_DIR / f"{SERIES_ID}_fred_live.csv"

CANDIDATE_URLS = [{
    "url": "https://raw.githubusercontent.com/csaladenes/eco-archive/main/BAMLH0A0HYM2.csv",
    "save_as": "github_csaladenes_eco_archive_BAMLH0A0HYM2.csv",
    "label": "GitHub csaladenes/eco-archive",
}]

FRED_GRAPH_PERMALINKS = [
    {"url": "https://fred.stlouisfed.org/graph/fredgraph.csv?g=OUJ", "save_as": "fred_graph_OUJ.csv", "label": "FRED graph OUJ"},
    {"url": "https://fred.stlouisfed.org/graph/fredgraph.csv?g=qV1C", "save_as": "fred_graph_qV1C.csv", "label": "FRED graph qV1C"},
    {"url": "https://fred.stlouisfed.org/graph/fredgraph.csv?g=1lax", "save_as": "fred_graph_1lax.csv", "label": "FRED graph 1lax"},
]

FRED_LIVE_URL = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES_ID}"

WAYBACK_CDX_URL = (
    "https://web.archive.org/cdx"
    "?url=fred.stlouisfed.org/graph/fredgraph.csv%3Fid%3DBAMLH0A0HYM2"
    "&output=json&fl=timestamp,original,statuscode,mimetype,digest"
    "&filter=statuscode:200&collapse=digest"
)

WAYBACK_TEMPLATE = "https://web.archive.org/web/{ts}id_/https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2"
PRIORITY_YEARS = ["2025", "2024", "2023", "2022", "2021", "2020"]


def ensure_dirs():
    for d in [EXTERNAL_DIR, MANUAL_DIR, FRED_LIVE_DIR, RAW_DIR / "rejected_candidates", AUDIT_DIR, METADATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def download_file(url, save_path, timeout=60):
    r = {"url": url, "save_path": str(save_path), "success": False, "status_code": None, "error": None, "file_size": None}
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (research-bot; internal)"}, timeout=timeout)
        r["status_code"] = resp.status_code
        if resp.status_code == 200:
            content = resp.content
            if content.strip().startswith(b"<!") or content.strip().startswith(b"<html"):
                r["error"] = "HTML instead of CSV"
                return r
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(content)
            r["file_size"] = len(content)
            r["success"] = True
        else:
            r["error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        r["error"] = str(e)
    return r


def download_fred_live():
    return download_file(FRED_LIVE_URL, FRED_LIVE_PATH)


def download_github():
    results = []
    for item in CANDIDATE_URLS:
        r = download_file(item["url"], EXTERNAL_DIR / item["save_as"])
        r["label"] = item["label"]
        results.append(r)
    return results


def download_graph_permalinks():
    results = []
    for item in FRED_GRAPH_PERMALINKS:
        sp = EXTERNAL_DIR / item["save_as"]
        r = download_file(item["url"], sp)
        r["label"] = item["label"]
        if r["success"]:
            try:
                txt = sp.read_text(encoding="utf-8", errors="ignore")
                lines = [l for l in txt.strip().split("\n") if l.strip()]
                if len(lines) < 1500:
                    r["note"] = "fred_permission_limited_3y"
            except Exception:
                pass
        results.append(r)
    return results


def download_wayback():
    results = []
    try:
        cdx = requests.get(WAYBACK_CDX_URL, timeout=30)
        if cdx.status_code != 200:
            return [{"source": "wayback_cdx", "success": False, "error": f"CDX HTTP {cdx.status_code}"}]
        snapshots = {}
        for line in cdx.text.strip().split("\n"):
            if not line.strip():
                continue
            try:
                parts = json.loads(line)
                if isinstance(parts, list) and len(parts) >= 1:
                    ts = parts[0]
                    yr = ts[:4]
                    if yr not in snapshots or ts > snapshots[yr]:
                        snapshots[yr] = ts
            except json.JSONDecodeError:
                continue
        results.append({"source": "wayback_cdx", "success": True, "total_years": len(snapshots)})
        downloaded = 0
        for yr in PRIORITY_YEARS:
            if downloaded >= 5:
                break
            if yr in snapshots:
                ts = snapshots[yr]
                r = download_file(WAYBACK_TEMPLATE.format(ts=ts), EXTERNAL_DIR / f"wayback_{ts}_BAMLH0A0HYM2.csv", timeout=120)
                r["label"] = f"Wayback {yr}"
                r["wayback_timestamp"] = ts
                results.append(r)
                if r["success"]:
                    downloaded += 1
                time.sleep(1)
    except Exception as e:
        results.append({"source": "wayback_cdx", "success": False, "error": str(e)})
    return results


def scan_manual():
    if not MANUAL_DIR.exists():
        return []
    files = []
    for ext in ["*.csv", "*.xlsx", "*.parquet"]:
        files.extend(str(p) for p in MANUAL_DIR.glob(ext))
    return sorted(files)


def collect_all():
    files = []
    for item in CANDIDATE_URLS:
        fp = EXTERNAL_DIR / item["save_as"]
        if fp.exists():
            files.append(str(fp))
    for item in FRED_GRAPH_PERMALINKS:
        fp = EXTERNAL_DIR / item["save_as"]
        if fp.exists():
            files.append(str(fp))
    files.extend(str(p) for p in EXTERNAL_DIR.glob("wayback_*.csv"))
    files.extend(scan_manual())
    return sorted(set(files))


def generate_audit(dl_results, val_results, fred_info, best_seed):
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    accepted = [r for r in val_results if r["candidate_status"] == "accepted_seed"]
    partials = [r for r in val_results if r["candidate_status"] == "accepted_partial_seed"]

    seed_status = "missing"
    history_quality = "live_only"
    if best_seed:
        seed_status = "found" if best_seed["candidate_status"] == "accepted_seed" else "partial"
        history_quality = "complete" if seed_status == "found" else "incomplete"

    audit = {
        "series_id": SERIES_ID,
        "audit_timestamp": now_ts,
        "seed_status": seed_status,
        "history_quality": history_quality,
        "fred_live_info": fred_info,
        "download_attempts": dl_results,
        "total_candidates": len(val_results),
        "accepted_count": len(accepted),
        "partial_count": len(partials),
        "best_seed": best_seed,
        "per_candidate": val_results,
        "license_note": "ICE/FRED raw historical data may be copyrighted. For internal research/backtesting only. Do not redistribute.",
    }
    return audit


def run():
    ensure_dirs()
    all_dl = []

    # 1. FRED live
    print("=== Downloading FRED live ===")
    fred_r = download_fred_live()
    all_dl.append(fred_r)
    fred_ok = fred_r["success"]

    fred_info = {}
    if fred_ok:
        import pandas as pd
        try:
            df = pd.read_csv(FRED_LIVE_PATH)
            fred_info = {"path": str(FRED_LIVE_PATH), "rows": len(df), "columns": list(df.columns)}
            print(f"  FRED live: {len(df)} rows")
        except Exception:
            fred_info = {"path": str(FRED_LIVE_PATH), "error": "parse failed"}
    else:
        fred_info = {"error": fred_r.get("error", "download failed")}
        print(f"  FRED live download FAILED: {fred_r.get('error')}")

    # 2. GitHub
    print("=== Downloading GitHub candidates ===")
    gh = download_github()
    all_dl.extend(gh)

    # 3. FRED graph permalinks
    print("=== Downloading FRED graph permalinks ===")
    gp = download_graph_permalinks()
    all_dl.extend(gp)

    # 4. Wayback
    print("=== Querying Wayback Machine ===")
    wb = download_wayback()
    all_dl.extend(wb)

    # 5. Collect & validate
    candidates = collect_all()
    print(f"\n=== Validating {len(candidates)} candidates ===")
    val_results = []
    for fp in candidates:
        print(f"  Validating: {Path(fp).name} ...")
        if fred_ok:
            vr = validate_candidate(fp, str(FRED_LIVE_PATH))
        else:
            vr = validate_candidate(fp, None)  # skip overlap
        val_results.append(vr)
        print(f"    status={vr['candidate_status']} score={vr['score']}")

    # 6. Find best seed
    accepted = [r for r in val_results if r["candidate_status"] == "accepted_seed"]
    partials = [r for r in val_results if r["candidate_status"] == "accepted_partial_seed"]
    best_seed = None
    if accepted:
        best_seed = max(accepted, key=lambda x: (x["score"], x["rows"]))
    elif partials:
        best_seed = max(partials, key=lambda x: (x["score"], x["rows"]))

    # 7. Generate audit
    audit = generate_audit(all_dl, val_results, fred_info, best_seed)

    # Save audit JSON
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    audit_json_path = AUDIT_DIR / f"{SERIES_ID}_external_seed_audit.json"
    with open(audit_json_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nAudit written to: {audit_json_path}")

    # Save audit MD
    _write_audit_md(audit, AUDIT_DIR / f"{SERIES_ID}_external_seed_audit.md")

    # Save intermediate results for build
    val_path = DATA_DIR / "raw" / "validation_results.json"
    with open(val_path, "w", encoding="utf-8") as f:
        json.dump({"validation_results": val_results, "best_seed": best_seed, "fred_live_info": fred_info, "fred_live_ok": fred_ok},
                  f, indent=2, ensure_ascii=False, default=str)

    return audit, best_seed


def _write_audit_md(audit, path):
    """生成 audit markdown 文件。"""
    lines = [f"# BAMLH0A0HYM2 External Seed Audit", "",
             f"**Audit timestamp**: {audit['audit_timestamp']}", "",
             f"## Summary", "",
             f"- **seed_status**: `{audit['seed_status']}`",
             f"- **history_quality**: `{audit['history_quality']}`",
             f"- **total candidates**: {audit['total_candidates']}",
             f"- **accepted**: {audit['accepted_count']}",
             f"- **partial**: {audit['partial_count']}", "",
             f"## FRED Live", "",
             f"- {audit['fred_live_info']}", "",
             f"## Download Attempts", ""]

    for dl in audit["download_attempts"]:
        status = "OK" if dl.get("success") else f"FAIL: {dl.get('error', 'unknown')}"
        lines.append(f"- {dl.get('label', dl.get('url', '?'))}: {status}")

    lines.extend(["", "## Per-Candidate Validation", ""])

    for i, v in enumerate(audit["per_candidate"]):
        lines.append(f"### Candidate {i+1}: {Path(v.get('filepath', '?')).name}")
        lines.append(f"- **status**: `{v['candidate_status']}`")
        lines.append(f"- **score**: {v['score']}")
        lines.append(f"- **date range**: {v.get('start_date', '?')} → {v.get('end_date', '?')}")
        lines.append(f"- **rows**: {v.get('rows', 0)}")
        if v.get("overlap_status"):
            lines.append(f"- **overlap**: {v['overlap_status']} (count={v.get('overlap_count')}, match_ratio={v.get('match_ratio')}, median_diff={v.get('median_abs_diff')})")
        if v.get("errors"):
            for e in v["errors"]:
                lines.append(f"- **ERROR**: {e}")
        if v.get("warnings"):
            for w in v["warnings"]:
                lines.append(f"- WARNING: {w}")
        lines.append("")

    if audit["best_seed"]:
        bs = audit["best_seed"]
        lines.extend(["## Best Seed", "", f"- **file**: {bs.get('filepath', '?')}",
                      f"- **dates**: {bs.get('start_date')} → {bs.get('end_date')}",
                      f"- **rows**: {bs.get('rows')}", f"- **score**: {bs.get('score')}", f"- **status**: {bs.get('candidate_status')}", ""])
    else:
        lines.extend(["## Best Seed", "", "**No valid full historical seed found.**", ""])

    lines.extend(["## License Note", "", audit["license_note"]])

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Audit MD written to: {path}")


if __name__ == "__main__":
    run()
