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
