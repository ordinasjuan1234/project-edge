"""
PROJECT EDGE
Structure Engine — Structural Support / Resistance v1

Responsabilidad:
Derivar niveles estructurales de soporte y resistencia a partir de
swings confirmados, respetando el momento causal de confirmación.

Este módulo NO ejecuta órdenes ni genera señales LONG/SHORT.
"""

from __future__ import annotations

import pandas as pd


class StructuralLevels:
    """Construye soporte/resistencia conocidos en cada vela."""

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
            raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
        if df.empty:
            raise ValueError("El DataFrame está vacío.")

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
            if row["swing_type"] not in {"HIGH", "LOW"}:
                continue
            if pd.isna(row["swing_price"]) or pd.isna(row["swing_confirmation_index"]):
                continue

            confirmation_index = int(row["swing_confirmation_index"])
            if confirmation_index < 0 or confirmation_index >= len(data):
                raise ValueError("swing_confirmation_index fuera del DataFrame.")

            events.append(
                (
                    confirmation_index,
                    pivot_index,
                    str(row["swing_type"]),
                    float(row["swing_price"]),
                )
            )

        events.sort(key=lambda item: (item[0], item[1]))

        latest_support = None
        latest_resistance = None
        support_pivot = None
        resistance_pivot = None
        event_pos = 0

        for i in range(len(data)):
            while event_pos < len(events) and events[event_pos][0] == i:
                _, pivot_index, swing_type, price = events[event_pos]

                if swing_type == "LOW":
                    latest_support = price
                    support_pivot = pivot_index
                else:
                    latest_resistance = price
                    resistance_pivot = pivot_index

                event_pos += 1
current_price = float(data.at[i, "close"])

     if latest_support is not None and latest_support > current_price:
                latest_support = None
                support_pivot = None

     if latest_resistance is not None and latest_resistance < current_price:
                latest_resistance = None
                resistance_pivot = None
    data.at[i, "structural_support"] = latest_support
    data.at[i, "structural_resistance"] = latest_resistance
    data.at[i, "support_source_pivot"] = support_pivot
    data.at[i, "resistance_source_pivot"] = resistance_pivot

        return data


def calculate_structural_levels(df: pd.DataFrame) -> pd.DataFrame:
    return StructuralLevels().calculate(df)
