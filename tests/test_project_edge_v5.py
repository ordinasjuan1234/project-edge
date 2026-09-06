import pytest

from engine.decision.project_edge_v5 import ProjectEdgeV5, ProjectEdgeV5Config


def snapshot(direction="LONG", setup="A", atr_15m=0.5):
    long_side = direction == "LONG"
    side = "long" if long_side else "short"
    expected = "BULLISH" if long_side else "BEARISH"
    sign = 1.0 if long_side else -1.0
    result = {
        "state_4H": "TRANSITION",
        "state_1H": "TRANSITION",
        "state_30M": expected if setup == "A" else "TRANSITION",
        "state_15M": "TRANSITION",
        "state_5M": "TRANSITION",
        "pe_ema_fast_1H": 110.0 if long_side else 90.0,
        "pe_ema_slow_1H": 100.0,
        "pe_ema_slope_1H": sign,
        "pe_ema_fast_30M": 110.0 if long_side else 90.0,
        "pe_ema_slow_30M": 100.0,
        "pe_ema_slope_30M": sign,
        "pe_ema_fast_4H": 100.0,
        "pe_ema_slow_4H": 100.0,
        "pe_ema_slope_4H": 0.0,
        "pe_adx_1H": 30.0,
        "pe_adx_rising_1H": False,
        "pe_atr_15M": atr_15m,
        "pe_atr_5M": 1.0,
        "pe_close_5M": 100.0,
        "pe_distance_from_ema_pct_5M": 0.005,
        f"pe_pullback_{side}_15M": True,
        f"pe_trigger_{side}_5M": True,
        f"pe_breakout_{side}_30M": setup == "B",
        f"pe_fvg_{side}_15M": False,
        f"pe_fvg_{side}_5M": False,
    }
    return result


def test_v5_uses_ema_regime_even_when_1h_structure_is_transition():
    decision = ProjectEdgeV5().decide_snapshot(snapshot("LONG", "A"))
    assert decision["decision"] == "READY_LONG"
    assert decision["setup_type"] == "PULLBACK_CONTINUATION"
    assert decision["can_execute"] is True


def test_v5_supports_short_pullback_continuation():
    decision = ProjectEdgeV5().decide_snapshot(snapshot("SHORT", "A"))
    assert decision["decision"] == "READY_SHORT"
    assert decision["setup_type"] == "PULLBACK_CONTINUATION"


def test_v5_breakout_retest_can_use_30m_transition():
    decision = ProjectEdgeV5().decide_snapshot(snapshot("LONG", "B"))
    assert decision["decision"] == "READY_LONG"
    assert decision["setup_type"] == "BREAKOUT_RETEST"
    assert decision["diagnostics"]["breakout_30m"] is True


def test_v5_blocks_strong_4h_opposition():
    value = snapshot("LONG", "A")
    value.update(
        state_4H="BEARISH",
        pe_ema_fast_4H=90.0,
        pe_ema_slow_4H=100.0,
        pe_ema_slope_4H=-1.0,
    )
    decision = ProjectEdgeV5().decide_snapshot(value)
    assert decision["can_execute"] is False
    assert decision["checks"]["macro_4h_not_strongly_opposed"] is False


def test_v5_requires_rising_adx_between_25_and_30():
    value = snapshot("LONG", "A")
    value["pe_adx_1H"] = 27.0
    value["pe_adx_rising_1H"] = False
    blocked = ProjectEdgeV5().decide_snapshot(value)
    assert blocked["checks"]["adx_1h"] is False
    value["pe_adx_rising_1H"] = True
    ready = ProjectEdgeV5().decide_snapshot(value)
    assert ready["checks"]["adx_1h"] is True


def test_v5_accepts_strong_adx_even_if_not_rising():
    value = snapshot("LONG", "A")
    value["pe_adx_1H"] = 30.0
    value["pe_adx_rising_1H"] = False
    decision = ProjectEdgeV5().decide_snapshot(value)
    assert decision["can_execute"] is True


def test_v5_blocks_extended_5m_trigger():
    value = snapshot("LONG", "A")
    value["pe_distance_from_ema_pct_5M"] = 0.008
    decision = ProjectEdgeV5().decide_snapshot(value)
    assert decision["can_execute"] is False
    assert decision["checks"]["trigger_not_extended"] is False


def test_v5_fvg_changes_score_but_not_signal_requirement():
    strategy = ProjectEdgeV5()
    plain = strategy.decide_snapshot(snapshot("LONG", "A"))
    enriched_value = snapshot("LONG", "A")
    enriched_value["pe_fvg_long_5M"] = True
    enriched = strategy.decide_snapshot(enriched_value)
    assert plain["can_execute"] is enriched["can_execute"] is True
    assert enriched["quality_score"] == pytest.approx(plain["quality_score"] + 5.0)


def test_v5_cost_gate_rejects_small_stop_where_cost_dominates_risk():
    strategy = ProjectEdgeV5()
    decision = strategy.decide_snapshot(snapshot("LONG", "A", atr_15m=0.2))
    plan = strategy.build_trade_plan(decision, entry_price=100.0, account_equity=1000.0)
    assert plan["approved"] is False
    assert plan["estimated_cost_risk_ratio"] > 0.35
    assert "Costo estimado excesivo" in plan["reason"]


def test_v5_cost_gate_allows_healthier_stop_and_keeps_x1():
    strategy = ProjectEdgeV5()
    decision = strategy.decide_snapshot(snapshot("LONG", "A", atr_15m=0.5))
    plan = strategy.build_trade_plan(decision, entry_price=100.0, account_equity=1000.0)
    assert plan["approved"] is True
    assert plan["leverage"] == 1
    assert plan["estimated_cost_risk_ratio"] <= 0.35
    assert plan["estimated_net_reward_risk"] == pytest.approx(1.5, abs=1e-9)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"adx_strong": 24.0},
        {"max_trigger_distance_atr": 0.0},
        {"max_cost_risk_ratio": 0.0},
        {"max_cost_risk_ratio": 1.0},
        {"breakout_lookback": 0},
    ],
)
def test_v5_rejects_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        ProjectEdgeV5Config(**kwargs)
