import pandas as pd

from engine.structure.structure_engine import StructureEngine


def sample_ohlc():
    close = [
        100, 102, 105, 103, 99, 101, 106, 110,
        107, 104, 108, 113, 117, 114, 110, 112,
        118, 121, 117, 113, 109, 112, 116, 120,
        115, 111, 107, 110, 114, 119,
    ]

    return pd.DataFrame(
        {
            "open": close,
            "high": [x + 1.0 for x in close],
            "low": [x - 1.0 for x in close],
            "close": close,
        }
    )


def test_structure_engine_runs_complete_pipeline():
    engine = StructureEngine(
        pivot_left=2,
        pivot_right=2,
        atr_period=3,
        atr_multiplier=1.0,
        min_move_pct=0.001,
        max_move_pct=0.10,
    )

    result = engine.analyze(sample_ohlc())

    expected_columns = {
        "atr",
        "swing_candidate",
        "swing_confirmed",
        "swing_type",
        "swing_price",
        "swing_confirmation_index",
        "structure_label",
        "market_structure",
        "leg_type",
        "structural_support",
        "structural_resistance",
        "structure_break",
        "break_direction",
        "broken_level",
    }

    assert expected_columns.issubset(result.columns)
    assert len(result) == len(sample_ohlc())


def test_structure_engine_detects_confirmed_swings():
    engine = StructureEngine(
        pivot_left=2,
        pivot_right=2,
        atr_period=3,
        atr_multiplier=1.0,
        min_move_pct=0.001,
        max_move_pct=0.10,
    )

    result = engine.analyze(sample_ohlc())

    assert result["swing_confirmed"].any()
    assert result.loc[result["swing_confirmed"], "swing_type"].notna().all()


def test_structure_engine_preserves_input_ohlc():
    df = sample_ohlc()

    engine = StructureEngine(
        pivot_left=2,
        pivot_right=2,
        atr_period=3,
        atr_multiplier=1.0,
        min_move_pct=0.001,
        max_move_pct=0.10,
    )

    result = engine.analyze(df)

    for column in ["open", "high", "low", "close"]:
        assert result[column].tolist() == df[column].tolist()
