import pandas as pd
import pytest

from engine.execution.historical_backtest import HistoricalBacktestConfig
from engine.execution.v3_tp2_protection_backtest import (
    V3TP2ProtectionHistoricalBacktester,
)


def backtester():
    return V3TP2ProtectionHistoricalBacktester(
        HistoricalBacktestConfig(symbol="ETHUSDT", strategy="PROJECT_EDGE_V3")
    )


def position(direction="LONG"):
    if direction == "LONG":
        entry, stop, target = 100.0, 98.0, 104.0
    else:
        entry, stop, target = 100.0, 102.0, 96.0
    return {
        "direction": direction,
        "entry_price": entry,
        "stop_price": stop,
        "target_price": target,
        "position_size": 10.0,
        "entry_fee": 1.0,
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


def test_tp1_does_not_move_long_stop():
    bt = backtester()
    pos = position("LONG")
    assert bt._raw_exit(pos, candle(100.0, 102.2, 99.0)) is None
    assert pos["tp1_reached"] is True
    assert pos["stop_price"] == pytest.approx(98.0)
    assert not bool(pos.get("tp2_protection_active"))


def test_tp1_does_not_move_short_stop():
    bt = backtester()
    pos = position("SHORT")
    assert bt._raw_exit(pos, candle(100.0, 101.0, 97.8)) is None
    assert pos["tp1_reached"] is True
    assert pos["stop_price"] == pytest.approx(102.0)
    assert not bool(pos.get("tp2_protection_active"))


def test_tp2_moves_long_stop_to_tp1():
    bt = backtester()
    pos = position("LONG")
    assert bt._raw_exit(pos, candle(100.0, 103.2, 99.0)) is None
    assert pos["tp2_reached"] is True
    assert pos["tp2_protection_active"] is True
    assert pos["stop_price"] == pytest.approx(102.0)


def test_tp2_moves_short_stop_to_tp1():
    bt = backtester()
    pos = position("SHORT")
    assert bt._raw_exit(pos, candle(100.0, 101.0, 96.8)) is None
    assert pos["tp2_reached"] is True
    assert pos["tp2_protection_active"] is True
    assert pos["stop_price"] == pytest.approx(98.0)


def test_protected_long_exit_uses_tp1():
    bt = backtester()
    pos = position("LONG")
    bt._raw_exit(pos, candle(100.0, 103.2, 99.0))
    assert bt._raw_exit(pos, candle(103.0, 103.1, 101.5)) == (
        102.0,
        "PROTECTED_TP2_TP1",
    )


def test_protected_short_exit_uses_tp1():
    bt = backtester()
    pos = position("SHORT")
    bt._raw_exit(pos, candle(100.0, 101.0, 96.8))
    assert bt._raw_exit(pos, candle(97.0, 98.5, 96.9)) == (
        98.0,
        "PROTECTED_TP2_TP1",
    )


def test_original_stop_wins_if_same_candle_touches_stop_and_tp2():
    bt = backtester()
    pos = position("LONG")
    assert bt._raw_exit(pos, candle(100.0, 103.5, 97.5)) == (98.0, "STOP")
    assert not bool(pos.get("tp2_protection_active"))


def test_tp3_still_closes_at_original_target():
    bt = backtester()
    pos = position("LONG")
    assert bt._raw_exit(pos, candle(100.0, 104.5, 99.0)) == (104.0, "TARGET")


def test_rejects_non_v3_strategy():
    with pytest.raises(ValueError, match="PROJECT_EDGE_V3"):
        V3TP2ProtectionHistoricalBacktester(
            HistoricalBacktestConfig(
                symbol="ETHUSDT",
                strategy="PROJECT_EDGE_V4_INTRADAY",
            )
        )
