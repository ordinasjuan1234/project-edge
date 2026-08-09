import pandas as pd

from engine.structure.impulse_correction import ImpulseCorrectionClassifier


def test_bullish_impulse_and_correction():
    df = pd.DataFrame(
        {
            "swing_confirmed": [True, True, True],
            "swing_type": ["LOW", "HIGH", "LOW"],
            "swing_price": [100.0, 110.0, 105.0],
            "swing_confirmation_index": [2, 5, 8],
            "market_structure": ["BULLISH", "BULLISH", "BULLISH"],
        }
    )

    result = ImpulseCorrectionClassifier().classify(df)

    assert result.loc[1, "leg_type"] == "IMPULSE"
    assert result.loc[2, "leg_type"] == "CORRECTION"


def test_bearish_impulse_and_correction():
    df = pd.DataFrame(
        {
            "swing_confirmed": [True, True, True],
            "swing_type": ["HIGH", "LOW", "HIGH"],
            "swing_price": [110.0, 100.0, 105.0],
            "swing_confirmation_index": [2, 5, 8],
            "market_structure": ["BEARISH", "BEARISH", "BEARISH"],
        }
    )

    result = ImpulseCorrectionClassifier().classify(df)

    assert result.loc[1, "leg_type"] == "IMPULSE"
    assert result.loc[2, "leg_type"] == "CORRECTION"


def test_transition_is_undefined():
    df = pd.DataFrame(
        {
            "swing_confirmed": [True, True],
            "swing_type": ["LOW", "HIGH"],
            "swing_price": [100.0, 110.0],
            "swing_confirmation_index": [2, 5],
            "market_structure": ["TRANSITION", "TRANSITION"],
        }
    )

    result = ImpulseCorrectionClassifier().classify(df)
    assert result.loc[1, "leg_type"] == "UNDEFINED"


def test_leg_move_is_absolute_price_difference():
    df = pd.DataFrame(
        {
            "swing_confirmed": [True, True],
            "swing_type": ["LOW", "HIGH"],
            "swing_price": [100.0, 112.0],
            "swing_confirmation_index": [2, 5],
            "market_structure": ["BULLISH", "BULLISH"],
        }
    )

    result = ImpulseCorrectionClassifier().classify(df)
    assert result.loc[1, "leg_move"] == 12.0
