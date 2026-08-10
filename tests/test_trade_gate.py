from engine.execution.trade_gate import TradeGate


def mtf(states, alignment):
    return {
        "states": states,
        "alignment": {
            "alignment": alignment,
            "entry_ready": alignment == "FULL_ALIGNMENT",
        },
    }


def bullish_states():
    return {
        "4H": "BULLISH",
        "1H": "BULLISH",
        "30M": "BULLISH",
        "15M": "BULLISH",
        "5M": "BULLISH",
    }


def test_ready_long_and_valid_risk_authorizes_demo():
    result = TradeGate(max_risk_pct=0.01, min_rr=1.5).evaluate(
        mtf_result=mtf(bullish_states(), "FULL_ALIGNMENT"),
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    assert result["trade_status"] == "DEMO_READY"
    assert result["demo_authorized"] is True
    assert result["decision"]["decision"] == "READY_LONG"
    assert result["risk"]["approved"] is True


def test_watch_state_never_reaches_risk_execution():
    states = bullish_states()
    states["15M"] = "BEARISH"
    states["5M"] = "BEARISH"

    result = TradeGate().evaluate(
        mtf_result=mtf(states, "PULLBACK_OR_WAIT"),
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    assert result["trade_status"] == "NO_TRADE"
    assert result["demo_authorized"] is False
    assert result["risk"] is None


def test_ready_trade_with_bad_rr_is_rejected():
    result = TradeGate(min_rr=2.0).evaluate(
        mtf_result=mtf(bullish_states(), "FULL_ALIGNMENT"),
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=98.0,
        target_price=102.0,
    )

    assert result["trade_status"] == "RISK_REJECTED"
    assert result["demo_authorized"] is False
    assert result["risk"]["approved"] is False


def test_trade_gate_never_authorizes_real_execution():
    result = TradeGate().evaluate(
        mtf_result=mtf(bullish_states(), "FULL_ALIGNMENT"),
        account_equity=10000.0,
        entry_price=100.0,
        stop_price=98.0,
        target_price=104.0,
    )

    assert "real_authorized" not in result
    assert result["demo_authorized"] is True
