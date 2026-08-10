"""
PROJECT EDGE
Risk Engine v1

Responsabilidad:
- Validar que una decisión operativa tenga riesgo definido.
- Calcular distancia al stop.
- Calcular tamaño teórico de posición según riesgo máximo.
- Validar relación riesgo/beneficio mínima.

Este módulo NO ejecuta órdenes.
"""

from __future__ import annotations


class RiskEngine:
    """Motor básico de control de riesgo para PROJECT EDGE."""

    def __init__(
        self,
        max_risk_pct: float = 0.01,
        min_rr: float = 1.5,
    ) -> None:
        if not 0 < max_risk_pct <= 0.05:
            raise ValueError("max_risk_pct debe estar entre 0 y 0.05.")
        if min_rr <= 0:
            raise ValueError("min_rr debe ser mayor que cero.")

        self.max_risk_pct = max_risk_pct
        self.min_rr = min_rr

    def evaluate(
        self,
        decision: dict[str, object],
        account_equity: float,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> dict[str, object]:
        if account_equity <= 0:
            raise ValueError("account_equity debe ser mayor que cero.")
        if entry_price <= 0 or stop_price <= 0 or target_price <= 0:
            raise ValueError("Los precios deben ser mayores que cero.")

        decision_state = str(decision.get("decision", "")).upper()
        direction = decision.get("direction")

        if decision_state not in {"READY_LONG", "READY_SHORT"}:
            return {
                "approved": False,
                "reason": "La decisión todavía no está en estado READY.",
                "position_size": 0.0,
                "risk_amount": 0.0,
                "rr": None,
            }

        if direction not in {"LONG", "SHORT"}:
            raise ValueError("La dirección debe ser LONG o SHORT.")

        if direction == "LONG":
            if not stop_price < entry_price < target_price:
                raise ValueError("Para LONG debe cumplirse stop < entrada < objetivo.")
            risk_per_unit = entry_price - stop_price
            reward_per_unit = target_price - entry_price
        else:
            if not target_price < entry_price < stop_price:
                raise ValueError("Para SHORT debe cumplirse objetivo < entrada < stop.")
            risk_per_unit = stop_price - entry_price
            reward_per_unit = entry_price - target_price

        rr = reward_per_unit / risk_per_unit
        risk_amount = account_equity * self.max_risk_pct
        position_size = risk_amount / risk_per_unit

        if rr < self.min_rr:
            return {
                "approved": False,
                "reason": f"Relación riesgo/beneficio insuficiente: {rr:.2f}",
                "position_size": position_size,
                "risk_amount": risk_amount,
                "rr": rr,
            }

        return {
            "approved": True,
            "reason": "Riesgo aceptado.",
            "position_size": position_size,
            "risk_amount": risk_amount,
            "rr": rr,
        }


def evaluate_risk(
    decision: dict[str, object],
    account_equity: float,
    entry_price: float,
    stop_price: float,
    target_price: float,
    max_risk_pct: float = 0.01,
    min_rr: float = 1.5,
) -> dict[str, object]:
    engine = RiskEngine(
        max_risk_pct=max_risk_pct,
        min_rr=min_rr,
    )
    return engine.evaluate(
        decision=decision,
        account_equity=account_equity,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
    )
