"""
PROJECT EDGE
Decision Engine v1

Convierte la lectura multitemporal en un estado operativo.
NO ejecuta órdenes ni conecta con un broker.
"""

from __future__ import annotations


class DecisionEngine:
    """Decide si esperar, vigilar, preparar o bloquear una operación."""

    VALID_STATES = {"BULLISH", "BEARISH", "TRANSITION", "UNDEFINED"}

    def decide(self, mtf_result: dict[str, object]) -> dict[str, object]:
        if "states" not in mtf_result or "alignment" not in mtf_result:
            raise ValueError("Faltan 'states' o 'alignment' en el resultado multitemporal.")

        states = mtf_result["states"]
        alignment_data = mtf_result["alignment"]

        if not isinstance(states, dict) or not isinstance(alignment_data, dict):
            raise ValueError("'states' y 'alignment' deben ser diccionarios.")

        required = ("4H", "1H", "30M", "15M", "5M")
        missing = [tf for tf in required if tf not in states]
        if missing:
            raise ValueError(f"Faltan temporalidades requeridas: {missing}")

        normalized = {tf: str(states[tf]).upper() for tf in required}

        for tf, state in normalized.items():
            if state not in self.VALID_STATES:
                raise ValueError(f"Estado inválido para {tf}: {state}")

        alignment = str(alignment_data.get("alignment", "")).upper()
        macro = normalized["4H"]
        lower = (normalized["15M"], normalized["5M"])

        decision = "WAIT"
        direction = None
        reason = "Sin alineación suficiente."

        if alignment in {"MACRO_CONTEXT_CONFLICT", "INTERMEDIATE_CONFLICT"}:
            decision = "BLOCKED"
            reason = "Conflicto entre temporalidades superiores."

        elif macro not in {"BULLISH", "BEARISH"}:
            decision = "WAIT"
            reason = "La temporalidad 4H no tiene dirección estructural definida."

        elif alignment == "FULL_ALIGNMENT":
            direction = "LONG" if macro == "BULLISH" else "SHORT"
            decision = f"READY_{direction}"
            reason = "Todas las temporalidades están alineadas."

        elif alignment == "PULLBACK_OR_WAIT":
            direction = "LONG" if macro == "BULLISH" else "SHORT"
            if all(state == macro for state in lower):
                decision = f"WATCH_{direction}"
                reason = "La dirección macro sigue vigente y las temporalidades bajas se realinean."
            else:
                decision = f"WATCH_{direction}"
                reason = "Hay dirección macro, pero falta confirmación completa en temporalidades bajas."

        else:
            direction = "LONG" if macro == "BULLISH" else "SHORT"
            decision = f"WATCH_{direction}"
            reason = "Existe sesgo macro, pero la alineación todavía es parcial."

        return {
            "decision": decision,
            "direction": direction,
            "alignment": alignment,
            "reason": reason,
            "can_execute": False,
        }


def make_decision(mtf_result: dict[str, object]) -> dict[str, object]:
    return DecisionEngine().decide(mtf_result)
