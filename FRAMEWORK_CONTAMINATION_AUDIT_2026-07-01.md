# 2026-07-01 Framework Contamination Audit & Clean v3.5 Paper Trade Reset

## 1. Validated Lineage

| Version | Date | Summary |
|---|---|---|
| v3.0 | 2026-05-25 | Backtest archive (§4 rejected signals) |
| v3.1 | 2026-05-26 | Data foundation patch |
| v3.2 | 2026-05-26 | Evening Task 1-3 |
| v3.5 | 2026-05-27 | Paper trade candidate / drawdown warning reposition |

**LAST VALIDATED VERSION = v3.5**

## 2. Contamination Event: 2026-05-27 → 2026-07-01

### Timeline

| Date | Change | Classification |
|---|---|---|
| 2026-06-15 | Risk OS SSoT v1.0 established | Unvalidated mechanism |
| 2026-06-16 | Orchestrator v2.0, R1-R4 Regime | Unvalidated mechanism |
| 2026-06-17 | VTS three-state interlock | Diagnostic overlay |
| 2026-06-18 | Verdicts fix, §7 charter | Diagnostic overlay |
| 2026-06-19-20 | 2s10s curve structure, DGS2-IORB | Diagnostic overlay |
| 2026-06-21 | SR3 Repair Watch, Real Yield Nowcast z-score | Diagnostic + data fix |
| 2026-06-22 | TLT Leg-2 Phase 1-2 PASS (16/0/2) | Independently validated ✅ |
| 2026-06-23-30 | SR3 Dashboard v7, data source unification | Data engineering |
| 2026-07-01 | Bear Steepening fix, date parse fix | Data engineering |

### Root Cause

1. **Rejected signals re-entered position engine**: DUR5 directional, DFII10>2%, EFFR-IORB>-3bp were all rejected by v3.0 §4 backtest but reappeared in v3.5.1 regime logic
2. **Unvalidated mechanisms stacked**: CASC, VTS, RCV, 双探针 interlock entered production without backtest
3. **Paper trade promise not honored**: The 5/27 commitment to 30-day clean v3.5 paper trade was overridden. CHANGELOG v1.0 states "paper_trade 已废弃，被 risk_dashboard 替代"
4. **Important null was masked**: 5 validated signals all calm (0/5 triggers) → should have recorded "important null", instead v3.5.1 used rejected + unvalidated signals to derive R3/R4

### Evidence

- `_pipeline_snapshots/CHANGELOG.md` v1.0: "paper_trade 已废弃"
- 6/15 daily reports show S_VTS/S_RCV/SSoT in production position chain
- No cross-check evidence found for CASC/VTS/RCV/双探针 before production entry
- Two reports (daily vs dashboard) produced different regimes/positions on same day

## 3. v3.5.1 Component Classification

| Component | Category | Action |
|---|---|---|
| Real Yield Nowcast stale fix | Data engineering | ✅ Keep |
| SR3 Watch Dashboard v7 | Diagnostic overlay | ✅ Keep, mark unvalidated |
| 2s10s / 2s3m curve structure | Diagnostic overlay | ✅ Keep, mark unvalidated |
| CASC 4-leg stress confirmation | Diagnostic overlay | ✅ Keep, mark unvalidated |
| VTS §0.8 term structure | Diagnostic overlay | ✅ Keep, mark unvalidated |
| RCV §0.9 rate curve vol | Diagnostic overlay | ✅ Keep, mark unvalidated |
| 双探针 interlock | Diagnostic overlay | ✅ Keep, mark unvalidated |
| TLT Leg-2 (Phase 1-2) | Independently validated | ✅ Keep as Tier 2 experimental |
| **DUR5 directional confirmation** | **Rejected by v3.0 §4** | ❌ **Permanently ban from position engine** |
| **DFII10 > 2.00% as trigger** | **Rejected by v3.0 §4** | ❌ **Permanently ban from position engine** |
| **5Y5Y > 2.45% as trigger** | **Rejected by v3.0 §4** | ❌ **Permanently ban from position engine** |
| **EFFR-IORB > -3bp as trigger** | **Rejected by v3.0 §4** | ❌ **Permanently ban from position engine** |
| **SSoT Orchestrator auto-position** | **Governance violation** | ❌ **Permanently ban from position engine** |

## 4. Reset Action (2026-07-01)

- ✅ `REJECTED_SIGNALS.md` created with hard constraints
- ✅ `paper_trade_v35.py` created — clean v3.5 signal checker
- ✅ `paper_trade_v3_5_clean.csv` created — ledger
- ✅ 2026-07-01 result: **0/5 triggers, P=55% H=25% C=20%, important null**

Clean v3.5 paper trade **restarts from 2026-07-01 for one month**.

## 5. Future-Claude / Future-CodeBuddy Warning

**Hard constraints — must be verified before any position engine modification:**

```
1. DUR5 directional confirmation → BANNED (v3.0 §4 F1 negative)
2. DFII10 > 2.00% as drawdown predictor → BANNED (Precision 7.7% < baseline)
3. 5Y5Y > 2.45% warning as position driver → BANNED (F1=0.13)
4. EFFR-IORB > -3bp as negative alpha trigger → BANNED (Precision 11.8%)
5. SSoT auto-裁决 replacing clean v3.5 paper trade / human review → BANNED
```

**Red flags to watch for:**
- Complexity ≠ alpha (v3.1→v3.4 stacked 7-8 layers, most backtest-negative)
- AI collaboration ≠ AI verification (SSoT Orchestrator = single-AI closed loop)
- "Engineering consistency passed" ≠ "strategy validity passed"
- CodeBuddy completion pressure can create contamination
- Human-in-the-loop is the real CI
- **Audit current state against last promise before archiving**

## 6. Today's Paper Trade Conclusion

```
Date: 2026-07-01
v3.5 clean signals:
  HY OAS 20dΔ: +8.0bp → OK
  HYG 5d: +0.1% → OK
  FXY 5d: -0.6% → OK
  SPY vs 200MA: OK
  Extreme Meltdown: OK
  Triggers: 0/5
  Position: P=55% H=25% C=20%
  Verdict: IMPORTANT NULL — no trigger fired, market calm
```

**v3.5.1 给出的 R4/P25-H45-C30 只能作为污染事件样本，不得作为有效 paper trade 仓位。**

---

## 7. §44: 2026-06-10 Audit Failure Mode

The 2026-06-10 audit (`us_abcd_v35_audit_2026-06-10.md`) was technically high
quality — it correctly fixed Reserve units, HY OAS arrows, VTS dual-ratio
extraction, CASC FX column semantics, Mortgage stale labeling, and letter
collision. **But it audited the wrong object.**

| What 06-10 audited | What it should have audited |
|---|---|
| Display correctness of v3.5.1 stack | Strategic validity of v3.5.1 components |
| Rendering bugs (units, arrows, labels) | Whether CASC/VTS/RCV/SSoT should be in position engine |
| Field consistency | Whether 5/25 rejected signals had re-entered |

**CHANGELOG v1.0 (2026-06-10) explicitly states:**
> "paper_trade 已废弃，被 risk_dashboard 替代"

This was not a stealth drift — it was an **explicit strategic replacement**
of the 5/27 paper trade protocol, recorded in CHANGELOG, and then audited
for display correctness rather than strategic validity.

**This is the precise failure point of "engineering consistency ≠ strategy validity."**

### Lesson for future Claude

When CodeBuddy presents a professional-looking audit report, Claude's first
task is NOT to endorse the specific fixes. It is to ask:
1. "What is the scope of this audit?"
2. "Does it challenge strategic validity, or only review rendering/consistency/units?"
3. "Has the audit checked against the last archived promise (5/27 paper trade protocol)?"

---

## 8. §45: TLT Leg-2 — Independently Validated

`docs/tlt_leg2_spec.md` v6 documents the credit veto signal (z⊕level).
`data/credit_veto_validation.json` records **18 tests: 16 PASS / 0 FAIL / 2 DEFERRED**.

| Metric | Result |
|---|---|
| P(veto) | 24.0% (1779/7422 days) |
| GFC 09Q1 | 65/65 days high_floor reject ✅ |
| 2021 false positive | 0/262 days (gate=400 suppressed all noise) ✅ |
| SVB | 43.5% veto rate (weakest, but Phase 3 candidate) |

**Status**: Tier 2 experimental. Phase 1+2 complete (spec + veto validation).
Phase 3 (joint leg test with Leg-1 macro signal) deferred. Phase 4 (production
integration) not started.

TLT Leg-2 is the **only component** in the v3.5.1 stack that passed independent
validation comparable to Task 5 standards. However, it requires Bonferroni
correction before Tier 0 promotion, and it's a TLT-specific signal — not a
general position engine mechanism.

---

## 9. §46: Signal Definition Clarification

The original v3.0 §5 (2026-05-25) defines the 5 validated triggers as:

| Signal | Threshold |
|---|---|
| HY OAS 20d Δ | > +20bp (★★★) |
| FXY 5d | > +2.5% (★★) |
| HY OAS 5d Δ | > +15bp (★) |
| SPY | < 200MA |
| T10YIE | > 2.30% (谨慎, T/X=0.66, not primary trigger) |

**HYG 5d < -1.5%** is a **proxy** calibrated in Task 5.5. It matches
HY OAS 20d Δ > +20bp (not the 5d Δ signal) because BAML OAS has only
3 years of data. The HYG proxy enables 11-year coverage but is not a
separate independent signal.

The clean paper trade ledger must use the BAML-based signals (20d Δ and
5d Δ) as primary, with HYG as a secondary confirmation proxy when BAML
data is available.

---

## 10. §47: New Signal Intake Discipline — The RYS Case (2026-07-01)

The Real Yield Spread diagnostic module was the first new signal proposed
**after** the framework contamination audit. Its intake path serves as a
template for how new ideas enter without becoming contamination.

### 10.1 Intake Timeline

| Step | What happened | Lesson |
|---|---|---|
| 1. Suspicion | "DFII10 being used as regim trigger — isn't that rejected?" | Start from the rejected registry, not from the idea |
| 2. Decomposition | DFII10 → Gordon Growth → RYS = E/P − RF | Don't ban data fields — ban how they're used |
| 3. Spec with guards | §0 (diagnostic only) + §5 (red-flag self-check) | Write constraints before code, not after |
| 4. Implementation | `real_yield_spread_diagnostic.py` | Code against spec, not against "what would be useful" |
| 5. Audit #1 | Threshold leak check — zero violations | Grep for `if RYS >` in non-comment lines |
| 6. Data quality found | "0/5 tickers PE available" — traced to SNOW negative EPS | Insufficient is a valid answer, not a failure |
| 7. Substitution attempted | "Use IGV ETF PE for portfolio" | Same pattern as filling missing growth with market average — caught by §5 |
| 8. Three-tier gradient | CRM/MSFT mature, DDOG/OKTA barely-profitable, SNOW unprofitable | Real structure > clean number |
| 9. Freeze | Diagnostic only, human-read, not in clean ledger | Ship and stop |

### 10.2 Rules Extracted

**What made this intake clean (not contamination):**

1. **Started from REJECTED_SIGNALS.md, not from "this would be useful"**
   The question was "is DFII10 being revived?" not "let's build a real yield dashboard"

2. **Spec had hard guardrails before a single line of code**
   §0: "诊断层,不进 paper trade,不做自动触发器"
   §5: "阈值化/合并分数/编造数据/自动调仓 — 四件事红旗自查"

3. **Every audit round found real issues, none were deflected**
   - Audit #1: growth data was None, not fabricated
   - Audit #2: "0/5 PE" wasn't a bug — it was a genuine finding about the portfolio
   - Audit #3: IGV substitution proposal was correctly identified as the same pattern §1.3 forbids
   - Audit #4: "双峰" was imprecise; "三段梯度" is structurally correct

4. **Never entered the position engine or paper trade ledger**
   No path from RYS to any position decision exists in the code

**What would have made this intake contaminated:**

- Adding `if RYS < 0: flag = "equity expensive"`
- Merging RYS and 2s10s into a "monetary conditions index"
- Filling missing PE with sector average
- Writing `RYS_portfolio` into `paper_trade_v3_5_clean.csv`
- Calling it "v3.6 candidate" and slipping it into daily report output

### 10.3 Template for Future Intake

When a new signal or diagnostic is proposed:

```
1. Check REJECTED_SIGNALS.md — is this a renamed version of something rejected?
2. Write spec with §0 (scope) + §5 (red flags) BEFORE code
3. Implement against spec, not against usefulness
4. Audit: grep for threshold comparisons, composite scores, data fabrication
5. Test data quality edge case (force missing data, verify "insufficient" not "average")
6. Freeze — diagnostic only, human-read, no position authority
7. Archive the intake as §N+1 in this document
```

**The RYS case proves: new ideas don't need to "look useful" to get in.**
They need to survive being taken apart. If they survive, they enter clean.

The opposite — "it works, let's activate it" — is exactly how 6/10-6/15 happened.

---

## 11. §48: Clean Ledger Deep Audit — The July 2 Round (2026-07-02)

### 11.1 Trigger

The audit began with a single question: "Is HYG 5d < -1.5% in the clean v3.5
paper trade actually the signal §40 locked, or has the DFII10 contamination
pattern recurred under a different name?"

It was not. The discovery cascaded into the largest bug-hunt in this project's
history.

### 11.2 Bugs Found

| # | Bug | Location | Originally Showed | Root Cause |
|---|-----|----------|------------------|------------|
| 1 | Signal #2 used HYG 5d < -1.5%, not HY OAS 5dΔ > +15bp | `paper_trade_v35.py:55` | "OK" (benign by coincidence) | Wrong signal definition from first version |
| 2 | SPY data key was "SP500" (doesn't exist in series.json) | `paper_trade_v35.py:32` | "OK" (silently returned None→False) | Key mismatch, never tested against actual data |
| 3 | VIX data key was "VIX" (doesn't exist; actual key is "VIXCLS") | `paper_trade_v35.py:45` | "OK" (silently returned None) | Same key mismatch pattern |
| 4 | fetch_data ran before FRED BAML T+1 posting | Pipeline timing | 7/1 20dΔ=8.0bp (should be 4.0bp) | No BAML freshness check; fetch ran too early |

**Critical pattern**: Bugs #2, #3, and the first version of #1 all produced
"OK" not because conditions weren't met, but because data couldn't be read.
The system silently collapsed "unknown" into "benign zero" — the exact failure
mode warned about in §41's "未知状态坍缩为良性零" principle. This wasn't a
theoretical risk — it was found operating in production.

### 11.3 Rebuild Script Defect

The `_final.py` rebuild script computed both 7/1 and 7/2 rows with the same
`idx=-1` parameter, producing identical row content for two different dates.
VIX=16.45 being identical on consecutive days was the smoking gun that exposed
this. Fixed by independent recomputation for each date.

### 11.4 Schema Violation

`HYG_5d_pct` was present in the CSV schema despite not appearing in the §40
field list. §40 describes HYG 5d only as a proxy fallback for the 20d signal
(BAML data gaps), not as a schema column. Removed.

### 11.5 New Guards Deployed

| Guard | Mechanism | Verified? |
|---|---|---|
| BAML freshness check | Added to daily_report.py `stale_warnings`. Lags >1 business day trigger warning. | ✅ Replayed 7/1 scenario — `_biz_days_between(06-29, 07-01)=2` would have fired |
| Banned pattern blocker | `scripts/_check_banned_patterns.py` hooks into both `daily_report.py` and `generate_risk_dashboard.py`. `sys.exit(1)` on detection. | ✅ Injected "SSoT 唯一裁决" into live output — exit=1 confirmed |
| as_of_date reproducibility | `n_day_chg()` and `pct_5d()` now accept `as_of_idx` parameter. Default -1 preserves backward compatibility. Historical backfills can specify exact data cutoffs. | ✅ Default behavior unchanged; parameter available for backfills |
| DEPRECATED function naming | `read_ssot_position` → `DEPRECATED_TIER3_read_ssot_position`. Zero residual callers confirmed by grep. | ✅ Grep verified |

### 11.6 Methodology Crystallized

This round produced the most rigorous audit trail in the project's history.
The pattern was consistent:

1. **Suspicion** → "Is X actually what it claims to be?"
2. **Decompose** → Break the claim into falsifiable sub-questions
3. **Demand raw evidence** → Not summaries, not "logic says it should work," but actual terminal output, actual CSV rows, actual grep results
4. **Test edge cases** → Inject banned patterns, replay historical scenarios, force data gaps

The round itself demonstrated the method: it took three attempts before the
"raw CSV content" was actually raw terminal output rather than a description
of it. The process caught its own evidence gap — proving the method works
even when the operator stumbles.

### 11.7 Key Principle

**"当时对" and "现在核对后对" are different things.**

7/1's 0/5 trigger count was correct in net, but 3 of 5 signals were computed
wrong (HYG instead of HY_OAS, null SPY key, null VIX key). The conclusion
happened to survive the bugs, but the ledger now records that it did so by
accident, not by design.

### 11.8 Files Modified

| File | Changes |
|---|---|
| `paper_trade_v35.py` | Signal #2 fixed (HYG→HY_OAS), #4 key (SP500→SPY), #5 key (VIX→VIXCLS), HYG_5d_pct removed, as_of_idx support, DEPRECATED prefix |
| `daily_report.py` | Position table removed, SSoT computation stopped, DEPRECATED prefix, column headers de-positionified, BAML freshness check, banned check auto-run |
| `generate_risk_dashboard.py` | P/H/C removed from header/table/PNG, position row removed, verdicts de-positionified, banned check auto-run |
| `scripts/_check_banned_patterns.py` | Created — P/H/C, SSoT, DUR5, HYG 5d pattern detection, blocking mode |
| `paper_trade_v3_5_clean.csv` | Rebuilt — all 5 signals from correct keys, 7/1 audit trail, BAML lag note, known gaps recorded, HYG_5d_pct removed |
| `FRAMEWORK_CONTAMINATION_AUDIT_2026-07-01.md` | §44-§47 added (6/10 audit failure mode, TLT Leg-2, signal definitions, RYS intake) |
