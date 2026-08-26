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
