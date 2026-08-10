"""PROJECT EDGE — BOS / CHoCH Detector v1."""

from __future__ import annotations
import pandas as pd


class BreakOfStructureDetector:
    REQUIRED_COLUMNS = {"close", "structural_support", "structural_resistance"}

    @classmethod
    def _validate_data(cls, df: pd.DataFrame) -> None:
        missing = cls.REQUIRED_COLUMNS.difference(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
        if df.empty:
            raise ValueError("El DataFrame está vacío.")

    @staticmethod
    def _normalize_trend(value):
        if pd.isna(value):
            return None
        value = str(value).upper()
        if value in {"BULLISH", "BULL", "UPTREND", "UP"}:
            return "BULLISH"
        if value in {"BEARISH", "BEAR", "DOWNTREND", "DOWN"}:
            return "BEARISH"
        return None

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_data(df)
        data = df.copy().reset_index(drop=True)
        data["structure_break"] = None
        data["break_direction"] = None
        data["broken_level"] = None

        trend_col = next(
            (c for c in ("market_structure", "structure", "trend") if c in data.columns),
            None,
        )

        for i in range(1, len(data)):
            close = float(data.at[i, "close"])
            previous_close = float(data.at[i - 1, "close"])
            resistance = data.at[i, "structural_resistance"]
            support = data.at[i, "structural_support"]

            broke_up = (
                pd.notna(resistance)
                and previous_close <= float(resistance)
                and close > float(resistance)
            )
            broke_down = (
                pd.notna(support)
                and previous_close >= float(support)
                and close < float(support)
            )

            if not broke_up and not broke_down:
                continue

            trend = self._normalize_trend(data.at[i, trend_col]) if trend_col else None

            if broke_up:
                data.at[i, "break_direction"] = "UP"
                data.at[i, "broken_level"] = float(resistance)
                data.at[i, "structure_break"] = "CHoCH" if trend == "BEARISH" else "BOS"
            else:
                data.at[i, "break_direction"] = "DOWN"
                data.at[i, "broken_level"] = float(support)
                data.at[i, "structure_break"] = "CHoCH" if trend == "BULLISH" else "BOS"

        return data


def detect_structure_breaks(df: pd.DataFrame) -> pd.DataFrame:
    return BreakOfStructureDetector().detect(df)
