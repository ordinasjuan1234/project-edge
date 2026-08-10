import math

import pytest

from engine.execution.backtest_metrics import BacktestMetrics


def test_calculates_profit_factor_and_averages():
    trades = [
        {"pnl": 200.0},
        {"pnl": -100.0},
        {"pnl": 100.0},
        {"pnl": -50.0},
    ]

    result = BacktestMetrics().calculate(trades)

    assert result["profit_factor"] == pytest.approx(2.0)
    assert result["average_win"] == pytest.approx(150.0)
    assert result["average_loss"] == pytest.approx(-75.0)
    assert result["expectancy"] == pytest.approx(37.5)


def test_calculates_max_drawdown_from_equity_curve():
    trades = [
        {"pnl": 100.0},
        {"pnl": 50.0},
        {"pnl": -80.0},
        {"pnl": -100.0},
        {"pnl": 200.0},
    ]

    result = BacktestMetrics().calculate(trades)

    assert result["max_drawdown"] == pytest.approx(180.0)


def test_no_losses_returns_infinite_profit_factor():
    trades = [
        {"pnl": 100.0},
        {"pnl": 50.0},
    ]

    result = BacktestMetrics().calculate(trades)

    assert math.isinf(result["profit_factor"])
    assert result["max_drawdown"] == pytest.approx(0.0)


def test_empty_trades_return_zero_metrics():
    result = BacktestMetrics().calculate([])

    assert result["profit_factor"] == 0.0
    assert result["max_drawdown"] == 0.0
    assert result["average_win"] == 0.0
    assert result["average_loss"] == 0.0
    assert result["expectancy"] == 0.0


def test_breakeven_trade_does_not_count_as_win_or_loss():
    trades = [
        {"pnl": 100.0},
        {"pnl": -50.0},
        {"pnl": 0.0},
    ]

    result = BacktestMetrics().calculate(trades)

    assert result["profit_factor"] == pytest.approx(2.0)
    assert result["expectancy"] == pytest.approx(100.0 / 3 - 50.0 / 3)
