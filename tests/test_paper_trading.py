import pytest

from engine.execution.paper_trading import PaperTradingEngine


def authorized_gate(direction="LONG", position_size=50.0):
    return {
        "demo_authorized": True,
        "decision": {
            "decision": f"READY_{direction}",
            "direction": direction,
        },
        "risk": {
            "approved": True,
            "position_size": position_size,
        },
        "reason": "Decisión y riesgo aprobados para simulación.",
    }


def test_open_long_paper_trade():
    trade = PaperTradingEngine().open_trade(
        gate_result=authorized_gate("LONG", 50.0),
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    assert trade["opened"] is True
    assert trade["status"] == "OPEN"
    assert trade["mode"] == "PAPER"
    assert trade["direction"] == "LONG"
    assert trade["position_size"] == pytest.approx(50.0)
    assert trade["real_order_sent"] is False


def test_rejected_gate_does_not_open_trade():
    trade = PaperTradingEngine().open_trade(
        gate_result={
            "demo_authorized": False,
            "reason": "Riesgo rechazado.",
        },
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    assert trade["opened"] is False
    assert trade["status"] == "REJECTED"


def test_close_long_calculates_positive_pnl():
    engine = PaperTradingEngine()
    trade = engine.open_trade(
        gate_result=authorized_gate("LONG", 50.0),
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    closed = engine.close_trade(trade, exit_price=104.0)

    assert closed["status"] == "CLOSED"
    assert closed["pnl"] == pytest.approx(200.0)
    assert closed["real_order_sent"] is False


def test_close_short_calculates_positive_pnl():
    engine = PaperTradingEngine()
    trade = engine.open_trade(
        gate_result=authorized_gate("SHORT", 50.0),
        entry_price=100.0,
        stop_price=102.0,
        target_price=96.0,
    )

    closed = engine.close_trade(trade, exit_price=96.0)

    assert closed["pnl"] == pytest.approx(200.0)


def test_cannot_close_rejected_trade():
    with pytest.raises(ValueError):
        PaperTradingEngine().close_trade(
            {"opened": False, "status": "REJECTED"},
            exit_price=100.0,
        )
