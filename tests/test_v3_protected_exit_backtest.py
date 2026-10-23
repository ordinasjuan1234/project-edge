import pandas as pd
import pytest

from engine.execution.historical_backtest import HistoricalBacktestConfig
from engine.execution.v3_protected_exit_backtest import (
    V3ProtectedExitHistoricalBacktester,
)


def backtester():
    return V3ProtectedExitHistoricalBacktester(
        HistoricalBacktestConfig(symbol="ETHUSDT", strategy="PROJECT_EDGE_V3")
    )


def position(direction="LONG"):
    if direction == "LONG":
        entry, stop, target = 100.0, 98.0, 104.0
    else:
        entry, stop, target = 100.0, 102.0, 96.0
    quantity = 10.0
    return {
        "direction": direction,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "position_size": quantity,
        "entry_fee": entry * quantity * 0.001,
    }


def candle(open_, high, low, close=None):
    return pd.Series(
        {
            "open": float(open_),
            "high": float(high),
            "low": float(low),
            "close": float(close if close is not None else open_),
        }
    )


def test_tp1_moves_long_stop_to_cost_covered_break_even():
    bt = backtester()
    pos = position("LONG")
    result = bt._raw_exit(pos, candle(100.0, 102.2, 99.0))
    assert result is None
    assert pos["tp1_reached"] is True
    assert pos["protected_stop_stage"] == "TP1_TO_BE_COSTS"
    assert pos["stop_price"] > pos["entry_price"]

    raw_stop = pos["stop_price"]
    closed = bt._close_trade(
        {**pos, "entry_time": "2026-01-01T00:00:00+00:00"},
        raw_exit_price=raw_stop,
        reason="PROTECTED_TP1_BE",
        exit_index=1,
        exit_time="2026-01-01T00:05:00+00:00",
    )
    assert closed["pnl"] == pytest.approx(0.0, abs=1e-8)


def test_tp1_moves_short_stop_to_cost_covered_break_even():
    bt = backtester()
    pos = position("SHORT")
    result = bt._raw_exit(pos, candle(100.0, 101.0, 97.8))
    assert result is None
    assert pos["tp1_reached"] is True
    assert pos["protected_stop_stage"] == "TP1_TO_BE_COSTS"
    assert pos["stop_price"] < pos["entry_price"]


def test_tp2_moves_long_stop_to_tp1():
    bt = backtester()
    pos = position("LONG")
    result = bt._raw_exit(pos, candle(100.0, 103.2, 99.0))
    assert result is None
    assert pos["tp1_reached"] is True
    assert pos["tp2_reached"] is True
    assert pos["protected_stop_stage"] == "TP2_TO_TP1"
    assert pos["stop_price"] == pytest.approx(102.0)


def test_tp2_moves_short_stop_to_tp1():
    bt = backtester()
    pos = position("SHORT")
    result = bt._raw_exit(pos, candle(100.0, 101.0, 96.8))
    assert result is None
    assert pos["tp2_reached"] is True
    assert pos["protected_stop_stage"] == "TP2_TO_TP1"
    assert pos["stop_price"] == pytest.approx(98.0)


def test_protected_tp2_stop_closes_with_positive_result():
    bt = backtester()
    pos = position("LONG")
    bt._raw_exit(pos, candle(100.0, 103.2, 99.0))
    hit = bt._raw_exit(pos, candle(103.0, 103.1, 101.5))
    assert hit is not None
    raw_exit, reason = hit
    assert raw_exit == pytest.approx(102.0)
    assert reason == "PROTECTED_TP2_TP1"


def test_original_stop_wins_if_same_candle_touches_stop_and_tp1():
    bt = backtester()
    pos = position("LONG")
    hit = bt._raw_exit(pos, candle(100.0, 102.5, 97.5))
    assert hit == (98.0, "STOP")
    assert "tp1_reached" not in pos


def test_tp3_still_closes_at_original_target():
    bt = backtester()
    pos = position("LONG")
    hit = bt._raw_exit(pos, candle(100.0, 104.5, 99.0))
    assert hit == (104.0, "TARGET")


def test_rejects_non_v3_strategy():
    with pytest.raises(ValueError, match="PROJECT_EDGE_V3"):
        V3ProtectedExitHistoricalBacktester(
            HistoricalBacktestConfig(
                symbol="ETHUSDT",
                strategy="PROJECT_EDGE_V4_INTRADAY",
            )
        )
