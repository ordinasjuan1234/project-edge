"""
PROJECT EDGE
Trade Manager v1

Gestiona una operación PAPER ya abierta vela por vela.
Puede mantenerla abierta o cerrarla por STOP o TARGET.

Este módulo NO ejecuta órdenes reales.
"""

from __future__ import annotations


class TradeManager:
    """Gestiona el ciclo de vida de una operación paper abierta."""

    def update_trade(
        self,
        trade: dict[str, object],
        candle_high: float,
        candle_low: float,
    ) -> dict[str, object]:
        if not trade.get("opened", False):
            raise ValueError("La operación no está abierta.")

        if trade.get("status") != "OPEN":
            return dict(trade)

        direction = trade.get("direction")
        stop_price = float(trade["stop_price"])
        target_price = float(trade["target_price"])
        entry_price = float(trade["entry_price"])
        position_size = float(trade["position_size"])

        candle_high = float(candle_high)
        candle_low = float(candle_low)

        if candle_high < candle_low:
            raise ValueError("candle_high no puede ser menor que candle_low.")

        result = dict(trade)

        if direction == "LONG":
            stop_hit = candle_low <= stop_price
            target_hit = candle_high >= target_price

            # Política conservadora:
            # si stop y target ocurren en la misma vela y no conocemos
            # el orden intrabar, se asume STOP primero.
            if stop_hit:
                exit_price = stop_price
                close_reason = "STOP"
            elif target_hit:
                exit_price = target_price
                close_reason = "TARGET"
            else:
                return result

            pnl = (exit_price - entry_price) * position_size

        elif direction == "SHORT":
            stop_hit = candle_high >= stop_price
            target_hit = candle_low <= target_price

            if stop_hit:
                exit_price = stop_price
                close_reason = "STOP"
            elif target_hit:
                exit_price = target_price
                close_reason = "TARGET"
            else:
                return result

            pnl = (entry_price - exit_price) * position_size

        else:
            raise ValueError("Dirección inválida en la operación.")

        result.update(
            {
                "opened": False,
                "status": "CLOSED",
                "exit_price": exit_price,
                "close_reason": close_reason,
                "pnl": pnl,
                "real_order_sent": False,
            }
        )

        return result


def manage_trade(
    trade: dict[str, object],
    candle_high: float,
    candle_low: float,
) -> dict[str, object]:
    return TradeManager().update_trade(
        trade=trade,
        candle_high=candle_high,
        candle_low=candle_low,
    )
