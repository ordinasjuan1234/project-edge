import pandas as pd
import pytest

from engine.structure.support_resistance import StructuralLevels


def sample_data():
    return pd.DataFrame(
        {
            "close": [100.0, 101.0, 110.0, 111.0, 105.0, 106.0],
            "swing_confirmed": [True, False, True, False, True, False],
            "swing_type": ["LOW", None, "HIGH", None, "LOW", None],
            "swing_price": [100.0, None, 112.0, None, 105.0, None],
            "swing_confirmation_index": [1, None, 3, None, 5, None],
        }
    )


def test_level_does_not_exist_before_confirmation():
    result = StructuralLevels().calculate(sample_data())

    assert pd.isna(result.loc[0, "structural_support"])
    assert result.loc[1, "structural_support"] == 100.0


def test_resistance_appears_at_confirmation():
    result = StructuralLevels().calculate(sample_data())

    assert pd.isna(result.loc[2, "structural_resistance"])
    assert result.loc[3, "structural_resistance"] == 112.0


def test_latest_confirmed_low_updates_support():
    result = StructuralLevels().calculate(sample_data())

    assert result.loc[4, "structural_support"] == 100.0
    assert result.loc[5, "structural_support"] == 105.0
    assert result.loc[5, "support_source_pivot"] == 4


def test_support_never_exceeds_resistance_when_both_exist():
    result = StructuralLevels().calculate(sample_data())

    valid = result[
        result["structural_support"].notna()
        & result["structural_resistance"].notna()
    ]

    assert not valid.empty
    assert (
        valid["structural_support"] <= valid["structural_resistance"]
    ).all()


def test_missing_columns_raise_error():
    with pytest.raises(ValueError):
        StructuralLevels().calculate(
            pd.DataFrame(
                {
                    "close": [100.0],
                }
            )
        )
