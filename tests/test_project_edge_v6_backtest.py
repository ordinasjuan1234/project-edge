import csv
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd
import pytest

from engine.decision.project_edge_v3 import ProjectEdgeV3
from engine.decision.project_edge_v6 import ProjectEdgeV6
from engine.execution.v6_historical_backtest import (
    V6HistoricalBacktester,
    V6PortfolioHistoricalBacktester,
    V6_STRATEGY,
)
import run_btc_paper
import run_v6_comparison
from trading_mode import RealModeLockedError


def constant_timeline(periods=50):
    close_times = pd.date_range(
        "2026-01-01 00:05",
        periods=periods,
        freq="5min",
        tz="UTC",
    )
    result = pd.DataFrame(
        {
            "open_time": close_times - pd.Timedelta(minutes=5),
            "close_time": close_times,
            "open": [100.0] * periods,
            "high": [100.10] * periods,
            "low": [99.90] * periods,
            "close": [100.0] * periods,
        }
    )
    for timeframe in ("4H", "1H", "30M", "15M", "5M"):
        result[f"state_{timeframe}"] = "TRANSITION"
    return result


def ready_v6(score=80.0, direction="LONG", setup="SCALP_PULLBACK"):
    return {
        "strategy": V6_STRATEGY,
        "decision": f"READY_{direction}",
        "direction": direction,
        "setup_type": setup,
        "can_execute": True,
        "atr_15m": 1.0,
        "quality_score": score,
        "diagnostics": {
            "setup_type": setup,
        },
    }


def test_v6_adapter_does_not_replace_live_auto_strategy():
    backtester = V6HistoricalBacktester("ETHUSDT")
    assert isinstance(backtester.selected_strategy, ProjectEdgeV6)
    assert isinstance(run_btc_paper.STRATEGY, ProjectEdgeV3)
    live_source = Path(run_btc_paper.__file__).read_text(encoding="utf-8")
    assert "PROJECT_EDGE_V6" not in live_source


def test_v6_time_exit_closes_after_four_hours_without_stop_or_target():
    backtester = V6HistoricalBacktester("ETHUSDT")
    backtester._decision_for_row = lambda row: {
        **ready_v6(),
        "strategy": "PROJECT_EDGE_V3",
    }
    result = backtester.run_prepared(constant_timeline())
    assert result.trades
    first = result.trades[0]
    assert first["close_reason"] == "TIME_EXIT"
    assert first["holding_minutes"] >= 240.0
    assert first["strategy"] == V6_STRATEGY
    assert first["real_order_sent"] is False


def test_v6_portfolio_selects_single_best_symbol():
    portfolio = V6PortfolioHistoricalBacktester()
    portfolio.backtesters["BTCUSDT"]._decision_for_row = lambda row: {
        **ready_v6(90, "LONG", "SCALP_PULLBACK"),
        "strategy": "PROJECT_EDGE_V3",
    }
    portfolio.backtesters["ETHUSDT"]._decision_for_row = lambda row: {
        **ready_v6(70, "SHORT", "SCALP_MOMENTUM"),
        "strategy": "PROJECT_EDGE_V3",
    }
    timelines = {
        "BTCUSDT": constant_timeline(),
        "ETHUSDT": constant_timeline(),
    }
    result = portfolio.run_prepared(timelines)
    assert result.report["shared_balance"] is True
    assert result.report["one_position_at_a_time"] is True
    assert result.trades
    assert result.trades[0]["symbol"] == "BTCUSDT"
    assert result.trades[0]["strategy"] == V6_STRATEGY
    assert result.report["trades_by_direction"]["LONG"] >= 1


def test_comparator_blocks_real_before_market_or_output(monkeypatch):
    monkeypatch.setenv("PROJECT_EDGE_MODE", "REAL")
    monkeypatch.setattr(
        run_v6_comparison,
        "BinanceHistoricalData",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("No debe consultar mercado")
        ),
    )
    with patch.object(sys, "argv", ["run_v6_comparison.py"]):
        with pytest.raises(RealModeLockedError):
            run_v6_comparison.main()


def test_v6_outputs_preserve_setup_and_never_real(tmp_path):
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
            "v6_eth": "V6_ETH_SCALP",
            "v6_portfolio": "V6_BTC_ETH_SCALP",
        }.items()
    }
    trade = {
        "symbol": "ETHUSDT",
        "strategy": V6_STRATEGY,
        "setup_type": "SCALP_MOMENTUM",
        "direction": "LONG",
        "close_reason": "TIME_EXIT",
        "pnl": 2.0,
        "real_order_sent": False,
    }
    run_v6_comparison.write_outputs(
        tmp_path,
        {"mode": "PAPER_BACKTEST_ONLY", "reports": reports},
        {"V6_ETH_SCALP": [trade]},
    )

    payload = json.loads(
        (tmp_path / "v6_comparison_report.json").read_text(encoding="utf-8")
    )
    assert payload["reports"]["v3_eth"]["profit_factor"] is None

    with (tmp_path / "v6_comparison_trades.csv").open(
        newline="",
        encoding="utf-8",
    ) as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["setup_type"] == "SCALP_MOMENTUM"
    assert rows[0]["close_reason"] == "TIME_EXIT"
    assert rows[0]["real_order_sent"] == "False"


def test_workflow_is_paper_only_and_uses_unseen_block():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/v6_scalp_comparison.yml"
    ).read_text(encoding="utf-8")
    assert "PROJECT_EDGE_MODE: PAPER" in workflow
    assert "default: '2'" in workflow
    assert "run_v6_comparison.py" in workflow
    assert "workflow_dispatch" in workflow
