"""
PROJECT EDGE
Structure Engine — Impulse / Correction Classifier v1

Responsabilidad:
Clasificar cada tramo entre swings confirmados como IMPULSE o CORRECTION
según el estado de estructura de mercado conocido.

Este módulo NO ejecuta órdenes ni genera señales LONG/SHORT.
"""

from __future__ import annotations

import pandas as pd


class ImpulseCorrectionClassifier:
    """Clasifica tramos estructurales entre swings consecutivos."""

    REQUIRED_COLUMNS = {
        "swing_confirmed",
        "swing_type",
        "swing_price",
        "swing_confirmation_index",
        "market_structure",
    }

    @classmethod
    def _validate_data(cls, df: pd.DataFrame) -> None:
        missing = cls.REQUIRED_COLUMNS.difference(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
        if df.empty:
            raise ValueError("El DataFrame está vacío.")

    @staticmethod
    def _classify_leg(
        previous_type: str,
        current_type: str,
        market_structure: str,
    ) -> str:
        if previous_type == current_type:
            return "UNDEFINED"

        if market_structure == "BULLISH":
            return "IMPULSE" if previous_type == "LOW" and current_type == "HIGH" else "CORRECTION"

        if market_structure == "BEARISH":
            return "IMPULSE" if previous_type == "HIGH" and current_type == "LOW" else "CORRECTION"

        return "UNDEFINED"

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_data(df)

        data = df.copy()
        data["leg_type"] = None
        data["leg_start_price"] = None
        data["leg_end_price"] = None
        data["leg_move"] = None

        swings = data[
            data["swing_confirmed"].eq(True)
            & data["swing_type"].isin(["HIGH", "LOW"])
            & data["swing_price"].notna()
            & data["swing_confirmation_index"].notna()
        ].copy()

        if len(swings) < 2:
            return data

        swings["_pivot_index"] = swings.index
        swings = swings.sort_values(
            ["swing_confirmation_index", "_pivot_index"],
            kind="stable",
        )

        previous = None

        for _, current in swings.iterrows():
            if previous is None:
                previous = current
                continue

            idx = current["_pivot_index"]
            previous_type = str(previous["swing_type"])
            current_type = str(current["swing_type"])
            structure = str(current["market_structure"])
            start_price = float(previous["swing_price"])
            end_price = float(current["swing_price"])

            data.at[idx, "leg_type"] = self._classify_leg(
                previous_type,
                current_type,
                structure,
            )
            data.at[idx, "leg_start_price"] = start_price
            data.at[idx, "leg_end_price"] = end_price
            data.at[idx, "leg_move"] = abs(end_price - start_price)

            previous = current

        return data


def classify_impulse_correction(df: pd.DataFrame) -> pd.DataFrame:
    return ImpulseCorrectionClassifier().classify(df)
