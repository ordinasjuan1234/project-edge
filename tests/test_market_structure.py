import pandas as pd
import pytest

from engine.structure.market_structure import MarketStructureInterpreter


def test_bullish_structure_from_hh_hl():
    df = pd.DataFrame({"structure_label": ["HH", "HL"]})
    result = MarketStructureInterpreter().interpret(df)
    assert result.iloc[-1]["market_structure"] == "BULLISH"


def test_bearish_structure_from_lh_ll():
    df = pd.DataFrame({"structure_label": ["LH", "LL"]})
    result = MarketStructureInterpreter().interpret(df)
    assert result.iloc[-1]["market_structure"] == "BEARISH"


def test_mixed_structure_is_transition():
    df = pd.DataFrame({"structure_label": ["HH", "LL"]})
    result = MarketStructureInterpreter().interpret(df)
    assert result.iloc[-1]["market_structure"] == "TRANSITION"


def test_state_is_carried_forward_between_structure_events():
    df = pd.DataFrame({"structure_label": ["HH", "HL", None, None]})
    result = MarketStructureInterpreter().interpret(df)
    assert result.iloc[-1]["market_structure"] == "BULLISH"


def test_invalid_label_raises_error():
    df = pd.DataFrame({"structure_label": ["HH", "XX"]})
    with pytest.raises(ValueError):
        MarketStructureInterpreter().interpret(df)
