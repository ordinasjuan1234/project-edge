"""
PROJECT EDGE
Structure Engine — Market Structure Interpreter v1

Interpreta etiquetas estructurales HH / HL / LH / LL y determina
el estado de estructura del mercado.

Este módulo NO:
- ejecuta órdenes
- genera señales LONG/SHORT
- se conecta a exchanges
"""

from __future__ import annotations

import pandas as pd


class MarketStructureInterpreter:
    """Interpreta una secuencia causal de etiquetas HH/HL/LH/LL."""

    VALID_LABELS = {"HH", "HL", "LH", "LL"}

    @staticmethod
    def _state_from_context(last_high: str | None, last_low: str | None) -> str:
        if last_high == "HH" and last_low == "HL":
            return "BULLISH"
        if last_high == "LH" and last_low == "LL":
            return "BEARISH"
        return "TRANSITION"

    def interpret(
        self,
        df: pd.DataFrame,
        label_column: str = "structure_label",
    ) -> pd.DataFrame:
        if label_column not in df.columns:
            raise ValueError(f"Falta la columna requerida: {label_column}")

        data = df.copy()
        data["market_structure"] = "UNDEFINED"

        last_high = None
        last_low = None

        for idx, label in data[label_column].items():
            if pd.isna(label):
                continue

            label = str(label).upper()
            if label not in self.VALID_LABELS:
                raise ValueError(f"Etiqueta estructural inválida: {label}")

            if label in {"HH", "LH"}:
                last_high = label
            else:
                last_low = label

            if last_high is not None and last_low is not None:
                data.at[idx, "market_structure"] = self._state_from_context(
                    last_high, last_low
                )

        # El estado conocido se mantiene hasta el próximo evento estructural.
        data["market_structure"] = (
            data["market_structure"]
            .replace("UNDEFINED", pd.NA)
            .ffill()
            .fillna("UNDEFINED")
        )

        return data


def interpret_market_structure(
    df: pd.DataFrame,
    label_column: str = "structure_label",
) -> pd.DataFrame:
    return MarketStructureInterpreter().interpret(df, label_column=label_column)
