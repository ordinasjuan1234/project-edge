import pandas as pd

from engine.structure.structure_classifier import StructureClassifier


def sample_swings():
    return pd.DataFrame(
        {
            "swing_confirmed": [True, True, True, True, True, True],
            "swing_type": ["HIGH", "LOW", "HIGH", "LOW", "HIGH", "LOW"],
            "swing_price": [110.0, 100.0, 115.0, 103.0, 112.0, 98.0],
            "swing_confirmation_index": [3, 6, 9, 12, 15, 18],
        }
    )


def test_structure_labels_are_correct():
    result = StructureClassifier().classify(sample_swings())
    labels = result["structure_label"].tolist()

    assert labels == [
        "FIRST_HIGH",
        "FIRST_LOW",
        "HH",
        "HL",
        "LH",
        "LL",
    ]


def test_structure_known_at_matches_confirmation_index():
    result = StructureClassifier().classify(sample_swings())

    for _, row in result.iterrows():
        assert int(row["structure_known_at"]) == int(
            row["swing_confirmation_index"]
        )


def test_equal_high_and_low_are_classified():
    df = pd.DataFrame(
        {
            "swing_confirmed": [True, True, True, True],
            "swing_type": ["HIGH", "LOW", "HIGH", "LOW"],
            "swing_price": [110.0, 100.0, 110.0, 100.0],
            "swing_confirmation_index": [3, 6, 9, 12],
        }
    )

    result = StructureClassifier().classify(df)

    assert result.loc[2, "structure_label"] == "EH"
    assert result.loc[3, "structure_label"] == "EL"


def test_unconfirmed_swings_are_ignored():
    df = pd.DataFrame(
        {
            "swing_confirmed": [True, False, True],
            "swing_type": ["HIGH", "HIGH", "HIGH"],
            "swing_price": [100.0, 200.0, 105.0],
            "swing_confirmation_index": [2, None, 6],
        }
    )

    result = StructureClassifier().classify(df)

    assert result.loc[0, "structure_label"] == "FIRST_HIGH"
    assert result.loc[1, "structure_label"] is None
    assert result.loc[2, "structure_label"] == "HH"
