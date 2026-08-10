import math

import pytest

from engine.execution.backtest_report import BacktestReport


def test_report_combines_basic_and_advanced_metrics():
    trades = [
        {"pnl": 200.0},
        {"pnl": -100.0},
        {"pnl": 100.0},
        {"pnl": -50.0},
    ]

    report = BacktestReport().generate(
        trades=trades,
        rejected=2,
        no_trade=3,
    )

    assert report["total_trades"] == 4
    assert report["winners"] == 2
    assert report["losers"] == 2
    assert report["total_pnl"] == pytest.approx(150.0)
    assert report["win_rate"] == pytest.approx(0.5)

    assert report["profit_factor"] == pytest.approx(2.0)
    assert report["average_win"] == pytest.approx(150.0)
    assert report["average_loss"] == pytest.approx(-75.0)
    assert report["expectancy"] == pytest.approx(37.5)
    assert report["max_drawdown"] == pytest.approx(100.0)

    assert report["rejected"] == 2
    assert report["no_trade"] == 3


def test_empty_report_returns_zero_metrics():
    report = BacktestReport().generate([])

    assert report["total_trades"] == 0
    assert report["total_pnl"] == 0
    assert report["win_rate"] == 0
    assert report["profit_factor"] == 0
    assert report["max_drawdown"] == 0
    assert report["rejected"] == 0
    assert report["no_trade"] == 0


def test_report_without_losses_has_infinite_profit_factor():
    report = BacktestReport().generate([
        {"pnl": 100.0},
        {"pnl": 50.0},
    ])

    assert math.isinf(report["profit_factor"])


def test_negative_counters_are_rejected():
    with pytest.raises(ValueError):
        BacktestReport().generate([], rejected=-1)

    with pytest.raises(ValueError):
        BacktestReport().generate([], no_trade=-1)
