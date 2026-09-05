import csv
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd
import pytest

from engine.decision.project_edge_v3 import ProjectEdgeV3
from engine.decision.project_edge_v5 import ProjectEdgeV5
from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktester,
)
from engine.execution.portfolio_historical_backtest import (
    PortfolioHistoricalBacktester,
    PortfolioHistoricalConfig,
)
import run_btc_paper
import run_v5_comparison
from trading_mode import RealModeLockedError


V5 = "PROJECT_EDGE_V5_DUAL_SETUP"


def test_historical_config_accepts_v5_but_live_runner_remains_v3():
    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(symbol="ETHUSDT", strategy=V5)
    )
    assert isinstance(backtester.selected_strategy, ProjectEdgeV5)
    assert isinstance(run_btc_paper.STRATEGY, ProjectEdgeV3)
    assert not isinstance(run_btc_paper.STRATEGY, ProjectEdgeV5)
    source = Path(run_btc_paper.__file__).read_text(encoding="utf-8")
    assert "PROJECT_EDGE_V5" not in source


def test_historical_config_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        HistoricalBacktestConfig(symbol="ETHUSDT", strategy="UNKNOWN_V5")


def test_portfolio_can_select_v5_without_changing_v4_default():
    legacy = PortfolioHistoricalBacktester()
    v5 = PortfolioHistoricalBacktester(PortfolioHistoricalConfig(strategy=V5))
    assert all(
        backtester.config.strategy == "PROJECT_EDGE_V4_INTRADAY"
        for backtester in legacy.backtesters.values()
    )
    assert all(
        isinstance(backtester.selected_strategy, ProjectEdgeV5)
        for backtester in v5.backtesters.values()
    )


def simple_timeline():
    close_times = pd.date_range(
        "2026-01-01 00:05", periods=4, freq="5min", tz="UTC"
    )
    result = pd.DataFrame(
        {
            "open_time": close_times - pd.Timedelta(minutes=5),
            "close_time": close_times,
            "open": [100.0] * 4,
            "high": [100.5, 110.0, 100.5, 100.5],
            "low": [99.5, 99.5, 99.5, 99.5],
            "close": [100.0] * 4,
        }
    )
    for timeframe in ("4H", "1H", "30M", "15M", "5M"):
        result[f"state_{timeframe}"] = "TRANSITION"
    return result


def ready_v5(score, direction="LONG", setup="PULLBACK_CONTINUATION"):
    return {
        "strategy": V5,
        "decision": f"READY_{direction}",
        "direction": direction,
        "setup_type": setup,
        "can_execute": True,
        "atr_15m": 1.0,
        "quality_score": score,
        "diagnostics": {"setup_type": setup},
    }


def test_v5_portfolio_selects_one_best_signal_and_reports_breakdowns():
    portfolio = PortfolioHistoricalBacktester(
        PortfolioHistoricalConfig(strategy=V5)
    )
    portfolio.backtesters["BTCUSDT"]._decision_for_row = (
        lambda row: ready_v5(90, "LONG", "PULLBACK_CONTINUATION")
    )
    portfolio.backtesters["ETHUSDT"]._decision_for_row = (
        lambda row: ready_v5(70, "SHORT", "BREAKOUT_RETEST")
    )
    timelines = {
        "BTCUSDT": simple_timeline(),
        "ETHUSDT": simple_timeline(),
    }
    result = portfolio.run_prepared(timelines)
    assert result.report["shared_balance"] is True
    assert result.report["one_position_at_a_time"] is True
    assert result.report["simultaneous_signal_bars"] == 1
    assert result.report["ready_signals_by_symbol"] == {
        "BTCUSDT": 1,
        "ETHUSDT": 1,
    }
    assert result.report["ready_signals_by_direction"] == {
        "LONG": 1,
        "SHORT": 1,
    }
    assert result.report["ready_signals_by_setup"] == {
        "PULLBACK_CONTINUATION": 1,
        "BREAKOUT_RETEST": 1,
    }
    assert result.report["total_trades"] == 1
    assert result.report["trades_by_symbol"] == {"BTCUSDT": 1}
    assert result.report["trades_by_direction"] == {"LONG": 1}
    assert result.report["trades_by_setup"] == {"PULLBACK_CONTINUATION": 1}
    assert result.trades[0]["strategy"] == V5
    assert result.trades[0]["setup_type"] == "PULLBACK_CONTINUATION"
    assert result.trades[0]["real_order_sent"] is False


def test_comparator_blocks_real_before_market_or_files(monkeypatch):
    monkeypatch.setenv("PROJECT_EDGE_MODE", "REAL")
    monkeypatch.setattr(
        run_v5_comparison,
        "BinanceHistoricalData",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("No debe consultar mercado")
        ),
    )
    with patch.object(sys, "argv", ["run_v5_comparison.py"]):
        with pytest.raises(RealModeLockedError):
            run_v5_comparison.main()


def test_v5_outputs_include_setup_type(tmp_path):
    reports = {
        key: {
            "candidate": candidate,
            "symbol": "ETHUSDT",
            "total_trades": 1,
            "trades_per_day": 0.01,
            "winners": 1,
            "losers": 0,
            "win_rate": 1.0,
            "total_pnl": 2.0,
            "return_pct": 0.0002,
            "profit_factor": float("inf"),
            "max_drawdown_pct": 0.0,
            "total_fees": 0.5,
            "cost_per_trade": 0.5,
        }
        for key, candidate in {
            "v3_eth": "V3_ETH_ACTUAL",
            "v5_eth": "V5_ETH_DUAL_SETUP",
            "v5_portfolio": "V5_BTC_ETH_UNA_POSICION",
        }.items()
    }
    trade = {
        "symbol": "ETHUSDT",
        "strategy": V5,
        "setup_type": "BREAKOUT_RETEST",
        "direction": "LONG",
        "pnl": 2.0,
        "real_order_sent": False,
    }
    run_v5_comparison.write_outputs(
        tmp_path,
        {"mode": "PAPER_BACKTEST_ONLY", "reports": reports},
        {"V5_ETH_DUAL_SETUP": [trade]},
    )
    payload = json.loads(
        (tmp_path / "v5_comparison_report.json").read_text(encoding="utf-8")
    )
    assert payload["reports"]["v3_eth"]["profit_factor"] is None
    with (tmp_path / "v5_comparison_trades.csv").open(
        newline="", encoding="utf-8"
    ) as file:
        trades = list(csv.DictReader(file))
    assert trades[0]["setup_type"] == "BREAKOUT_RETEST"
    assert trades[0]["real_order_sent"] == "False"


def test_workflow_is_paper_only_and_defaults_to_unseen_block():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/v5_dual_setup_comparison.yml"
    ).read_text(encoding="utf-8")
    assert "PROJECT_EDGE_MODE: PAPER" in workflow
    assert "default: '5'" in workflow
    assert "run_v5_comparison.py" in workflow
    assert "workflow_dispatch" in workflow
