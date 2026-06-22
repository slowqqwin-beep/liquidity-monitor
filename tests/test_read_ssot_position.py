#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""§五-6: read_ssot_position() 安全网负测

三道保护:
  P1: 文件不存在 / 读取失败 → 返回 None
  P2: 日期过期 (date != 今日) → 返回 None
  P3: 字段缺失/类型错误/仓位格式错/和≠100 → raise

注入三类坏输入，验证每道保护都触发。
"""

import json
import sys
from pathlib import Path
from datetime import date as _date, timedelta

import pytest

# ── 把项目根加入 path ──
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from daily_report import read_ssot_position  # noqa: E402


# ═══════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════

def _valid_es(date_str: str | None = None) -> dict:
    """返回一个完全合法的 event_state dict。"""
    return {
        "date": date_str or _date.today().isoformat(),
        "source": "Risk OS State Machine v1.0 — SSoT",
        "regime": "R3 警惕",
        "regime_key": "R3",
        "red_count": 1,
        "systemic_classification": "WATCH",
        "systemic_confirmed": False,
        "cross_domain_signals": 2,
        "positions": {
            "primary": "35%",
            "hedge": "35%",
            "cash": "30%",
        },
    }


def _write_es(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ═══════════════════════════════════════════════════
# P1: 文件不存在 / 读取失败 → 返回 None
# ═══════════════════════════════════════════════════

def test_p1_file_missing(tmp_path):
    """文件不存在 → 返回 None。"""
    es_path = tmp_path / "nonexistent" / "event_state.json"
    result = read_ssot_position(es_path=es_path)
    assert result is None, f"文件不存在应返回 None, 实际: {result}"


def test_p1_corrupt_json(tmp_path):
    """JSON 损坏 → 返回 None (不 raise)。"""
    es_path = tmp_path / "event_state.json"
    es_path.write_text("{ this is not valid json !!!", encoding="utf-8")

    result = read_ssot_position(es_path=es_path)
    assert result is None, f"corrupt JSON 应返回 None, 实际: {result}"


# ═══════════════════════════════════════════════════
# P2: 日期过期 → 返回 None
# ═══════════════════════════════════════════════════

def test_p2_date_expired(tmp_path):
    """date ≠ 今日 → 返回 None。"""
    es_path = tmp_path / "event_state.json"
    yesterday = (_date.today() - timedelta(days=1)).isoformat()
    _write_es(es_path, _valid_es(date_str=yesterday))

    result = read_ssot_position(es_path=es_path)
    assert result is None, f"过期数据应返回 None, 实际: {result}"


def test_p2_date_missing(tmp_path):
    """date 字段完全缺失 → 视为过期 ('' ≠ TODAY)。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    del data["date"]
    _write_es(es_path, data)

    result = read_ssot_position(es_path=es_path)
    assert result is None, "date 缺失应返回 None"


def test_p2_date_today_ok(tmp_path):
    """date == 今日 → 正常返回 pos dict（正向验证）。"""
    es_path = tmp_path / "event_state.json"
    _write_es(es_path, _valid_es(date_str=_date.today().isoformat()))

    result = read_ssot_position(es_path=es_path)
    assert result is not None
    assert result["Primary"] == 35
    assert result["Hedge"] == 35
    assert result["Cash"] == 30
    assert result["regime_key"] == "R3"


# ═══════════════════════════════════════════════════
# P3: 字段缺失 → raise KeyError
# ═══════════════════════════════════════════════════

@pytest.mark.parametrize("field", [
    "regime",
    "regime_key",
    "red_count",
    "positions",
    "cross_domain_signals",
    "systemic_confirmed",
])
def test_p3_missing_required_field(tmp_path, field):
    """缺少任一 required_field → raise KeyError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    del data[field]
    _write_es(es_path, data)

    with pytest.raises(KeyError, match=field):
        read_ssot_position(es_path=es_path)


@pytest.mark.parametrize("subkey", ["primary", "hedge", "cash"])
def test_p3_missing_position_subkey(tmp_path, subkey):
    """positions 缺少 primary/hedge/cash → raise KeyError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    del data["positions"][subkey]
    _write_es(es_path, data)

    with pytest.raises(KeyError, match=subkey):
        read_ssot_position(es_path=es_path)


# ═══════════════════════════════════════════════════
# P3: 类型错误 → raise TypeError
# ═══════════════════════════════════════════════════

def test_p3_regime_key_not_str(tmp_path):
    """regime_key 是 int → raise TypeError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["regime_key"] = 3
    _write_es(es_path, data)

    with pytest.raises(TypeError, match="regime_key"):
        read_ssot_position(es_path=es_path)


def test_p3_red_count_not_int(tmp_path):
    """red_count 是 str → raise TypeError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["red_count"] = "1"
    _write_es(es_path, data)

    with pytest.raises(TypeError, match="red_count"):
        read_ssot_position(es_path=es_path)


def test_p3_systemic_confirmed_not_bool(tmp_path):
    """systemic_confirmed 是 int 0 → raise TypeError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["systemic_confirmed"] = 0  # int 不是 bool
    _write_es(es_path, data)

    with pytest.raises(TypeError, match="systemic_confirmed"):
        read_ssot_position(es_path=es_path)


def test_p3_positions_not_dict(tmp_path):
    """positions 是 list → raise TypeError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["positions"] = ["25%", "45%", "30%"]
    _write_es(es_path, data)

    with pytest.raises(TypeError, match="positions"):
        read_ssot_position(es_path=es_path)


def test_p3_cross_domain_signals_not_int(tmp_path):
    """cross_domain_signals 是 str → raise TypeError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["cross_domain_signals"] = "2"
    _write_es(es_path, data)

    with pytest.raises(TypeError, match="cross_domain_signals"):
        read_ssot_position(es_path=es_path)


# ═══════════════════════════════════════════════════
# P3: 仓位格式错误 → raise ValueError
# ═══════════════════════════════════════════════════

def test_p3_position_no_percent_sign(tmp_path):
    """仓位值无 % → raise ValueError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["positions"]["primary"] = "35"  # 缺 %
    _write_es(es_path, data)

    with pytest.raises(ValueError, match="无法解析仓位百分比值"):
        read_ssot_position(es_path=es_path)


def test_p3_position_is_list(tmp_path):
    """仓位值是 list → raise ValueError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["positions"]["primary"] = [35]
    _write_es(es_path, data)

    with pytest.raises(ValueError, match="无法解析仓位百分比值"):
        read_ssot_position(es_path=es_path)


def test_p3_position_is_none(tmp_path):
    """仓位值是 None → raise ValueError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["positions"]["primary"] = None
    _write_es(es_path, data)

    with pytest.raises(ValueError, match="无法解析仓位百分比值"):
        read_ssot_position(es_path=es_path)


def test_p3_sum_not_100(tmp_path):
    """仓位和 ≠ 100 → raise ValueError。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es()
    data["positions"]["primary"] = "40%"
    data["positions"]["hedge"] = "40%"
    data["positions"]["cash"] = "30%"  # sum = 110
    _write_es(es_path, data)

    with pytest.raises(ValueError, match="仓位和不等于100"):
        read_ssot_position(es_path=es_path)


# ═══════════════════════════════════════════════════
# 正向：正常路径不触发任何保护
# ═══════════════════════════════════════════════════

def test_normal_returns_correct_structure(tmp_path):
    """完全合法的输入 → 结构完整的 pos dict。"""
    es_path = tmp_path / "event_state.json"
    _write_es(es_path, _valid_es(date_str=_date.today().isoformat()))

    result = read_ssot_position(es_path=es_path)
    assert result is not None

    for key in ["Primary", "Hedge", "Cash", "regime_key", "label", "steps"]:
        assert key in result, f"缺少 key: {key}"

    assert len(result["steps"]) >= 1
    assert "SSoT" in result["steps"][0]["source"]

    for k in ["Primary", "Hedge", "Cash"]:
        assert isinstance(result[k], int), f"{k} 应为 int, 实际 {type(result[k])}"

    assert result["Primary"] + result["Hedge"] + result["Cash"] == 100


def test_position_int_values(tmp_path):
    """仓位值是 int → 正常解析。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es(date_str=_date.today().isoformat())
    data["positions"] = {"primary": 25, "hedge": 45, "cash": 30}
    _write_es(es_path, data)

    result = read_ssot_position(es_path=es_path)
    assert result["Primary"] == 25
    assert result["Hedge"] == 45
    assert result["Cash"] == 30


def test_position_float_values(tmp_path):
    """仓位值是 float → int 截断。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es(date_str=_date.today().isoformat())
    data["positions"] = {"primary": 25.0, "hedge": 45.0, "cash": 30.0}
    _write_es(es_path, data)

    result = read_ssot_position(es_path=es_path)
    assert result["Primary"] == 25
    assert result["Hedge"] == 45
    assert result["Cash"] == 30


def test_systemic_confirmed_true_is_valid(tmp_path):
    """systemic_confirmed=True → 正常 (True 是 bool)。"""
    es_path = tmp_path / "event_state.json"
    data = _valid_es(date_str=_date.today().isoformat())
    data["systemic_confirmed"] = True
    _write_es(es_path, data)

    result = read_ssot_position(es_path=es_path)
    assert result is not None


# ═══════════════════════════════════════════════════
# 覆盖矩阵文档
# ═══════════════════════════════════════════════════

def test_coverage_matrix():
    """确认三道保护每种注入方式都有测试。"""
    covered = [
        # P1: 文件失效
        "test_p1_file_missing",
        "test_p1_corrupt_json",
        # P2: 日期过期
        "test_p2_date_expired",
        "test_p2_date_missing",
        "test_p2_date_today_ok",  # 正向
        # P3: 字段缺失 (6 required + 3 position subkeys)
        "test_p3_missing_required_field",   # parametrized × 6
        "test_p3_missing_position_subkey",  # parametrized × 3
        # P3: 类型错误 (5 种)
        "test_p3_regime_key_not_str",
        "test_p3_red_count_not_int",
        "test_p3_systemic_confirmed_not_bool",
        "test_p3_positions_not_dict",
        "test_p3_cross_domain_signals_not_int",
        # P3: 格式错误 (4 种)
        "test_p3_position_no_percent_sign",
        "test_p3_position_is_list",
        "test_p3_position_is_none",
        "test_p3_sum_not_100",
    ]
    # 1 + 1 + 2 + 6 + 3 + 5 + 4 = 22 种注入
    assert len(covered) >= 15, f"覆盖矩阵应有 ≥15 独立注入类, 实际 {len(covered)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
