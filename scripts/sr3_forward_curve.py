"""
SR3 远期曲线对比图（每日运行）

输入: D:\\liquidity-dashboard\\v3.5\\data\\历史数据\\100-CME_DL_SR3H2027, 1D.csv
      (TradingView 导出, time 列已是 YYYY-MM-DD 格式)

输出:
  1. 日期修正后的全量 CSV (time -> date)
  2. 最新一天的快照 CSV
  3. 5 条曲线对比 PNG（1日/3日/一周/一月/三个月前的远期曲线 + 最新）
  4. 同步到 sofr_sr3.csv (期货价 = 100 - 利率)

曲线含义:
  - X 轴: SR3 合约按到期月份排序 (M26 -> N26 -> Q26 -> U26 -> V26 -> X26 -> Z26 -> H27 -> M27 -> U27)
  - Y 轴: 远期利率 (%)  - TradingView 的 SR3 数值已是利率形式 (3.xx ~ 4.xx)
  - 5 条线: 最新 + 1/3/7/30/90 自然日前最近交易日的曲线

运行:
  cd d:\\liquidity-dashboard\\v3.5
  uv run python scripts/sr3_forward_curve.py
"""
from __future__ import annotations

import re
import sys
from datetime import timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Windows 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ─────────────────────────────────────────────────────────────────────────────
# 路径
# ─────────────────────────────────────────────────────────────────────────────
HIST_DIR = Path(r"D:\liquidity-dashboard\v3.5\data\历史数据")
SRC_CSV = HIST_DIR / "100-CME_DL_SR3H2027, 1D.csv"

# 主图合约（文件名里就标了 SR3H2027，对应 close 列）
MAIN_CONTRACT = "SR3H2027"

# SR3 月份代码 → (英文缩写, 月份数)
MONTH_CODES = {
    "F": ("Jan", 1),  "G": ("Feb", 2),  "H": ("Mar", 3),  "J": ("Apr", 4),
    "K": ("May", 5),  "M": ("Jun", 6),  "N": ("Jul", 7),  "Q": ("Aug", 8),
    "U": ("Sep", 9),  "V": ("Oct", 10), "X": ("Nov", 11), "Z": ("Dec", 12),
}

# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────
def parse_contract(col: str) -> str | None:
    """从列名提取合约代码。
    'close'                       -> 'SR3H2027' (主图)
    '100-SR3U2027 · CME: close'   -> 'SR3U2027'
    """
    if col == "close":
        return MAIN_CONTRACT
    m = re.search(r"SR3([FGHJKMNQUVXZ])(\d{4})", str(col))
    return f"SR3{m.group(1)}{m.group(2)}" if m else None


def contract_to_date(code: str) -> pd.Timestamp | None:
    """SR3H2027 -> Timestamp(2027-03-01)."""
    m = re.match(r"SR3([FGHJKMNQUVXZ])(\d{4})", code)
    if not m:
        return None
    return pd.Timestamp(year=int(m.group(2)), month=MONTH_CODES[m.group(1)][1], day=1)


def contract_label(code: str) -> str:
    """SR3H2027 -> 'H27 (Mar27)'  便于 X 轴显示."""
    m = re.match(r"SR3([FGHJKMNQUVXZ])(\d{4})", code)
    if not m:
        return code
    letter, yy = m.group(1), m.group(2)[-2:]
    mon_abbr = MONTH_CODES[letter][0]
    return f"{letter}{yy}\n{mon_abbr}'{yy}"


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    if not SRC_CSV.exists():
        print(f"[ERROR] 源文件不存在: {SRC_CSV}")
        return 1

    # 1. 读 CSV
    df = pd.read_csv(SRC_CSV)
    print(f"读取 {len(df)} 行, 列: {df.columns.tolist()}")

    # 2. 日期已是 YYYY-MM-DD 格式，直接重命名 time -> date
    df["date"] = df["time"].astype(str)
    df = df.sort_values("date").reset_index(drop=True)

    print(f"日期范围: {df['date'].min()} -> {df['date'].max()}")

    # 3. 重命名合约列
    rename_map = {}
    for col in df.columns:
        code = parse_contract(col)
        if code:
            rename_map[col] = code
    df = df.rename(columns=rename_map)

    # 合约列（按到期月份排序）
    contract_cols = [c for c in df.columns if c.startswith("SR3")]
    contract_cols_sorted = sorted(contract_cols, key=contract_to_date)
    print(f"合约 ({len(contract_cols_sorted)}): {contract_cols_sorted}")

    # 4. 保存日期修正后的全量 CSV
    fixed_csv = HIST_DIR / "100-CME_DL_SR3H2027_1D_fixed.csv"
    out_cols = ["date"] + contract_cols_sorted
    df[out_cols].to_csv(fixed_csv, index=False)
    print(f"日期修正 CSV: {fixed_csv}")

    # 5. 最新一天数据
    latest_idx = len(df) - 1
    latest_date = df.loc[latest_idx, "date"]
    latest_row = df.loc[[latest_idx], ["date"] + contract_cols_sorted]
    latest_csv = HIST_DIR / f"sr3_latest_{latest_date}.csv"
    latest_row.to_csv(latest_csv, index=False)
    print(f"最新一天 CSV: {latest_csv}")
    print(f"最新日期: {latest_date}")
    print("最新数据:")
    print(latest_row.to_string(index=False))

    # 6. 定位 5 个时间点（按自然日，自动找最近交易日）
    latest_ts = pd.Timestamp(latest_date)
    spans = [
        ("1日",  1,   "#1f77b4"),
        ("3日",  3,   "#2ca02c"),
        ("1周",  7,   "#ff7f0e"),
        ("1月",  30,  "#9467bd"),
        ("3月",  90,  "#8c564b"),
    ]
    points = []  # (label, date_str, idx)
    for label, days, color in spans:
        target = latest_ts - timedelta(days=days)
        # 找 <= target 的最大日期
        mask = df["date"] <= target.strftime("%Y-%m-%d")
        if mask.any():
            idx = mask.values[::-1].argmax()  # last True
            idx = len(df) - 1 - idx
            points.append((label, df.loc[idx, "date"], idx, color))
        else:
            print(f"[WARN] {label} ({target.date()}) 无可用数据，跳过")
    # 最新作为高亮线
    points.append(("最新", latest_date, latest_idx, "#d62728"))

    # 7. 画图
    fig, ax = plt.subplots(figsize=(14, 7.5))

    for label, date_str, idx, color in points:
        row = df.loc[idx]
        rates, xticks, xlabels = [], [], []
        for code in contract_cols_sorted:
            v = row[code]
            if pd.notna(v):
                rates.append(float(v))
                xticks.append(len(rates) - 1)
                xlabels.append(contract_label(code))
        if not rates:
            continue
        lw = 2.5 if label == "最新" else 1.6
        ms = 8 if label == "最新" else 6
        ax.plot(xticks, rates, marker="o", markersize=ms, linewidth=lw,
                label=f"{label} ({date_str})", color=color, alpha=0.9)

    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels, fontsize=10)
    ax.set_xlabel("SR3 合约 (按到期月份排序)", fontsize=12)
    ax.set_ylabel("远期利率 (%)", fontsize=12)
    ax.set_title(f"SR3 远期曲线对比  |  最新: {latest_date}",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3, linestyle="--")

    # Y 轴留 5% 余量
    all_vals = []
    for _, _, idx, _ in points:
        row = df.loc[idx]
        for code in contract_cols_sorted:
            v = row[code]
            if pd.notna(v):
                all_vals.append(float(v))
    if all_vals:
        ymin, ymax = min(all_vals), max(all_vals)
        pad = (ymax - ymin) * 0.1 if ymax > ymin else 0.1
        ax.set_ylim(ymin - pad, ymax + pad)

    plt.tight_layout()
    out_png = HIST_DIR / f"sr3_forward_curve_{latest_date}.png"
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\n曲线图已保存: {out_png}")

    # 8. 同时输出一个不带日期戳的固定文件名（便于每天覆盖查看）
    latest_png = HIST_DIR / "sr3_forward_curve_latest.png"
    plt.savefig  # noop
    # 重新画一次到 latest_png（避免 close 后失活）
    fig2, ax2 = plt.subplots(figsize=(14, 7.5))
    for label, date_str, idx, color in points:
        row = df.loc[idx]
        rates, xticks2, xlabels2 = [], [], []
        for code in contract_cols_sorted:
            v = row[code]
            if pd.notna(v):
                rates.append(float(v))
                xticks2.append(len(rates) - 1)
                xlabels2.append(contract_label(code))
        if not rates:
            continue
        lw = 2.5 if label == "最新" else 1.6
        ms = 8 if label == "最新" else 6
        ax2.plot(xticks2, rates, marker="o", markersize=ms, linewidth=lw,
                 label=f"{label} ({date_str})", color=color, alpha=0.9)
    ax2.set_xticks(xticks2)
    ax2.set_xticklabels(xlabels2, fontsize=10)
    ax2.set_xlabel("SR3 合约 (按到期月份排序)", fontsize=12)
    ax2.set_ylabel("远期利率 (%)", fontsize=12)
    ax2.set_title(f"SR3 远期曲线对比  |  最新: {latest_date}",
                  fontsize=14, fontweight="bold")
    ax2.legend(loc="best", fontsize=10, framealpha=0.9)
    ax2.grid(True, alpha=0.3, linestyle="--")
    if all_vals:
        ax2.set_ylim(ymin - pad, ymax + pad)
    plt.tight_layout()
    plt.savefig(latest_png, dpi=120, bbox_inches="tight")
    plt.close(fig2)
    print(f"固定名最新版: {latest_png}")

    # 9. 同步到 sofr_sr3.csv（期货价 96.xx 形式）
    update_sofr_sr3(df, contract_cols_sorted)

    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 同步到 sofr_sr3.csv
# ─────────────────────────────────────────────────────────────────────────────
# sofr_sr3.csv 列: date, SR3M2026, SR3N2026, SR3Q2026, SR3U2026, SR3V2026,
#                  SR3X2026, SR3Z2026, SR3H2027, SR3M2027, SR3U2027, note
# 第 1 行是表头，第 2 行是月份注释 (26-Jun, 26-Jul, ...) 跳过
# TV 数据是利率 (%)，sofr_sr3 是期货价 = 100 - 利率
SOFR_SR3_CSV = Path(r"D:\liquidity-dashboard\v3.5\data\sofr_sr3.csv")
SOFR_CONTRACTS = ["SR3M2026", "SR3N2026", "SR3Q2026", "SR3U2026", "SR3V2026",
                  "SR3X2026", "SR3Z2026", "SR3H2027", "SR3M2027", "SR3U2027"]


def update_sofr_sr3(tv_df: pd.DataFrame, tv_contracts: list[str]) -> None:
    """把 TV 数据（利率形式）同步到 sofr_sr3.csv（期货价形式）。"""
    if not SOFR_SR3_CSV.exists():
        print(f"[WARN] sofr_sr3.csv 不存在: {SOFR_SR3_CSV}，跳过同步")
        return

    # 读 sofr_sr3.csv，跳过第 2 行月份注释
    sr = pd.read_csv(SOFR_SR3_CSV, skiprows=[1])
    # 第 1 行是表头，已读为列名
    # 转 TV 日期 -> sofr_sr3 的 M/D/YYYY 格式
    tv_dates = pd.to_datetime(tv_df["date"])
    sr_dates = pd.to_datetime(sr["date"], format="mixed")

    # 建立 sofr_sr3 缺失日期到 TV 行的映射
    updated_count = 0
    appended_count = 0
    for i, tv_row in tv_df.iterrows():
        tv_date = pd.to_datetime(tv_row["date"])
        target_str = f"{tv_date.month}/{tv_date.day}/{tv_date.year}"  # 6/22/2026

        # 计算期货价 (100 - rate)
        values = {}
        for code in SOFR_CONTRACTS:
            if code in tv_row.index and pd.notna(tv_row[code]):
                values[code] = round(100 - float(tv_row[code]), 4)
            else:
                values[code] = None  # 留空，比如 SR3Z2026 / SR3M2027

        # 已有日期 → 更新
        if target_str in sr["date"].values:
            idx = sr.index[sr["date"] == target_str][0]
            for code in SOFR_CONTRACTS:
                if values[code] is not None:
                    cur = sr.at[idx, code]
                    if pd.isna(cur) or str(cur).strip() == "":
                        sr.at[idx, code] = values[code]
                        updated_count += 1
                    # 已有非空值不覆盖（保留手填或更早同步的数据）
            continue

        # 新日期 → 追加
        new_row = {"date": target_str}
        new_row.update({c: values[c] for c in SOFR_CONTRACTS})
        new_row["note"] = "from TradingView"
        sr = pd.concat([sr, pd.DataFrame([new_row])], ignore_index=True)
        appended_count += 1

    # 按日期排序
    sr["_dt"] = pd.to_datetime(sr["date"], format="mixed", errors="coerce")
    sr = sr.sort_values("_dt").drop(columns=["_dt"]).reset_index(drop=True)

    # 保留 note 列（如果原文件没有就加一个空列）
    if "note" not in sr.columns:
        sr["note"] = ""

    # 写回 - 保留原格式：表头 + 月份注释行 + 数据
    month_labels = ["# 月份", "26-Jun", "26-Jul", "26-Aug", "26-Sep", "26-Oct",
                    "26-Nov", "26-Dec", "27-Mar", "27-Jun", "27-Sep", ""]
    with open(SOFR_SR3_CSV, "w", encoding="utf-8", newline="") as f:
        # 表头
        f.write(",".join(sr.columns) + "\n")
        # 月份注释行
        f.write(",".join(month_labels) + "\n")
        # 数据行
        for _, row in sr.iterrows():
            cells = []
            for col in sr.columns:
                v = row[col]
                if pd.isna(v):
                    cells.append("")
                else:
                    cells.append(str(v))
            f.write(",".join(cells) + "\n")

    print(f"\nsofr_sr3.csv 已同步: 填充 {updated_count} 个空位, 追加 {appended_count} 行")
    print(f"  路径: {SOFR_SR3_CSV}")
    print(f"  总行数: {len(sr)}")
    # 打印最后 3 行
    print("  最后 3 行:")
    print(sr.tail(3).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
