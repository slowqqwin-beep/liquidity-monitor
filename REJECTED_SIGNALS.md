# Rejected Signal Registry

Per v3.0 §4 backtest (2026-05-25), the following signal thresholds are **rejected**
and must NOT enter any position engine, paper trade, or drawdown trigger.

| Signal | Threshold | v3.0 §4 Verdict | Notes |
|---|---|---|---|
| DUR5 directional confirmation | 5/5 count | F1 negative impact | Precision < baseline |
| DFII10 > 2.00% | drawdown predictor | Precision 7.7% < 17.2% baseline | Reverse indicator |
| 5Y5Y > 2.45% warning | position driver | F1=0.13 | Statistically null |
| EFFR-IORB > -3bp | negative alpha trigger | Precision 11.8% | Reverse indicator |

## Validated v3.5 Signals (paper trade approved)

Per v3.0 §5 original definition (5/25):

| # | Signal | Trigger | F1 | Role |
|---|---|---|---|---|
| 1 | HY OAS 20d Δ > +20bp | Drawdown Warning | 0.23→0.43 (★★★) | Primary drawdown signal |
| 2 | FXY 5d > +2.5% | FX risk | 0.27→0.67 (★★) | D-end cross-border |
| 3 | HY OAS 5d Δ > +15bp | Credit stress (short-term) | 0.21→0.37 (★) | Supplementary |
| 4 | SPY < 200MA | Trend break | 0.43→0.30 | Technical baseline |
| 5 | T10YIE > 2.30% (谨慎) | Inflation expectations | 0.41→0.27 (T/X=0.66) | Narrative, not primary trigger |
| -- | Extreme Meltdown 5 项 | Systemic | Circuit breaker only | 不进入日常信号计数 |

**Note on HYG 5d < -1.5%**: This is a **proxy** calibrated in Task 5.5 to match HY OAS 20d Δ > +20bp
(because BAML OAS has only 3 years of data). The HYG proxy provides 11-year coverage but
is NOT a separate independent signal. The primary signal is HY OAS 20d Δ > +20bp.

## Mechanism Tier Classification

| Tier | Authority | Examples |
|---|---|---|
| Tier 0 | Position engine (validated) | v3.5 5 signals (above) |
| Tier 1 | Diagnostic overlay (unvalidated) | CASC, VTS, RCV, SR3 Watch, Real Yield Nowcast |
| Tier 2 | Experimental (requires backtest + Bonferroni + robustness) | TLT Leg-2 Phase 3 (16/0/2, Phase 4 pending) |
| Tier 3 | Rejected / Forbidden | DUR5, DFII10>2%, 5Y5Y>2.45%, EFFR-IORB>-3bp |

### Tier 3 — Governance Violation (structural rejection)

These are **structurally forbidden**, not "pending backtest":

| Mechanism | Reason |
|---|---|
| SSoT auto-裁决 | Single-AI closed loop, replaces human review |
| Risk OS Orchestrator auto regime→position mapping | No human-in-the-loop, unvalidated regime buckets |

These will NOT become valid even if future backtests show statistical significance,
because they violate the governance requirement of human-in-the-loop final decision.

## Enforcement (2026-07-01)

Any future version (v3.x.y) or new module that reintroduces a Tier 3 rejected
mechanism — regardless of renaming, repackaging, or "improvement" claims —
is **automatically rejected**.

### Renaming detection

The following are the same rejected mechanism under different names:
- "DUR5" → "confirmation counter" / "N-day filter" / "persistent trigger"
- "DFII10 > 2%" → "real yield threshold" / "high-rate regime" / "贴现率压力"
- "5Y5Y > 2.45%" → "inflation anchor warning" / "长期通胀锚警戒"
- "EFFR-IORB > -3bp" → "funding stress" / "资金管道偏紧"
- "SSoT auto-裁决" → "Orchestrator" / "state machine" / "unified verdict" / "唯一裁决"

### Reintroduction barrier

If CodeBuddy proposes reintroducing a rejected mechanism with justification
"new backtest supports it", the **minimum** evidence required is:

1. Bonferroni-corrected p < 0.001 (not p < 0.05)
2. 11-year full sample (not subset)
3. First-half / second-half robustness (both halves independently significant)
4. Claude (not CodeBuddy) cross-check of methodology
5. Human user explicit approval (not "looks good, proceed")

Without ALL five: **automatic rejection. No exception.**

### Hard constraint — paste first line in every position-code conversation

```
硬约束清单 (5/25 backtest 已证伪, 禁止进入 position engine):
1. DUR5 directional confirmation — F1 negative
2. DFII10 > 2.00% as drawdown predictor — Precision 7.7% < baseline
3. 5Y5Y > 2.45% warning as position driver — F1 = 0.13
4. EFFR-IORB > -3bp as negative alpha trigger — Precision 11.8%
5. SSoT auto-裁决取代 clean v3.5 paper trade / human review

违反任一条 = 立即停止, 不要 "改进" 或 "修复"; 报告违规并等待指令.
```
