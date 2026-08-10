"""
PROJECT EDGE
Backtest Report v1

Unifica métricas básicas y avanzadas en un único reporte.
NO ejecuta órdenes reales.
"""

from __future__ import annotations

from engine.execution.backtest_engine import BacktestResult
from engine.execution.backtest_metrics import BacktestMetrics


class BacktestReport:
    """Genera un reporte completo a partir de trades cerrados."""

    def generate(
        self,
        trades: list[dict[str, object]],
        rejected: int = 0,
        no_trade: int = 0,
    ) -> dict[str, object]:
        if rejected < 0 or no_trade < 0:
            raise ValueError("rejected y no_trade no pueden ser negativos.")

        basic = BacktestResult(trades=trades).summary()
        advanced = BacktestMetrics().calculate(trades)

        return {
            **basic,
            **advanced,
            "rejected": int(rejected),
            "no_trade": int(no_trade),
        }


def generate_backtest_report(
    trades: list[dict[str, object]],
    rejected: int = 0,
    no_trade: int = 0,
) -> dict[str, object]:
    return BacktestReport().generate(
        trades=trades,
        rejected=rejected,
        no_trade=no_trade,
    )
