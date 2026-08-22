"""
PROJECT EDGE
Paper State v2

Guarda y recupera el estado del Paper Trading.

Este modulo:
- NO conecta con Binance.
- NO ejecuta ordenes reales.
- NO usa dinero real.
- Guarda saldo, posicion abierta e historial en un archivo JSON.
- Permite cierres parciales sin inflar el numero de trades.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


DEFAULT_STATE_FILE = "paper_state.json"
DEFAULT_BALANCE = 10000.0

MIN_QUANTITY = 1e-12


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

    @staticmethod
    def _calculate_pnl(
        direction: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
    ) -> float:
        direction = direction.upper()

        if direction == "LONG":
            return (
                float(exit_price) - float(entry_price)
            ) * float(quantity)

        if direction == "SHORT":
            return (
                float(entry_price) - float(exit_price)
            ) * float(quantity)

        raise ValueError(
            "direction debe ser LONG o SHORT."
        )

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        source: str = "UNCLASSIFIED",
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

        source = source.upper()

        if source not in {
            "MANUAL",
            "AUTO",
            "UNCLASSIFIED",
        }:
            raise ValueError(
                "source debe ser MANUAL, AUTO o UNCLASSIFIED."
            )

        quantity = float(quantity)

        if quantity <= 0:
            raise ValueError(
                "La cantidad debe ser mayor que 0."
            )

        trade_id = uuid4().hex

        position = {
            "trade_id": trade_id,
            "symbol": symbol,
            "direction": direction,
            "entry_price": float(entry_price),
            "quantity": quantity,
            "initial_quantity": quantity,
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "source": source,
            "realized_pnl": 0.0,
            "partial_closes": [],
        }

        self.data["position"] = position
        self.save()

        return position

    def partial_close_position(
        self,
        exit_price: float,
        percent: float,
        reason: str = "PARTIAL_CLOSE",
    ) -> dict[str, Any]:
        """
        Cierra un porcentaje de la cantidad que sigue abierta.

        El parcial:
        - actualiza el saldo PAPER;
        - reduce la cantidad abierta;
        - NO agrega una nueva operacion a closed_trades;
        - queda guardado dentro del mismo trade_id.

        Si percent == 100, se cierra la posicion completa.
        """

        if not self.has_open_position:
            raise ValueError(
                "No existe una posicion paper abierta."
            )

        percent = float(percent)

        if percent <= 0 or percent > 100:
            raise ValueError(
                "El porcentaje de cierre debe ser mayor "
                "que 0 y menor o igual a 100."
            )

        if percent == 100:
            return self.close_position(
                exit_price=exit_price,
                reason=reason,
            )

        position = self.position

        current_quantity = float(
            position["quantity"]
        )

        if current_quantity <= MIN_QUANTITY:
            raise ValueError(
                "La posicion no tiene cantidad suficiente "
                "para realizar un cierre parcial."
            )

        entry_price = float(
            position["entry_price"]
        )
        exit_price = float(exit_price)
        direction = position["direction"]

        closed_quantity = (
            current_quantity * percent / 100.0
        )

        remaining_quantity = (
            current_quantity - closed_quantity
        )

        if closed_quantity <= MIN_QUANTITY:
            raise ValueError(
                "La cantidad a cerrar es demasiado pequena."
            )

        pnl = self._calculate_pnl(
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=closed_quantity,
        )

        self.data["balance"] = (
            float(self.data["balance"]) + pnl
        )

        previous_realized = float(
            position.get("realized_pnl", 0.0)
        )

        position["realized_pnl"] = (
            previous_realized + pnl
        )

        initial_quantity = float(
            position.get(
                "initial_quantity",
                current_quantity,
            )
        )

        position["initial_quantity"] = (
            initial_quantity
        )

        partial = {
            "percent_of_remaining": percent,
            "exit_price": exit_price,
            "quantity": closed_quantity,
            "pnl": float(pnl),
            "balance": float(
                self.data["balance"]
            ),
            "reason": reason,
        }

        partial_closes = list(
            position.get(
                "partial_closes",
                [],
            )
        )

        partial_closes.append(partial)

        position["partial_closes"] = (
            partial_closes
        )

        position["quantity"] = (
            remaining_quantity
        )

        # Si la posicion tiene capital/exposicion,
        # los reducimos proporcionalmente a la
        # cantidad que sigue abierta.
        remaining_fraction = (
            remaining_quantity / initial_quantity
        )

        if "capital" in position:
            if "initial_capital" not in position:
                position["initial_capital"] = float(
                    position["capital"]
                )

            position["capital"] = (
                float(
                    position["initial_capital"]
                )
                * remaining_fraction
            )

        if "exposure" in position:
            if "initial_exposure" not in position:
                position["initial_exposure"] = float(
                    position["exposure"]
                )

            position["exposure"] = (
                float(
                    position["initial_exposure"]
                )
                * remaining_fraction
            )

        self.data["position"] = position
        self.save()

        return {
            "trade_id": position.get(
                "trade_id"
            ),
            "symbol": position["symbol"],
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "percent": percent,
            "closed_quantity": closed_quantity,
            "remaining_quantity": (
                remaining_quantity
            ),
            "pnl": float(pnl),
            "realized_pnl_total": float(
                position["realized_pnl"]
            ),
            "balance": float(
                self.data["balance"]
            ),
            "reason": reason,
            "is_final": False,
        }

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

        entry_price = float(
            position["entry_price"]
        )

        remaining_quantity = float(
            position["quantity"]
        )

        initial_quantity = float(
            position.get(
                "initial_quantity",
                remaining_quantity,
            )
        )

        exit_price = float(exit_price)
        direction = position["direction"]

        final_leg_pnl = self._calculate_pnl(
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=remaining_quantity,
        )

        realized_before_final = float(
            position.get(
                "realized_pnl",
                0.0,
            )
        )

        total_trade_pnl = (
            realized_before_final
            + final_leg_pnl
        )

        # Los parciales ya fueron acreditados al saldo.
        # Al cierre final solamente acreditamos el tramo
        # que todavia permanecia abierto.
        self.data["balance"] = (
            float(self.data["balance"])
            + final_leg_pnl
        )

        trade = {
            "trade_id": position.get(
                "trade_id"
            ),
            "symbol": position["symbol"],
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": initial_quantity,
            "final_leg_quantity": (
                remaining_quantity
            ),
            "stop_loss": float(
                position["stop_loss"]
            ),
            "take_profit": float(
                position["take_profit"]
            ),
            "source": position.get(
                "source",
                "UNCLASSIFIED",
            ),
            "partial_closes": list(
                position.get(
                    "partial_closes",
                    [],
                )
            ),
            "partial_count": len(
                position.get(
                    "partial_closes",
                    [],
                )
            ),
            "realized_pnl_before_final": (
                realized_before_final
            ),
            "final_leg_pnl": float(
                final_leg_pnl
            ),
            "pnl": float(
                total_trade_pnl
            ),
            "reason": reason,
            "balance": float(
                self.data["balance"]
            ),
            "is_final": True,
        }

        if "initial_capital" in position:
            trade["capital"] = float(
                position["initial_capital"]
            )
        elif "capital" in position:
            trade["capital"] = float(
                position["capital"]
            )

        if "leverage" in position:
            trade["leverage"] = int(
                position["leverage"]
            )

        if "initial_exposure" in position:
            trade["exposure"] = float(
                position["initial_exposure"]
            )
        elif "exposure" in position:
            trade["exposure"] = float(
                position["exposure"]
            )

        if "order_type" in position:
            trade["order_type"] = (
                position["order_type"]
            )

        self.data["closed_trades"].append(
            trade
        )

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
