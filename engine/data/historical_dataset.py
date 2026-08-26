"""
PROJECT EDGE
Historical Dataset v1

Construye las cinco temporalidades del proyecto a partir de velas 5M
cerradas. Así todas las series comparten el mismo reloj y no se utilizan
velas superiores todavía incompletas.

Solo procesa datos públicos; no ejecuta órdenes.
"""

from __future__ import annotations

import pandas as pd


class HistoricalDataset:
    REQUIRED_COLUMNS = {"open_time", "open", "high", "low", "close"}
    TIMEFRAMES = {
        "15M": ("15min", 3),
        "30M": ("30min", 6),
        "1H": ("1h", 12),
        "4H": ("4h", 48),
    }

    @classmethod
    def _normalize(cls, candles_5m: pd.DataFrame) -> pd.DataFrame:
        missing = cls.REQUIRED_COLUMNS.difference(candles_5m.columns)
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
        if candles_5m.empty:
            raise ValueError("No hay velas 5M para construir el histórico.")

        data = candles_5m.copy()
        data["open_time"] = pd.to_datetime(data["open_time"], utc=True)

        for column in ("open", "high", "low", "close"):
            data[column] = pd.to_numeric(data[column], errors="raise")

        if "volume" in data.columns:
            data["volume"] = pd.to_numeric(data["volume"], errors="raise")
        else:
            data["volume"] = 0.0

        data = (
            data.drop_duplicates(subset=["open_time"], keep="last")
            .sort_values("open_time")
            .reset_index(drop=True)
        )

        if (data["high"] < data["low"]).any():
            raise ValueError("Hay velas con high menor que low.")

        expected_close = data["open_time"] + pd.Timedelta(minutes=5)
        if "close_time" in data.columns:
            close_time = pd.to_datetime(data["close_time"], utc=True)
            data["close_time"] = close_time
        else:
            data["close_time"] = expected_close

        return data

    @staticmethod
    def _resample(
        data: pd.DataFrame,
        rule: str,
        expected_bars: int,
    ) -> pd.DataFrame:
        indexed = data.set_index("open_time")
        aggregated = indexed.resample(
            rule,
            origin="epoch",
            label="left",
            closed="left",
        ).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            close_time=("close_time", "max"),
            bar_count=("close", "count"),
        )

        complete = aggregated[aggregated["bar_count"].eq(expected_bars)]
        complete = complete.drop(columns=["bar_count"]).reset_index()
        return complete

    def build(self, candles_5m: pd.DataFrame) -> dict[str, pd.DataFrame]:
        data = self._normalize(candles_5m)
        result = {"5M": data}

        for timeframe, (rule, expected_bars) in self.TIMEFRAMES.items():
            result[timeframe] = self._resample(
                data,
                rule=rule,
                expected_bars=expected_bars,
            )

        return {
            timeframe: result[timeframe]
            for timeframe in ("4H", "1H", "30M", "15M", "5M")
        }


def build_historical_timeframes(
    candles_5m: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    return HistoricalDataset().build(candles_5m)
