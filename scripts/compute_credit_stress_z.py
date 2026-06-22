"""
Phase 1: credit_stress_z + z⊕level veto 计算
输入：data/BAMLH0A0HYM2_tv_full.csv
输出：data/credit_stress_z.csv

Spec: docs/tlt_leg2_spec.md v3
  low_gate = 400bp, high_floor = 750bp, z threshold = +1.0
"""

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_CSV = ROOT / "data" / "BAMLH0A0HYM2_tv_full.csv"
OUT_CSV = ROOT / "data" / "credit_stress_z.csv"

# ── 参数 ──────────────────────────────────
HIGH_FLOOR = 750   # bp — 强制否决
LOW_GATE = 400      # bp — z-arm 门槛
Z_THRESHOLD = 1.0   # z > 1.0 否决
DELTA_WINDOW = 20   # 日 — Δ20
Z_WINDOW = 252      # 日 — μ/σ 滚动窗

# ── 读取 ──────────────────────────────────
df = pd.read_csv(IN_CSV, parse_dates=["date"])
df["hy_oas_bp"] = (df["hy_oas_pct"] * 100).round(1)

# ── Δ20 ───────────────────────────────────
df["delta20"] = df["hy_oas_bp"].diff(DELTA_WINDOW)

# ── z-score (rolling μ/σ of Δ20) ──────────
rolling_mean = df["delta20"].rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
rolling_std = df["delta20"].rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
df["z"] = ((df["delta20"] - rolling_mean) / rolling_std).round(4)

# ── z⊕level veto ──────────────────────────
df["veto_high_floor"] = df["hy_oas_bp"] >= HIGH_FLOOR
df["veto_z_gate"] = (df["z"] > Z_THRESHOLD) & (df["hy_oas_bp"] >= LOW_GATE)
df["veto"] = df["veto_high_floor"] | df["veto_z_gate"]

# ── 标记不可用区间（前 Z_WINDOW + DELTA_WINDOW 天无有效 z/μ/σ） ──
warmup_days = Z_WINDOW + DELTA_WINDOW
df["quality_flag"] = ""
df.loc[: warmup_days - 1, "quality_flag"] = "warmup"
df.loc[df["veto"].isna(), "quality_flag"] = "nan_veto"  # 不应发生

# ── 输出 ──────────────────────────────────
df_out = df[["date", "hy_oas_bp", "delta20", "z",
             "veto_high_floor", "veto_z_gate", "veto", "quality_flag"]]
df_out.to_csv(OUT_CSV, index=False, date_format="%Y-%m-%d")

# ── 摘要 ──────────────────────────────────
n = len(df_out)
n_warmup = warmup_days
n_valid = n - n_warmup
n_veto = df_out["veto"].iloc[warmup_days:].sum()
n_hf = df_out["veto_high_floor"].iloc[warmup_days:].sum()
n_zg = df_out["veto_z_gate"].iloc[warmup_days:].sum()
n_nan = df_out["z"].iloc[warmup_days:].isna().sum()

print(f"credit_stress_z + veto 已生成 → {OUT_CSV}")
print(f"  全量: {n} 行  |  预热: {warmup_days} 天 (前 {Z_WINDOW}+{DELTA_WINDOW})  |  有效: {n_valid} 天")
print(f"  z 有效期间 NaN 行: {n_nan}")
print(f"  veto=TRUE: {n_veto} 天 ({n_veto/n_valid*100:.1f}%)")
print(f"    high_floor 臂: {n_hf} 天")
print(f"    z_gate 臂:    {n_zg} 天")
print(f"  参数: high_floor={HIGH_FLOOR}bp  low_gate={LOW_GATE}bp  z>{Z_THRESHOLD}")
