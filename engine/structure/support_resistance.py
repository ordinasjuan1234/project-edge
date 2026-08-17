"""
PROJECT EDGE
Structure Engine - Structural Support / Resistance v2

Calcula soporte y resistencia estructural usando swings confirmados.

Reglas:
- Swing LOW confirmado = candidato a soporte.
- Swing HIGH confirmado = candidato a resistencia.
- Soporte valido: nivel igual o inferior al precio actual.
- Resistencia valida: nivel igual o superior al precio actual.
- Se utiliza el nivel valido mas cercano al precio.

Este modulo NO ejecuta ordenes ni genera senales LONG/SHORT.
"""

from __future__ import annotations

import pandas as pd


class StructuralLevels:
    """Calcula soporte y resistencia estructural para cada vela."""

    REQUIRED_COLUMNS = {
        "close",
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
                f"Faltan columnas requeridas: {sorted(missing)}"
            )

        if df.empty:
            raise ValueError("El DataFrame esta vacio.")

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_data(df)

        data = df.copy().reset_index(drop=True)

        data["structural_support"] = None
        data["structural_resistance"] = None
        data["support_source_pivot"] = None
        data["resistance_source_pivot"] = None

        events = []

        for pivot_index, row in data.iterrows():
            if not bool(row["swing_confirmed"]):
                continue

            swing_type = row["swing_type"]

            if swing_type not in {"HIGH", "LOW"}:
                continue

            if pd.isna(row["swing_price"]):
                continue

            if pd.isna(row["swing_confirmation_index"]):
                continue

            confirmation_index = int(
                row["swing_confirmation_index"]
            )

            if confirmation_index < 0 or confirmation_index >= len(data):
                raise ValueError(
                    "swing_confirmation_index fuera del DataFrame."
                )

            events.append(
                (
                    confirmation_index,
                    pivot_index,
                    str(swing_type),
                    float(row["swing_price"]),
                )
            )

        events.sort(key=lambda item: (item[0], item[1]))

        confirmed_supports = []
        confirmed_resistances = []

        event_pos = 0

        for i in range(len(data)):
            while (
                event_pos < len(events)
                and events[event_pos][0] == i
            ):
                (
                    _,
                    pivot_index,
                    swing_type,
                    price,
                ) = events[event_pos]

                if swing_type == "LOW":
                    confirmed_supports.append(
                        (price, pivot_index)
                    )

                elif swing_type == "HIGH":
                    confirmed_resistances.append(
                        (price, pivot_index)
                    )

                event_pos += 1

            current_price = float(data.at[i, "close"])

            valid_supports = [
                item
                for item in confirmed_supports
                if item[0] <= current_price
            ]

            valid_resistances = [
                item
                for item in confirmed_resistances
                if item[0] >= current_price
            ]

            if valid_supports:
                support_price, support_pivot = max(
                    valid_supports,
                    key=lambda item: item[0],
                )

                data.at[i, "structural_support"] = support_price
                data.at[i, "support_source_pivot"] = support_pivot

            if valid_resistances:
                resistance_price, resistance_pivot = min(
                    valid_resistances,
                    key=lambda item: item[0],
                )

                data.at[i, "structural_resistance"] = resistance_price
                data.at[i, "resistance_source_pivot"] = resistance_pivot

        return data


def calculate_structural_levels(
    df: pd.DataFrame,
) -> pd.DataFrame:
    return StructuralLevels().calculate(df)
