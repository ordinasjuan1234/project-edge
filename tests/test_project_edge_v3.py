from datetime import datetime, timezone

import pandas as pd
import pytest

from engine.decision.project_edge_v3 import (
    ProjectEdgeV3,
    ProjectEdgeV3Config,
    loss_guard_remaining_minutes,
)


def ready_snapshot(direction="LONG"):
    bullish = direction == "LONG"
    macro_state = "BULLISH" if bullish else "BEARISH"
    snapshot = {
        **{
            f"state_{timeframe}": macro_state
            for timeframe in ("4H", "1H", "30M", "15M", "5M")
        },
        "pe_ema_fast_4H": 110.0 if bullish else 90.0,
        "pe_ema_slow_4H": 100.0,
        "pe_ema_slope_4H": 1.0 if bullish else -1.0,
        "pe_ema_fast_1H": 105.0 if bullish else 95.0,
        "pe_ema_slow_1H": 100.0,
        "pe_ema_slope_1H": 0.5 if bullish else -0.5,
        "pe_adx_1H": 30.0,
        "pe_adx_delta_1H": 2.5,
        "pe_adx_rising_1H": True,
        "pe_ema_gap_pct_4H": 0.10,
        "pe_ema_gap_pct_1H": 0.05,
        "pe_ema_slope_pct_4H": 0.01 if bullish else -0.01,
        "pe_ema_slope_pct_1H": 0.005 if bullish else -0.005,
        "pe_efficiency_ratio_1H": 0.42,
        "pe_atr_15M": 2.0,
        "pe_atr_pct_15M": 0.02,
        f"pe_pullback_depth_{'long' if bullish else 'short'}_pct_15M": 0.006,
        "pe_distance_from_ema_pct_5M": 0.003 if bullish else -0.003,
        f"pe_pullback_{'long' if bullish else 'short'}_15M": True,
        f"pe_trigger_{'long' if bullish else 'short'}_5M": True,
    }
    return snapshot


def sample_ohlc(rows=90):
    close = pd.Series([100.0 + index * 0.2 for index in range(rows)])
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
        }
    )


def test_ready_long_requires_trend_pullback_and_trigger():
    decision = ProjectEdgeV3().decide_snapshot(ready_snapshot("LONG"))

    assert decision["decision"] == "READY_LONG"
    assert decision["can_execute"] is True
    assert decision["checks"]["adx_1h"] is True


def test_missing_5m_trigger_keeps_signal_on_watch():
    snapshot = ready_snapshot("SHORT")
    snapshot["pe_trigger_short_5M"] = False

    decision = ProjectEdgeV3().decide_snapshot(snapshot)

    assert decision["decision"] == "WATCH_SHORT"
    assert decision["can_execute"] is False
    assert "trigger_5m" in decision["reason"]


def test_ready_signal_exposes_diagnostics_without_changing_decision():
    decision = ProjectEdgeV3().decide_snapshot(ready_snapshot("SHORT"))

    assert decision["decision"] == "READY_SHORT"
    assert decision["can_execute"] is True
    assert decision["diagnostics"] == {
        "state_4h": "BEARISH",
        "state_1h": "BEARISH",
        "state_30m": "BEARISH",
        "state_15m": "BEARISH",
        "state_5m": "BEARISH",
        "adx_1h": pytest.approx(30.0),
        "adx_delta_1h": pytest.approx(2.5),
        "ema_gap_pct_4h": pytest.approx(0.10),
        "ema_gap_pct_1h": pytest.approx(0.05),
        "ema_slope_pct_4h": pytest.approx(-0.01),
        "ema_slope_pct_1h": pytest.approx(-0.005),
        "efficiency_ratio_1h": pytest.approx(0.42),
        "atr_pct_15m": pytest.approx(0.02),
        "pullback_depth_pct_15m": pytest.approx(0.006),
        "distance_from_ema_pct_5m": pytest.approx(-0.003),
        "fvg_confluence": False,
    }


def test_features_are_causal_when_future_candle_changes():
    strategy = ProjectEdgeV3()
    original = sample_ohlc()
    changed = original.copy()
    changed.loc[len(changed) - 1, ["open", "high", "low", "close"]] = [
        200.0,
        205.0,
        195.0,
        204.0,
    ]

    before = strategy.add_features(original).iloc[:-1]
    after = strategy.add_features(changed).iloc[:-1]

    pd.testing.assert_frame_equal(
        before[list(strategy.FEATURE_FIELDS)],
        after[list(strategy.FEATURE_FIELDS)],
    )


def test_trade_plan_risks_half_percent_without_leverage():
    strategy = ProjectEdgeV3()
    decision = strategy.decide_snapshot(ready_snapshot("LONG"))

    plan = strategy.build_trade_plan(
        decision=decision,
        entry_price=100.0,
        account_equity=10000.0,
    )

    assert plan["approved"] is True
    assert plan["estimated_risk"] <= 50.0 + 1e-9
    assert plan["exposure"] <= 5000.0 + 1e-9
    assert plan["estimated_net_reward_risk"] >= 1.5
    assert plan["leverage"] == 1


def test_minimum_stop_distance_is_six_tenths_percent():
    config = ProjectEdgeV3Config()

    assert config.minimum_stop_pct == pytest.approx(0.006)


def test_trade_plan_rejects_excessive_atr():
    strategy = ProjectEdgeV3()
    decision = strategy.decide_snapshot(ready_snapshot("LONG"))
    decision["atr_15m"] = 10.0

    plan = strategy.build_trade_plan(decision, 100.0, 10000.0)

    assert plan["approved"] is False
    assert "Volatilidad excesiva" in plan["reason"]


def test_loss_guard_blocks_after_three_recent_auto_losses():
    trades = [
        {
            "source": "AUTO",
            "pnl": -10.0,
            "closed_at": f"2026-08-26T{hour:02d}:00:00+00:00",
        }
        for hour in (8, 9, 10)
    ]
    now = datetime(2026, 8, 26, 11, 0, tzinfo=timezone.utc)

    remaining = loss_guard_remaining_minutes(trades, now=now)

    assert remaining == pytest.approx(180.0)


def test_loss_guard_ignores_manual_trade_and_winning_sequence():
    trades = [
        {"source": "AUTO", "pnl": -10.0, "closed_at": "2026-08-26T08:00:00Z"},
        {"source": "MANUAL", "pnl": -10.0, "closed_at": "2026-08-26T09:00:00Z"},
        {"source": "AUTO", "pnl": 5.0, "closed_at": "2026-08-26T10:00:00Z"},
        {"source": "AUTO", "pnl": -2.0, "closed_at": "2026-08-26T11:00:00Z"},
    ]

    assert loss_guard_remaining_minutes(trades) == 0.0


def test_invalid_strategy_parameters_are_rejected():
    with pytest.raises(ValueError, match="ema_slow_period"):
        ProjectEdgeV3Config(ema_fast_period=20, ema_slow_period=10)
