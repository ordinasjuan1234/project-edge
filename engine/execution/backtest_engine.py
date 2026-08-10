"""
PROJECT EDGE
Backtest Engine v1

Recorre datos históricos y gestiona operaciones PAPER ya generadas.
Registra resultados agregados básicos.

Este módulo NO conecta con Binance ni ejecuta órdenes reales.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.execution.trade_manager import TradeManager


@dataclass
class BacktestResult:
    trades: list[dict[str, object]] = field(default_factory=list)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winners(self) -> int:
        return sum(1 for trade in self.trades if float(trade.get("pnl", 0.0)) > 0)

    @property
    def losers(self) -> int:
        return sum(1 for trade in self.trades if float(trade.get("pnl", 0.0)) < 0)

    @property
    def breakeven(self) -> int:
        return sum(1 for trade in self.trades if float(trade.get("pnl", 0.0)) == 0)

    @property
    def total_pnl(self) -> float:
        return sum(float(trade.get("pnl", 0.0)) for trade in self.trades)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winners / self.total_trades

    def summary(self) -> dict[str, object]:
        return {
            "total_trades": self.total_trades,
            "winners": self.winners,
            "losers": self.losers,
            "breakeven": self.breakeven,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
        }


class BacktestEngine:
    """Gestor simple de trades paper sobre velas históricas."""

    REQUIRED_COLUMNS = {"high", "low"}

    def __init__(self) -> None:
        self.trade_manager = TradeManager()

    @classmethod
    def _validate_data(cls, df: pd.DataFrame) -> None:
        missing = cls.REQUIRED_COLUMNS.difference(df.columns)
        if missing:
            raise ValueError(f"Faltan columnas requeridas: {sorted(missing)}")
        if df.empty:
            raise ValueError("El DataFrame está vacío.")

    def run_trade(
        self,
        trade: dict[str, object],
        candles: pd.DataFrame,
        start_index: int = 0,
    ) -> dict[str, object]:
        """
        Gestiona una operación paper desde start_index hasta cierre o fin de datos.
        """
        self._validate_data(candles)

        if start_index < 0 or start_index >= len(candles):
            raise ValueError("start_index fuera de rango.")

        current = dict(trade)

        for i in range(start_index, len(candles)):
            row = candles.iloc[i]
            current = self.trade_manager.update_trade(
                current,
                candle_high=float(row["high"]),
                candle_low=float(row["low"]),
            )

            if current.get("status") == "CLOSED":
                current["close_index"] = i
                return current

        current["close_index"] = None
        return current

    def summarize_trades(
        self,
        trades: list[dict[str, object]],
    ) -> dict[str, object]:
        return BacktestResult(trades=trades).summary()


def summarize_backtest(
    trades: list[dict[str, object]],
) -> dict[str, object]:
    return BacktestResult(trades=trades).summary()
