"""
PROJECT EDGE
Backtest Metrics v1

Métricas avanzadas para evaluar resultados históricos:
- Profit Factor
- Max Drawdown
- Ganancia media
- Pérdida media
- Expectativa por operación

NO ejecuta órdenes.
"""

from __future__ import annotations


class BacktestMetrics:
    """Calcula métricas de rendimiento sobre una lista de trades cerrados."""

    @staticmethod
    def _pnls(trades: list[dict[str, object]]) -> list[float]:
        return [float(trade.get("pnl", 0.0)) for trade in trades]

    def calculate(self, trades: list[dict[str, object]]) -> dict[str, float]:
        pnls = self._pnls(trades)

        if not pnls:
            return {
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
                "average_win": 0.0,
                "average_loss": 0.0,
                "expectancy": 0.0,
            }

        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))

        if gross_loss == 0:
            profit_factor = float("inf") if gross_profit > 0 else 0.0
        else:
            profit_factor = gross_profit / gross_loss

        average_win = sum(wins) / len(wins) if wins else 0.0
        average_loss = sum(losses) / len(losses) if losses else 0.0

        win_rate = len(wins) / len(pnls)
        loss_rate = len(losses) / len(pnls)

        expectancy = (
            win_rate * average_win
            + loss_rate * average_loss
        )

        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for pnl in pnls:
            equity += pnl
            peak = max(peak, equity)
            drawdown = peak - equity
            max_drawdown = max(max_drawdown, drawdown)

        return {
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "average_win": average_win,
            "average_loss": average_loss,
            "expectancy": expectancy,
        }


def calculate_backtest_metrics(
    trades: list[dict[str, object]],
) -> dict[str, float]:
    return BacktestMetrics().calculate(trades)
