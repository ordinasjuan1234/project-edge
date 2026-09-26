import pandas as pd
import pytest

from engine.structure.break_of_structure import (
    BreakOfStructureDetector,
)


def test_bullish_bos_uses_level_known_before_break():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                105.0,
                111.0,
            ],
            "structural_support": [
                95.0,
                95.0,
                95.0,
            ],
            # Al cerrar en 111, el viejo nivel 110
            # puede dejar de ser la resistencia actual.
            # La ruptura debe igualmente detectarse
            # contra el 110 conocido en la vela anterior.
            "structural_resistance": [
                110.0,
                110.0,
                120.0,
            ],
            "market_structure": [
                "BULLISH",
                "BULLISH",
                "BULLISH",
            ],
        }
    )

    result = (
        BreakOfStructureDetector()
        .detect(df)
    )

    assert (
        result.loc[
            2,
            "structure_break",
        ]
        == "BOS"
    )

    assert (
        result.loc[
            2,
            "break_direction",
        ]
        == "UP"
    )

    assert (
        result.loc[
            2,
            "broken_level",
        ]
        == 110.0
    )


def test_bearish_bos_uses_level_known_before_break():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                96.0,
                94.0,
            ],
            # Después de romper 95,
            # el soporte actual puede pasar a 90.
            # La ruptura correcta sigue siendo 95.
            "structural_support": [
                95.0,
                95.0,
                90.0,
            ],
            "structural_resistance": [
                110.0,
                110.0,
                110.0,
            ],
            "market_structure": [
                "BEARISH",
                "BEARISH",
                "BEARISH",
            ],
        }
    )

    result = (
        BreakOfStructureDetector()
        .detect(df)
    )

    assert (
        result.loc[
            2,
            "structure_break",
        ]
        == "BOS"
    )

    assert (
        result.loc[
            2,
            "break_direction",
        ]
        == "DOWN"
    )

    assert (
        result.loc[
            2,
            "broken_level",
        ]
        == 95.0
    )


def test_bullish_choch_uses_previous_regime():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                97.0,
                94.0,
            ],
            "structural_support": [
                95.0,
                95.0,
                90.0,
            ],
            "structural_resistance": [
                110.0,
                110.0,
                110.0,
            ],
            # La estructura puede cambiar en la
            # misma vela de ruptura.
            # Debemos clasificar usando la anterior.
            "market_structure": [
                "BULLISH",
                "BULLISH",
                "BEARISH",
            ],
        }
    )

    result = (
        BreakOfStructureDetector()
        .detect(df)
    )

    assert (
        result.loc[
            2,
            "structure_break",
        ]
        == "CHoCH"
    )

    assert (
        result.loc[
            2,
            "break_direction",
        ]
        == "DOWN"
    )

    assert (
        result.loc[
            2,
            "broken_level",
        ]
        == 95.0
    )


def test_bearish_choch_uses_previous_regime():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                105.0,
                111.0,
            ],
            "structural_support": [
                95.0,
                95.0,
                95.0,
            ],
            "structural_resistance": [
                110.0,
                110.0,
                120.0,
            ],
            "market_structure": [
                "BEARISH",
                "BEARISH",
                "BULLISH",
            ],
        }
    )

    result = (
        BreakOfStructureDetector()
        .detect(df)
    )

    assert (
        result.loc[
            2,
            "structure_break",
        ]
        == "CHoCH"
    )

    assert (
        result.loc[
            2,
            "break_direction",
        ]
        == "UP"
    )

    assert (
        result.loc[
            2,
            "broken_level",
        ]
        == 110.0
    )


def test_no_false_break_when_close_does_not_cross_previous_level():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                109.0,
                109.5,
            ],
            "structural_support": [
                95.0,
                95.0,
                95.0,
            ],
            "structural_resistance": [
                110.0,
                110.0,
                110.0,
            ],
            "market_structure": [
                "BULLISH",
                "BULLISH",
                "BULLISH",
            ],
        }
    )

    result = (
        BreakOfStructureDetector()
        .detect(df)
    )

    assert (
        result[
            "structure_break"
        ].isna().all()
    )

    assert (
        result[
            "break_direction"
        ].isna().all()
    )

    assert (
        result[
            "broken_level"
        ].isna().all()
    )


def test_no_break_without_previously_known_resistance():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                105.0,
                111.0,
            ],
            "structural_support": [
                95.0,
                95.0,
                95.0,
            ],
            "structural_resistance": [
                None,
                None,
                110.0,
            ],
            "market_structure": [
                "BULLISH",
                "BULLISH",
                "BULLISH",
            ],
        }
    )

    result = (
        BreakOfStructureDetector()
        .detect(df)
    )

    assert (
        result[
            "structure_break"
        ].isna().all()
    )


def test_no_break_without_previously_known_support():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                96.0,
                94.0,
            ],
            "structural_support": [
                None,
                None,
                95.0,
            ],
            "structural_resistance": [
                110.0,
                110.0,
                110.0,
            ],
            "market_structure": [
                "BEARISH",
                "BEARISH",
                "BEARISH",
            ],
        }
    )

    result = (
        BreakOfStructureDetector()
        .detect(df)
    )

    assert (
        result[
            "structure_break"
        ].isna().all()
    )


def test_missing_required_column_is_rejected():
    df = pd.DataFrame(
        {
            "close": [
                100.0,
                101.0,
            ],
            "structural_support": [
                95.0,
                95.0,
            ],
        }
    )

    with pytest.raises(
        ValueError
    ):
        (
            BreakOfStructureDetector()
            .detect(df)
        )


def test_empty_dataframe_is_rejected():
    df = pd.DataFrame(
        columns=[
            "close",
            "structural_support",
            "structural_resistance",
        ]
    )

    with pytest.raises(
        ValueError
    ):
        (
            BreakOfStructureDetector()
            .detect(df)
        )
