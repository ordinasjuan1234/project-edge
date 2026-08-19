import pytest

from engine.decision.decision_engine import DecisionEngine


def mtf(states, alignment):
    return {
        "states": states,
        "alignment": {
            "alignment": alignment,
            "entry_ready": alignment == "FULL_ALIGNMENT",
        },
    }


def test_full_bullish_alignment_is_ready_long():
    states = {
        "4H": "BULLISH", "1H": "BULLISH", "30M": "BULLISH",
        "15M": "BULLISH", "5M": "BULLISH",
    }
    result = DecisionEngine().decide(mtf(states, "FULL_ALIGNMENT"))
    assert result["decision"] == "READY_LONG"
    assert result["direction"] == "LONG"
    assert result["can_execute"] is False


def test_full_bearish_alignment_is_ready_short():
    states = {
        "4H": "BEARISH", "1H": "BEARISH", "30M": "BEARISH",
        "15M": "BEARISH", "5M": "BEARISH",
    }
    result = DecisionEngine().decide(mtf(states, "FULL_ALIGNMENT"))
    assert result["decision"] == "READY_SHORT"
    assert result["direction"] == "SHORT"


def test_macro_conflict_is_blocked():
    states = {
        "4H": "BULLISH", "1H": "BEARISH", "30M": "BEARISH",
        "15M": "BEARISH", "5M": "BEARISH",
    }
    result = DecisionEngine().decide(mtf(states, "MACRO_CONTEXT_CONFLICT"))
    assert result["decision"] == "BLOCKED"
    assert result["direction"] is None


def test_pullback_is_watch_long():
    states = {
        "4H": "BULLISH", "1H": "BULLISH", "30M": "BULLISH",
        "15M": "BEARISH", "5M": "BEARISH",
    }
    result = DecisionEngine().decide(mtf(states, "PULLBACK_OR_WAIT"))
    assert result["decision"] == "WATCH_LONG"
    assert result["can_execute"] is False


def test_undefined_macro_waits():
    states = {
        "4H": "UNDEFINED", "1H": "BULLISH", "30M": "BULLISH",
        "15M": "BULLISH", "5M": "BULLISH",
    }
    result = DecisionEngine().decide(mtf(states, "NO_DIRECTION"))
    assert result["decision"] == "WAIT"
    assert result["direction"] is None


def test_missing_timeframe_raises_error():
    states = {
        "4H": "BULLISH", "1H": "BULLISH", "30M": "BULLISH",
        "15M": "BULLISH",
    }
    with pytest.raises(ValueError):
        DecisionEngine().decide(mtf(states, "FULL_ALIGNMENT"))
