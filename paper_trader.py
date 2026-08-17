"""
PROJECT EDGE
Paper Trader v1

Simulador de operaciones.
NO conecta con Binance.
NO usa dinero real.
NO ejecuta órdenes reales.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PaperPosition:
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float


class PaperTrader:
    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.position: Optional[PaperPosition] = None
        self.closed_trades = []

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
    ):
        if self.position is not None:
            raise ValueError("Ya existe una posicion abierta.")

        direction = direction.upper()

        if direction not in {"LONG", "SHORT"}:
            raise ValueError("direction debe ser LONG o SHORT.")

        if entry_price <= 0:
            raise ValueError("entry_price debe ser mayor que cero.")

        if quantity <= 0:
            raise ValueError("quantity debe ser mayor que cero.")

        if direction == "LONG":
            if stop_loss >= entry_price:
                raise ValueError("En LONG, el stop debe estar debajo de la entrada.")
            if take_profit <= entry_price:
                raise ValueError("En LONG, el objetivo debe estar arriba de la entrada.")

        if direction == "SHORT":
            if stop_loss <= entry_price:
                raise ValueError("En SHORT, el stop debe estar arriba de la entrada.")
            if take_profit >= entry_price:
                raise ValueError("En SHORT, el objetivo debe estar debajo de la entrada.")

        self.position = PaperPosition(
            symbol=symbol,
            direction=direction,
            entry_price=float(entry_price),
            quantity=float(quantity),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
        )

        return self.position

    def update_price(self, current_price: float):
        if self.position is None:
            return None

        current_price = float(current_price)
        position = self.position

        if position.direction == "LONG":
            if current_price <= position.stop_loss:
                return self.close_position(position.stop_loss, "STOP_LOSS")

            if current_price >= position.take_profit:
                return self.close_position(position.take_profit, "TAKE_PROFIT")

        if position.direction == "SHORT":
            if current_price >= position.stop_loss:
                return self.close_position(position.stop_loss, "STOP_LOSS")

            if current_price <= position.take_profit:
                return self.close_position(position.take_profit, "TAKE_PROFIT")

        return None

    def close_position(self, exit_price: float, reason: str):
        if self.position is None:
            raise ValueError("No existe una posicion abierta.")

        position = self.position
        exit_price = float(exit_price)

        if position.direction == "LONG":
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        self.balance += pnl

        result = {
            "symbol": position.symbol,
            "direction": position.direction,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "quantity": position.quantity,
            "pnl": pnl,
            "reason": reason,
            "balance": self.balance,
        }

        self.closed_trades.append(result)
        self.position = None

        return result

    def status(self):
        return {
            "initial_balance": self.initial_balance,
            "balance": self.balance,
            "position": self.position,
            "closed_trades": len(self.closed_trades),
        }
