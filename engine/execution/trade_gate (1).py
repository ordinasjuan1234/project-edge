"""
PROJECT EDGE
Trade Gate v1

Integra Decision Engine + Risk Engine y devuelve si una operación
queda habilitada para entorno DEMO/PAPER.

Este módulo NO ejecuta órdenes reales.
"""

from __future__ import annotations

from engine.decision.decision_engine import DecisionEngine
from engine.risk.risk_engine import RiskEngine


class TradeGate:
    """Puerta de control entre análisis y ejecución simulada."""

    def __init__(
        self,
        max_risk_pct: float = 0.01,
        min_rr: float = 1.5,
    ) -> None:
        self.decision_engine = DecisionEngine()
        self.risk_engine = RiskEngine(
            max_risk_pct=max_risk_pct,
            min_rr=min_rr,
        )

    def evaluate(
        self,
        mtf_result: dict[str, object],
        account_equity: float,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> dict[str, object]:
        decision = self.decision_engine.decide(mtf_result)

        if decision["decision"] not in {"READY_LONG", "READY_SHORT"}:
            return {
                "trade_status": "NO_TRADE",
                "decision": decision,
                "risk": None,
                "demo_authorized": False,
                "reason": decision["reason"],
            }

        risk = self.risk_engine.evaluate(
            decision=decision,
            account_equity=account_equity,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )

        if not risk["approved"]:
            return {
                "trade_status": "RISK_REJECTED",
                "decision": decision,
                "risk": risk,
                "demo_authorized": False,
                "reason": risk["reason"],
            }

        return {
            "trade_status": "DEMO_READY",
            "decision": decision,
            "risk": risk,
            "demo_authorized": True,
            "reason": "Decisión y riesgo aprobados para simulación.",
        }


def evaluate_trade_gate(
    mtf_result: dict[str, object],
    account_equity: float,
    entry_price: float,
    stop_price: float,
    target_price: float,
    max_risk_pct: float = 0.01,
    min_rr: float = 1.5,
) -> dict[str, object]:
    gate = TradeGate(
        max_risk_pct=max_risk_pct,
        min_rr=min_rr,
    )

    return gate.evaluate(
        mtf_result=mtf_result,
        account_equity=account_equity,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
    )
