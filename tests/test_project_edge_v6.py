import pytest

from engine.decision.project_edge_v6 import ProjectEdgeV6, ProjectEdgeV6Config


def snapshot(direction="LONG", setup="PULLBACK"):
    long_side = direction == "LONG"
    side = "long" if long_side else "short"
    expected = "BULLISH" if long_side else "BEARISH"
    sign = 1.0 if long_side else -1.0

    result = {
        "state_4H": "TRANSITION",
        "state_1H": "TRANSITION",
        "state_30M": "TRANSITION",
        "state_15M": "TRANSITION" if setup == "PULLBACK" else expected,
        "state_5M": "TRANSITION",
        "pe_ema_fast_1H": 110.0 if long_side else 90.0,
        "pe_ema_slow_1H": 100.0,
        "pe_ema_slope_1H": sign,
        "pe_ema_fast_15M": 110.0 if long_side else 90.0,
        "pe_ema_slow_15M": 100.0,
        "pe_ema_slope_15M": sign,
        "pe_ema_fast_4H": 100.0,
        "pe_ema_slow_4H": 100.0,
        "pe_ema_slope_4H": 0.0,
        "pe_adx_15M": 30.0,
        "pe_adx_rising_15M": False,
        "pe_atr_15M": 0.8,
        "pe_atr_5M": 0.5,
        "pe_close_5M": 100.0,
        "pe_distance_from_ema_pct_5M": 0.002,
        f"pe_pullback_{side}_15M": setup == "PULLBACK",
        f"pe_trigger_{side}_5M": True,
        f"pe_fvg_{side}_15M": False,
        f"pe_fvg_{side}_5M": False,
    }
    return result


def test_v6_defaults_are_scalp_and_conservative():
    config = ProjectEdgeV6Config()
    assert config.risk_pct == pytest.approx(0.003)
    assert config.cooldown_minutes == 15
    assert config.gross_reward_risk == pytest.approx(1.5)
    assert config.max_exposure_pct == pytest.approx(1.0)


def test_v6_uses_1h_as_context_without_requiring_4h_alignment():
    decision = ProjectEdgeV6().decide_snapshot(snapshot("LONG", "PULLBACK"))
    assert decision["decision"] == "READY_LONG"
    assert decision["setup_type"] == "SCALP_PULLBACK"
    assert decision["can_execute"] is True


def test_v6_supports_short_scalp():
    decision = ProjectEdgeV6().decide_snapshot(snapshot("SHORT", "PULLBACK"))
    assert decision["decision"] == "READY_SHORT"
    assert decision["can_execute"] is True


def test_v6_accepts_momentum_15m_without_pullback():
    decision = ProjectEdgeV6().decide_snapshot(snapshot("LONG", "MOMENTUM"))
    assert decision["decision"] == "READY_LONG"
    assert decision["setup_type"] == "SCALP_MOMENTUM"


def test_v6_blocks_strong_4h_opposition():
    value = snapshot("LONG", "PULLBACK")
    value.update(
        state_4H="BEARISH",
        pe_ema_fast_4H=90.0,
        pe_ema_slow_4H=100.0,
        pe_ema_slope_4H=-1.0,
    )
    decision = ProjectEdgeV6().decide_snapshot(value)
    assert decision["can_execute"] is False
    assert decision["checks"]["macro_4h_not_strongly_opposed"] is False


def test_v6_requires_15m_strength():
    value = snapshot("LONG", "PULLBACK")
    value["pe_adx_15M"] = 19.0
    value["pe_adx_rising_15M"] = True
    decision = ProjectEdgeV6().decide_snapshot(value)
    assert decision["can_execute"] is False
    assert decision["checks"]["adx_15m"] is False


def test_v6_accepts_adx_20_to_28_only_if_rising():
    value = snapshot("LONG", "PULLBACK")
    value["pe_adx_15M"] = 24.0
    value["pe_adx_rising_15M"] = False
    blocked = ProjectEdgeV6().decide_snapshot(value)
    assert blocked["can_execute"] is False

    value["pe_adx_rising_15M"] = True
    ready = ProjectEdgeV6().decide_snapshot(value)
    assert ready["can_execute"] is True


def test_v6_blocks_extended_5m_trigger():
    value = snapshot("LONG", "PULLBACK")
    value["pe_distance_from_ema_pct_5M"] = 0.006
    decision = ProjectEdgeV6().decide_snapshot(value)
    assert decision["can_execute"] is False
    assert decision["checks"]["trigger_not_extended"] is False


def test_v6_trade_plan_stays_x1_and_risks_03_percent():
    strategy = ProjectEdgeV6()
    decision = strategy.decide_snapshot(snapshot("LONG", "PULLBACK"))
    plan = strategy.build_trade_plan(
        decision,
        entry_price=100.0,
        account_equity=1000.0,
    )
    assert plan["approved"] is True
    assert plan["leverage"] == 1
    assert plan["risk_budget"] == pytest.approx(3.0)
    assert plan["estimated_risk"] <= 3.0 + 1e-9


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_trigger_distance_atr": 0.0},
        {"strong_adx_15m": 19.0},
    ],
)
def test_v6_rejects_invalid_specific_parameters(kwargs):
    with pytest.raises(ValueError):
        ProjectEdgeV6Config(**kwargs)
