import pandas as pd
import pytest

from engine.execution.backtest_engine import BacktestEngine, BacktestResult


def open_long_trade():
    return {
        "opened": True,
        "status": "OPEN",
        "mode": "PAPER",
        "direction": "LONG",
        "entry_price": 100.0,
        "stop_price": 98.0,
        "target_price": 104.0,
        "position_size": 50.0,
        "real_order_sent": False,
    }


def test_backtest_closes_trade_at_target():
    candles = pd.DataFrame(
        {
            "high": [101.0, 103.0, 104.5],
            "low": [99.0, 99.5, 100.0],
        }
    )

    result = BacktestEngine().run_trade(open_long_trade(), candles)

    assert result["status"] == "CLOSED"
    assert result["close_reason"] == "TARGET"
    assert result["close_index"] == 2
    assert result["pnl"] == pytest.approx(200.0)


def test_backtest_closes_trade_at_stop():
    candles = pd.DataFrame(
        {
            "high": [101.0, 101.5],
            "low": [99.0, 97.5],
        }
    )

    result = BacktestEngine().run_trade(open_long_trade(), candles)

    assert result["close_reason"] == "STOP"
    assert result["close_index"] == 1
    assert result["pnl"] == pytest.approx(-100.0)


def test_trade_remains_open_if_no_exit_is_hit():
    candles = pd.DataFrame(
        {
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 99.5, 100.0],
        }
    )

    result = BacktestEngine().run_trade(open_long_trade(), candles)

    assert result["status"] == "OPEN"
    assert result["close_index"] is None


def test_summary_calculates_metrics():
    trades = [
        {"pnl": 200.0},
        {"pnl": -100.0},
        {"pnl": 50.0},
        {"pnl": 0.0},
    ]

    summary = BacktestResult(trades=trades).summary()

    assert summary["total_trades"] == 4
    assert summary["winners"] == 2
    assert summary["losers"] == 1
    assert summary["breakeven"] == 1
    assert summary["total_pnl"] == pytest.approx(150.0)
    assert summary["win_rate"] == pytest.approx(0.5)


def test_missing_high_or_low_raises_error():
    candles = pd.DataFrame({"close": [100.0, 101.0]})

    with pytest.raises(ValueError):
        BacktestEngine().run_trade(open_long_trade(), candles)
