"""La candidata v4 permanece aislada y solo se evalua en PAPER backtest."""

import csv
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd
import pytest

from engine.decision.project_edge_v3 import ProjectEdgeV3
from engine.decision.project_edge_v4 import (
    ProjectEdgeV4,
    ProjectEdgeV4Config,
)
from engine.execution.historical_backtest import HistoricalBacktestConfig
from engine.execution.portfolio_historical_backtest import (
    PortfolioHistoricalBacktester,
)
import run_btc_paper
import run_v4_comparison
from trading_mode import RealModeLockedError


def v4_snapshot(direction="LONG"):
    long_side = direction == "LONG"
    one_hour = "BULLISH" if long_side else "BEARISH"
    snapshot = {
        "state_4H": "TRANSITION",
        "state_1H": one_hour,
        "state_30M": "TRANSITION",
        "state_15M": "TRANSITION",
        "state_5M": "TRANSITION",
        "pe_ema_fast_1H": 110.0 if long_side else 90.0,
        "pe_ema_slow_1H": 100.0,
        "pe_ema_slope_1H": 1.0 if long_side else -1.0,
        "pe_ema_fast_4H": 100.0,
        "pe_ema_slow_4H": 100.0,
        "pe_ema_slope_4H": 0.0,
        "pe_adx_1H": 30.0,
        "pe_adx_rising_1H": False,
        "pe_efficiency_ratio_1H": 0.30,
        "pe_atr_15M": 2.0,
        "pe_atr_5M": 1.0,
        "pe_close_5M": 100.0,
        "pe_distance_from_ema_pct_5M": 0.005,
        f"pe_pullback_{'long' if long_side else 'short'}_15M": True,
        f"pe_trigger_{'long' if long_side else 'short'}_5M": True,
        f"pe_fvg_{'long' if long_side else 'short'}_15M": False,
        f"pe_fvg_{'long' if long_side else 'short'}_5M": False,
    }
    return snapshot


def test_v4_allows_4h_transition_but_v3_keeps_waiting():
    snapshot = v4_snapshot("LONG")
    v4 = ProjectEdgeV4().decide_snapshot(snapshot)
    v3 = ProjectEdgeV3().decide_snapshot(snapshot)
    assert v4["decision"] == "READY_LONG"
    assert v4["can_execute"] is True
    assert v4["checks"]["macro_4h_not_strongly_opposed"] is True
    assert v3["decision"] == "WAIT"
    assert v3["can_execute"] is False


def test_v4_supports_short_with_one_hour_direction():
    decision = ProjectEdgeV4().decide_snapshot(v4_snapshot("SHORT"))
    assert decision["decision"] == "READY_SHORT"
    assert decision["can_execute"] is True


def test_v4_blocks_strong_4h_opposition():
    snapshot = v4_snapshot("LONG")
    snapshot.update(
        state_4H="BEARISH",
        pe_ema_fast_4H=90.0,
        pe_ema_slow_4H=100.0,
        pe_ema_slope_4H=-1.0,
    )
    decision = ProjectEdgeV4().decide_snapshot(snapshot)
    assert decision["decision"] == "WATCH_LONG"
    assert decision["can_execute"] is False
    assert decision["checks"]["macro_4h_not_strongly_opposed"] is False


@pytest.mark.parametrize(
    "field,value,missing_check",
    [
        ("pe_adx_1H", 29.99, "adx_1h"),
        ("pe_efficiency_ratio_1H", 0.299, "efficiency_1h"),
        ("pe_distance_from_ema_pct_5M", 0.011, "trigger_not_extended"),
        ("pe_trigger_long_5M", False, "trigger_5m"),
        ("pe_pullback_long_15M", False, "pullback_15m"),
    ],
)
def test_v4_quality_guards_are_independent(field, value, missing_check):
    snapshot = v4_snapshot("LONG")
    snapshot[field] = value
    decision = ProjectEdgeV4().decide_snapshot(snapshot)
    assert decision["can_execute"] is False
    assert decision["checks"][missing_check] is False
    assert missing_check in decision["reason"]


def test_v4_fvg_and_rising_adx_rank_but_do_not_create_a_signal():
    strategy = ProjectEdgeV4()
    plain = strategy.decide_snapshot(v4_snapshot("LONG"))
    enriched_snapshot = v4_snapshot("LONG")
    enriched_snapshot["pe_fvg_long_5M"] = True
    enriched_snapshot["pe_adx_rising_1H"] = True
    enriched = strategy.decide_snapshot(enriched_snapshot)
    assert plain["can_execute"] is enriched["can_execute"] is True
    assert enriched["quality_score"] == pytest.approx(
        plain["quality_score"] + 10.0
    )


def test_v4_reuses_v3_money_management_without_leverage():
    strategy = ProjectEdgeV4()
    decision = strategy.decide_snapshot(v4_snapshot("LONG"))
    plan = strategy.build_trade_plan(decision, entry_price=100, account_equity=1000)
    assert plan["approved"] is True
    assert plan["leverage"] == 1
    assert plan["risk_budget"] == pytest.approx(5.0)
    assert plan["estimated_risk"] <= 5.0 + 1e-9
    assert plan["estimated_net_reward_risk"] >= 1.5
    assert plan["exposure"] <= 1000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"efficiency_minimum": 0},
        {"efficiency_minimum": 1.1},
        {"max_trigger_distance_atr": 0},
    ],
)
def test_v4_rejects_invalid_new_parameters(kwargs):
    with pytest.raises(ValueError):
        ProjectEdgeV4Config(**kwargs)


def simple_timeline():
    close_times = pd.date_range("2026-01-01 00:05", periods=4, freq="5min", tz="UTC")
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
        result[f"state_{timeframe}"] = "BULLISH"
    return result


def ready_decision(score):
    return {
        "strategy": "PROJECT_EDGE_V4_INTRADAY",
        "decision": "READY_LONG",
        "direction": "LONG",
        "can_execute": True,
        "atr_15m": 1.0,
        "quality_score": score,
        "diagnostics": {},
    }


def test_portfolio_uses_shared_balance_and_selects_only_best_signal():
    portfolio = PortfolioHistoricalBacktester()
    portfolio.backtesters["BTCUSDT"]._decision_for_row = lambda row: ready_decision(90)
    portfolio.backtesters["ETHUSDT"]._decision_for_row = lambda row: ready_decision(70)
    timelines = {
        "BTCUSDT": simple_timeline(),
        "ETHUSDT": simple_timeline(),
    }
    original = {symbol: frame.copy(deep=True) for symbol, frame in timelines.items()}
    result = portfolio.run_prepared(timelines)
    assert result.report["shared_balance"] is True
    assert result.report["one_position_at_a_time"] is True
    assert result.report["simultaneous_signal_bars"] == 1
    assert result.report["ready_signals_by_symbol"] == {
        "BTCUSDT": 1,
        "ETHUSDT": 1,
    }
    assert result.report["total_trades"] == 1
    assert result.report["trades_by_symbol"] == {"BTCUSDT": 1}
    assert result.trades[0]["symbol"] == "BTCUSDT"
    assert result.trades[0]["real_order_sent"] is False
    assert result.report["final_balance"] == pytest.approx(
        10000 + result.trades[0]["pnl"]
    )
    for symbol in timelines:
        pd.testing.assert_frame_equal(timelines[symbol], original[symbol])


def test_historical_config_accepts_v4_but_live_runner_remains_v3():
    config = HistoricalBacktestConfig(
        symbol="ETHUSDT",
        strategy="PROJECT_EDGE_V4_INTRADAY",
    )
    assert config.strategy == "PROJECT_EDGE_V4_INTRADAY"
    assert isinstance(run_btc_paper.STRATEGY, ProjectEdgeV3)
    assert not isinstance(run_btc_paper.STRATEGY, ProjectEdgeV4)
    source = Path(run_btc_paper.__file__).read_text(encoding="utf-8")
    assert "PROJECT_EDGE_V4" not in source


def test_comparator_blocks_real_before_market_or_files(monkeypatch):
    monkeypatch.setenv("PROJECT_EDGE_MODE", "REAL")
    monkeypatch.setattr(
        run_v4_comparison,
        "BinanceHistoricalData",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("No debe consultar mercado")
        ),
    )
    with patch.object(sys, "argv", ["run_v4_comparison.py"]):
        with pytest.raises(RealModeLockedError):
            run_v4_comparison.main()


def test_comparator_outputs_summary_report_and_trade_detail(tmp_path):
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
            "v4_eth": "V4_ETH_MISMO_ACTIVO",
            "v4_portfolio": "V4_BTC_ETH_UNA_POSICION",
        }.items()
    }
    trade = {
        "symbol": "ETHUSDT",
        "strategy": "PROJECT_EDGE_V4_INTRADAY",
        "direction": "LONG",
        "pnl": 2.0,
        "real_order_sent": False,
    }
    run_v4_comparison.write_outputs(
        tmp_path,
        {"mode": "PAPER_BACKTEST_ONLY", "reports": reports},
        {"V4_ETH_MISMO_ACTIVO": [trade]},
    )

    payload = json.loads(
        (tmp_path / "v4_comparison_report.json").read_text(encoding="utf-8")
    )
    assert payload["reports"]["v3_eth"]["profit_factor"] is None
    with (tmp_path / "v4_comparison_summary.csv").open(
        newline="", encoding="utf-8"
    ) as file:
        summary = list(csv.DictReader(file))
    assert [row["candidate"] for row in summary] == [
        "V3_ETH_ACTUAL",
        "V4_ETH_MISMO_ACTIVO",
        "V4_BTC_ETH_UNA_POSICION",
    ]
    with (tmp_path / "v4_comparison_trades.csv").open(
        newline="", encoding="utf-8"
    ) as file:
        trades = list(csv.DictReader(file))
    assert trades[0]["candidate"] == "V4_ETH_MISMO_ACTIVO"
    assert trades[0]["real_order_sent"] == "False"


def test_workflow_runs_only_paper_out_of_sample_blocks():
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/v4_intraday_comparison.yml"
    ).read_text(encoding="utf-8")
    assert "PROJECT_EDGE_MODE: PAPER" in workflow
    assert "years_ago:" in workflow
    assert "- 3" in workflow
    assert "- 4" in workflow
    assert "run_v4_comparison.py" in workflow
    assert "workflow_dispatch" in workflow
