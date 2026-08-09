"""
PROJECT EDGE
Structure Engine — Swing Detector v1

Responsabilidad:
    Detectar Swing High y Swing Low confirmados.

Este módulo NO:
    - ejecuta órdenes
    - genera señales LONG/SHORT
    - se conecta a Binance
    - decide si operar

Entrada:
    Datos OHLCV en formato pandas.DataFrame.

Salida:
    DataFrame con ATR, candidatos de swing y swings confirmados.
"""

from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass
class Swing:
    """Representa un swing confirmado."""
    index: int
    timestamp: object
    swing_type: str
    price: float
    atr: float
    move: float
    threshold: float


class SwingDetector:
    """Detector adaptativo de swings."""

    def __init__(
        self,
        pivot_left: int = 2,
        pivot_right: int = 2,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        min_move_pct: float = 0.0025,
        max_move_pct: float = 0.05,
    ) -> None:
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

    def calculate_atr(self, df: pd.DataFrame) -> pd.Series:
        """Calcula ATR mediante True Range."""
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

    def _local_high(self, df: pd.DataFrame, i: int) -> bool:
        start = i - self.pivot_left
        end = i + self.pivot_right + 1
        window = df["high"].iloc[start:end]
        return df["high"].iloc[i] == window.max()

    def _local_low(self, df: pd.DataFrame, i: int) -> bool:
        start = i - self.pivot_left
        end = i + self.pivot_right + 1
        window = df["low"].iloc[start:end]
        return df["low"].iloc[i] == window.min()

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

        start = max(self.pivot_left, self.atr_period - 1)
        end = len(data) - self.pivot_right

        for i in range(start, end):
            atr = data.at[i, "atr"]
            if pd.isna(atr) or atr <= 0:
                continue

            high = float(data.at[i, "high"])
            low = float(data.at[i, "low"])

            if self._local_high(data, i):
                data.at[i, "swing_candidate"] = "HIGH"
                threshold = self._adaptive_threshold(high, float(atr))
                future_lows = data["low"].iloc[i + 1:]

                if not future_lows.empty:
                    lowest_future = float(future_lows.min())
                    move = high - lowest_future

                    if move >= threshold:
                        data.at[i, "swing_confirmed"] = True
                        data.at[i, "swing_type"] = "HIGH"
                        data.at[i, "swing_price"] = high
                        data.at[i, "swing_move"] = move
                        data.at[i, "swing_threshold"] = threshold

            if self._local_low(data, i):
                data.at[i, "swing_candidate"] = "LOW"
                threshold = self._adaptive_threshold(low, float(atr))
                future_highs = data["high"].iloc[i + 1:]

                if not future_highs.empty:
                    highest_future = float(future_highs.max())
                    move = highest_future - low

                    if move >= threshold:
                        data.at[i, "swing_confirmed"] = True
                        data.at[i, "swing_type"] = "LOW"
                        data.at[i, "swing_price"] = low
                        data.at[i, "swing_move"] = move
                        data.at[i, "swing_threshold"] = threshold

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
    """Función simplificada para utilizar el detector."""
    detector = SwingDetector(
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        atr_period=atr_period,
        atr_multiplier=atr_multiplier,
        min_move_pct=min_move_pct,
        max_move_pct=max_move_pct,
    )
    return detector.detect(df)
