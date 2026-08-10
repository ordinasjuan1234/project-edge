"""
PROJECT EDGE
Paper Trading Engine v1

Simula operaciones autorizadas por Trade Gate.
NO envía órdenes reales ni se conecta a ningún exchange.
"""

from __future__ import annotations


class PaperTradingEngine:
    """Simulador básico de operaciones demo/paper."""

    def open_trade(
        self,
        gate_result: dict[str, object],
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> dict[str, object]:
        if not gate_result.get("demo_authorized", False):
            return {
                "opened": False,
                "status": "REJECTED",
                "reason": gate_result.get(
                    "reason",
                    "La operación no está autorizada para demo.",
                ),
            }

        decision = gate_result.get("decision", {})
        risk = gate_result.get("risk", {})

        direction = decision.get("direction")
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("La dirección debe ser LONG o SHORT.")

        position_size = float(risk.get("position_size", 0.0))
        if position_size <= 0:
            raise ValueError("El tamaño de posición debe ser mayor que cero.")

        return {
            "opened": True,
            "status": "OPEN",
            "mode": "PAPER",
            "direction": direction,
            "entry_price": float(entry_price),
            "stop_price": float(stop_price),
            "target_price": float(target_price),
            "position_size": position_size,
            "real_order_sent": False,
        }

    def close_trade(
        self,
        trade: dict[str, object],
        exit_price: float,
    ) -> dict[str, object]:
        if not trade.get("opened", False):
            raise ValueError("La operación paper no está abierta.")

        direction = trade["direction"]
        entry_price = float(trade["entry_price"])
        position_size = float(trade["position_size"])
        exit_price = float(exit_price)

        if exit_price <= 0:
            raise ValueError("exit_price debe ser mayor que cero.")

        if direction == "LONG":
            pnl = (exit_price - entry_price) * position_size
        elif direction == "SHORT":
            pnl = (entry_price - exit_price) * position_size
        else:
            raise ValueError("Dirección inválida en la operación.")

        result = dict(trade)
        result.update(
            {
                "status": "CLOSED",
                "exit_price": exit_price,
                "pnl": pnl,
                "real_order_sent": False,
            }
        )
        return result


def open_paper_trade(
    gate_result: dict[str, object],
    entry_price: float,
    stop_price: float,
    target_price: float,
) -> dict[str, object]:
    return PaperTradingEngine().open_trade(
        gate_result=gate_result,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
    )
