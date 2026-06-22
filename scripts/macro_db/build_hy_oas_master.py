"""
build_hy_oas_master.py — 构建 BAMLH0A0HYM2 master 数据集 + DuckDB 入库
独立模块，不依赖 Risk OS。
输入: validation_results.json (由 find_external_hy_oas_seed.py 产出)
输出: master CSV/Parquet + DuckDB + metadata JSON
"""
import sys, json
from pathlib import Path

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False
    print("NOTE: duckdb not installed — DuckDB write will be skipped. pip install duckdb to enable.")
from datetime import datetime, timezone
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "macro_db"
RAW_DIR = DATA_DIR / "raw" / "BAMLH0A0HYM2"
PROCESSED_DIR = DATA_DIR / "processed"
DB_DIR = DATA_DIR / "db"
METADATA_DIR = DATA_DIR / "metadata"
AUDIT_DIR = DATA_DIR / "audit"
FRED_LIVE_PATH = RAW_DIR / "fred_live" / "BAMLH0A0HYM2_fred_live.csv"
VALIDATION_JSON = DATA_DIR / "raw" / "validation_results.json"

SERIES_ID = "BAMLH0A0HYM2"
SERIES_NAME = "ICE BofA US High Yield Index Option-Adjusted Spread"


def load_fred_live():
    """加载并标准化 FRED live 数据。"""
    if not FRED_LIVE_PATH.exists():
        return None
    df = pd.read_csv(FRED_LIVE_PATH)
    # 检测列
    from validate_hy_oas_candidate import _detect_columns
    date_col, val_col = _detect_columns(df)
    if date_col is None or val_col is None:
        return None
    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    df["value"] = pd.to_numeric(df[val_col], errors="coerce")
    df = df.dropna(subset=["date", "value"])
    # 检测单位
    med = df["value"].median()
    if 50 < med < 2500:
        df["value"] = df["value"] / 100.0
    df = df[["date", "value"]].drop_duplicates(subset="date", keep="last").sort_values("date")
    return df


def load_best_seed(best_seed_info):
    """加载 best seed 的标准化数据。"""
    if best_seed_info is None:
        return None
    fp = best_seed_info.get("filepath")
    if not fp or not Path(fp).exists():
        return None
    from validate_hy_oas_candidate import normalize_candidate
    r = normalize_candidate(fp)
    if r.get("df") is not None:
        return r["df"]
    return None


def build_master(validation_json_path=None):
    """构建 master 数据集。"""
    if validation_json_path is None:
        validation_json_path = VALIDATION_JSON

    if not Path(validation_json_path).exists():
        print(f"Validation results not found at {validation_json_path}")
        print("Run find_external_hy_oas_seed.py first.")
        return None

    with open(validation_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    best_seed = data.get("best_seed")
    fred_live_ok = data.get("fred_live_ok", False)

    fred_df = load_fred_live()
    seed_df = load_best_seed(best_seed)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)

    gap_info = ""  # init

    if seed_df is None or seed_df.empty:
        # 没有合格 seed，只生成 live-only
        print("No valid seed found. Generating live-only output.")
        master = _build_live_only(fred_df)
        seed_status = "missing"
        history_quality = "live_only"
    else:
        master, gap_info = _merge_seed_and_live(seed_df, fred_df, best_seed)
        overlap_status = best_seed.get("overlap_status", "")
        if overlap_status == "passed_no_overlap":
            # Seed 与 FRED live 不重叠（gap），接受但标记
            seed_status = "found"
            history_quality = "incomplete"  # gap 存在，不算 complete
            print(f"Note: Seed accepted with gap. {gap_info}")
        elif best_seed["candidate_status"] == "accepted_seed":
            seed_status = "found"
            history_quality = "complete"
        else:
            seed_status = "partial"
            history_quality = "incomplete"

    if master is None or master.empty:
        print("ERROR: Could not build master.")
        return None

    # gap_note 统一
    gap_note = gap_info if gap_info else None
    if best_seed and not gap_note:
        gap_note = best_seed.get("overlap_status", "")

    # 写入 CSV + Parquet
    csv_path = PROCESSED_DIR / f"{SERIES_ID}_master.csv"
    pq_path = PROCESSED_DIR / f"{SERIES_ID}_master.parquet"
    master.to_csv(csv_path, index=False)
    print(f"Master CSV: {csv_path} ({len(master)} rows)")
    try:
        master.to_parquet(pq_path, index=False)
        print(f"Master Parquet: {pq_path}")
    except ImportError:
        print("Parquet skipped (pyarrow/fastparquet not installed).")

    # DuckDB 入库 (optional)
    if HAS_DUCKDB:
        db_path = DB_DIR / "macro_timeseries.duckdb"
        _write_duckdb(master, db_path, seed_status, history_quality, gap_note)
    else:
        print("DuckDB skipped (not installed). Install with: uv pip install duckdb")

    # Metadata
    _write_metadata(master, seed_status, history_quality, gap_note)

    # Update audit if needed
    _update_audit_with_master(master, seed_status, history_quality)

    return master


def _build_live_only(fred_df):
    """只用 FRED live 构建 live-only 数据集。"""
    if fred_df is None or fred_df.empty:
        return None
    df = fred_df.copy()
    df["series_id"] = SERIES_ID
    df["source_layer"] = "fred_live_rolling_3y"
    df["source_file"] = "FRED"
    df = df[["date", "series_id", "value", "source_layer", "source_file"]].sort_values("date")
    # 保存为 live-only 文件
    live_path = PROCESSED_DIR / "BAMLH0A0HYM2_live_only.csv"
    df.to_csv(live_path, index=False)
    print(f"Live-only CSV: {live_path} ({len(df)} rows)")
    return df


def _merge_seed_and_live(seed_df, fred_df, best_seed):
    """合并 seed + FRED live。重叠日期 live 优先。返回 (combined_df, gap_info)。"""
    seed_source = best_seed.get("filepath", "unknown") if best_seed else "unknown"
    seed_df["series_id"] = SERIES_ID
    seed_df["source_layer"] = "seed"
    seed_df["source_file"] = seed_source

    if fred_df is not None and not fred_df.empty:
        fred_df["series_id"] = SERIES_ID
        fred_df["source_layer"] = "fred_live_rolling_3y"
        fred_df["source_file"] = "FRED"
        combined = pd.concat([seed_df, fred_df], ignore_index=True)
    else:
        combined = seed_df

    # 去重：按 date 去重，source_layer live 优先
    combined["_priority"] = combined["source_layer"].map({"fred_live_rolling_3y": 0, "seed": 1}).fillna(2)
    combined = combined.sort_values(["_priority"]).drop_duplicates(subset=["date"], keep="first")
    combined = combined.drop(columns=["_priority"]).sort_values("date").reset_index(drop=True)

    # 检测 gap
    combined["_date_diff"] = combined["date"].diff().dt.days
    gaps = combined[combined["_date_diff"] > 10]
    gap_info = ""
    if not gaps.empty:
        gap_descs = []
        for _, g in gaps.iterrows():
            gap_descs.append(f"{g['date'].strftime('%Y-%m-%d')} gap {int(g['_date_diff'])}d")
        gap_info = "; ".join(gap_descs[:5])

    combined = combined[["date", "series_id", "value", "source_layer", "source_file"]]
    return combined, gap_info


def _write_duckdb(master, db_path, seed_status, history_quality, gap_note=None):
    """写入 DuckDB。"""
    con = duckdb.connect(str(db_path))

    con.execute("""
        CREATE TABLE IF NOT EXISTS macro_series (
            series_id TEXT,
            date DATE,
            value DOUBLE,
            source_layer TEXT,
            source_file TEXT,
            updated_at TIMESTAMP
        )
    """)

    # Drop old schema (may lack gap_note col from v1), recreate
    con.execute("DROP TABLE IF EXISTS series_metadata")
    con.execute("""
        CREATE TABLE series_metadata (
            series_id TEXT PRIMARY KEY,
            name TEXT,
            vendor TEXT,
            source TEXT,
            frequency TEXT,
            unit TEXT,
            start_date DATE,
            end_date DATE,
            rows INTEGER,
            seed_status TEXT,
            history_quality TEXT,
            gap_note TEXT,
            license_note TEXT,
            updated_at TIMESTAMP
        )
    """)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # 删除旧数据
    con.execute("DELETE FROM macro_series WHERE series_id = ?", [SERIES_ID])

    import_df = master[["series_id", "date", "value", "source_layer", "source_file"]].copy()
    import_df["updated_at"] = now
    con.execute("INSERT INTO macro_series SELECT * FROM import_df")

    # Upsert metadata
    con.execute("DELETE FROM series_metadata WHERE series_id = ?", [SERIES_ID])
    con.execute("""
        INSERT INTO series_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        SERIES_ID,
        SERIES_NAME,
        "ICE BofA / FRED",
        "FRED St. Louis Fed",
        "daily",
        "percent",
        master["date"].min().strftime("%Y-%m-%d") if hasattr(master["date"].min(), "strftime") else str(master["date"].min()),
        master["date"].max().strftime("%Y-%m-%d") if hasattr(master["date"].max(), "strftime") else str(master["date"].max()),
        len(master),
        seed_status,
        history_quality,
        gap_note if gap_note else None,
        "ICE/FRED raw data may be copyrighted. Internal research/backtesting only.",
        now,
    ])

    con.close()
    print(f"DuckDB written: {db_path}")


def _write_metadata(master, seed_status, history_quality, gap_note=None):
    """生成 metadata JSON。"""
    meta = {
        "series_id": SERIES_ID,
        "name": SERIES_NAME,
        "alias": "HY OAS",
        "vendor": "ICE BofA / FRED",
        "source": "FRED St. Louis Fed",
        "fred_url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
        "frequency": "daily",
        "unit": "percent",
        "start_date": str(master["date"].min())[:10],
        "end_date": str(master["date"].max())[:10],
        "rows": len(master),
        "seed_status": seed_status,
        "history_quality": history_quality,
        "gap_note": gap_note,
        "license_note": "ICE/FRED raw historical data may be copyrighted. For internal research and backtesting only. Do not publish raw full history or redistribute the dataset.",
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    meta_path = METADATA_DIR / f"{SERIES_ID}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"Metadata: {meta_path}")

    # series registry
    reg_path = METADATA_DIR / "series_registry.json"
    registry = {}
    if reg_path.exists():
        with open(reg_path, "r") as f:
            registry = json.load(f)
    registry[SERIES_ID] = meta
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def _update_audit_with_master(master, seed_status, history_quality):
    """更新 audit 文件加入 master 信息。"""
    audit_path = AUDIT_DIR / f"{SERIES_ID}_external_seed_audit.json"
    if not audit_path.exists():
        return
    with open(audit_path, "r", encoding="utf-8") as f:
        audit = json.load(f)
    audit["master_start_date"] = str(master["date"].min())[:10]
    audit["master_end_date"] = str(master["date"].max())[:10]
    audit["master_rows"] = len(master)
    audit["seed_status"] = seed_status
    audit["history_quality"] = history_quality
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False, default=str)


if __name__ == "__main__":
    build_master()
