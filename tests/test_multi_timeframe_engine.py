import pytest

from engine.multitimeframe.multi_timeframe_engine import MultiTimeframeEngine


def test_full_bullish_alignment():
    states = {
        "4H": "BULLISH",
        "1H": "BULLISH",
        "30M": "BULLISH",
        "15M": "BULLISH",
        "5M": "BULLISH",
    }

    result = MultiTimeframeEngine().analyze(states)

    assert result["alignment"] == "FULL_ALIGNMENT"
    assert result["entry_ready"] is True
    assert result["macro_4h"] == "BULLISH"


def test_full_bearish_alignment():
    states = {
        "4H": "BEARISH",
        "1H": "BEARISH",
        "30M": "BEARISH",
        "15M": "BEARISH",
        "5M": "BEARISH",
    }

    result = MultiTimeframeEngine().analyze(states)

    assert result["alignment"] == "FULL_ALIGNMENT"
    assert result["entry_ready"] is True


def test_pullback_or_wait_when_lower_timeframes_disagree():
    states = {
        "4H": "BULLISH",
        "1H": "BULLISH",
        "30M": "BULLISH",
        "15M": "BEARISH",
        "5M": "BEARISH",
    }

    result = MultiTimeframeEngine().analyze(states)

    assert result["alignment"] == "PULLBACK_OR_WAIT"
    assert result["entry_ready"] is False


def test_macro_context_conflict():
    states = {
        "4H": "BULLISH",
        "1H": "BEARISH",
        "30M": "BEARISH",
        "15M": "BEARISH",
        "5M": "BEARISH",
    }

    result = MultiTimeframeEngine().analyze(states)

    assert result["alignment"] == "MACRO_CONTEXT_CONFLICT"
    assert result["entry_ready"] is False


def test_missing_timeframe_raises_error():
    states = {
        "4H": "BULLISH",
        "1H": "BULLISH",
        "30M": "BULLISH",
        "15M": "BULLISH",
    }

    with pytest.raises(ValueError):
        MultiTimeframeEngine().analyze(states)


def test_invalid_state_raises_error():
    states = {
        "4H": "BULLISH",
        "1H": "BULLISH",
        "30M": "SIDEWAYS",
        "15M": "BULLISH",
        "5M": "BULLISH",
    }

    with pytest.raises(ValueError):
        MultiTimeframeEngine().analyze(states)
