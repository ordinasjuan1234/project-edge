"""
PROJECT EDGE
Structure Engine — Structure Classifier v1

Responsabilidad:
    Clasificar swings confirmados como:
        HIGH -> HH / LH / EH
        LOW  -> HL / LL / EL

Principio causal:
    Solo utiliza swings que ya poseen swing_confirmation_index.
    La clasificación queda disponible a partir de la confirmación del swing.

Este módulo NO:
    - ejecuta órdenes
    - genera señales LONG/SHORT
    - se conecta a Binance
"""

from __future__ import annotations

import pandas as pd


class StructureClassifier:
    """Clasifica la secuencia de swings confirmados."""

    REQUIRED_COLUMNS = {
        "swing_confirmed",
        "swing_type",
        "swing_price",
        "swing_confirmation_index",
    }

    @classmethod
    def _validate_data(cls, df: pd.DataFrame) -> None:
        missing = cls.REQUIRED_COLUMNS.difference(df.columns)
        if missing:
            raise ValueError(
                f"Faltan columnas requeridas del Swing Detector: {sorted(missing)}"
            )
        if df.empty:
            raise ValueError("El DataFrame está vacío.")

    def classify(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_data(df)

        data = df.copy()
        data["structure_label"] = None
        data["previous_same_type_price"] = None
        data["structure_known_at"] = None

        confirmed = data[
            data["swing_confirmed"].eq(True)
            & data["swing_type"].isin(["HIGH", "LOW"])
            & data["swing_price"].notna()
            & data["swing_confirmation_index"].notna()
        ].copy()

        if confirmed.empty:
            return data

        confirmed["_pivot_index"] = confirmed.index
        confirmed = confirmed.sort_values(
            by=["swing_confirmation_index", "_pivot_index"],
            kind="stable",
        )

        previous_high = None
        previous_low = None

        for _, swing in confirmed.iterrows():
            pivot_index = swing["_pivot_index"]
            swing_type = swing["swing_type"]
            price = float(swing["swing_price"])
            confirmation_index = int(swing["swing_confirmation_index"])

            if swing_type == "HIGH":
                if previous_high is None:
                    label = "FIRST_HIGH"
                elif price > previous_high:
                    label = "HH"
                elif price < previous_high:
                    label = "LH"
                else:
                    label = "EH"

                data.at[pivot_index, "previous_same_type_price"] = previous_high
                previous_high = price

            else:
                if previous_low is None:
                    label = "FIRST_LOW"
                elif price > previous_low:
                    label = "HL"
                elif price < previous_low:
                    label = "LL"
                else:
                    label = "EL"

                data.at[pivot_index, "previous_same_type_price"] = previous_low
                previous_low = price

            data.at[pivot_index, "structure_label"] = label
            data.at[pivot_index, "structure_known_at"] = confirmation_index

        return data


def classify_structure(df: pd.DataFrame) -> pd.DataFrame:
    """Función simplificada para clasificar estructura."""
    return StructureClassifier().classify(df)
