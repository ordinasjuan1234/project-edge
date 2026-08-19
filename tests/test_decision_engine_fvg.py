import pandas as pd

from engine.decision.decision_engine import DecisionEngine


def _analysis(fvg_type=None, state=None, distance=None):
    return pd.DataFrame([{
        "active_fvg_type": fvg_type,
        "active_fvg_state": state,
        "active_fvg_distance_pct": distance,
    }])


def _mtf(direction="BULLISH", fvg_15m=None, fvg_5m=None):
    states = {
        "4H": direction,
        "1H": direction,
        "30M": direction,
        "15M": direction,
        "5M": direction,
    }

    analysis_15m = fvg_15m if fvg_15m is not None else _analysis()
    analysis_5m = fvg_5m if fvg_5m is not None else _analysis()

    return {
        "states": states,
        "alignment": {
            "alignment": "FULL_ALIGNMENT",
            "entry_ready": True,
        },
        "analyses": {
            "4H": _analysis(),
            "1H": _analysis(),
            "30M": _analysis(),
            "15M": analysis_15m,
            "5M": analysis_5m,
        },
    }


def test_bullish_fvg_confirms_ready_long():
    result = DecisionEngine().decide(
        _mtf(
            "BULLISH",
            fvg_15m=_analysis("BULLISH", "ACTIVE", 0.008),
        )
    )
    assert result["decision"] == "READY_LONG"
    assert result["can_execute"] is True
    assert result["fvg_confirmed"] is True
    assert "15M" in result["fvg_timeframes"]


def test_wrong_fvg_direction_keeps_long_on_watch():
    result = DecisionEngine().decide(
        _mtf(
            "BULLISH",
            fvg_15m=_analysis("BEARISH", "ACTIVE", 0.004),
            fvg_5m=_analysis("BEARISH", "PARTIAL", 0.003),
        )
    )
    assert result["decision"] == "WATCH_LONG"
    assert result["can_execute"] is False
    assert result["fvg_confirmed"] is False


def test_far_fvg_does_not_confirm():
    result = DecisionEngine(
        fvg_max_distance_pct=0.015
    ).decide(
        _mtf(
            "BULLISH",
            fvg_5m=_analysis("BULLISH", "ACTIVE", 0.02),
        )
    )
    assert result["decision"] == "WATCH_LONG"
    assert result["can_execute"] is False


def test_bearish_fvg_confirms_ready_short():
    result = DecisionEngine().decide(
        _mtf(
            "BEARISH",
            fvg_5m=_analysis("BEARISH", "PARTIAL", 0.01),
        )
    )
    assert result["decision"] == "READY_SHORT"
    assert result["can_execute"] is True
    assert result["fvg_confirmed"] is True
