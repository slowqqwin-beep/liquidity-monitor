window.SR3_DATA = {
  "generated_at": "2026-06-23T17:10:29.897439",
  "data_date": "2026-06-23",
  "reference_peak": "formal shock",
  "status": "Research-Only",
  "state": "State 2: Deceleration",
  "state_note": "短端预期：全线合约低于参考峰（结构松动），但动能信号仍在鹰派区；结构性下降领先",
  "hawkish_impulse": false,
  "deceleration": true,
  "deceleration_since": "2026-06-22",
  "level_repair": false,
  "classification": "structural_easing",
  "classification_reason": "全线合约低于参考峰(2026-06-09)，但 5日累计仍正向 — 结构松动先于动能",
  "repair": false,
  "repair_start_date": null,
  "repair_magnitude_bp": 0.0,
  "mixed_repair_warning": "",
  "near_rate": 3.79,
  "drawdown_from_peak_bp": -8.0,
  "daily_change_bp": -2.88,
  "five_day_change_bp": 10.38,
  "high_plateau": true,
  "hy_oas": 266.0,
  "dgs10": 4.46,
  "real_yield_nowcast": 2.23,
  "constraints": {
    "research_only": true,
    "standalone_sr3_watch": true,
    "no_risk_os": true,
    "no_existing_dashboard_merge": true,
    "no_run_all": true,
    "no_position_impact": true,
    "deceleration_not_buy_signal": true
  },
  "reference_peaks": [
    {
      "source": "Formal Shock",
      "date": "2026-06-09",
      "distance": "10d",
      "near_rate": 3.71,
      "height": "8.0bp"
    },
    {
      "source": "Recent 60d Peak",
      "date": "2026-06-22",
      "distance": "1d",
      "near_rate": 3.8025,
      "height": "—"
    }
  ],
  "signal_matrix": [
    {
      "condition": "信用不扩 + SR3 钝化",
      "meaning": "鹰派动能衰竭，但短端预期尚未回落"
    },
    {
      "condition": "信用不扩 + SR3 level repair + real yield 不再创新高",
      "meaning": "短端预期已明显回落，信用未恶化"
    },
    {
      "condition": "信用不扩 + SR3 benign repair + 分子兑现",
      "meaning": "软着陆情景：利率回落 + 信用收窄"
    },
    {
      "condition": "SR3 钝化但不修复",
      "meaning": "暂停后利率继续上行，不构成拐点信号"
    }
  ],
  "curve_comparison": [
    {
      "date": "2026-06-16",
      "label": "2026-06-16",
      "rates": {
        "Z2026": 3.885,
        "H2027": 3.6675,
        "M2027": 3.94
      }
    },
    {
      "date": "2026-06-17",
      "label": "2026-06-17",
      "rates": {
        "Z2026": 4.035,
        "H2027": 3.7,
        "M2027": 4.08
      }
    },
    {
      "date": "2026-06-18",
      "label": "2026-06-18",
      "rates": {
        "Z2026": 4.095,
        "H2027": 3.715,
        "M2027": 4.11
      }
    },
    {
      "date": "2026-06-22",
      "label": "2026-06-22",
      "rates": {
        "Z2026": 4.125,
        "H2027": 3.72,
        "M2027": 4.175
      }
    },
    {
      "date": "2026-06-23",
      "label": "2026-06-23",
      "rates": {
        "Z2026": 4.075,
        "H2027": 3.7125,
        "M2027": 4.125
      }
    }
  ],
  "curve_bp_changes": [
    {
      "label": "Z2026 (2026-06-16→2026-06-23)",
      "bp_change": 19.0
    },
    {
      "label": "H2027 (2026-06-16→2026-06-23)",
      "bp_change": 4.5
    },
    {
      "label": "M2027 (2026-06-16→2026-06-23)",
      "bp_change": 18.5
    }
  ],
  "curve_warning": null,
  "contract_diffs": [
    {
      "contract": "SR3N2026",
      "close": 96.21,
      "close_chg": 0.0125,
      "implied_rate_pct": 3.79,
      "implied_chg_bp": -1.25
    },
    {
      "contract": "SR3Q2026",
      "close": 96.135,
      "close_chg": 0.015,
      "implied_rate_pct": 3.865,
      "implied_chg_bp": -1.5
    },
    {
      "contract": "SR3U2026",
      "close": 96.075,
      "close_chg": 0.04,
      "implied_rate_pct": 3.925,
      "implied_chg_bp": -4.0
    },
    {
      "contract": "SR3Z2026",
      "close": 95.925,
      "close_chg": 0.05,
      "implied_rate_pct": 4.075,
      "implied_chg_bp": -5.0
    },
    {
      "contract": "SR3H2027",
      "close": 96.2875,
      "close_chg": 0.0075,
      "implied_rate_pct": 3.7125,
      "implied_chg_bp": -0.75
    },
    {
      "contract": "SR3M2027",
      "close": 95.875,
      "close_chg": 0.05,
      "implied_rate_pct": 4.125,
      "implied_chg_bp": -5.0
    },
    {
      "contract": "SR3U2027",
      "close": 95.93,
      "close_chg": 0.045,
      "implied_rate_pct": 4.07,
      "implied_chg_bp": -4.5
    }
  ]
};