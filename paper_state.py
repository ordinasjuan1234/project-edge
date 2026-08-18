"""
PROJECT EDGE
Paper State v1

Guarda y recupera el estado del Paper Trading.

Este modulo:
- NO conecta con Binance.
- NO ejecuta ordenes reales.
- NO usa dinero real.
- Guarda saldo, posicion abierta e historial en un archivo JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


DEFAULT_STATE_FILE = "paper_state.json"
DEFAULT_BALANCE = 10000.0


class PaperState:
    def __init__(
        self,
        file_path: str = DEFAULT_STATE_FILE,
        initial_balance: float = DEFAULT_BALANCE,
    ):
        self.file_path = Path(file_path)
        self.initial_balance = float(initial_balance)
        self.data = self._load()

    def _default_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "initial_balance": self.initial_balance,
            "balance": self.initial_balance,
            "position": None,
            "closed_trades": [],
        }

    def _load(self) -> dict[str, Any]:
        if not self.file_path.exists():
            return self._default_state()

        try:
            with self.file_path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(
                f"No se pudo leer el estado paper: {exc}"
            ) from exc

        required = {
            "version",
            "initial_balance",
            "balance",
            "position",
            "closed_trades",
        }

        missing = required.difference(data.keys())

        if missing:
            raise ValueError(
                f"Faltan campos en paper_state.json: {sorted(missing)}"
            )

        return data

    def save(self) -> None:
        with self.file_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                self.data,
                file,
                indent=2,
                ensure_ascii=False,
            )

    @property
    def balance(self) -> float:
        return float(self.data["balance"])

    @property
    def position(self) -> Optional[dict[str, Any]]:
        return self.data["position"]

    @property
    def has_open_position(self) -> bool:
        return self.position is not None

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
    ) -> dict[str, Any]:
        if self.has_open_position:
            raise ValueError(
                "Ya existe una posicion paper abierta."
            )

        direction = direction.upper()

        if direction not in {"LONG", "SHORT"}:
            raise ValueError(
                "direction debe ser LONG o SHORT."
            )

        position = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": float(entry_price),
            "quantity": float(quantity),
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
        }

        self.data["position"] = position
        self.save()

        return position

    def close_position(
        self,
        exit_price: float,
        reason: str,
    ) -> dict[str, Any]:
        if not self.has_open_position:
            raise ValueError(
                "No existe una posicion paper abierta."
            )

        position = self.position

        entry_price = float(position["entry_price"])
        quantity = float(position["quantity"])
        exit_price = float(exit_price)
        direction = position["direction"]

        if direction == "LONG":
            pnl = (
                exit_price - entry_price
            ) * quantity
        else:
            pnl = (
                entry_price - exit_price
            ) * quantity

        self.data["balance"] = (
            float(self.data["balance"]) + pnl
        )

        trade = {
            "symbol": position["symbol"],
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "stop_loss": float(position["stop_loss"]),
            "take_profit": float(
                position["take_profit"]
            ),
            "pnl": float(pnl),
            "reason": reason,
            "balance": float(self.data["balance"]),
        }

        self.data["closed_trades"].append(trade)
        self.data["position"] = None

        self.save()

        return trade

    def status(self) -> dict[str, Any]:
        return {
            "initial_balance": float(
                self.data["initial_balance"]
            ),
            "balance": self.balance,
            "position": self.position,
            "closed_trades": len(
                self.data["closed_trades"]
            ),
        }

    def reset(self) -> None:
        self.data = self._default_state()
        self.save()
