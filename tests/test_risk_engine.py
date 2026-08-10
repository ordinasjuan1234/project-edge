import pytest

from engine.risk.risk_engine import RiskEngine


def ready_long():
    return {"decision": "READY_LONG", "direction": "LONG"}


def ready_short():
    return {"decision": "READY_SHORT", "direction": "SHORT"}


def test_ready_long_with_valid_risk_is_approved():
    result = RiskEngine(max_risk_pct=0.01, min_rr=1.5).evaluate(
        decision=ready_long(),
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    assert result["approved"] is True
    assert result["risk_amount"] == pytest.approx(100.0)
    assert result["position_size"] == pytest.approx(50.0)
    assert result["rr"] == pytest.approx(2.0)


def test_ready_short_with_valid_risk_is_approved():
    result = RiskEngine(max_risk_pct=0.01, min_rr=1.5).evaluate(
        decision=ready_short(),
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=102.0,
        target_price=96.0,
    )

    assert result["approved"] is True
    assert result["position_size"] == pytest.approx(50.0)
    assert result["rr"] == pytest.approx(2.0)


def test_non_ready_decision_is_rejected():
    result = RiskEngine().evaluate(
        decision={"decision": "WATCH_LONG", "direction": "LONG"},
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    assert result["approved"] is False
    assert result["position_size"] == 0.0


def test_low_risk_reward_is_rejected():
    result = RiskEngine(min_rr=2.0).evaluate(
        decision=ready_long(),
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=98.0,
        target_price=102.0,
    )

    assert result["approved"] is False
    assert result["rr"] == pytest.approx(1.0)


def test_invalid_long_price_order_raises_error():
    with pytest.raises(ValueError):
        RiskEngine().evaluate(
            decision=ready_long(),
            account_equity=10000.0,
            entry_price=100.0,
            stop_price=101.0,
            target_price=104.0,
        )


def test_max_risk_above_five_percent_is_rejected():
    with pytest.raises(ValueError):
        RiskEngine(max_risk_pct=0.06)
