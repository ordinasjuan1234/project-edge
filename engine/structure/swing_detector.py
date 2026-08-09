"""
PROJECT EDGE
Structure Engine — Swing Detector v2

Detector causal de Swing High / Swing Low.

Principio:
- Un pivote solo puede reconocerse después de `pivot_right` velas.
- Un swing se confirma únicamente cuando el precio, en velas posteriores,
  se aleja del pivote al menos el umbral adaptativo.
- Se registra la vela exacta de confirmación para evitar look-ahead bias.

Este módulo NO ejecuta órdenes ni genera señales LONG/SHORT.
"""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class Swing:
    pivot_index: int
    confirmation_index: int
    swing_type: str
    price: float
    atr: float
    move: float
    threshold: float


class SwingDetector:
    """Detector adaptativo y causal de swings."""

    def __init__(
        self,
        pivot_left: int = 2,
        pivot_right: int = 2,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        min_move_pct: float = 0.0025,
        max_move_pct: float = 0.05,
    ) -> None:
        if pivot_left < 1 or pivot_right < 1:
            raise ValueError("pivot_left y pivot_right deben ser >= 1.")
        if atr_period < 2:
            raise ValueError("atr_period debe ser >= 2.")
        if atr_multiplier <= 0:
            raise ValueError("atr_multiplier debe ser > 0.")
        if not 0 <= min_move_pct <= max_move_pct:
            raise ValueError("Debe cumplirse 0 <= min_move_pct <= max_move_pct.")

        self.pivot_left = pivot_left
        self.pivot_right = pivot_right
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.min_move_pct = min_move_pct
        self.max_move_pct = max_move_pct

    @staticmethod
    def _validate_data(df: pd.DataFrame) -> None:
        required = {"open", "high", "low", "close"}
        missing = required.difference(df.columns)

        if missing:
            raise ValueError(f"Faltan columnas OHLC requeridas: {sorted(missing)}")
        if df.empty:
            raise ValueError("El DataFrame está vacío.")
        if df[["open", "high", "low", "close"]].isna().any().any():
            raise ValueError("Los datos OHLC contienen valores nulos.")
        if (df["high"] < df["low"]).any():
            raise ValueError("Hay velas con high < low.")

    def calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        previous_close = df["close"].shift(1)
        true_range = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - previous_close).abs(),
                (df["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        return true_range.rolling(
            window=self.atr_period,
            min_periods=self.atr_period,
        ).mean()

    def _is_local_high(self, data: pd.DataFrame, i: int) -> bool:
        left = data["high"].iloc[i - self.pivot_left:i]
        right = data["high"].iloc[i + 1:i + self.pivot_right + 1]
        current = float(data["high"].iloc[i])
        return current > float(left.max()) and current >= float(right.max())

    def _is_local_low(self, data: pd.DataFrame, i: int) -> bool:
        left = data["low"].iloc[i - self.pivot_left:i]
        right = data["low"].iloc[i + 1:i + self.pivot_right + 1]
        current = float(data["low"].iloc[i])
        return current < float(left.min()) and current <= float(right.min())

    def _adaptive_threshold(self, price: float, atr: float) -> float:
        if price <= 0:
            raise ValueError("El precio debe ser mayor que cero.")

        atr_pct = atr / price
        threshold_pct = atr_pct * self.atr_multiplier
        threshold_pct = max(threshold_pct, self.min_move_pct)
        threshold_pct = min(threshold_pct, self.max_move_pct)
        return price * threshold_pct

    def detect(self, df: pd.DataFrame) -> pd.DataFrame:
        self._validate_data(df)

        data = df.copy().reset_index(drop=False)
        data["atr"] = self.calculate_atr(data)

        data["swing_candidate"] = None
        data["swing_confirmed"] = False
        data["swing_type"] = None
        data["swing_price"] = None
        data["swing_move"] = None
        data["swing_threshold"] = None
        data["swing_confirmation_index"] = None
        data["swing_confirmation_price"] = None

        start = max(self.pivot_left, self.atr_period - 1)
        last_pivot_index = len(data) - self.pivot_right - 1

        for i in range(start, last_pivot_index + 1):
            atr = data.at[i, "atr"]
            if pd.isna(atr) or atr <= 0:
                continue

            high = float(data.at[i, "high"])
            low = float(data.at[i, "low"])

            if self._is_local_high(data, i):
                data.at[i, "swing_candidate"] = "HIGH"
                threshold = self._adaptive_threshold(high, float(atr))
                first_known_at = i + self.pivot_right

                for j in range(first_known_at, len(data)):
                    move = high - float(data.at[j, "low"])
                    if move >= threshold:
                        data.at[i, "swing_confirmed"] = True
                        data.at[i, "swing_type"] = "HIGH"
                        data.at[i, "swing_price"] = high
                        data.at[i, "swing_move"] = move
                        data.at[i, "swing_threshold"] = threshold
                        data.at[i, "swing_confirmation_index"] = j
                        data.at[i, "swing_confirmation_price"] = float(data.at[j, "low"])
                        break

            if self._is_local_low(data, i):
                data.at[i, "swing_candidate"] = "LOW"
                threshold = self._adaptive_threshold(low, float(atr))
                first_known_at = i + self.pivot_right

                for j in range(first_known_at, len(data)):
                    move = float(data.at[j, "high"]) - low
                    if move >= threshold:
                        data.at[i, "swing_confirmed"] = True
                        data.at[i, "swing_type"] = "LOW"
                        data.at[i, "swing_price"] = low
                        data.at[i, "swing_move"] = move
                        data.at[i, "swing_threshold"] = threshold
                        data.at[i, "swing_confirmation_index"] = j
                        data.at[i, "swing_confirmation_price"] = float(data.at[j, "high"])
                        break

        return data


def detect_swings(
    df: pd.DataFrame,
    pivot_left: int = 2,
    pivot_right: int = 2,
    atr_period: int = 14,
    atr_multiplier: float = 1.5,
    min_move_pct: float = 0.0025,
    max_move_pct: float = 0.05,
) -> pd.DataFrame:
    detector = SwingDetector(
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        atr_period=atr_period,
        atr_multiplier=atr_multiplier,
        min_move_pct=min_move_pct,
        max_move_pct=max_move_pct,
    )
    return detector.detect(df)
