"""
PROJECT EDGE
Paper State v5

Estado persistente del Paper Trading.

Este modulo:
- NO conecta con Binance.
- NO ejecuta ordenes reales.
- NO usa dinero real.
- Guarda saldo, posicion abierta e historial.
- Guarda una orden LIMIT pendiente.
- Permite cierres parciales sin inflar el numero de trades.
- Guarda si el modo AUTO esta habilitado o pausado.
- Puede descontar comision y deslizamiento simulados en operaciones AUTO.
- Separa el saldo AUTO DEMO del saldo MANUAL heredado.
- Guarda una escalera visual TP1 / TP2 / TP3 sin cambiar el TP final.

IMPORTANTE:
Pausar AUTO NO cierra posiciones y NO cancela LIMIT pendientes.
Solo se usara para impedir NUEVAS entradas automaticas.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


DEFAULT_STATE_FILE = "paper_state.json"
DEFAULT_BALANCE = 10000.0
DEFAULT_AUTO_DEMO_BALANCE = 1000.0

STATE_VERSION = 5
MIN_QUANTITY = 1e-12

TARGET_LEVELS = (
    ("TP1", 0.50),
    ("TP2", 0.75),
    ("TP3", 1.00),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_target_plan(
    entry_price: float,
    take_profit: float,
) -> list[dict[str, Any]]:
    """
    Divide el recorrido hasta el TP final en tres hitos acumulativos.

    TP1 y TP2 son hitos visuales/estadisticos. TP3 conserva exactamente el
    Take Profit final de la estrategia o de la mesa MANUAL, por lo que esta
    funcion no altera riesgo, cantidad ni reglas de salida.
    """
    entry_price = float(entry_price)
    take_profit = float(take_profit)
    distance = take_profit - entry_price

    if entry_price <= 0 or take_profit <= 0 or distance == 0:
        raise ValueError(
            "Entrada y Take Profit deben definir un recorrido valido."
        )

    return [
        {
            "name": name,
            "price": entry_price + distance * fraction,
            "fraction_to_final": fraction,
            "hit_at": None,
        }
        for name, fraction in TARGET_LEVELS
    ]


class PaperState:
    def __init__(
        self,
        file_path: str = DEFAULT_STATE_FILE,
        initial_balance: float = DEFAULT_BALANCE,
        auto_initial_balance: float = DEFAULT_AUTO_DEMO_BALANCE,
    ):
        self.file_path = Path(file_path)
        self.initial_balance = float(initial_balance)
        self.auto_initial_balance = float(auto_initial_balance)
        self.data = self._load()

    def _default_state(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "initial_balance": self.initial_balance,
            "balance": self.initial_balance,
            "auto_demo_initial_balance": self.auto_initial_balance,
            "auto_demo_balance": self.auto_initial_balance,
            "auto_demo_started_at": utc_now(),
            "position": None,
            "pending_order": None,
            "closed_trades": [],
            "auto_enabled": True,
            "auto_pause_reason": None,
            "auto_updated_at": None,
        }

    def _load(self) -> dict[str, Any]:
        if not self.file_path.exists():
            data = self._default_state()
            self._write(data)
            return data

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(
                f"No se pudo leer el estado paper: {exc}"
            ) from exc

        required = {
            "initial_balance",
            "balance",
            "position",
            "closed_trades",
        }

        missing = required.difference(data.keys())
        if missing:
            raise ValueError(
                "Faltan campos en paper_state.json: "
                f"{sorted(missing)}"
            )

        # Migracion automatica desde versiones anteriores. La migracion se
        # persiste al cargar para que el inicio de la cuenta AUTO DEMO sea
        # estable aunque el ciclo termine sin abrir una operacion.
        migrated = False
        defaults = {
            "pending_order": None,
            "auto_enabled": True,
            "auto_pause_reason": None,
            "auto_updated_at": None,
            "auto_demo_initial_balance": self.auto_initial_balance,
            "auto_demo_started_at": utc_now(),
        }
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
                migrated = True

        if "auto_demo_balance" not in data:
            data["auto_demo_balance"] = float(
                data["auto_demo_initial_balance"]
            )
            migrated = True

        position = data.get("position")
        if position and "target_plan" not in position:
            position["target_plan"] = build_target_plan(
                position["entry_price"],
                position["take_profit"],
            )
            migrated = True

        pending_order = data.get("pending_order")
        if pending_order and "target_plan" not in pending_order:
            pending_order["target_plan"] = build_target_plan(
                pending_order["limit_price"],
                pending_order["take_profit"],
            )
            migrated = True

        if data.get("version") != STATE_VERSION:
            data["version"] = STATE_VERSION
            migrated = True

        if migrated:
            self._write(data)

        return data

    def _write(self, data: dict[str, Any]) -> None:
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
            )

    def save(self) -> None:
        self._write(self.data)

    @property
    def balance(self) -> float:
        return float(self.data["balance"])

    @property
    def auto_demo_initial_balance(self) -> float:
        return float(self.data["auto_demo_initial_balance"])

    @property
    def auto_demo_balance(self) -> float:
        return float(self.data["auto_demo_balance"])

    def balance_for_source(self, source: str) -> float:
        """Devuelve el saldo virtual que corresponde al origen."""
        if str(source).upper() == "AUTO":
            return self.auto_demo_balance
        return self.balance

    def _apply_pnl(self, source: str, pnl: float) -> float:
        """Acredita P&L sin mezclar las cuentas AUTO y MANUAL."""
        key = (
            "auto_demo_balance"
            if str(source).upper() == "AUTO"
            else "balance"
        )
        self.data[key] = float(self.data[key]) + float(pnl)
        return float(self.data[key])

    @property
    def position(self) -> Optional[dict[str, Any]]:
        return self.data["position"]

    @property
    def pending_order(self) -> Optional[dict[str, Any]]:
        return self.data["pending_order"]

    @property
    def auto_enabled(self) -> bool:
        return bool(
            self.data.get("auto_enabled", True)
        )

    @property
    def has_open_position(self) -> bool:
        return self.position is not None

    @property
    def has_pending_order(self) -> bool:
        return self.pending_order is not None

    @property
    def has_active_commitment(self) -> bool:
        return (
            self.has_open_position
            or self.has_pending_order
        )

    def set_auto_enabled(
        self,
        enabled: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Habilita o pausa NUEVAS entradas AUTO.

        No cierra una posicion abierta.
        No cancela una orden LIMIT pendiente.
        No modifica el balance.
        """
        enabled = bool(enabled)

        self.data["auto_enabled"] = enabled
        self.data["auto_pause_reason"] = (
            None
            if enabled
            else (
                str(reason).strip()
                if reason
                else "MANUAL_PAUSE"
            )
        )
        self.data["auto_updated_at"] = utc_now()

        self.save()

        return {
            "auto_enabled": self.auto_enabled,
            "auto_pause_reason": self.data.get(
                "auto_pause_reason"
            ),
            "auto_updated_at": self.data.get(
                "auto_updated_at"
            ),
        }

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
                float(exit_price)
                - float(entry_price)
            ) * float(quantity)

        if direction == "SHORT":
            return (
                float(entry_price)
                - float(exit_price)
            ) * float(quantity)

        raise ValueError(
            "direction debe ser LONG o SHORT."
        )

    @staticmethod
    def _validate_source(source: str) -> str:
        source = source.upper()

        if source not in {
            "MANUAL",
            "AUTO",
            "UNCLASSIFIED",
        }:
            raise ValueError(
                "source debe ser MANUAL, AUTO "
                "o UNCLASSIFIED."
            )

        return source

    @staticmethod
    def _validate_direction(
        direction: str,
    ) -> str:
        direction = direction.upper()

        if direction not in {"LONG", "SHORT"}:
            raise ValueError(
                "direction debe ser LONG o SHORT."
            )

        return direction

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        source: str = "UNCLASSIFIED",
        fee_rate: float = 0.0,
        slippage_rate: float = 0.0,
    ) -> dict[str, Any]:
        if self.has_open_position:
            raise ValueError(
                "Ya existe una posicion PAPER abierta."
            )

        if self.has_pending_order:
            raise ValueError(
                "Existe una orden LIMIT pendiente. "
                "Debe ejecutarse o cancelarse antes "
                "de abrir otra posicion."
            )

        direction = self._validate_direction(
            direction
        )
        source = self._validate_source(source)
        quantity = float(quantity)
        raw_entry_price = float(entry_price)
        fee_rate = float(fee_rate)
        slippage_rate = float(slippage_rate)

        if quantity <= 0:
            raise ValueError(
                "La cantidad debe ser mayor que 0."
            )
        if raw_entry_price <= 0:
            raise ValueError("El precio de entrada debe ser mayor que 0.")
        if not 0 <= fee_rate < 0.1 or not 0 <= slippage_rate < 0.1:
            raise ValueError("Las tasas de costo PAPER son invalidas.")

        if direction == "LONG":
            executed_entry_price = raw_entry_price * (1.0 + slippage_rate)
        else:
            executed_entry_price = raw_entry_price * (1.0 - slippage_rate)

        position = {
            "trade_id": uuid4().hex,
            "symbol": symbol,
            "direction": direction,
            "signal_entry_price": raw_entry_price,
            "entry_price": executed_entry_price,
            "quantity": quantity,
            "initial_quantity": quantity,
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "target_plan": build_target_plan(
                executed_entry_price,
                take_profit,
            ),
            "source": source,
            "fee_rate": fee_rate,
            "slippage_rate": slippage_rate,
            "realized_pnl": 0.0,
            "realized_gross_pnl": 0.0,
            "realized_fees": 0.0,
            "partial_closes": [],
            "opened_at": utc_now(),
        }

        self.data["position"] = position
        self.save()
        return position

    def create_pending_order(
        self,
        symbol: str,
        direction: str,
        limit_price: float,
        capital: float,
        leverage: int,
        stop_loss: float,
        take_profit: float,
        source: str = "MANUAL",
    ) -> dict[str, Any]:
        """
        Crea una orden LIMIT PAPER pendiente.

        No abre una posicion todavia.
        El dinero no se descuenta del saldo.

        Solo puede existir:
        - una posicion abierta, o
        - una orden pendiente.

        Nunca ambas al mismo tiempo.
        """
        if self.has_open_position:
            raise ValueError(
                "No se puede crear una orden LIMIT "
                "porque ya existe una posicion abierta."
            )

        if self.has_pending_order:
            raise ValueError(
                "Ya existe una orden LIMIT PAPER pendiente."
            )

        direction = self._validate_direction(
            direction
        )
        source = self._validate_source(source)

        limit_price = float(limit_price)
        capital = float(capital)
        leverage = int(leverage)

        if limit_price <= 0:
            raise ValueError(
                "El precio LIMIT debe ser mayor que 0."
            )

        if capital <= 0:
            raise ValueError(
                "El capital debe ser mayor que 0."
            )

        if capital > self.balance:
            raise ValueError(
                "Capital insuficiente. "
                f"Saldo PAPER: {self.balance:.2f} USDT."
            )

        if leverage not in {1, 2, 3}:
            raise ValueError(
                "Apalancamiento PAPER permitido: "
                "x1, x2 o x3."
            )

        exposure = capital * leverage
        quantity = exposure / limit_price

        order = {
            "order_id": uuid4().hex,
            "symbol": symbol,
            "direction": direction,
            "order_type": "LIMIT",
            "limit_price": limit_price,
            "capital": capital,
            "leverage": leverage,
            "exposure": exposure,
            "quantity": quantity,
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "target_plan": build_target_plan(
                limit_price,
                take_profit,
            ),
            "source": source,
            "status": "PENDING",
            "created_at": utc_now(),
        }

        self.data["pending_order"] = order
        self.save()
        return order

    def cancel_pending_order(
        self,
        reason: str = "MANUAL_CANCEL",
    ) -> dict[str, Any]:
        """
        Cancela la orden LIMIT pendiente.

        No afecta el saldo porque la orden
        todavia no era una posicion abierta.
        """
        if not self.has_pending_order:
            raise ValueError(
                "No existe una orden LIMIT "
                "pendiente para cancelar."
            )

        order = dict(self.pending_order)
        order["status"] = "CANCELLED"
        order["cancel_reason"] = reason
        order["cancelled_at"] = utc_now()

        self.data["pending_order"] = None
        self.save()
        return order

    def fill_pending_order(
        self,
        fill_price: float | None = None,
    ) -> dict[str, Any]:
        """
        Convierte una orden LIMIT pendiente
        en una posicion PAPER abierta.

        Por defecto la simulacion utiliza
        el precio LIMIT como precio de ejecucion.
        """
        if self.has_open_position:
            raise ValueError(
                "Ya existe una posicion PAPER abierta."
            )

        if not self.has_pending_order:
            raise ValueError(
                "No existe una orden LIMIT "
                "pendiente para ejecutar."
            )

        order = dict(self.pending_order)

        if fill_price is None:
            entry_price = float(
                order["limit_price"]
            )
        else:
            entry_price = float(fill_price)

        if entry_price <= 0:
            raise ValueError(
                "El precio de ejecucion "
                "debe ser mayor que 0."
            )

        quantity = float(order["quantity"])
        if quantity <= 0:
            raise ValueError(
                "La cantidad de la orden "
                "LIMIT es invalida."
            )

        position = {
            "trade_id": uuid4().hex,
            "order_id": order["order_id"],
            "symbol": order["symbol"],
            "direction": order["direction"],
            "entry_price": entry_price,
            "quantity": quantity,
            "initial_quantity": quantity,
            "stop_loss": float(
                order["stop_loss"]
            ),
            "take_profit": float(
                order["take_profit"]
            ),
            "target_plan": build_target_plan(
                entry_price,
                order["take_profit"],
            ),
            "source": order.get(
                "source",
                "MANUAL",
            ),
            "capital": float(order["capital"]),
            "initial_capital": float(
                order["capital"]
            ),
            "leverage": int(order["leverage"]),
            "exposure": float(
                order["exposure"]
            ),
            "initial_exposure": float(
                order["exposure"]
            ),
            "order_type": "LIMIT",
            "limit_price": float(
                order["limit_price"]
            ),
            "filled_from_pending": True,
            "pending_created_at": order.get(
                "created_at"
            ),
            "opened_at": utc_now(),
            "realized_pnl": 0.0,
            "partial_closes": [],
            "trailing_enabled": False,
            "trailing_pct": None,
            "trailing_anchor": None,
        }

        self.data["pending_order"] = None
        self.data["position"] = position
        self.save()
        return position

    def replace_target_plan(
        self,
        take_profit: float,
    ) -> list[dict[str, Any]]:
        """Actualiza el TP final y reinicia sus hitos tras un cambio MANUAL."""
        if not self.has_open_position:
            raise ValueError(
                "No existe una posicion PAPER abierta."
            )

        position = self.position
        position["take_profit"] = float(take_profit)
        position["target_plan"] = build_target_plan(
            position["entry_price"],
            take_profit,
        )
        self.data["position"] = position
        self.save()
        return position["target_plan"]

    def mark_reached_targets(
        self,
        current_price: float,
    ) -> list[dict[str, Any]]:
        """Marca una sola vez cada TP visual alcanzado por una posicion."""
        if not self.has_open_position:
            return []

        position = self.position
        plan = position.get("target_plan")
        if not isinstance(plan, list) or not plan:
            plan = build_target_plan(
                position["entry_price"],
                position["take_profit"],
            )
            position["target_plan"] = plan

        direction = self._validate_direction(position["direction"])
        current_price = float(current_price)
        reached_at = utc_now()
        newly_reached = []

        for target in plan:
            if target.get("hit_at"):
                continue
            target_price = float(target["price"])
            reached = (
                current_price >= target_price
                if direction == "LONG"
                else current_price <= target_price
            )
            if reached:
                target["hit_at"] = reached_at
                newly_reached.append(dict(target))

        if newly_reached:
            self.data["position"] = position
            self.save()

        return newly_reached

    def partial_close_position(
        self,
        exit_price: float,
        percent: float,
        reason: str = "PARTIAL_CLOSE",
    ) -> dict[str, Any]:
        """
        Cierra un porcentaje de la cantidad
        que sigue abierta.

        El parcial:
        - actualiza el saldo PAPER;
        - reduce la cantidad abierta;
        - NO agrega un nuevo trade;
        - permanece en el mismo trade_id.

        Si percent == 100:
        se cierra toda la posicion.
        """
        if not self.has_open_position:
            raise ValueError(
                "No existe una posicion PAPER abierta."
            )

        percent = float(percent)
        if percent <= 0 or percent > 100:
            raise ValueError(
                "El porcentaje debe ser mayor que 0 "
                "y menor o igual a 100."
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
                "La posicion no tiene cantidad "
                "suficiente para un cierre parcial."
            )

        entry_price = float(
            position["entry_price"]
        )
        raw_exit_price = float(exit_price)
        direction = position["direction"]
        fee_rate = float(position.get("fee_rate", 0.0))
        slippage_rate = float(position.get("slippage_rate", 0.0))
        if direction == "LONG":
            exit_price = raw_exit_price * (1.0 - slippage_rate)
        else:
            exit_price = raw_exit_price * (1.0 + slippage_rate)

        closed_quantity = (
            current_quantity
            * percent
            / 100.0
        )
        remaining_quantity = (
            current_quantity
            - closed_quantity
        )

        if closed_quantity <= MIN_QUANTITY:
            raise ValueError(
                "La cantidad a cerrar es "
                "demasiado pequena."
            )

        gross_pnl = self._calculate_pnl(
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=closed_quantity,
        )
        entry_fee = entry_price * closed_quantity * fee_rate
        exit_fee = exit_price * closed_quantity * fee_rate
        fees = entry_fee + exit_fee
        pnl = gross_pnl - fees

        account_balance = self._apply_pnl(
            position.get("source", "UNCLASSIFIED"),
            pnl,
        )

        previous_realized = float(
            position.get(
                "realized_pnl",
                0.0,
            )
        )

        position["realized_pnl"] = (
            previous_realized + pnl
        )
        position["realized_gross_pnl"] = float(
            position.get("realized_gross_pnl", 0.0)
        ) + gross_pnl
        position["realized_fees"] = float(
            position.get("realized_fees", 0.0)
        ) + fees

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
            "raw_exit_price": raw_exit_price,
            "exit_price": exit_price,
            "quantity": closed_quantity,
            "gross_pnl": float(gross_pnl),
            "fees": float(fees),
            "pnl": float(pnl),
            "balance": account_balance,
            "reason": reason,
            "closed_at": utc_now(),
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

        remaining_fraction = (
            remaining_quantity
            / initial_quantity
        )

        if "capital" in position:
            if "initial_capital" not in position:
                position["initial_capital"] = float(
                    position["capital"]
                )

            position["capital"] = (
                float(
                    position[
                        "initial_capital"
                    ]
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
                    position[
                        "initial_exposure"
                    ]
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
            "raw_exit_price": raw_exit_price,
            "exit_price": exit_price,
            "percent": percent,
            "closed_quantity": closed_quantity,
            # Metadatos informativos para Telegram; no cambian el cálculo.
            "source": position.get("source", "UNCLASSIFIED"),
            "leverage": position.get("leverage"),
            "fee_rate": fee_rate,
            "slippage_rate": slippage_rate,
            "remaining_quantity": (
                remaining_quantity
            ),
            "pnl": float(pnl),
            "gross_pnl": float(gross_pnl),
            "fees": float(fees),
            "realized_pnl_total": float(
                position["realized_pnl"]
            ),
            "balance": account_balance,
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
                "No existe una posicion PAPER abierta."
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
        raw_exit_price = float(exit_price)
        direction = position["direction"]
        fee_rate = float(position.get("fee_rate", 0.0))
        slippage_rate = float(position.get("slippage_rate", 0.0))
        if direction == "LONG":
            exit_price = raw_exit_price * (1.0 - slippage_rate)
        else:
            exit_price = raw_exit_price * (1.0 + slippage_rate)

        final_leg_gross_pnl = self._calculate_pnl(
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=remaining_quantity,
        )
        final_leg_fees = (
            entry_price * remaining_quantity * fee_rate
            + exit_price * remaining_quantity * fee_rate
        )
        final_leg_pnl = final_leg_gross_pnl - final_leg_fees

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
        total_gross_pnl = float(
            position.get("realized_gross_pnl", 0.0)
        ) + final_leg_gross_pnl
        total_fees = float(
            position.get("realized_fees", 0.0)
        ) + final_leg_fees

        # Los parciales ya fueron acreditados antes.
        account_balance = self._apply_pnl(
            position.get("source", "UNCLASSIFIED"),
            final_leg_pnl,
        )

        trade = {
            "trade_id": position.get(
                "trade_id"
            ),
            "symbol": position["symbol"],
            "direction": direction,
            "entry_price": entry_price,
            "signal_entry_price": float(
                position.get("signal_entry_price", entry_price)
            ),
            "raw_exit_price": raw_exit_price,
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
            "target_plan": list(
                position.get("target_plan", [])
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
            "gross_pnl": float(total_gross_pnl),
            "fee_rate": fee_rate,
            "slippage_rate": slippage_rate,
            "fees": float(total_fees),
            "pnl": float(
                total_trade_pnl
            ),
            "reason": reason,
            "balance": account_balance,
            "is_final": True,
            "closed_at": utc_now(),
        }

        if "opened_at" in position:
            trade["opened_at"] = (
                position["opened_at"]
            )

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

        if "order_id" in position:
            trade["order_id"] = (
                position["order_id"]
            )

        if "limit_price" in position:
            trade["limit_price"] = float(
                position["limit_price"]
            )

        if "filled_from_pending" in position:
            trade["filled_from_pending"] = bool(
                position[
                    "filled_from_pending"
                ]
            )

        if "pending_created_at" in position:
            trade["pending_created_at"] = (
                position[
                    "pending_created_at"
                ]
            )

        for field in (
            "strategy",
            "risk_pct",
            "risk_budget",
            "estimated_risk",
            "estimated_cost",
            "estimated_net_reward_risk",
        ):
            if field in position:
                trade[field] = position[field]

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
            "auto_demo_initial_balance": self.auto_demo_initial_balance,
            "auto_demo_balance": self.auto_demo_balance,
            "auto_demo_started_at": self.data.get(
                "auto_demo_started_at"
            ),
            "position": self.position,
            "pending_order": (
                self.pending_order
            ),
            "closed_trades": len(
                self.data["closed_trades"]
            ),
            "auto_enabled": (
                self.auto_enabled
            ),
            "auto_pause_reason": (
                self.data.get(
                    "auto_pause_reason"
                )
            ),
            "auto_updated_at": (
                self.data.get(
                    "auto_updated_at"
                )
            ),
        }

    def reset(self) -> None:
        self.data = self._default_state()
        self.save()
