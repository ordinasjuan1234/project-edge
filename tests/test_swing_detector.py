import pandas as pd
from engine.structure.swing_detector import SwingDetector

def sample_data():
    close = [100,101,102,103,104,105,106,107,109,111,110,108,106,104,103,104,106,108,110,112,111,109,107,106]
    return pd.DataFrame({
        "open": close,
        "high": [x + 0.5 for x in close],
        "low": [x - 0.5 for x in close],
        "close": close,
    })

def test_detector_runs_and_returns_expected_columns():
    detector = SwingDetector(
        pivot_left=2,
        pivot_right=2,
        atr_period=3,
        atr_multiplier=1.0,
        min_move_pct=0.001,
        max_move_pct=0.10,
    )
    result = detector.detect(sample_data())

    expected = {
        "atr",
        "swing_candidate",
        "swing_confirmed",
        "swing_type",
        "swing_price",
        "swing_move",
        "swing_threshold",
        "swing_confirmation_index",
        "swing_confirmation_price",
    }
    assert expected.issubset(result.columns)

def test_confirmed_swing_never_confirms_before_pivot_is_known():
    detector = SwingDetector(
        pivot_left=2,
        pivot_right=2,
        atr_period=3,
        atr_multiplier=1.0,
        min_move_pct=0.001,
        max_move_pct=0.10,
    )
    result = detector.detect(sample_data())
    confirmed = result[result["swing_confirmed"]]

    assert not confirmed.empty

    for pivot_index, row in confirmed.iterrows():
        confirmation_index = int(row["swing_confirmation_index"])
        assert confirmation_index >= pivot_index + detector.pivot_right
