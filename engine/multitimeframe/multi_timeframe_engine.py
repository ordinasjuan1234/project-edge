"""
PROJECT EDGE
Multi-Timeframe Engine v1

Combina estados estructurales de varias temporalidades sin ejecutar órdenes.

Jerarquía inicial:
4H  -> tendencia principal
1H  -> contexto/fase
30m -> estructura intermedia
15m -> corrección/zona
5m  -> confirmación

La salida distingue alineación, conflicto y transición.
"""

from __future__ import annotations

from dataclasses import dataclass


VALID_STATES = {"BULLISH", "BEARISH", "TRANSITION", "UNDEFINED"}


@dataclass(frozen=True)
class TimeframeState:
    timeframe: str
    market_structure: str

    def normalized(self) -> str:
        state = str(self.market_structure).upper()
        if state not in VALID_STATES:
            raise ValueError(
                f"Estado inválido para {self.timeframe}: {self.market_structure}"
            )
        return state


class MultiTimeframeEngine:
    """Evalúa coherencia estructural entre temporalidades."""

    REQUIRED_TIMEFRAMES = ("4H", "1H", "30M", "15M", "5M")

    def analyze(self, states: dict[str, str]) -> dict[str, object]:
        normalized = {
            str(tf).upper(): str(state).upper()
            for tf, state in states.items()
        }

        missing = [
            tf for tf in self.REQUIRED_TIMEFRAMES
            if tf not in normalized
        ]
        if missing:
            raise ValueError(f"Faltan temporalidades requeridas: {missing}")

        for tf in self.REQUIRED_TIMEFRAMES:
            if normalized[tf] not in VALID_STATES:
                raise ValueError(
                    f"Estado inválido para {tf}: {normalized[tf]}"
                )

        macro = normalized["4H"]
        context = normalized["1H"]
        intermediate = normalized["30M"]
        zone = normalized["15M"]
        trigger = normalized["5M"]

        directional = {"BULLISH", "BEARISH"}

        if macro not in directional:
            alignment = "NO_DIRECTION"
        elif context == macro and intermediate == macro:
            if zone == macro and trigger == macro:
                alignment = "FULL_ALIGNMENT"
            elif zone != macro or trigger != macro:
                alignment = "PULLBACK_OR_WAIT"
            else:
                alignment = "PARTIAL_ALIGNMENT"
        elif context in directional and context != macro:
            alignment = "MACRO_CONTEXT_CONFLICT"
        elif intermediate in directional and intermediate != macro:
            alignment = "INTERMEDIATE_CONFLICT"
        else:
            alignment = "PARTIAL_ALIGNMENT"

        entry_ready = (
            alignment == "FULL_ALIGNMENT"
            and macro in directional
        )

        return {
            "macro_4h": macro,
            "context_1h": context,
            "structure_30m": intermediate,
            "zone_15m": zone,
            "confirmation_5m": trigger,
            "alignment": alignment,
            "entry_ready": entry_ready,
        }


def analyze_timeframes(states: dict[str, str]) -> dict[str, object]:
    return MultiTimeframeEngine().analyze(states)
