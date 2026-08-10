"""
PROJECT EDGE
Entry Readiness v1

Explica qué condiciones faltan para que una oportunidad
pase de WAIT / WATCH / BLOCKED a READY.

NO ejecuta órdenes.
"""

from __future__ import annotations


class EntryReadiness:
    """Describe el estado actual y qué falta para habilitar una entrada."""

    REQUIRED_TIMEFRAMES = ("4H", "1H", "30M", "15M", "5M")

    def evaluate(
        self,
        mtf_result: dict[str, object],
        decision_result: dict[str, object],
    ) -> dict[str, object]:
        if "states" not in mtf_result or "alignment" not in mtf_result:
            raise ValueError("El resultado multitemporal está incompleto.")

        states = mtf_result["states"]
        if not isinstance(states, dict):
            raise ValueError("'states' debe ser un diccionario.")

        missing = [tf for tf in self.REQUIRED_TIMEFRAMES if tf not in states]
        if missing:
            raise ValueError(f"Faltan temporalidades requeridas: {missing}")

        normalized = {tf: str(states[tf]).upper() for tf in self.REQUIRED_TIMEFRAMES}

        decision = str(decision_result.get("decision", "WAIT")).upper()
        direction = decision_result.get("direction")

        macro = normalized["4H"]
        one_hour = normalized["1H"]
        m30 = normalized["30M"]
        m15 = normalized["15M"]
        m5 = normalized["5M"]

        missing_conditions: list[str] = []

        if macro == "BULLISH":
            bias = "LONG"
        elif macro == "BEARISH":
            bias = "SHORT"
        else:
            bias = None

        if decision in {"READY_LONG", "READY_SHORT"}:
            return {
                "status": "READY",
                "bias": direction,
                "decision": decision,
                "missing_conditions": [],
                "message": "La estructura está alineada para evaluación de riesgo.",
            }

        if bias == "LONG":
            if one_hour != "BULLISH":
                missing_conditions.append("1H debe volver a BULLISH.")
            if m30 != "BULLISH":
                missing_conditions.append("30M debe recuperar estructura BULLISH.")
            if m15 != "BULLISH":
                missing_conditions.append("15M debe confirmar BULLISH.")
            if m5 != "BULLISH":
                missing_conditions.append("5M debe confirmar BULLISH.")

            message = (
                "Sesgo macro LONG, pero faltan confirmaciones "
                "en temporalidades inferiores."
            )

        elif bias == "SHORT":
            if one_hour != "BEARISH":
                missing_conditions.append("1H debe volver a BEARISH.")
            if m30 != "BEARISH":
                missing_conditions.append("30M debe recuperar estructura BEARISH.")
            if m15 != "BEARISH":
                missing_conditions.append("15M debe confirmar BEARISH.")
            if m5 != "BEARISH":
                missing_conditions.append("5M debe confirmar BEARISH.")

            message = (
                "Sesgo macro SHORT, pero faltan confirmaciones "
                "en temporalidades inferiores."
            )

        else:
            message = "4H todavía no tiene una dirección estructural definida."
            missing_conditions.append(
                "4H debe definir una estructura BULLISH o BEARISH."
            )

        return {
            "status": "NOT_READY",
            "bias": bias,
            "decision": decision,
            "missing_conditions": missing_conditions,
            "message": message,
        }


def evaluate_entry_readiness(
    mtf_result: dict[str, object],
    decision_result: dict[str, object],
) -> dict[str, object]:
    return EntryReadiness().evaluate(
        mtf_result=mtf_result,
        decision_result=decision_result,
    )
