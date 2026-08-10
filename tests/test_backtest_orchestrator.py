import pandas as pd

from engine.execution.backtest_orchestrator import BacktestOrchestrator


def sample_ohlc(offset: float = 0.0):
    close = [
        100, 102, 105, 103, 99, 101, 106, 110,
        107, 104, 108, 113, 117, 114, 110, 112,
        118, 121, 117, 113, 109, 112, 116, 120,
        115, 111, 107, 110, 114, 119,
    ]
    close = [x + offset for x in close]

    return pd.DataFrame({
        "open": close,
        "high": [x + 1.0 for x in close],
        "low": [x - 1.0 for x in close],
        "close": close,
    })


def sample_timeframes():
    return {
        "4H": sample_ohlc(0.0),
        "1H": sample_ohlc(1.0),
        "30M": sample_ohlc(2.0),
        "15M": sample_ohlc(3.0),
        "5M": sample_ohlc(4.0),
    }


def engine():
    return BacktestOrchestrator(
        account_equity=10000.0,
        max_risk_pct=0.01,
        min_rr=1.5,
        structure_engine_kwargs={
            "pivot_left": 2,
            "pivot_right": 2,
            "atr_period": 3,
            "atr_multiplier": 1.0,
            "min_move_pct": 0.001,
            "max_move_pct": 0.10,
        },
    )


def test_run_case_returns_complete_pipeline_result():
    future = pd.DataFrame({
        "high": [120.0, 121.0],
        "low": [118.0, 117.0],
    })

    result = engine().run_case(
        timeframe_data=sample_timeframes(),
        entry_price=119.0,
        stop_price=123.0,
        target_price=113.0,
        future_candles=future,
    )

    assert "executed" in result
    assert "trade_status" in result
    assert "gate" in result
    assert "mtf" in result


def test_summary_returns_backtest_metrics():
    summary = engine().summarize_cases([])

    assert summary["total_trades"] == 0
    assert summary["winners"] == 0
    assert summary["losers"] == 0
    assert summary["total_pnl"] == 0
    assert summary["win_rate"] == 0
    assert summary["rejected"] == 0
    assert summary["no_trade"] == 0


def test_invalid_equity_raises_error():
    try:
        BacktestOrchestrator(account_equity=0)
    except ValueError as exc:
        assert "account_equity" in str(exc)
    else:
        raise AssertionError("Se esperaba ValueError")
