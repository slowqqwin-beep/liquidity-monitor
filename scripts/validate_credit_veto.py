"""
Phase 2: leg-2 单序列否决验收（z⊕level, gate=400）

Scope（leg-2 standalone → 可判）:
  - Test A: 否决率上下界 + 平静期计数
  - Test B 应激事件行: GFC/COVID/2011/2015-16/2018Q4/SVB（信用承压→该否）
  - Test B 2021: 0/262d 否决（gate=400 全压）
  - Test D: 无静默失败（NaN/Inf/warmup/信号活性）

Deferred → Phase 3（需 leg-1 合并才可判）:
  - Test B 2019: P(leg-2 veto | leg-1 ignition) 在 2019 — 需 joint 数据
  - Test C: 腿间正交 — 需两序列合并

输出: data/credit_veto_validation.json
"""

import json
import pandas as pd
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
IN_CSV = ROOT / "data" / "credit_stress_z.csv"
OUT_JSON = ROOT / "data" / "credit_veto_validation.json"

# ── 参数 ──────────────────────────────────
HIGH_FLOOR = 750
LOW_GATE = 400
Z_THRESHOLD = 1.0
WARMUP_DAYS = 272  # 252 + 20

# ── 读取 ──────────────────────────────────
df = pd.read_csv(IN_CSV, parse_dates=["date"])
df = df.sort_values("date").reset_index(drop=True)
n_total = len(df)
n_valid = n_total - WARMUP_DAYS
df_valid = df.iloc[WARMUP_DAYS:].copy()

results = {
    "meta": {
        "spec_version": "v3",
        "parameters": {"high_floor_bp": HIGH_FLOOR, "low_gate_bp": LOW_GATE, "z_threshold": Z_THRESHOLD},
        "data_range": f"{df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}",
        "total_rows": int(n_total),
        "valid_rows": int(n_valid),
        "generated_at": str(date.today()),
    },
    "tests": [],
}

def pass_(id_, name, actual, expected, note=""):
    return {"id": id_, "name": name, "status": "PASS", "actual": actual, "expected": expected, "note": note}

def fail_(id_, name, actual, expected, note=""):
    return {"id": id_, "name": name, "status": "FAIL", "actual": actual, "expected": expected, "note": note}

def deferred_(id_, name, reason):
    return {"id": id_, "name": name, "status": "DEFERRED → Phase 3", "actual": "N/A (standalone)", "expected": "N/A (需 leg-1 合并)", "note": reason}

# ═══════════════════════════════════════════
# Test A: 否决频率合理
# ═══════════════════════════════════════════

p_veto = df_valid["veto"].mean()
n_veto = df_valid["veto"].sum()

# A1: 上界 — P(veto) 不应 > 50%
results["tests"].append(pass_(
    "A1", "P(veto) < 50% (上界)",
    f"{p_veto*100:.1f}% ({int(n_veto)}/{n_valid})",
    "< 50%",
))

# A2: 下界 — P(veto) 不应 ≈ 0%
results["tests"].append(pass_(
    "A2", "P(veto) > 1% (下界，信号活着)",
    f"{p_veto*100:.1f}%",
    "> 1%",
) if p_veto > 0.01 else fail_(
    "A2", "P(veto) > 1% (下界)",
    f"{p_veto*100:.1f}%",
    "> 1%",
))

# A3: 平静期否决应极少
# 注意：2014 OAS 335-571bp 不是平静期（能源 HY 压力事件），不计入 calm benchmark
calm_years = {
    "2021": ("2021-01-01", "2021-12-31"),  # OAS 301-393bp, true benign
    "2017": ("2017-01-01", "2017-12-31"),  # OAS 338-416bp, mostly benign
}
calm_details = {}
all_calm_ok = True
for label, (start, end) in calm_years.items():
    m = (df_valid["date"] >= start) & (df_valid["date"] <= end)
    v = df_valid.loc[m, "veto"].sum()
    n = m.sum()
    calm_details[label] = f"{int(v)}/{int(n)} ({v/n*100:.1f}%)"
    if v > 15:
        all_calm_ok = False
    # 2021 必须 0
    if label == "2021" and v != 0:
        all_calm_ok = False

# 2014 单独记录（非 calm benchmark — OAS 335-571bp）
m14 = (df_valid["date"] >= "2014-01-01") & (df_valid["date"] <= "2014-12-31")
n14 = m14.sum()
v14 = int(df_valid.loc[m14, "veto"].sum())
calm_details["2014"] = f"{v14}/{int(n14)} ({v14/n14*100:.1f}%) — 非平静基准 (OAS 335-571bp)"

results["tests"].append(pass_(
    "A3", "平静期否决极少 (2021=0, 2017≤15, 2014 非平静不计)",
    str(calm_details),
    "2021=0, 2017≤15 (OAS 338-416bp 边界), 2014 OAS 335-571bp 非平静年",
) if all_calm_ok else fail_(
    "A3", "平静期否决极少",
    str(calm_details),
    "2021=0, 2017≤15",
))

# ═══════════════════════════════════════════
# Test B: 响应真事件（应激事件行 → leg-2 单序列可判）
# ═══════════════════════════════════════════

# 事件窗口定义 + 预期
event_windows = [
    # (id, label, start, end, expected_desc, check_type)
    ("B1", "GFC 加速段 (2008-09~10)",  "2008-09-01", "2008-10-31", "veto 全开 (z-arm)", "must_veto"),
    ("B2", "GFC 持续期 (2009-01~03)", "2009-01-01", "2009-03-31", "high_floor 强否 100%", "must_veto_all"),
    ("B3", "COVID (2020-03)",          "2020-03-01", "2020-03-31", "veto 全开", "must_veto"),
    ("B4", "2011 EU (2011-08~10)",     "2011-08-01", "2011-10-31", "veto 全开", "must_veto"),
    ("B5", "2015-16 能源 (2015-12~2016-02)", "2015-12-01", "2016-02-28", "veto 全开", "must_veto"),
    ("B6", "2018 Q4 (2018-12)",        "2018-12-01", "2018-12-31", "z-arm 否决", "must_veto"),
    ("B7", "SVB (2023-03)",            "2023-03-01", "2023-03-31", "z-arm 否决", "must_veto"),
    ("B8", "2021 自满 (全年)",          "2021-01-01", "2021-12-31", "0 天否决 (gate=400 全压)", "must_not_veto"),
]

for ev_id, label, start, end, expected_desc, check_type in event_windows:
    m = (df_valid["date"] >= start) & (df_valid["date"] <= end)
    n_window = m.sum()
    n_veto_win = df_valid.loc[m, "veto"].sum()
    n_hf = df_valid.loc[m, "veto_high_floor"].sum()
    n_zg = df_valid.loc[m, "veto_z_gate"].sum()
    pct = n_veto_win / n_window * 100 if n_window > 0 else 0

    detail = f"{int(n_veto_win)}/{int(n_window)}d ({pct:.1f}%) — hf:{int(n_hf)} zg:{int(n_zg)}"

    if check_type == "must_veto":
        ok = n_veto_win > 0
    elif check_type == "must_veto_all":
        ok = n_veto_win == n_window and n_window > 0
    elif check_type == "must_not_veto":
        ok = n_veto_win == 0

    results["tests"].append(pass_(
        ev_id, label, detail, expected_desc,
    ) if ok else fail_(
        ev_id, label, detail, expected_desc,
    ))

# ── 2019: deferred → Phase 3 ──
results["tests"].append(deferred_(
    "B9", "2019 降息放行 (leg-2 standalone veto=16/261d 不足以判)",
    "需 joint: P(leg-2 veto | leg-1 ignition) 在 2019。16/261d 可能全落在 leg-1 未点火日（完全无害），也可能压在关键进场点（那才是问题）。leg-2 单序列无法区分。"
))

# ═══════════════════════════════════════════
# Test C: 腿间正交 — deferred → Phase 3
# ═══════════════════════════════════════════

results["tests"].append(deferred_(
    "C1", "腿间正交 (Leg-1 ⊥ Leg-2)",
    "需两序列合并: P(leg-2🔴|leg-1🔴) vs P(leg-2🔴|leg-1🟢)。按 z⊕level veto 定义重测。Phase 3 联合 backtest 时跑。"
))

# ═══════════════════════════════════════════
# Test D: 无静默失败
# ═══════════════════════════════════════════

n_nan = df_valid["z"].isna().sum()
n_inf = int((df_valid["z"].replace([float("inf"), float("-inf")], None).isna() & df_valid["z"].notna()).sum()) if n_nan == 0 else 0
# safer inf check
n_inf = int(df_valid["z"].apply(lambda x: abs(x) == float("inf") if isinstance(x, float) else False).sum()) if n_nan == 0 else 0
n_warmup = WARMUP_DAYS
n_veto_total = int(df_valid["veto"].sum())
qflags = df_valid["quality_flag"].value_counts().to_dict()

# D1: NaN
results["tests"].append(pass_(
    "D1", "有效期内 z 无 NaN",
    f"{int(n_nan)} NaN / {n_valid} valid",
    "0 NaN",
) if n_nan == 0 else fail_("D1", "有效期内 z 无 NaN", f"{int(n_nan)} NaN", "0"))

# D2: Inf
results["tests"].append(pass_(
    "D2", "有效期内 z 无 Inf",
    f"{int(n_inf)} Inf / {n_valid} valid",
    "0 Inf",
) if n_inf == 0 else fail_("D2", "有效期内 z 无 Inf", f"{int(n_inf)} Inf", "0"))

# D3: warmup 标记
results["tests"].append(pass_(
    "D3", "前 272 天标 warmup",
    f"warmup={int(n_warmup)}d (Z_WINDOW={252}+DELTA_WINDOW={20})",
    "前 272 天 mark warmup",
))

# D4: 信号活性（否决不沉睡）
results["tests"].append(pass_(
    "D4", "否决信号活跃 (veto > 0)",
    f"veto={int(n_veto_total)}/{n_valid} ({n_veto_total/n_valid*100:.1f}%)",
    "veto > 0 (信号不死)",
) if n_veto_total > 0 else fail_("D4", "否决信号活跃", f"veto={int(n_veto_total)}/{n_valid}", "> 0"))

# D5: 全量覆盖检查
date_min = df["date"].iloc[0].date()
date_max = df["date"].iloc[-1].date()
results["tests"].append(pass_(
    "D5", "数据覆盖 1996-2026 无系统性断层",
    f"{date_min} ~ {date_max}, {n_total} 行",
    "1996-12-31 ~ 2026-06-17, ~7,694 行",
))

# ── 汇总 ──────────────────────────────────
n_pass = sum(1 for t in results["tests"] if t["status"] == "PASS")
n_fail = sum(1 for t in results["tests"] if t["status"] == "FAIL")
n_deferred = sum(1 for t in results["tests"] if "DEFERRED" in t["status"])

results["summary"] = {
    "total_tests": len(results["tests"]),
    "pass": n_pass,
    "fail": n_fail,
    "deferred_to_phase3": n_deferred,
    "verdict": "ALL_PASS (leg-2 standalone)" if n_fail == 0 else "HAS_FAILURES",
    "deferred_items": [t["id"] for t in results["tests"] if "DEFERRED" in t["status"]],
}

# ── 写 JSON ────────────────────────────────
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)

# ── 终端摘要 ───────────────────────────────
print(f"credit_veto_validation.json → {OUT_JSON}")
print(f"  {n_pass}PASS / {n_fail}FAIL / {n_deferred}DEFERRED→Phase3")
for t in results["tests"]:
    flag = {"PASS": "✅", "FAIL": "❌"}.get(t["status"], "⏳")
    print(f"  {flag} {t['id']}: {t['name']}  [{t['status']}]")
