"""
PROJECT EDGE
Decision Engine v2 - FVG confirmation

Convierte la lectura multitemporal en un estado operativo.
El FVG se usa SOLO como confirmacion adicional cuando la
estructura ya esta completamente alineada.

Regla FVG:
- LONG: FVG BULLISH activo/parcial en 15M o 5M.
- SHORT: FVG BEARISH activo/parcial en 15M o 5M.
- El FVG debe estar a una distancia maxima configurable.
- El FVG nunca genera una entrada por si solo.

NO ejecuta ordenes ni conecta con un broker.
"""

from __future__ import annotations

import math


class DecisionEngine:
    """Decide si esperar, vigilar, preparar o habilitar una operacion PAPER."""

    VALID_STATES = {"BULLISH", "BEARISH", "TRANSITION", "UNDEFINED"}
    FVG_TIMEFRAMES = ("15M", "5M")

    def __init__(self, fvg_max_distance_pct: float = 0.015) -> None:
        if fvg_max_distance_pct < 0:
            raise ValueError("fvg_max_distance_pct no puede ser negativo.")
        self.fvg_max_distance_pct = float(fvg_max_distance_pct)

    @staticmethod
    def _clean(value):
        if value is None:
            return None

        try:
            if math.isnan(value):
                return None
        except (TypeError, ValueError):
            pass

        if hasattr(value, "item"):
            value = value.item()

        return value

    def _latest_fvg(self, analysis):
        if analysis is None:
            return None

        if getattr(analysis, "empty", True):
            return None

        row = analysis.iloc[-1]

        fvg_type = self._clean(row.get("active_fvg_type"))
        state = self._clean(row.get("active_fvg_state"))
        distance = self._clean(row.get("active_fvg_distance_pct"))

        if fvg_type is None or state is None:
            return None

        return {
            "type": str(fvg_type).upper(),
            "state": str(state).upper(),
            "distance_pct": (
                float(distance)
                if distance is not None
                else None
            ),
        }

    def _evaluate_fvg_confirmation(
        self,
        mtf_result: dict[str, object],
        direction: str,
    ) -> dict[str, object]:
        analyses = mtf_result.get("analyses")

        # Compatibilidad con tests/consumidores antiguos que solo entregan states.
        if not isinstance(analyses, dict):
            return {
                "required": False,
                "confirmed": None,
                "expected_type": None,
                "timeframes": [],
            }

        expected_type = "BULLISH" if direction == "LONG" else "BEARISH"
        confirmed_timeframes: list[str] = []

        for timeframe in self.FVG_TIMEFRAMES:
            zone = self._latest_fvg(analyses.get(timeframe))
            if zone is None:
                continue

            if zone["type"] != expected_type:
                continue

            if zone["state"] not in {"ACTIVE", "PARTIAL"}:
                continue

            distance = zone["distance_pct"]
            if distance is None or distance > self.fvg_max_distance_pct:
                continue

            confirmed_timeframes.append(timeframe)

        return {
            "required": True,
            "confirmed": bool(confirmed_timeframes),
            "expected_type": expected_type,
            "timeframes": confirmed_timeframes,
        }

    def decide(self, mtf_result: dict[str, object]) -> dict[str, object]:
        if "states" not in mtf_result or "alignment" not in mtf_result:
            raise ValueError(
                "Faltan 'states' o 'alignment' en el resultado multitemporal."
            )

        states = mtf_result["states"]
        alignment_data = mtf_result["alignment"]

        if not isinstance(states, dict) or not isinstance(alignment_data, dict):
            raise ValueError("'states' y 'alignment' deben ser diccionarios.")

        required = ("4H", "1H", "30M", "15M", "5M")
        missing = [tf for tf in required if tf not in states]
        if missing:
            raise ValueError(f"Faltan temporalidades requeridas: {missing}")

        normalized = {
            tf: str(states[tf]).upper()
            for tf in required
        }

        for tf, state in normalized.items():
            if state not in self.VALID_STATES:
                raise ValueError(f"Estado invalido para {tf}: {state}")

        alignment = str(
            alignment_data.get("alignment", "")
        ).upper()

        macro = normalized["4H"]
        lower = (
            normalized["15M"],
            normalized["5M"],
        )

        decision = "WAIT"
        direction = None
        reason = "Sin alineacion suficiente."
        can_execute = False

        fvg_required = False
        fvg_confirmed = None
        fvg_expected_type = None
        fvg_timeframes: list[str] = []

        if alignment in {
            "MACRO_CONTEXT_CONFLICT",
            "INTERMEDIATE_CONFLICT",
        }:
            decision = "BLOCKED"
            reason = "Conflicto entre temporalidades superiores."

        elif macro not in {"BULLISH", "BEARISH"}:
            decision = "WAIT"
            reason = (
                "La temporalidad 4H no tiene direccion "
                "estructural definida."
            )

        elif alignment == "FULL_ALIGNMENT":
            direction = "LONG" if macro == "BULLISH" else "SHORT"

            fvg = self._evaluate_fvg_confirmation(
                mtf_result,
                direction,
            )

            fvg_required = bool(fvg["required"])
            fvg_confirmed = fvg["confirmed"]
            fvg_expected_type = fvg["expected_type"]
            fvg_timeframes = list(fvg["timeframes"])

            if not fvg_required:
                # Mantiene compatibilidad cuando no se entregan analyses.
                decision = f"READY_{direction}"
                reason = "Todas las temporalidades estan alineadas."
                can_execute = False

            elif fvg_confirmed:
                decision = f"READY_{direction}"
                can_execute = True
                frames = " / ".join(fvg_timeframes)
                reason = (
                    "Estructura completamente alineada y FVG "
                    f"{fvg_expected_type} confirmado en {frames}."
                )

            else:
                decision = f"WATCH_{direction}"
                can_execute = False
                reason = (
                    "La estructura esta alineada, pero falta un FVG "
                    f"{fvg_expected_type} cercano en 15M o 5M."
                )

        elif alignment == "PULLBACK_OR_WAIT":
            direction = "LONG" if macro == "BULLISH" else "SHORT"
            decision = f"WATCH_{direction}"

            if all(state == macro for state in lower):
                reason = (
                    "La direccion macro sigue vigente y las "
                    "temporalidades bajas se realinean."
                )
            else:
                reason = (
                    "Hay direccion macro, pero falta confirmacion "
                    "completa en temporalidades bajas."
                )

        else:
            direction = "LONG" if macro == "BULLISH" else "SHORT"
            decision = f"WATCH_{direction}"
            reason = (
                "Existe sesgo macro, pero la alineacion "
                "todavia es parcial."
            )

        return {
            "decision": decision,
            "direction": direction,
            "alignment": alignment,
            "reason": reason,
            "can_execute": can_execute,
            "fvg_required": fvg_required,
            "fvg_confirmed": fvg_confirmed,
            "fvg_expected_type": fvg_expected_type,
            "fvg_timeframes": fvg_timeframes,
            "fvg_max_distance_pct": self.fvg_max_distance_pct,
        }


def make_decision(
    mtf_result: dict[str, object],
) -> dict[str, object]:
    return DecisionEngine().decide(mtf_result)
