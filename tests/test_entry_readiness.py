import pytest

from engine.decision.entry_readiness import EntryReadiness


def mtf(states):
    return {
        "states": states,
        "alignment": {
            "alignment": "TEST",
            "entry_ready": False,
        },
    }


def test_blocked_bullish_macro_explains_missing_lower_timeframes():
    result = EntryReadiness().evaluate(
        mtf({
            "4H": "BULLISH",
            "1H": "BULLISH",
            "30M": "BEARISH",
            "15M": "TRANSITION",
            "5M": "BEARISH",
        }),
        {
            "decision": "BLOCKED",
            "direction": None,
            "can_execute": False,
        },
    )

    assert result["status"] == "NOT_READY"
    assert result["bias"] == "LONG"
    assert "30M debe recuperar estructura BULLISH." in result["missing_conditions"]
    assert "15M debe confirmar BULLISH." in result["missing_conditions"]
    assert "5M debe confirmar BULLISH." in result["missing_conditions"]
    assert "1H debe volver a BULLISH." not in result["missing_conditions"]


def test_ready_long_has_no_missing_conditions():
    result = EntryReadiness().evaluate(
        mtf({
            "4H": "BULLISH",
            "1H": "BULLISH",
            "30M": "BULLISH",
            "15M": "BULLISH",
            "5M": "BULLISH",
        }),
        {
            "decision": "READY_LONG",
            "direction": "LONG",
            "can_execute": True,
        },
    )

    assert result["status"] == "READY"
    assert result["bias"] == "LONG"
    assert result["missing_conditions"] == []


def test_bearish_macro_builds_short_requirements():
    result = EntryReadiness().evaluate(
        mtf({
            "4H": "BEARISH",
            "1H": "BEARISH",
            "30M": "TRANSITION",
            "15M": "BEARISH",
            "5M": "BULLISH",
        }),
        {"decision": "WATCH_SHORT", "direction": "SHORT"},
    )

    assert result["bias"] == "SHORT"
    assert "30M debe recuperar estructura BEARISH." in result["missing_conditions"]
    assert "5M debe confirmar BEARISH." in result["missing_conditions"]


def test_transition_macro_has_no_directional_bias():
    result = EntryReadiness().evaluate(
        mtf({
            "4H": "TRANSITION",
            "1H": "BULLISH",
            "30M": "BULLISH",
            "15M": "BULLISH",
            "5M": "BULLISH",
        }),
        {"decision": "WAIT", "direction": None},
    )

    assert result["bias"] is None
    assert result["status"] == "NOT_READY"


def test_missing_timeframe_is_rejected():
    with pytest.raises(ValueError):
        EntryReadiness().evaluate(
            mtf({
                "4H": "BULLISH",
                "1H": "BULLISH",
                "30M": "BULLISH",
                "15M": "BULLISH",
            }),
            {"decision": "BLOCKED"},
        )
