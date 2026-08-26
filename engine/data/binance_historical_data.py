"""
PROJECT EDGE
Binance Historical Data Loader v1

Descarga velas históricas públicas de Binance Spot mediante
el endpoint de market-data-only.

NO usa API key.
NO accede a saldo.
NO ejecuta órdenes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd


class BinanceHistoricalData:
    BASE_URL = "https://data-api.binance.vision/api/v3/klines"

    VALID_INTERVALS = {"5m", "15m", "30m", "1h", "4h"}
    INTERVAL_MS = {
        "5m": 5 * 60 * 1000,
        "15m": 15 * 60 * 1000,
        "30m": 30 * 60 * 1000,
        "1h": 60 * 60 * 1000,
        "4h": 4 * 60 * 60 * 1000,
    }

    def __init__(self, timeout: int = 20) -> None:
        if timeout <= 0:
            raise ValueError("timeout debe ser mayor que cero.")
        self.timeout = timeout

    @classmethod
    def _validate_interval(cls, interval: str) -> str:
        interval = str(interval)
        if interval not in cls.VALID_INTERVALS:
            raise ValueError(
                f"Intervalo inválido: {interval}. "
                f"Permitidos: {sorted(cls.VALID_INTERVALS)}"
            )
        return interval

    def fetch(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        interval = self._validate_interval(interval)
        symbol = str(symbol).upper().replace("/", "")

        if not symbol:
            raise ValueError("symbol no puede estar vacío.")

        if not 1 <= limit <= 1000:
            raise ValueError("limit debe estar entre 1 y 1000.")

        params: dict[str, object] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        if start_time_ms is not None:
            params["startTime"] = int(start_time_ms)

        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)

        url = f"{self.BASE_URL}?{urlencode(params)}"

        with urlopen(url, timeout=self.timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))

        if not isinstance(raw, list):
            raise ValueError(f"Respuesta inesperada de Binance: {raw}")

        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "ignore",
        ]

        data = pd.DataFrame(raw, columns=columns)

        if data.empty:
            return data

        for column in ["open", "high", "low", "close", "volume"]:
            data[column] = pd.to_numeric(data[column], errors="raise")

        data["open_time"] = pd.to_datetime(
            data["open_time"],
            unit="ms",
            utc=True,
        )
        data["close_time"] = pd.to_datetime(
            data["close_time"],
            unit="ms",
            utc=True,
        )

        return data

    def fetch_project_edge_timeframes(
        self,
        symbol: str,
        limit: int = 500,
    ) -> dict[str, pd.DataFrame]:
        mapping = {
            "4H": "4h",
            "1H": "1h",
            "30M": "30m",
            "15M": "15m",
            "5M": "5m",
        }

        return {
            project_tf: self.fetch(
                symbol=symbol,
                interval=binance_tf,
                limit=limit,
            )
            for project_tf, binance_tf in mapping.items()
        }

    def fetch_range(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> pd.DataFrame:
        """Descarga un rango completo usando páginas de hasta 1000 velas."""
        interval = self._validate_interval(interval)
        start_time_ms = int(start_time_ms)
        end_time_ms = int(end_time_ms)

        if start_time_ms < 0 or end_time_ms < 0:
            raise ValueError("Los tiempos no pueden ser negativos.")
        if start_time_ms > end_time_ms:
            raise ValueError("start_time_ms no puede superar end_time_ms.")

        cursor = start_time_ms
        step_ms = self.INTERVAL_MS[interval]
        batches: list[pd.DataFrame] = []

        while cursor <= end_time_ms:
            batch = self.fetch(
                symbol=symbol,
                interval=interval,
                start_time_ms=cursor,
                end_time_ms=end_time_ms,
                limit=1000,
            )

            if batch.empty:
                break

            batches.append(batch)
            last_open_ms = int(
                batch["open_time"].iloc[-1].timestamp() * 1000
            )
            next_cursor = last_open_ms + step_ms

            if next_cursor <= cursor:
                raise RuntimeError(
                    "Binance no avanzó al paginar los datos históricos."
                )

            cursor = next_cursor

            if len(batch) < 1000:
                break

        if not batches:
            return pd.DataFrame()

        result = pd.concat(batches, ignore_index=True)
        result = (
            result.drop_duplicates(subset=["open_time"], keep="last")
            .sort_values("open_time")
            .reset_index(drop=True)
        )
        return result

    def fetch_recent(
        self,
        symbol: str,
        interval: str = "5m",
        days: int = 90,
        now: datetime | None = None,
    ) -> pd.DataFrame:
        """Descarga velas cerradas de los últimos ``days`` días."""
        interval = self._validate_interval(interval)
        days = int(days)

        if not 1 <= days <= 730:
            raise ValueError("days debe estar entre 1 y 730.")

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)

        step_ms = self.INTERVAL_MS[interval]
        now_ms = int(current.timestamp() * 1000)
        current_open_ms = (now_ms // step_ms) * step_ms
        last_closed_open_ms = current_open_ms - step_ms
        start_time_ms = last_closed_open_ms - days * 24 * 60 * 60 * 1000

        return self.fetch_range(
            symbol=symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=last_closed_open_ms,
        )


def fetch_project_edge_timeframes(
    symbol: str,
    limit: int = 500,
) -> dict[str, pd.DataFrame]:
    return BinanceHistoricalData().fetch_project_edge_timeframes(
        symbol=symbol,
        limit=limit,
    )
