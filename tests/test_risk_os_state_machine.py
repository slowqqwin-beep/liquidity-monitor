# -*- coding: utf-8 -*-
"""
test_risk_os_state_machine.py — SSoT 审计修复 F1-F4 正向测试
=============================================================
覆盖 8 个用例，保护 v3.5 审计修复成果：

  F3-1: EFFR_IORB 缺失 → d5=None, t2_determinable=False, T2 "无法判定"
  F3-2: EFFR_IORB 正常 → d5 按序计算, t2_determinable=True, T2 正常判定
  F2-1: FRED 序列缺失 → data_degraded=True, confidence != high
  F2-2: FRED 序列过期 >5d → data_degraded=True, stale_series 非空
  F2-3: 全部数据新鲜 → confidence=high, data_degraded=False
  F4-1: 数据降级 → regime 标记 ⚠️, judgement 含数据不足
  F4-2: 数据正常 → regime 无标记, judgement 含数据不足
  F5: R4 死代码已消除 → red_count>=2 映射 R4，>=3 不再存在

运行: uv run pytest tests/test_risk_os_state_machine.py -v
"""

from __future__ import annotations

import copy
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.risk_os_state_machine import (
    assess_data_quality,
    compute_transmission,
    compute_triggers,
    compute_rate_shock,
    compute_nowcast,
    run_orchestrator,
    assemble,
    EFFR_IORB_THRESHOLD,
    EFFR_IORB_DUR5_MIN,
    DFII10_THRESHOLD,
    HY_OAS_THRESHOLD,
)


# ══════════════════════════════════════════════════════════════════════
#  Fixtures — 构造最小可行 raw dict
# ══════════════════════════════════════════════════════════════════════

TODAY = "2026-06-20"

def _make_point(value, date_str=None):
    """构造单个数据点 {"value": ..., "date": ...}"""
    return {"value": value, "date": date_str or TODAY}


def _make_series(values_with_dates):
    """构造系列 [{"value": v, "date": d}, ...]"""
    return [_make_point(v, d) for v, d in values_with_dates]


def _fresh_raw():
    """构造一个全部数据新鲜、信号平静的 raw dict 基线。

    基线状态：VIX~18, MOVE~100, HY OAS~250, DFII10~1.5, EFFR-IORB~-10, SOFR~IORB.
    所有数据日期 = TODAY，全部正常——不应该触发任何红/橙色信号。
    """
    return {
        # Yahoo
        "^VIX":    _make_series([(18.0, TODAY), (17.5, "2026-06-19")]),
        "^VIX3M":  _make_series([(19.0, TODAY)]),
        "^VIX9D":  _make_series([(17.0, TODAY)]),
        "FXY":     _make_series([(100.0, TODAY)]),
        "HYG":     _make_series([(76.0, TODAY)]),
        "SPY":     _make_series([(580.0, TODAY)]),
        "^TNX":    _make_series([(4.2, TODAY)]),

        # FRED / market
        "DGS2":    _make_series([(4.40, TODAY)]),
        "DGS10":   _make_series([(4.35, TODAY)]),
        "DFII10":  _make_series([(1.44, "2026-06-13"), (1.45, "2026-06-16"),
                                  (1.46, "2026-06-17"), (1.47, "2026-06-18"),
                                  (1.48, "2026-06-19"), (1.50, TODAY)]),
        "T10YIE":  _make_series([(2.40, TODAY)]),
        "EFFR":    _make_series([(4.38, TODAY)]),
        "IORB":    _make_series([(4.40, TODAY)]),
        "SOFR":    _make_series([(4.40, TODAY)]),
        "VIXCLS":  _make_series([(18.0, TODAY)]),
        "MOVE":    _make_series([(100.0, TODAY)]),
        "BAMLH0A0HYM2": _make_series([(2.45, "2026-06-04"), (2.50, TODAY)]),
        "BAMLC0A0CM":   _make_series([(1.20, TODAY)]),

        # Derived (computed by pipeline, present in series.json)
        # IMPORTANT: latest date must be LAST element (assess_data_quality reads _ld)
        "EFFR_IORB": _make_series([(-1.0, "2026-06-13"), (-1.3, "2026-06-16"),
                                   (-1.5, "2026-06-17"), (-1.8, "2026-06-19"),
                                   (-2.0, TODAY)]),
    }


# ══════════════════════════════════════════════════════════════════════
#  F3: EFFR_IORB 派生序列缺失 → T2 "无法判定" (非静默 False)
# ══════════════════════════════════════════════════════════════════════

class TestF3_EFRR_IORB_Missing:
    """正向：缺数据 → 正确地表达不确定性，而非静默输出安全值。"""

    def test_missing_effr_iorb__d5_is_None_not_zero(self):
        """F3-1: EFFR_IORB缺失 → compute_transmission d5=None, t2_determinable=False"""
        raw = _fresh_raw()
        del raw["EFFR_IORB"]  # 删除派生序列

        rs = {"active": False}
        tx = compute_transmission(raw, rs)

        assert tx["t2_determinable"] is False, \
            "EFFR_IORB缺失时t2_determinable应为False"
        assert tx["dur5_effr_iorb"] is None, \
            "缺数据时d5应为None，不是0（不能静默停在安全值）"
        assert tx["dur5_confirmed"] is None, \
            "缺数据时dur5_confirmed应为None"
        assert tx["liquidity_buffer_thinning"] is None, \
            "缺数据时liquidity_buffer_thinning应为None（无法判定），不是False"

    def test_missing_effr_iorb__trigger_T2_undeterminable(self):
        """F3-1续: EFFR_IORB缺失 → compute_triggers T2输出"无法判定" """
        raw = _fresh_raw()
        del raw["EFFR_IORB"]

        rs = {"active": False}
        tx = compute_transmission(raw, rs)
        tg = compute_triggers(raw, tx)

        liq = tg["liquidity"]
        assert liq["active"] is False, \
            "数据缺失时T2 active应为False（不能确认触发）"
        assert liq["label"] == "无法判定", \
            f"EFFR_IORB缺失时T2 label应为'无法判定'，实际: {liq['label']}"
        assert "缺失" in liq.get("evidence", ""), \
            f"evidence应标明数据缺失，实际: {liq.get('evidence', '')}"

    def test_normal_effr_iorb__d5_and_dur5_confirmed_correct(self):
        """F3-2: EFFR_IORB正常 → d5按序计算，t2_determinable=True"""
        raw = _fresh_raw()

        # 基线：EFFR_IORB 序列 = [-1.0, -1.3, -1.5, -1.8, -2.0]
        # _dur5 从最新往旧数：-2.0 ≥ -3 ✓, -1.8 ≥ -3 ✓, -1.5 ≥ -3 ✓ → 到第3个break（-1.3 ≥ -3...等，一直≥-3）
        # 实际上全部 5 天都 ≥ -3，所以 d5 = 5（cap at mn=3... wait, _dur5 logic:
        #   cnt goes up to mn=3, then returns mn. So d5 = 3.
        rs = {"active": False}
        tx = compute_transmission(raw, rs)

        assert tx["t2_determinable"] is True
        assert tx["dur5_effr_iorb"] == 3, \
            f"DUR5应为3（连续3天≥EFFR_IORB_THRESHOLD），实际: {tx['dur5_effr_iorb']}"
        assert tx["dur5_confirmed"] is True, \
            "DUR5≥3应确认"
        assert tx["liquidity_buffer_thinning"] is True, \
            f"DUR5≥3应liquidity_buffer_thinning=True，实际: {tx['liquidity_buffer_thinning']}"


# ══════════════════════════════════════════════════════════════════════
#  F2: FRED 序列缺/过期 → confidence 降级
# ══════════════════════════════════════════════════════════════════════

class TestF2_DataQuality:
    """正向：FRED序列缺失或过期 → confidence不能是high。"""

    def test_fred_missing__data_degraded(self):
        """F2-1: FRED序列缺失 → data_degraded=True, confidence=low"""
        raw = _fresh_raw()
        del raw["DGS2"]  # 删除关键FRED序列

        dq = assess_data_quality(raw, TODAY)

        assert dq["data_degraded"] is True, \
            f"缺失FRED序列时data_degraded应为True，实际: {dq}"
        assert dq["confidence"] == "low", \
            f"缺数据时confidence应为low，实际: {dq['confidence']}"
        assert len(dq["missing_series"]) >= 1, \
            f"missing_series应包含DGS2，实际: {dq['missing_series']}"

    def test_fred_stale__data_degraded(self):
        """F2-2: FRED序列过期>5天 → data_degraded=True"""
        raw = _fresh_raw()
        # DGS2 最新日期设为 12 天前
        stale_date = (date.today() - timedelta(days=12)).strftime("%Y-%m-%d")
        raw["DGS2"] = _make_series([(4.40, stale_date)])

        dq = assess_data_quality(raw, TODAY)

        assert dq["data_degraded"] is True, \
            "FRED序列过期应触发data_degraded"
        assert dq["confidence"] == "low"
        assert len(dq["stale_series"]) >= 1, \
            f"stale_series应包含DGS2，实际: {dq['stale_series']}"

    def test_all_fresh__confidence_high(self):
        """F2-3: 全部数据新鲜 → confidence=high, data_degraded=False"""
        raw = _fresh_raw()
        dq = assess_data_quality(raw, TODAY)

        assert dq["data_degraded"] is False, \
            "全部数据新鲜时data_degraded应为False"
        assert dq["confidence"] == "high", \
            f"数据正常时confidence应为high，实际: {dq['confidence']}"
        assert len(dq["stale_series"]) == 0
        assert len(dq["missing_series"]) == 0

    def test_derived_missing__data_degraded(self):
        """F2-1续: EFFR_IORB派生序列缺失 → data_degraded"""
        raw = _fresh_raw()
        del raw["EFFR_IORB"]

        dq = assess_data_quality(raw, TODAY)

        assert dq["data_degraded"] is True
        assert any("EFFR_IORB" in m for m in dq["missing_series"]), \
            f"missing_series应包含EFFR_IORB，实际: {dq['missing_series']}"


# ══════════════════════════════════════════════════════════════════════
#  F4: 数据降级 → regime 标记不确定性（不只覆盖 systemic_confirmed）
# ══════════════════════════════════════════════════════════════════════

class TestF4_RegimeDegradation:
    """正向：数据降级时 regime 和 judgement 都要标记，不只盖 systemic_confirmed。"""

    def test_data_degraded__regime_flagged(self):
        """F4-1: 数据降级 → regime 标⚠️, judgement 含数据不足"""
        raw = _fresh_raw()
        # 构造：DGS2 缺失 + EFFR_IORB 存在 → data_degraded
        del raw["DGS2"]

        nc = compute_nowcast(raw)
        fe = {"active": False, "type": "", "intensity": "", "label": "", "sources": []}
        rs = compute_rate_shock(raw, nc)
        tx = compute_transmission(raw, rs)
        dq = assess_data_quality(raw, TODAY)
        tg = compute_triggers(raw, tx)

        orch = run_orchestrator(raw, fe, rs, tx, tg, dq)

        rff = orch["risk_os_final"]
        # 数据降级时regime应标记
        assert "⚠️" in rff["final_regime"], \
            f"数据降级时regime应标记⚠️，实际: {rff['final_regime']}"
        assert "数据不足" in rff["final_judgement"], \
            f"judgement应含数据不足警告，实际: {rff['final_judgement']}"
        assert rff["data_quality"]["data_degraded"] is True
        assert len(rff["data_quality"]["missing_series"]) >= 1

    def test_data_normal__regime_clean(self):
        """F4-2: 数据正常 → regime 无⚠️标记, confidence=high"""
        raw = _fresh_raw()

        nc = compute_nowcast(raw)
        fe = {"active": False, "type": "", "intensity": "", "label": "", "sources": []}
        rs = compute_rate_shock(raw, nc)
        tx = compute_transmission(raw, rs)
        dq = assess_data_quality(raw, TODAY)
        tg = compute_triggers(raw, tx)

        orch = run_orchestrator(raw, fe, rs, tx, tg, dq)

        rff = orch["risk_os_final"]
        assert "⚠️" not in rff["final_regime"], \
            f"数据正常时regime不应有⚠️，实际: {rff['final_regime']}"
        assert rff["data_quality"]["data_degraded"] is False
        assert rff["confidence"] == "high"


# ══════════════════════════════════════════════════════════════════════
#  F5: R4 死代码已消除
# ══════════════════════════════════════════════════════════════════════

class TestF5_DeadCodeRemoved:
    """验证 red_count>=3 不再独立分支，已并入>=2统一映射R4。"""

    def test_red3__maps_to_R4(self):
        """red_count=3 → R4（与 red_count=2 同一分支）"""
        raw = _fresh_raw()
        # 构造 C红: DFII10 ≥ 2.00
        raw["DFII10"] = _make_series([(2.20, TODAY)])
        # 构造 A红: EFFR_IORB高 + DUR5满
        raw["EFFR_IORB"] = _make_series([
            (-1.0, TODAY), (-1.0, "2026-06-19"), (-1.0, "2026-06-17"),
            (-1.0, "2026-06-16"), (-1.0, "2026-06-13"),
        ])
        # 构造 B红: HY OAS ≥ 300
        raw["BAMLH0A0HYM2"] = _make_series([(3.20, TODAY)])

        nc = compute_nowcast(raw)
        fe = {"active": False, "type": "", "intensity": "", "label": "", "sources": []}
        rs = compute_rate_shock(raw, nc)
        tx = compute_transmission(raw, rs)
        dq = assess_data_quality(raw, TODAY)
        tg = compute_triggers(raw, tx)

        orch = run_orchestrator(raw, fe, rs, tx, tg, dq)

        assert orch["red_count"] >= 3, \
            f"应至少有3个红(C+A+B)，实际: red_count={orch['red_count']}"
        assert orch["risk_os_final"]["final_regime_key"] == "R4", \
            f"red≥3应映射R4，实际: {orch['risk_os_final']['final_regime_key']}"

    def test_red2__maps_to_R4(self):
        """red_count=2 → R4（与 red_count=3 同分支，验证死代码已消除）"""
        raw = _fresh_raw()
        # C红 + A红 但没有 B红
        raw["DFII10"] = _make_series([(2.20, TODAY)])
        raw["EFFR_IORB"] = _make_series([
            (-1.0, TODAY), (-1.0, "2026-06-19"), (-1.0, "2026-06-17"),
        ])

        nc = compute_nowcast(raw)
        fe = {"active": False, "type": "", "intensity": "", "label": "", "sources": []}
        rs = compute_rate_shock(raw, nc)
        tx = compute_transmission(raw, rs)
        dq = assess_data_quality(raw, TODAY)
        tg = compute_triggers(raw, tx)

        orch = run_orchestrator(raw, fe, rs, tx, tg, dq)

        assert orch["red_count"] == 2
        assert orch["risk_os_final"]["final_regime_key"] == "R4", \
            "red=2应映射R4，A+C双红即防御模式"
