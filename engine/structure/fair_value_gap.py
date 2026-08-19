"""
PROJECT EDGE
Structure Engine - Fair Value Gap Detector v1

Detecta Fair Value Gaps (FVG) de 3 velas de forma causal.

Reglas:
- FVG alcista: low de la vela actual > high de hace 2 velas.
- FVG bajista: high de la vela actual < low de hace 2 velas.
- La zona permanece activa hasta ser completamente rellenada.
- Si el precio entra parcialmente en la zona, su estado pasa a PARTIAL.

Este modulo NO ejecuta ordenes ni genera senales LONG/SHORT por si solo.
"""

from __future__ import annotations

import pandas as pd


class FairValueGapDetector:
    """Detecta FVG y mantiene la zona activa mas cercana al precio."""

    REQUIRED_COLUMNS = {"high", "low", "close"}

    def __init__(self, min_gap_pct: float = 0.0) -> None:
        if min_gap_pct < 0:
            raise ValueError("min_gap_pct no puede ser negativo.")
        self.min_gap_pct = float(min_gap_pct)

    @classmethod
    def _validate_data(cls, df: pd.DataFrame) -> None:
        missing = cls.REQUIRED_COLUMNS.difference(df.columns)
        if missing:
            raise ValueError(
                f"Faltan columnas requeridas: {sorted(missing)}"
            )

        if df.empty:
            raise ValueError("El DataFrame esta vacio.")

    @staticmethod
    def _distance_pct(
        close: float,
        lower: float,
        upper: float,
    ) -> float:
        if lower <= close <= upper:
            return 0.0

        if close < lower:
            return (lower - close) / close

        return (close - upper) / close

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_data(df)

        data = df.copy().reset_index(drop=True)

        data["fvg_created"] = False
        data["fvg_type"] = None
        data["fvg_lower"] = None
        data["fvg_upper"] = None
        data["fvg_mid"] = None
        data["fvg_gap_pct"] = None

        data["active_fvg_type"] = None
        data["active_fvg_lower"] = None
        data["active_fvg_upper"] = None
        data["active_fvg_mid"] = None
        data["active_fvg_state"] = None
        data["active_fvg_created_index"] = None
        data["active_fvg_distance_pct"] = None

        active_zones: list[dict] = []

        for i in range(len(data)):
            current_high = float(data.at[i, "high"])
            current_low = float(data.at[i, "low"])
            current_close = float(data.at[i, "close"])

            surviving_zones: list[dict] = []

            for zone in active_zones:
                if zone["type"] == "BULLISH":
                    if current_low <= zone["lower"]:
                        continue
                    if current_low <= zone["upper"]:
                        zone["state"] = "PARTIAL"
                else:
                    if current_high >= zone["upper"]:
                        continue
                    if current_high >= zone["lower"]:
                        zone["state"] = "PARTIAL"

                surviving_zones.append(zone)

            active_zones = surviving_zones

            if i >= 2:
                left_high = float(data.at[i - 2, "high"])
                left_low = float(data.at[i - 2, "low"])

                bullish = current_low > left_high
                bearish = current_high < left_low

                if bullish:
                    lower = left_high
                    upper = current_low
                    gap_pct = (upper - lower) / current_close

                    if gap_pct >= self.min_gap_pct:
                        zone = {
                            "type": "BULLISH",
                            "lower": lower,
                            "upper": upper,
                            "state": "ACTIVE",
                            "created_index": i,
                        }
                        active_zones.append(zone)

                        data.at[i, "fvg_created"] = True
                        data.at[i, "fvg_type"] = "BULLISH"
                        data.at[i, "fvg_lower"] = lower
                        data.at[i, "fvg_upper"] = upper
                        data.at[i, "fvg_mid"] = (lower + upper) / 2.0
                        data.at[i, "fvg_gap_pct"] = gap_pct

                elif bearish:
                    lower = current_high
                    upper = left_low
                    gap_pct = (upper - lower) / current_close

                    if gap_pct >= self.min_gap_pct:
                        zone = {
                            "type": "BEARISH",
                            "lower": lower,
                            "upper": upper,
                            "state": "ACTIVE",
                            "created_index": i,
                        }
                        active_zones.append(zone)

                        data.at[i, "fvg_created"] = True
                        data.at[i, "fvg_type"] = "BEARISH"
                        data.at[i, "fvg_lower"] = lower
                        data.at[i, "fvg_upper"] = upper
                        data.at[i, "fvg_mid"] = (lower + upper) / 2.0
                        data.at[i, "fvg_gap_pct"] = gap_pct

            if active_zones:
                nearest = min(
                    active_zones,
                    key=lambda z: self._distance_pct(
                        current_close,
                        float(z["lower"]),
                        float(z["upper"]),
                    ),
                )

                lower = float(nearest["lower"])
                upper = float(nearest["upper"])

                data.at[i, "active_fvg_type"] = nearest["type"]
                data.at[i, "active_fvg_lower"] = lower
                data.at[i, "active_fvg_upper"] = upper
                data.at[i, "active_fvg_mid"] = (lower + upper) / 2.0
                data.at[i, "active_fvg_state"] = nearest["state"]
                data.at[i, "active_fvg_created_index"] = nearest[
                    "created_index"
                ]
                data.at[i, "active_fvg_distance_pct"] = self._distance_pct(
                    current_close,
                    lower,
                    upper,
                )

        return data


def detect_fair_value_gaps(
    df: pd.DataFrame,
    min_gap_pct: float = 0.0,
) -> pd.DataFrame:
    return FairValueGapDetector(
        min_gap_pct=min_gap_pct
    ).detect(df)
