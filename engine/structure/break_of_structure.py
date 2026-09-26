"""PROJECT EDGE — BOS / CHoCH Detector v2.

Detecta rupturas estructurales de forma causal.

Principio importante:
- La vela actual NO puede definir el nivel que ella misma rompe.
- La ruptura se evalúa contra el soporte/resistencia que ya estaba
  disponible al cierre de la vela anterior.
- La clasificación BOS/CHoCH usa también el régimen previo a la ruptura.

Esto evita el problema lógico anterior donde:
- structural_resistance de la vela actual era siempre >= close actual;
- structural_support de la vela actual era siempre <= close actual;
por lo que close > resistencia o close < soporte podían quedar
prácticamente imposibles.
"""

from __future__ import annotations

import pandas as pd


class BreakOfStructureDetector:
    REQUIRED_COLUMNS = {
        "close",
        "structural_support",
        "structural_resistance",
    }

    @classmethod
    def _validate_data(
        cls,
        df: pd.DataFrame,
    ) -> None:
        missing = cls.REQUIRED_COLUMNS.difference(
            df.columns
        )

        if missing:
            raise ValueError(
                "Faltan columnas requeridas: "
                f"{sorted(missing)}"
            )

        if df.empty:
            raise ValueError(
                "El DataFrame está vacío."
            )

    @staticmethod
    def _normalize_trend(
        value,
    ) -> str | None:
        if pd.isna(value):
            return None

        value = str(value).upper()

        if value in {
            "BULLISH",
            "BULL",
            "UPTREND",
            "UP",
        }:
            return "BULLISH"

        if value in {
            "BEARISH",
            "BEAR",
            "DOWNTREND",
            "DOWN",
        }:
            return "BEARISH"

        return None

    def detect(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        self._validate_data(df)

        data = (
            df.copy()
            .reset_index(drop=True)
        )

        data["structure_break"] = None
        data["break_direction"] = None
        data["broken_level"] = None

        trend_col = next(
            (
                column
                for column in (
                    "market_structure",
                    "structure",
                    "trend",
                )
                if column in data.columns
            ),
            None,
        )

        for i in range(
            1,
            len(data),
        ):
            close = float(
                data.at[i, "close"]
            )

            previous_close = float(
                data.at[
                    i - 1,
                    "close",
                ]
            )

            # La vela actual debe compararse contra
            # niveles que YA eran conocidos antes
            # de que comenzara la ruptura.
            previous_resistance = data.at[
                i - 1,
                "structural_resistance",
            ]

            previous_support = data.at[
                i - 1,
                "structural_support",
            ]

            broke_up = (
                pd.notna(
                    previous_resistance
                )
                and previous_close
                <= float(
                    previous_resistance
                )
                and close
                > float(
                    previous_resistance
                )
            )

            broke_down = (
                pd.notna(
                    previous_support
                )
                and previous_close
                >= float(
                    previous_support
                )
                and close
                < float(
                    previous_support
                )
            )

            if (
                not broke_up
                and not broke_down
            ):
                continue

            # BOS / CHoCH se clasifica según
            # el régimen que existía ANTES
            # de la vela que produjo la ruptura.
            previous_trend = (
                self._normalize_trend(
                    data.at[
                        i - 1,
                        trend_col,
                    ]
                )
                if trend_col
                else None
            )

            if broke_up:
                broken_level = float(
                    previous_resistance
                )

                data.at[
                    i,
                    "break_direction",
                ] = "UP"

                data.at[
                    i,
                    "broken_level",
                ] = broken_level

                data.at[
                    i,
                    "structure_break",
                ] = (
                    "CHoCH"
                    if previous_trend
                    == "BEARISH"
                    else "BOS"
                )

            else:
                broken_level = float(
                    previous_support
                )

                data.at[
                    i,
                    "break_direction",
                ] = "DOWN"

                data.at[
                    i,
                    "broken_level",
                ] = broken_level

                data.at[
                    i,
                    "structure_break",
                ] = (
                    "CHoCH"
                    if previous_trend
                    == "BULLISH"
                    else "BOS"
                )

        return data


def detect_structure_breaks(
    df: pd.DataFrame,
) -> pd.DataFrame:
    return (
        BreakOfStructureDetector()
        .detect(df)
    )
