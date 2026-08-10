"""
PROJECT EDGE
Structure Engine — Integration Pipeline v1

Integra los módulos estructurales en una sola cadena:
OHLC -> swings -> HH/HL/LH/LL -> estado de mercado ->
impulso/corrección -> soportes/resistencias -> BOS/CHoCH.

No ejecuta órdenes ni genera señales LONG/SHORT.
"""

from __future__ import annotations

import pandas as pd

from engine.structure.swing_detector import SwingDetector
from engine.structure.structure_classifier import StructureClassifier
from engine.structure.market_structure import MarketStructureInterpreter
from engine.structure.impulse_correction import ImpulseCorrectionClassifier
from engine.structure.support_resistance import StructuralLevels
from engine.structure.break_of_structure import BreakOfStructureDetector


class StructureEngine:
    """Pipeline integrado del motor de estructura de PROJECT EDGE."""

    def __init__(
        self,
        pivot_left: int = 2,
        pivot_right: int = 2,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        min_move_pct: float = 0.0025,
        max_move_pct: float = 0.05,
    ) -> None:
        self.swing_detector = SwingDetector(
            pivot_left=pivot_left,
            pivot_right=pivot_right,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            min_move_pct=min_move_pct,
            max_move_pct=max_move_pct,
        )
        self.structure_classifier = StructureClassifier()
        self.market_interpreter = MarketStructureInterpreter()
        self.impulse_classifier = ImpulseCorrectionClassifier()
        self.structural_levels = StructuralLevels()
        self.break_detector = BreakOfStructureDetector()

    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ejecuta toda la cadena estructural en orden."""
        data = self.swing_detector.detect(df)
        data = self.structure_classifier.classify(data)
        data = self.market_interpreter.interpret(data)
        data = self.impulse_classifier.classify(data)
        data = self.structural_levels.calculate(data)
        data = self.break_detector.detect(data)
        return data


def analyze_structure(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Atajo para ejecutar el Structure Engine completo."""
    return StructureEngine(**kwargs).analyze(df)
