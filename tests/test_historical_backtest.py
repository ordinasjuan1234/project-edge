import pandas as pd
import pytest

from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktester,
)


def prepared_timeline(second_high=102.0, second_low=99.8):
    open_time = pd.date_range(
        "2026-01-01T00:00:00Z",
        periods=2,
        freq="5min",
    )
    data = {
        "open_time": open_time,
        "close_time": open_time + pd.Timedelta(minutes=5),
        "open": [100.0, 100.0],
        "high": [100.2, second_high],
        "low": [99.8, second_low],
        "close": [100.0, 101.0],
    }
    for timeframe in ("4H", "1H", "30M", "15M", "5M"):
        data[f"state_{timeframe}"] = ["BULLISH", "BULLISH"]
    return pd.DataFrame(data)


def signal_only_on_first_row(row):
    if row.name == 0:
        return {
            "decision": "READY_LONG",
            "direction": "LONG",
            "can_execute": True,
        }
    return {"decision": "WAIT", "direction": None, "can_execute": False}


def test_causal_state_appears_only_at_confirmation_index():
    analysis = pd.DataFrame(
        {
            "structure_label": ["HH", "HL", None, None, None],
            "structure_known_at": [3, 4, None, None, None],
        }
    )

    states = HistoricalBacktester.causal_market_states(analysis)

    assert states.iloc[0] == "UNDEFINED"
    assert states.iloc[2] == "UNDEFINED"
    assert states.iloc[3] == "UNDEFINED"
    assert states.iloc[4] == "BULLISH"


def test_rolling_structure_drops_swings_outside_live_window():
    analysis = pd.DataFrame(
        {
            "swing_confirmed": [False] * 55,
            "swing_type": [None] * 55,
            "swing_price": [None] * 55,
            "swing_confirmation_index": [None] * 55,
        }
    )
    for pivot, known_at, swing_type, price in (
        (1, 2, "HIGH", 100.0),
        (2, 3, "LOW", 90.0),
        (3, 4, "HIGH", 110.0),
        (4, 5, "LOW", 95.0),
    ):
        analysis.loc[pivot, "swing_confirmed"] = True
        analysis.loc[pivot, "swing_type"] = swing_type
        analysis.loc[pivot, "swing_price"] = price
        analysis.loc[pivot, "swing_confirmation_index"] = known_at

    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(
            symbol="ETHUSDT",
            analysis_window_bars=50,
        ),
        structure_engine_kwargs={
            "pivot_left": 1,
            "pivot_right": 1,
            "atr_period": 2,
        },
    )
    states = backtester.rolling_causal_market_states(analysis)

    assert states.iloc[5] == "BULLISH"
    assert states.iloc[54] == "UNDEFINED"


def test_rolling_structure_is_invariant_to_older_history():
    def analysis_for_range(start, end):
        size = end - start
        data = pd.DataFrame(
            {
                "swing_confirmed": [False] * size,
                "swing_type": [None] * size,
                "swing_price": [None] * size,
                "swing_confirmation_index": [None] * size,
            }
        )
        events = (
            (12, 13, "HIGH", 100.0),
            (18, 19, "LOW", 90.0),
            (24, 25, "HIGH", 110.0),
            (30, 31, "LOW", 95.0),
            (42, 43, "HIGH", 120.0),
            (48, 49, "LOW", 105.0),
            (56, 57, "HIGH", 125.0),
            (62, 63, "LOW", 110.0),
        )
        for pivot, known_at, swing_type, price in events:
            if not start <= pivot < end:
                continue
            row = pivot - start
            data.loc[row, "swing_confirmed"] = True
            data.loc[row, "swing_type"] = swing_type
            data.loc[row, "swing_price"] = price
            data.loc[row, "swing_confirmation_index"] = known_at - start
        return data

    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(
            symbol="ETHUSDT",
            analysis_window_bars=50,
        ),
        structure_engine_kwargs={
            "pivot_left": 1,
            "pivot_right": 1,
            "atr_period": 2,
        },
    )
    full = backtester.rolling_causal_market_states(
        analysis_for_range(0, 70)
    )
    shortened = backtester.rolling_causal_market_states(
        analysis_for_range(10, 70)
    )

    assert full.iloc[60:].tolist() == shortened.iloc[50:].tolist()


def test_enters_on_next_candle_and_includes_costs():
    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(symbol="BTCUSDT")
    )
    backtester._decision_for_row = signal_only_on_first_row

    result = backtester.run_prepared(prepared_timeline())
    trade = result.trades[0]

    assert trade["signal_index"] == 0
    assert trade["entry_index"] == 1
    assert trade["close_reason"] == "TARGET"
    assert trade["fees"] > 0
    assert trade["pnl"] < trade["gross_pnl"]
    assert trade["source"] == "AUTO"
    assert trade["real_order_sent"] is False
    assert result.report["manual_trades_included"] is False


def test_stop_wins_when_stop_and_target_share_a_candle():
    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(symbol="ETHUSDT")
    )
    backtester._decision_for_row = signal_only_on_first_row

    result = backtester.run_prepared(
        prepared_timeline(second_high=102.0, second_low=99.0)
    )

    assert result.trades[0]["close_reason"] == "STOP"
    assert result.trades[0]["pnl"] < 0


def test_v3_backtest_uses_atr_and_half_percent_risk_plan():
    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(symbol="ETHUSDT")
    )
    backtester._decision_for_row = lambda row: (
        {
            "strategy": "PROJECT_EDGE_V3",
            "decision": "READY_LONG",
            "direction": "LONG",
            "can_execute": True,
            "atr_15m": 0.2,
            "diagnostics": {
                "adx_1h": 31.0,
                "efficiency_ratio_1h": 0.44,
                "atr_pct_15m": 0.002,
            },
        }
        if row.name == 0
        else {"decision": "WAIT", "direction": None, "can_execute": False}
    )

    result = backtester.run_prepared(prepared_timeline())
    trade = result.trades[0]

    assert trade["strategy"] == "PROJECT_EDGE_V3"
    assert trade["risk_budget"] == pytest.approx(50.0)
    assert trade["estimated_risk"] <= 50.0 + 1e-9
    assert trade["position_size"] * trade["entry_price"] <= 10000.0 + 1e-9
    assert trade["estimated_net_reward_risk"] >= 1.5
    assert trade["diag_adx_1h"] == pytest.approx(31.0)
    assert trade["diag_efficiency_ratio_1h"] == pytest.approx(0.44)
    assert trade["diag_atr_pct_15m"] == pytest.approx(0.002)
    assert trade["holding_minutes"] == pytest.approx(5.0)
    assert trade["stop_distance_pct"] > 0
    assert trade["target_distance_pct"] > trade["stop_distance_pct"]


def test_realistic_cost_parameters_are_validated():
    try:
        HistoricalBacktestConfig(symbol="BTCUSDT", fee_rate=-0.1)
    except ValueError as exc:
        assert "fee_rate" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError")


def test_cooldown_blocks_immediate_reentry_after_close():
    open_time = pd.date_range(
        "2026-01-01T00:00:00Z",
        periods=10,
        freq="5min",
    )
    data = {
        "open_time": open_time,
        "close_time": open_time + pd.Timedelta(minutes=5),
        "open": [100.0] * 10,
        "high": [102.0] * 10,
        "low": [99.8] * 10,
        "close": [101.0] * 10,
    }
    for timeframe in ("4H", "1H", "30M", "15M", "5M"):
        data[f"state_{timeframe}"] = ["BULLISH"] * 10

    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(
            symbol="BTCUSDT",
            cooldown_minutes=30,
        )
    )
    backtester._decision_for_row = lambda row: {
        "decision": "READY_LONG",
        "direction": "LONG",
        "can_execute": True,
    }

    result = backtester.run_prepared(pd.DataFrame(data))

    assert len(result.trades) == 2
    assert result.trades[0]["exit_time"] == "2026-01-01T00:10:00+00:00"
    assert result.trades[1]["entry_time"] == "2026-01-01T00:40:00+00:00"
    assert result.report["cooldown_blocked_bars"] == 7


def test_negative_cooldown_is_rejected():
    with pytest.raises(ValueError, match="cooldown_minutes"):
        HistoricalBacktestConfig(
            symbol="BTCUSDT",
            cooldown_minutes=-1,
        )


def test_evaluation_start_excludes_warmup_from_results():
    timeline = pd.concat(
        [prepared_timeline(), prepared_timeline()],
        ignore_index=True,
    )
    timeline["open_time"] = pd.date_range(
        "2026-01-01T00:00:00Z",
        periods=4,
        freq="5min",
    )
    timeline["close_time"] = timeline["open_time"] + pd.Timedelta(minutes=5)

    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(symbol="ETHUSDT")
    )
    backtester._decision_for_row = signal_only_on_first_row

    result = backtester.run_prepared(
        timeline,
        evaluation_start="2026-01-01T00:10:00Z",
    )

    assert result.report["start_time"] == "2026-01-01T00:10:00+00:00"
    assert result.trades[0]["signal_time"] == "2026-01-01T00:15:00+00:00"
