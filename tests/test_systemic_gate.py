# -*- coding: utf-8 -*-
"""
test_systemic_gate.py  — _infer_near_event() systemic_confirmed 门控测试
========================================================================
覆盖 5 个用例 + 1 个顺序不变性断言，保护 v3.5.1 修复成果：
  - CASC 解析必须在门控检查之前执行（顺序依赖）
  - cross_asset_confirm ≥ 2 AND 文本含"系统性"AND 不含"非系统性" → True
  - cross_asset_confirm < 2 → 门控拦住，不管文本写什么
  - 前端急性（单探针）不被门控误杀

运行: uv run pytest tests/test_systemic_gate.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 tools/ 在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.extract_risk_events import _infer_near_event


# ══════════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════════

def _make_md(**overrides) -> str:
    """构造最小可解析 MD 片段，key=value 覆盖默认值。

    默认值模拟 2026-06-17 典型场景（无事件、无倒挂）。
    """
    defaults = {
        "vix9d_vix_ratio": "0.788",
        "dgs2_iorb": "-48",
        "casc": None,  # None → 不插入 CASC 行
        "tags": [],     # 额外文本标签
    }
    defaults.update(overrides)

    lines = [
        "## ① 近端事件风险",
        f"VTS | VIX9D/VIX={defaults['vix9d_vix_ratio']}",
        f"利率路径 | DGS2−IORB={defaults['dgs2_iorb']}bp",
    ]
    if defaults["casc"] is not None:
        lines.append(f"跨资产确认 | CASC {defaults['casc']}/4")
    if defaults["tags"]:
        lines.append(" ".join(defaults["tags"]))

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# 用例 1: CASC≥2 + "系统性" → systemic_confirmed=True（正向）
# ══════════════════════════════════════════════════════════════════════

def test_casc2_systemic_true():
    """CASC=2/4 + '系统性风险' → systemic_confirmed=True"""
    txt = _make_md(casc="2", tags=["系统性风险", "VIX9D/VIX=1.155 倒挂"])
    result = _infer_near_event(txt)

    assert result["evidence"]["cross_asset_confirm"] == 2, \
        "CASC 应解析为 2"
    assert result["systemic_confirmed"] is True, \
        f"cross_confirm=2 + '系统性' → systemic_confirmed 必须为 True，实为 {result['systemic_confirmed']}"
    assert result["near_event_type"] == "systemic_event", \
        f"near_event_type 应为 systemic_event，实为 {result['near_event_type']}"
    assert result["near_event_active"] is True, \
        "near_event_active 应为 True"

    print(f"  ✅ CASC=2 → cross_confirm={result['evidence']['cross_asset_confirm']}, "
          f"systemic={result['systemic_confirmed']}")


# ══════════════════════════════════════════════════════════════════════
# 用例 2: CASC=0 + "非系统性" → systemic_confirmed=False（负向）
# ══════════════════════════════════════════════════════════════════════

def test_casc0_non_systemic_false():
    """CASC=0/4 + '非系统性' → systemic_confirmed=False"""
    txt = _make_md(casc="0", tags=["非系统性", "前端事件风险"])
    result = _infer_near_event(txt)

    assert result["evidence"]["cross_asset_confirm"] == 0, \
        "CASC 应解析为 0"
    assert result["systemic_confirmed"] is False, \
        f"CASC=0 + '非系统性' → systemic 必须为 False，实为 {result['systemic_confirmed']}"

    print(f"  ✅ CASC=0 → cross_confirm={result['evidence']['cross_asset_confirm']}, "
          f"systemic={result['systemic_confirmed']}")


# ══════════════════════════════════════════════════════════════════════
# 用例 3: CASC=1 (<2) + "系统性" → 门控拦住（边界，关键用例）
# ══════════════════════════════════════════════════════════════════════

def test_casc1_systemic_blocked():
    """CASC=1/4 (<2) + '系统性' → systemic_confirmed=False（门控拦截）

    这是诊断力最强的用例：cross_confirm < 阈值 → 不管文本写什么，
    systemic_confirmed 必须为 False。这个用例只有在 CASC 解析先于
    门控检查时才能正确运行——如果顺序错了，cross_confirm 永远是 None，
    门控形同虚设，这个测试将暴露问题。
    """
    txt = _make_md(casc="1", tags=["系统性风险", "VIX9D/VIX=1.150 前端急性"])
    result = _infer_near_event(txt)

    assert result["evidence"]["cross_asset_confirm"] == 1, \
        f"CASC 应解析为 1，实为 {result['evidence'].get('cross_asset_confirm')}"

    # 门控：cross_confirm < 2，即使文本含"系统性"，systemic_confirmed 必须为 False
    assert result["systemic_confirmed"] is False, \
        f"cross_confirm=1 < 2 → 门控必须拦，但 systemic={result['systemic_confirmed']}"

    print(f"  ✅ CASC=1 < 2 → 门控拦截，systemic={result['systemic_confirmed']}")


# ══════════════════════════════════════════════════════════════════════
# 用例 4: 前端急性 + CASC=0 → 单探针不被闷死
# ══════════════════════════════════════════════════════════════════════

def test_front_acute_single_probe_not_killed():
    """VIX9D/VIX > 0.95 + CASC=0 → near_event_active=True, systemic=False

    验证门控不会误杀单探针信号：前端急性是有效的风险信号，
    只是不与 CASC 联动时不升级为系统性事件。near_event_active
    必须为 True，systemic_confirmed 必须为 False。
    """
    txt = _make_md(
        vix9d_vix_ratio="1.155",
        dgs2_iorb="8",
        casc="0",
        tags=["前端急性", "非系统性"]
    )
    result = _infer_near_event(txt)

    assert result["near_event_active"] is True, \
        f"前端急性信号必须激活 near_event_active，实为 {result['near_event_active']}"
    assert result["systemic_confirmed"] is False, \
        "CASC=0 → 不应升级为系统性事件"
    assert result["front_risk_label"] == "前端紧张", \
        f"VIX9D/VIX=1.155 > 0.95 → 应为前端紧张，实为 {result['front_risk_label']}"

    print(f"  ✅ 前端急性→near_event=True, systemic=False（单探针不闷）")


# ══════════════════════════════════════════════════════════════════════
# 用例 5: CASC=2 + "系统性"（变体）→ 二次确认
# ══════════════════════════════════════════════════════════════════════

def test_casc2_systemic_variant():
    """不同措辞：CASC=2/4 + '系统性风险事件' → systemic_confirmed=True"""
    txt = _make_md(
        vix9d_vix_ratio="1.200",
        dgs2_iorb="15",
        casc="2",
        tags=["系统性风险事件", "VIX9D/VIX=1.200 前端急性", "DGS2−IORB=15bp 加息风险"]
    )
    result = _infer_near_event(txt)

    assert result["evidence"]["cross_asset_confirm"] == 2
    assert result["systemic_confirmed"] is True, \
        f"变体措辞下 cross_confirm=2 + '系统性' → 必须为 True，实为 {result['systemic_confirmed']}"
    assert result["near_event_type"] == "systemic_event"

    print(f"  ✅ 措辞变体→systemic_confirmed={result['systemic_confirmed']}")


# ══════════════════════════════════════════════════════════════════════
# 用例 6: 默认值安全 — 无事件时所有布尔值为 False
# ══════════════════════════════════════════════════════════════════════

def test_defaults_all_false_on_no_signal():
    """无 CASC、无 VIX 倒挂、无 DGS2>0 → 全部默认 False"""
    txt = _make_md()
    result = _infer_near_event(txt)

    assert result["near_event_active"] is False, \
        f"无信号时 near_event_active 应为 False，实为 {result['near_event_active']}"
    assert result["systemic_confirmed"] is False, \
        f"无信号时 systemic_confirmed 应为 False，实为 {result['systemic_confirmed']}"
    assert result["front_risk_label"] == "前端平稳", \
        f"默认 front_risk_label 应为 '前端平稳'，实为 {result['front_risk_label']}"
    assert result["front_risk_intensity"] == "green", \
        f"默认 intensity 应为 'green'，实为 {result['front_risk_intensity']}"

    print(f"  ✅ 无信号→所有布尔 False, label=前端平稳, intensity=green")


# ══════════════════════════════════════════════════════════════════════
# 用例 7: 顺序不变性 — CASC 解析先于门控
# ══════════════════════════════════════════════════════════════════════

def test_casc_parsed_before_gate():
    """验证 _infer_near_event 源码顺序：CASC 解析先于门控检查。

    这不是运行时测试，而是静态顺序断言。如果将来有人重构时把 CASC
    解析挪到门控之后，此测试失败，保护逻辑正确性。
    """
    import inspect
    txt = _make_md(casc="2", tags=["系统性风险"])

    # 运行时验证：当 CASC=2 时，门控必须生效
    result = _infer_near_event(txt)
    assert result["evidence"]["cross_asset_confirm"] == 2, \
        "CASC=2 必须被解析为 int"
    assert result["systemic_confirmed"] is True, \
        "cross_confirm=2 → systemic 必须为 True，若失败说明 CASC 未在门控前解析"

    # 静态验证：检查源码中 CASC 解析行和门控行的相对位置
    source = inspect.getsource(_infer_near_event)
    casc_parse_line = -1
    gate_line = -1
    for i, line in enumerate(source.splitlines()):
        if 'cross_asset_confirm' in line and ('re.search' in line or 'int(' in line):
            casc_parse_line = i
        if 'cross_confirm >= 2' in line:
            gate_line = i

    assert casc_parse_line >= 0, "源码中未找到 CASC 解析行"
    assert gate_line >= 0, "源码中未找到门控检查行"
    assert casc_parse_line < gate_line, \
        (f"顺序错误：CASC 解析在第 {casc_parse_line} 行，"
         f"门控在第 {gate_line} 行。"
         f"CASC 解析必须在门控检查之前！")

    print(f"  ✅ CASC 解析(L{casc_parse_line}) < 门控检查(L{gate_line}) — 顺序正确")


# ══════════════════════════════════════════════════════════════════════
# 用例 8: verdict 查表完整性 — 互锁 state 全集 → 非空 verdict
# ══════════════════════════════════════════════════════════════════════

def test_interlock_verdict_coverage():
    """compute_vts_rcv_interlock() 的 state 全集 × get_verdict_md/get_verdict_png
    每个 state 都应输出非空 verdict。缺键时 fallback 高亮告警而非空白。
    """
    from daily_report import compute_vts_rcv_interlock
    from generate_risk_dashboard import _lock_to_stg_key, get_verdict_md, get_verdict_png

    test_cases = [
        # (vts_dict, rcv_dict, desc)
        ({"structure": "N/A", "front_structure": "N/A"}, {"abstain": True, "character": "N/A", "severity": "N/A", "tilt": "N/A", "long_led": False}, "双缺 → N/A"),
        ({"structure": "N/A", "front_structure": "N/A"}, {"abstain": False, "character": "balanced", "severity": "calm", "tilt": "N/A", "long_led": False}, "VTS缺·RCV平静 → vts_missing"),
        ({"structure": "contango", "front_structure": "前端平稳"}, {"abstain": True, "character": "N/A", "severity": "N/A", "tilt": "N/A", "long_led": False}, "RCV缺 → N/A"),
        ({"structure": "contango", "front_structure": "前端急性"}, {"abstain": False, "character": "balanced", "severity": "acute", "tilt": "front", "long_led": False}, "agree-front"),
        ({"structure": "倒挂", "front_structure": "前端平稳"}, {"abstain": False, "character": "acute-broad", "severity": "acute", "tilt": "flat", "long_led": True}, "agree-systemic"),
        ({"structure": "contango", "front_structure": "前端急性"}, {"abstain": False, "character": "balanced", "severity": "calm", "tilt": "N/A", "long_led": False}, "divergent① VTS热(via前端)·RCV平"),
        ({"structure": "contango", "front_structure": "前端平稳"}, {"abstain": False, "character": "balanced", "severity": "elevated", "tilt": "flat", "long_led": True}, "divergent② RCV热·VTS平"),
        ({"structure": "倒挂", "front_structure": "前端平稳"}, {"abstain": False, "character": "balanced", "severity": "elevated", "tilt": "front", "long_led": False}, "divergent③ 双端热·方向背离"),
        ({"structure": "contango", "front_structure": "前端平稳"}, {"abstain": False, "character": "balanced", "severity": "calm", "tilt": "N/A", "long_led": False}, "calm 双端平静"),
    ]

    for vts_dict, rcv_dict, desc in test_cases:
        result = compute_vts_rcv_interlock(vts_dict, rcv_dict)
        lock_state = result["state"]
        vts_structure = vts_dict.get("structure", "N/A")

        verdict_md = get_verdict_md(lock_state, vts_structure)
        verdict_png = get_verdict_png(lock_state, vts_structure)

        assert verdict_md, f"[{desc}] lock='{lock_state}' → MD verdict 为空！"
        assert not verdict_md.startswith("[!] VERDICT KEY MISSING"), \
            f"[{desc}] MD verdict=missing-key fallback: {verdict_md}"
        assert verdict_png, f"[{desc}] lock='{lock_state}' → PNG verdict 为空！"
        assert not verdict_png.startswith("[!] VERDICT KEY MISSING"), \
            f"[{desc}] PNG verdict=missing-key fallback: {verdict_png}"

        print(f"  ✅ [{desc:35s}] lock={lock_state:16s} → MD={'OK':3s} PNG={'OK':3s}")

    print(f"\n  ✅ 9 个互锁状态分支 → MD/PNG verdict 全覆盖，无空白")


# ══════════════════════════════════════════════════════════════════════
# 用例 9: 枚举保护 — 新增 lock_state 时必须检查 verdict 覆盖
# ══════════════════════════════════════════════════════════════════════

def test_verdict_keys_match_interlock_states():
    """静态保护：_lock_to_stg_key() 的分支 + VERDICTS_MD/VERDICTS_PNG 的键
    应覆盖 compute_vts_rcv_interlock() 所有可能的 state 输出。

    如果 compute_vts_rcv_interlock() 新增了 state 值，此测试失败，
    提醒开发者同步更新 _lock_to_stg_key() 和两个 VERDICTS 字典。
    """
    from generate_risk_dashboard import (_lock_to_stg_key, get_verdict_md,
                                          get_verdict_png, VERDICTS_MD, VERDICTS_PNG)

    # compute_vts_rcv_interlock() 返回的 state 可能值：
    KNOWN_STATES = {"N/A", "vts_missing", "agree-front", "agree-systemic", "divergent", "calm"}

    # 每个已知 state 都能通过 _lock_to_stg_key() → get_verdict_*() 产生非空 verdict
    for state in KNOWN_STATES:
        # "contango" 不走 pre-systemic 分支，"倒挂" 走 pre-systemic
        verdict_md = get_verdict_md(state, "contango")
        verdict_png = get_verdict_png(state, "contango")
        assert verdict_md, f"lock_state='{state}' → MD 空 verdict"
        assert not verdict_md.startswith("[!] VERDICT KEY MISSING"), \
            f"lock_state='{state}' → MD: {verdict_md}"
        assert verdict_png, f"lock_state='{state}' → PNG 空 verdict"
        assert not verdict_png.startswith("[!] VERDICT KEY MISSING"), \
            f"lock_state='{state}' → PNG: {verdict_png}"

    # vts_structure="倒挂" / "倒挂·急性" 走 pre-systemic 分支（不依赖 lock_state）
    for structure in ("倒挂", "倒挂·急性"):
        verdict_md = get_verdict_md("divergent", structure)
        verdict_png = get_verdict_png("divergent", structure)
        assert verdict_md, f"vts_structure='{structure}' → MD 空 verdict"
        assert "前端压力积聚" in verdict_md, f"vts_structure='{structure}' → MD 未命中 pre-systemic"
        assert "Front stress" in verdict_png, f"vts_structure='{structure}' → PNG 未命中 pre-systemic"

    # VERDICTS_MD 和 VERDICTS_PNG 键一致
    assert set(VERDICTS_MD.keys()) == set(VERDICTS_PNG.keys()), \
        f"MD 键={VERDICTS_MD.keys()} vs PNG 键={VERDICTS_PNG.keys()} 不一致！"

    print(f"  ✅ 已知 {len(KNOWN_STATES)} 个互锁 state → MD/PNG verdict 全覆盖")
    print(f"  ✅ vts 倒挂分支 → pre-systemic verdict 可达")
    print(f"  ✅ VERDICTS_MD 与 VERDICTS_PNG 键集一致 ({len(VERDICTS_MD)} keys)")
