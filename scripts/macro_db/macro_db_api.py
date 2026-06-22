"""
macro_db_api.py — 宏观时间序列数据库 Python API
独立模块，不依赖 Risk OS。
"""
import pandas as pd
from pathlib import Path

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "macro_db" / "db" / "macro_timeseries.duckdb"


def _get_con():
    if not HAS_DUCKDB:
        raise ImportError("duckdb not installed. Run: uv pip install duckdb")
    return duckdb.connect(str(_DB_PATH))


def load_series(series_id: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """加载指定时间序列。"""
    con = _get_con()
    query = "SELECT date, value, source_layer, source_file FROM macro_series WHERE series_id = ?"
    params = [series_id]
    if start:
        query += " AND date >= ?"
        params.append(start)
    if end:
        query += " AND date <= ?"
        params.append(end)
    query += " ORDER BY date"
    df = con.execute(query, params).df()
    con.close()
    return df


def get_latest(series_id: str) -> dict:
    """获取最新一条记录。"""
    con = _get_con()
    row = con.execute(
        "SELECT date, value, source_layer FROM macro_series WHERE series_id = ? ORDER BY date DESC LIMIT 1",
        [series_id]
    ).fetchone()
    con.close()
    if row:
        return {"date": str(row[0]), "value": row[1], "source_layer": row[2]}
    return {}


def get_metadata(series_id: str) -> dict:
    """获取时间序列元数据。"""
    con = _get_con()
    row = con.execute(
        "SELECT * FROM series_metadata WHERE series_id = ?", [series_id]
    ).fetchone()
    con.close()
    if row:
        cols = ["series_id", "name", "vendor", "source", "frequency", "unit",
                "start_date", "end_date", "rows", "seed_status", "history_quality",
                "gap_note", "license_note", "updated_at"]
        return dict(zip(cols, row))
    return {}


def get_percentile(series_id: str, value: float, start: str | None = None,
                   end: str | None = None) -> float:
    """计算 value 在历史序列中的分位数。"""
    df = load_series(series_id, start, end)
    if df.empty:
        return float("nan")
    return float((df["value"] <= value).mean())


def get_rolling_percentile(series_id: str, window_days: int = 756) -> pd.DataFrame:
    """计算滚动分位数。"""
    df = load_series(series_id)
    if df.empty:
        return df
    df["rolling_pct"] = df["value"].rolling(window=window_days, min_periods=min(window_days // 2, 126)).apply(
        lambda x: (x <= x.iloc[-1]).mean() if len(x) > 0 else float("nan"), raw=False
    )
    return df


def list_series() -> list[dict]:
    """列出所有已入库的时间序列。"""
    con = _get_con()
    rows = con.execute("SELECT series_id, name, seed_status, history_quality, start_date, end_date, rows FROM series_metadata ORDER BY series_id").fetchall()
    con.close()
    return [{"series_id": r[0], "name": r[1], "seed_status": r[2], "history_quality": r[3],
             "start_date": str(r[4]), "end_date": str(r[5]), "rows": r[6]} for r in rows]
