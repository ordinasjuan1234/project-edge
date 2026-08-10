import pytest

from engine.execution.trade_manager import TradeManager


def open_trade(direction="LONG"):
    if direction == "LONG":
        stop, target = 98.0, 104.0
    else:
        stop, target = 102.0, 96.0

    return {
        "opened": True,
        "status": "OPEN",
        "mode": "PAPER",
        "direction": direction,
        "entry_price": 100.0,
        "stop_price": stop,
        "target_price": target,
        "position_size": 50.0,
        "real_order_sent": False,
    }


def test_long_stays_open_when_no_level_is_hit():
    result = TradeManager().update_trade(
        open_trade("LONG"),
        candle_high=103.0,
        candle_low=99.0,
    )
    assert result["status"] == "OPEN"
    assert result["opened"] is True


def test_long_closes_at_target():
    result = TradeManager().update_trade(
        open_trade("LONG"),
        candle_high=104.5,
        candle_low=99.0,
    )
    assert result["status"] == "CLOSED"
    assert result["close_reason"] == "TARGET"
    assert result["exit_price"] == pytest.approx(104.0)
    assert result["pnl"] == pytest.approx(200.0)


def test_long_closes_at_stop():
    result = TradeManager().update_trade(
        open_trade("LONG"),
        candle_high=101.0,
        candle_low=97.5,
    )
    assert result["close_reason"] == "STOP"
    assert result["pnl"] == pytest.approx(-100.0)


def test_same_candle_uses_conservative_stop_first():
    result = TradeManager().update_trade(
        open_trade("LONG"),
        candle_high=105.0,
        candle_low=97.0,
    )
    assert result["close_reason"] == "STOP"


def test_short_closes_at_target():
    result = TradeManager().update_trade(
        open_trade("SHORT"),
        candle_high=101.0,
        candle_low=95.5,
    )
    assert result["close_reason"] == "TARGET"
    assert result["pnl"] == pytest.approx(200.0)


def test_invalid_candle_raises_error():
    with pytest.raises(ValueError):
        TradeManager().update_trade(
            open_trade("LONG"),
            candle_high=99.0,
            candle_low=101.0,
        )
