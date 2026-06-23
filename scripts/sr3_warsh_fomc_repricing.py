"""
沃什前后 + FOMC 事件窗口: SR3 如何重定价

X 轴: Z26 -> H27 -> M27 (远端 3 个合约, 覆盖 2026-12 ~ 2027-06)
对比 5 个时点:
  - 6/15 (Baseline, 沃什+FOMC 前)
  - 6/16 (沃什传闻)
  - 6/17 (沃什提名 + FOMC 决议)  ← 红色高亮
  - 6/18 (次日消化)
  - 6/23 (最新, 持续重定价)

输出: D:\\liquidity-dashboard\\v3.5\\data\\历史数据\\sr3_warsh_fomc_repricing_Z26_M27.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HIST_DIR = Path(r"D:\liquidity-dashboard\v3.5\data\历史数据")
SRC_CSV = HIST_DIR / "100-CME_DL_SR3H2027_1D_fixed.csv"

# 事件窗口 + 标签 + 颜色 + 标注
POINTS = [
    ("2026-06-15", "Baseline (6/15 周一)",      "#7f7f7f", "o", 6,  1.4),
    ("2026-06-16", "6/16 沃什传闻",             "#1f77b4", "s", 6,  1.4),
    ("2026-06-17", "6/17 沃什提名+FOMC 决议",   "#d62728", "*", 14, 2.6),
    ("2026-06-18", "6/18 次日消化",             "#ff7f0e", "^", 7,  1.6),
    ("2026-06-23", "6/23 最新 (持续重定价)",    "#2ca02c", "D", 7,  1.6),
]

# X 轴合约 (Z26 -> H27 -> M27)
CONTRACTS = ["SR3Z2026", "SR3H2027", "SR3M2027"]
CONTRACT_LABELS = {
    "SR3Z2026": "Z26\nDec'26",
    "SR3H2027": "H27\nMar'27",
    "SR3M2027": "M27\nJun'27",
}

BASELINE_DATE = "2026-06-15"  # 用于计算 bp 变化


def main() -> int:
    df = pd.read_csv(SRC_CSV)
    df["date"] = df["date"].astype(str)

    fig, ax = plt.subplots(figsize=(12, 7.5))

    # 先获取 baseline 值用于标注 bp 变化
    baseline_row = df[df["date"] == BASELINE_DATE]
    if baseline_row.empty:
        print(f"[WARN] baseline {BASELINE_DATE} 不存在")
        return 1
    baseline_vals = {c: float(baseline_row.iloc[0][c]) for c in CONTRACTS}

    all_vals = []
    for date_str, label, color, marker, ms, lw in POINTS:
        row = df[df["date"] == date_str]
        if row.empty:
            print(f"[WARN] {date_str} 不存在, 跳过")
            continue
        row = row.iloc[0]
        rates = [float(row[c]) for c in CONTRACTS]
        all_vals.extend(rates)
        x = list(range(len(CONTRACTS)))
        ax.plot(x, rates, marker=marker, markersize=ms, linewidth=lw,
                label=label, color=color, alpha=0.9)

        # 在每个点上标注 bp 变化 (相对 baseline)
        for i, c in enumerate(CONTRACTS):
            bp_change = (rates[i] - baseline_vals[c]) * 100  # % -> bp
            if abs(bp_change) < 0.5:
                continue
            sign = "+" if bp_change > 0 else ""
            # 标注位置: 稍微偏移
            offset_y = 0.012 if bp_change > 0 else -0.018
            ax.annotate(f"{sign}{bp_change:.1f}bp",
                        xy=(i, rates[i]),
                        xytext=(i + 0.08, rates[i] + offset_y),
                        fontsize=8, color=color, fontweight="bold",
                        arrowprops=None)

    ax.set_xticks(range(len(CONTRACTS)))
    ax.set_xticklabels([CONTRACT_LABELS[c] for c in CONTRACTS], fontsize=12)
    ax.set_xlabel("SR3 合约 (远端: 2026-12 → 2027-06)", fontsize=12)
    ax.set_ylabel("远期利率 (%)", fontsize=12)
    ax.set_title("沃什提名 + FOMC 事件窗口: SR3 远端如何重定价\n"
                 "(相对 6/15 baseline 的 bp 变化标注)",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="upper left", fontsize=10, framealpha=0.95)
    ax.grid(True, alpha=0.3, linestyle="--")

    if all_vals:
        ymin, ymax = min(all_vals), max(all_vals)
        pad = (ymax - ymin) * 0.18 if ymax > ymin else 0.1
        ax.set_ylim(ymin - pad, ymax + pad)

    plt.tight_layout()
    out_png = HIST_DIR / "sr3_warsh_fomc_repricing_Z26_M27.png"
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"已保存: {out_png}")

    # 同时输出事件窗口数据表
    csv_out = HIST_DIR / "sr3_warsh_fomc_repricing_Z26_M27.csv"
    rows = []
    for date_str, label, *_ in POINTS:
        row = df[df["date"] == date_str]
        if row.empty:
            continue
        r = row.iloc[0]
        rec = {"date": date_str, "event": label.split(" ", 1)[1] if " " in label else label}
        for c in CONTRACTS:
            v = r[c]
            rec[c] = float(v) if pd.notna(v) else None
            rec[f"{c}_vs_baseline_bp"] = round((float(v) - baseline_vals[c]) * 100, 1) if pd.notna(v) else None
        rows.append(rec)
    out_df = pd.DataFrame(rows)
    out_df.to_csv(csv_out, index=False)
    print(f"数据表: {csv_out}")
    print()
    print(out_df.to_string(index=False))

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
