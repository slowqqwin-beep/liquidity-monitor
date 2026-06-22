"""
validate_hy_oas_candidate.py — BAMLH0A0HYM2 候选文件验证引擎

独立模块，不依赖 Risk OS。对候选 CSV/XLSX/Parquet 执行严格验证。
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date
from typing import Optional
import json
import traceback


# ============================================================================
# 常量
# ============================================================================

SERIES_ID = "BAMLH0A0HYM2"
SERIES_NAME = "ICE BofA US High Yield Index Option-Adjusted Spread"
SERIES_ALIAS = "HY OAS"
SERIES_UNIT = "percent"
SERIES_FREQ = "daily"

ACCEPTABLE_DATE_COLS = ["DATE", "date", "observation_date", "Date", "Observation_Date"]
ACCEPTABLE_VALUE_COLS = ["BAMLH0A0HYM2", "hy_oas", "value", "VALUE", "Value", "HY_OAS"]

# 覆盖范围阈值
FULL_SEED_MIN_START = pd.Timestamp("2000-01-01")
FULL_SEED_MIN_END = pd.Timestamp("2023-01-01")
FULL_SEED_MIN_ROWS = 4000

IDEAL_START = pd.Timestamp("1997-01-31")
IDEAL_END = pd.Timestamp("2026-03-01")
IDEAL_MIN_ROWS = 6000

# 重叠校验阈值
OVERLAP_MIN_DATES = 100
OVERLAP_MIN_MATCH_RATIO = 0.98
OVERLAP_MAX_MEDIAN_ABS_DIFF = 0.02
OVERLAP_MAX_MAX_ABS_DIFF = 0.10

# 异常值阈值
MAX_ACCEPTABLE_VALUE = 25.0
MAX_SINGLE_DAY_CHANGE = 2.0
MAX_GAP_CALENDAR_DAYS = 10

# 单位检测阈值
BP_MEDIAN_LOW = 50
BP_MEDIAN_HIGH = 2500
PERCENT_MEDIAN_MAX = 30

CANDIDATE_STATUSES = [
    "accepted_seed",
    "accepted_partial_seed",
    "rejected_wrong_series",
    "rejected_live_window_only",
    "rejected_no_overlap_with_fred",
    "rejected_bad_columns",
    "rejected_bad_values",
    "rejected_permission_or_download_failed",
    "rejected_unit_suspicious",
    "fred_permission_limited_3y",
    "pending_validation",
]


def _detect_columns(df: pd.DataFrame) -> tuple[Optional[str], Optional[str]]:
    """检测日期列和数值列。"""
    date_col = None
    value_col = None

    for c in df.columns:
        if c in ACCEPTABLE_DATE_COLS:
            date_col = c
            break
        if c.lower() in ["date", "observation_date"]:
            date_col = c
            break

    for c in df.columns:
        if c in ACCEPTABLE_VALUE_COLS:
            value_col = c
            break
        if c.lower() in ["bamlh0a0hym2", "hy_oas", "value"]:
            value_col = c
            break

    # 如果没有匹配到列名，尝试用第一列作为日期，第二列作为数值
    if date_col is None and len(df.columns) >= 1:
        date_col = df.columns[0]
    if value_col is None and len(df.columns) >= 2:
        value_col = df.columns[1]

    return date_col, value_col


def normalize_candidate(filepath: str) -> dict:
    """
    规范化候选文件，返回统一格式的 dict。
    返回包含 normalized_df 和 validation_result 的 dict。
    """
    fp = Path(filepath)
    result = {
        "filepath": str(fp),
        "filename": fp.name,
        "ext": fp.suffix.lower(),
        "candidate_status": "pending_validation",
        "errors": [],
        "warnings": [],
        "unit_converted": False,
        "unit_original_median": None,
        "start_date": None,
        "end_date": None,
        "rows": 0,
        "valid_rows": 0,
        "score": 0,
        "overlap_count": None,
        "match_ratio": None,
        "median_abs_diff": None,
        "max_abs_diff": None,
        "overlap_start": None,
        "overlap_end": None,
        "overlap_status": None,
        "has_negative_values": False,
        "has_large_gap": False,
        "large_gap_details": [],
        "duplicate_dates": 0,
        "null_values_removed": 0,
        "single_day_spikes": [],
        "df": None,  # normalized DataFrame
        "direct_series_column_name": False,
    }

    try:
        # === 读取文件 ===
        if result["ext"] == ".csv":
            df = pd.read_csv(filepath)
        elif result["ext"] in [".xlsx", ".xls"]:
            df = pd.read_excel(filepath)
        elif result["ext"] == ".parquet":
            df = pd.read_parquet(filepath)
        else:
            result["candidate_status"] = "rejected_bad_columns"
            result["errors"].append(f"Unsupported file extension: {result['ext']}")
            return result

        # === 检测列 ===
        date_col, value_col = _detect_columns(df)
        if date_col is None:
            result["candidate_status"] = "rejected_bad_columns"
            result["errors"].append("No date column found")
            return result
        if value_col is None:
            result["candidate_status"] = "rejected_bad_columns"
            result["errors"].append("No value column found")
            return result

        if value_col == "BAMLH0A0HYM2":
            result["direct_series_column_name"] = True

        # === 解析日期 ===
        df["_date_parsed"] = pd.to_datetime(df[date_col], errors="coerce")
        before_drop = len(df)
        df = df.dropna(subset=["_date_parsed"]).copy()
        if len(df) < before_drop:
            result["warnings"].append(f"Dropped {before_drop - len(df)} rows with unparseable dates")

        if len(df) < 500:
            result["candidate_status"] = "rejected_bad_values"
            result["errors"].append(f"Only {len(df)} valid rows after date parsing, need > 500")
            return result

        # === 解析数值 ===
        raw_vals = pd.to_numeric(df[value_col], errors="coerce")
        null_mask = raw_vals.isna()
        result["null_values_removed"] = int(null_mask.sum())
        df = df[~null_mask].copy()
        df["_value_raw"] = raw_vals[~null_mask].values

        if len(df) < 500:
            result["candidate_status"] = "rejected_bad_values"
            result["errors"].append(f"Only {len(df)} valid rows after value parsing, need > 500")
            return result

        # === 单位检测与转换 ===
        median_val = float(df["_value_raw"].median())
        result["unit_original_median"] = median_val

        if BP_MEDIAN_LOW < median_val < BP_MEDIAN_HIGH:
            # 推定 bp，转换为 percent
            df["_value"] = df["_value_raw"] / 100.0
            result["unit_converted"] = True
            result["warnings"].append(f"Detected bp units (median={median_val:.1f}), converted to percent")
        elif median_val <= PERCENT_MEDIAN_MAX:
            df["_value"] = df["_value_raw"]
            result["unit_converted"] = False
        else:
            result["candidate_status"] = "rejected_unit_suspicious"
            result["errors"].append(f"Median value {median_val:.1f} outside expected ranges for bp (<{BP_MEDIAN_LOW}, >{BP_MEDIAN_HIGH}) or percent (<={PERCENT_MEDIAN_MAX})")
            return result

        # === 去重日期（保留最后一条） ===
        dup_count = int(df.duplicated(subset=["_date_parsed"], keep="last").sum())
        result["duplicate_dates"] = dup_count
        if dup_count > 0:
            result["warnings"].append(f"Found {dup_count} duplicate dates, keeping last occurrence")
            df = df.drop_duplicates(subset=["_date_parsed"], keep="last").copy()

        # === 排序 ===
        df = df.sort_values("_date_parsed").reset_index(drop=True)

        # === 异常值检查 ===
        # 负值
        neg_mask = df["_value"] < 0
        if neg_mask.any():
            result["has_negative_values"] = True
            neg_dates = df.loc[neg_mask, "_date_parsed"].dt.strftime("%Y-%m-%d").tolist()[:10]
            result["errors"].append(f"Negative values found on dates: {neg_dates}")

        # 极端高值 (>25)
        high_mask = df["_value"] > MAX_ACCEPTABLE_VALUE
        if high_mask.any():
            high_dates = df.loc[high_mask, "_date_parsed"].dt.strftime("%Y-%m-%d").tolist()[:10]
            result["warnings"].append(f"Values > {MAX_ACCEPTABLE_VALUE}% on dates: {high_dates}")

        # 单日变化绝对值 > 2
        df["_diff"] = df["_value"].diff().abs()
        spike_mask = df["_diff"] > MAX_SINGLE_DAY_CHANGE
        if spike_mask.any():
            spikes = []
            for _, row in df[spike_mask].iterrows():
                spikes.append({
                    "date": row["_date_parsed"].strftime("%Y-%m-%d"),
                    "value": float(row["_value"]),
                    "change": float(row["_diff"]),
                })
            result["single_day_spikes"] = spikes[:20]
            result["warnings"].append(f"Found {spike_mask.sum()} single-day changes > {MAX_SINGLE_DAY_CHANGE}")

        # 连续日期间隔 > 10 天
        df["_date_diff"] = df["_date_parsed"].diff().dt.days
        gap_mask = df["_date_diff"] > MAX_GAP_CALENDAR_DAYS
        if gap_mask.any():
            result["has_large_gap"] = True
            gaps = []
            for _, row in df[gap_mask].iterrows():
                gaps.append({
                    "after_date": row["_date_parsed"].strftime("%Y-%m-%d"),
                    "gap_days": int(row["_date_diff"]),
                })
            result["large_gap_details"] = gaps[:20]
            result["warnings"].append(f"Found {gap_mask.sum()} gaps > {MAX_GAP_CALENDAR_DAYS} calendar days")

        # === 构建输出 ===
        result["start_date"] = df["_date_parsed"].min().strftime("%Y-%m-%d")
        result["end_date"] = df["_date_parsed"].max().strftime("%Y-%m-%d")
        result["rows"] = len(df)
        result["valid_rows"] = len(df)

        # 只保留需要的列
        result["df"] = df[["_date_parsed", "_value"]].rename(
            columns={"_date_parsed": "date", "_value": "value"}
        )

        # === 如果到此没有状态，标记为基本通过基本检查 ===
        if result["candidate_status"] == "pending_validation":
            result["candidate_status"] = "pending_validation"  # 等待 overlap 检查

    except Exception as e:
        result["candidate_status"] = "rejected_bad_values"
        result["errors"].append(f"Exception during normalization: {str(e)}")
        result["errors"].append(traceback.format_exc())

    return result


def check_coverage(result: dict) -> dict:
    """检查时间覆盖范围，更新候选状态。"""
    if result["candidate_status"] not in ("pending_validation", "fred_permission_limited_3y"):
        return result

    start = pd.Timestamp(result["start_date"]) if result["start_date"] else None
    end = pd.Timestamp(result["end_date"]) if result["end_date"] else None
    rows = result["rows"]

    if start is None or end is None:
        result["candidate_status"] = "rejected_bad_values"
        result["errors"].append("Cannot determine date range")
        return result

    # 检测 live-only (FRED 三年窗口特征)
    live_window_start = pd.Timestamp.now() - pd.Timedelta(days=3 * 365)
    if start >= live_window_start:
        result["candidate_status"] = "rejected_live_window_only"
        result["errors"].append(f"Start date {result['start_date']} is within FRED 3y window — live_window_only")
        return result

    if start <= IDEAL_START and end >= IDEAL_END and rows >= IDEAL_MIN_ROWS:
        # 理想种子
        pass  # 保持 pending，等 overlap 确认
    elif start <= FULL_SEED_MIN_START and end >= FULL_SEED_MIN_END and rows >= FULL_SEED_MIN_ROWS:
        pass  # 最低种子标准
    else:
        result["candidate_status"] = "accepted_partial_seed"
        result["warnings"].append(f"Coverage insufficient for full seed: start={result['start_date']}, end={result['end_date']}, rows={rows}")

    return result


def check_overlap_with_fred_live(result: dict, fred_live_path: str) -> dict:
    """
    与 FRED live 做重叠校验。这是最重要的验证步骤。
    """
    if result.get("df") is None:
        result["candidate_status"] = "rejected_bad_values"
        result["errors"].append("No normalized dataframe for overlap check")
        return result

    try:
        fred_df = pd.read_csv(fred_live_path)
        # 标准化 FRED live
        date_col, value_col = _detect_columns(fred_df)
        if date_col is None or value_col is None:
            result["overlap_status"] = "fred_live_unreadable"
            result["errors"].append("Cannot parse FRED live file")
            return result

        fred_df["_date"] = pd.to_datetime(fred_df[date_col], errors="coerce")
        fred_df["_value"] = pd.to_numeric(fred_df[value_col], errors="coerce")
        fred_df = fred_df.dropna(subset=["_date", "_value"])

        if len(fred_df) == 0:
            result["overlap_status"] = "fred_live_empty"
            result["errors"].append("FRED live file is empty after parsing")
            return result

        # 合并
        merged = result["df"].merge(
            fred_df[["_date", "_value"]].rename(columns={"_date": "date", "_value": "fred_value"}),
            on="date",
            how="inner",
        )

        overlap_count = len(merged)
        result["overlap_count"] = overlap_count

        if overlap_count < OVERLAP_MIN_DATES:
            # 检测非重叠历史 seed：seed 在 FRED live 窗口之前，非错误序列
            if overlap_count == 0 and result.get("direct_series_column_name") and result.get("end_date"):
                seed_end = pd.Timestamp(result["end_date"])
                fred_start = fred_df["_date"].min()
                if seed_end < fred_start:
                    # Gap between seed end and FRED live start — accept as seed with gap note
                    result["overlap_status"] = "passed_no_overlap"
                    result["warnings"].append(
                        f"Seed ends {result['end_date']}, FRED live starts {fred_start.strftime('%Y-%m-%d')} — "
                        f"gap of ~{(fred_start - seed_end).days} days. Accepted based on direct series column name + value range."
                    )
                    if result["candidate_status"] == "pending_validation":
                        start = pd.Timestamp(result["start_date"])
                        if start <= FULL_SEED_MIN_START and result["rows"] >= FULL_SEED_MIN_ROWS:
                            result["candidate_status"] = "accepted_seed"
                        else:
                            result["candidate_status"] = "accepted_partial_seed"
                    return result

            result["overlap_status"] = "insufficient_overlap"
            result["candidate_status"] = "rejected_no_overlap_with_fred"
            result["errors"].append(f"Only {overlap_count} overlapping dates with FRED live, need >= {OVERLAP_MIN_DATES}")
            return result

        # 计算匹配度
        merged["abs_diff"] = (merged["value"] - merged["fred_value"]).abs()
        result["median_abs_diff"] = float(merged["abs_diff"].median())
        result["max_abs_diff"] = float(merged["abs_diff"].max())
        result["overlap_start"] = merged["date"].min().strftime("%Y-%m-%d")
        result["overlap_end"] = merged["date"].max().strftime("%Y-%m-%d")

        match_count = (merged["abs_diff"] <= 0.02).sum()
        result["match_ratio"] = float(match_count / overlap_count)

        # 判断
        if (result["match_ratio"] >= OVERLAP_MIN_MATCH_RATIO
                and result["median_abs_diff"] <= OVERLAP_MAX_MEDIAN_ABS_DIFF
                and result["max_abs_diff"] <= OVERLAP_MAX_MAX_ABS_DIFF):
            result["overlap_status"] = "passed"
            # 如果之前是 pending_validation，现在升级为 accepted
            if result["candidate_status"] == "pending_validation":
                # 根据覆盖范围确定是 seed 还是 partial_seed
                start = pd.Timestamp(result["start_date"])
                end = pd.Timestamp(result["end_date"])
                if start <= FULL_SEED_MIN_START and end >= FULL_SEED_MIN_END and result["rows"] >= FULL_SEED_MIN_ROWS:
                    result["candidate_status"] = "accepted_seed"
                else:
                    result["candidate_status"] = "accepted_partial_seed"
        else:
            result["overlap_status"] = "failed"
            result["candidate_status"] = "rejected_no_overlap_with_fred"
            result["errors"].append(
                f"Overlap mismatch: match_ratio={result['match_ratio']:.4f}, "
                f"median_abs_diff={result['median_abs_diff']:.4f}, "
                f"max_abs_diff={result['max_abs_diff']:.4f}"
            )

    except Exception as e:
        result["overlap_status"] = "error"
        result["errors"].append(f"Overlap check error: {str(e)}")

    return result


def compute_score(result: dict) -> dict:
    """计算候选评分。"""
    score = 0

    if result["start_date"]:
        start = pd.Timestamp(result["start_date"])
        if start <= IDEAL_START:
            score += 35
        elif start <= FULL_SEED_MIN_START:
            score += 25

    if result["end_date"]:
        end = pd.Timestamp(result["end_date"])
        if end >= IDEAL_END:
            score += 25
        elif end >= FULL_SEED_MIN_END:
            score += 15

    if result["rows"] >= IDEAL_MIN_ROWS:
        score += 15
    elif result["rows"] >= FULL_SEED_MIN_ROWS:
        score += 10

    if result.get("overlap_count") and result["overlap_count"] >= 500:
        score += 10

    if result.get("overlap_status") == "passed_no_overlap":
        # 无重叠但确认正确（列名+值域），给部分信用
        score += 20

    if result.get("match_ratio"):
        if result["match_ratio"] >= 0.995:
            score += 20
        elif result["match_ratio"] >= OVERLAP_MIN_MATCH_RATIO:
            score += 10

    if result.get("median_abs_diff") is not None:
        if result["median_abs_diff"] <= 0.01:
            score += 10
        elif result["median_abs_diff"] <= 0.02:
            score += 5

    if not result["has_negative_values"]:
        score += 5

    if not result["has_large_gap"]:
        score += 5

    if result["direct_series_column_name"]:
        score += 5

    result["score"] = score
    return result


def validate_candidate(filepath: str, fred_live_path: str) -> dict:
    """
    完整验证流程：规范化 → 覆盖检查 → overlap 校验 → 评分。
    """
    result = normalize_candidate(filepath)

    if result["candidate_status"] == "pending_validation":
        result = check_coverage(result)

    if result["candidate_status"] in ("pending_validation", "accepted_partial_seed"):
        result = check_overlap_with_fred_live(result, fred_live_path)

    result = compute_score(result)

    # 清理 DataFrame，不序列化到 JSON
    if "df" in result:
        del result["df"]

    return result


def validate_candidate_batch(candidate_files: list[str], fred_live_path: str) -> list[dict]:
    """批量验证候选文件。"""
    results = []
    for fp in candidate_files:
        r = validate_candidate(fp, fred_live_path)
        results.append(r)
    return results


if __name__ == "__main__":
    print("validate_hy_oas_candidate.py — 请通过 find_external_hy_oas_seed.py 或 build_hy_oas_master.py 调用")
