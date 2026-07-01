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

| # | Signal | Trigger |
|---|---|---|
| 1 | HY OAS 20dΔ > +20bp | Drawdown Warning |
| 2 | HYG 5d < -1.5% | Credit stress |
| 3 | FXY 5d > +2.5% | FX risk |
| 4 | SPY < 200MA | Trend break |
| 5 | Extreme Meltdown (VIX>35 + SOFR-IORB>5bp) | Systemic |

## Mechanism Tier Classification

| Tier | Authority | Examples |
|---|---|---|
| Tier 0 | Position engine (validated) | v3.5 5 signals |
| Tier 1 | Diagnostic only | CASC, VTS, RCV, SR3 Watch |
| Tier 2 | Experimental (requires backtest) | Real Yield Nowcast, 双探针 |
| Tier 3 | Rejected / Forbidden | DUR5, DFII10>2%, 5Y5Y>2.45%, EFFR-IORB>-3bp |
| - | Unvalidated (pending) | SSoT Orchestrator, Risk OS State Machine |
