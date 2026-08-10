"""
PROJECT EDGE
Backtest Orchestrator v1

Integra:
Multi-Timeframe Structure Engine
-> Decision Engine
-> Risk Engine
-> Trade Gate
-> Paper Trading
-> Trade Manager / Backtest Engine

IMPORTANTE:
Este v1 trabaja con escenarios históricos ya sincronizados.
Cada escenario debe incluir:
- datos OHLC de 4H, 1H, 30M, 15M y 5M
- precio de entrada
- stop
- objetivo
- velas futuras para gestionar la salida

NO conecta con Binance y NO ejecuta órdenes reales.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)
from engine.execution.trade_gate import TradeGate
from engine.execution.paper_trading import PaperTradingEngine
from engine.execution.backtest_engine import BacktestEngine


@dataclass
class OrchestratorResult:
    trades: list[dict[str, object]] = field(default_factory=list)
    rejected: int = 0
    no_trade: int = 0

    def summary(self) -> dict[str, object]:
        engine = BacktestEngine()
        metrics = engine.summarize_trades(self.trades)

        return {
            **metrics,
            "rejected": self.rejected,
            "no_trade": self.no_trade,
        }


class BacktestOrchestrator:
    """Integra toda la cadena de análisis y simulación."""

    def __init__(
        self,
        account_equity: float,
        max_risk_pct: float = 0.01,
        min_rr: float = 1.5,
        structure_engine_kwargs: dict | None = None,
    ) -> None:
        if account_equity <= 0:
            raise ValueError("account_equity debe ser mayor que cero.")

        self.account_equity = float(account_equity)

        self.mtf_engine = MultiTimeframeStructureEngine(
            structure_engine_kwargs=structure_engine_kwargs or {}
        )
        self.trade_gate = TradeGate(
            max_risk_pct=max_risk_pct,
            min_rr=min_rr,
        )
        self.paper = PaperTradingEngine()
        self.backtest = BacktestEngine()

    def run_case(
        self,
        timeframe_data: dict[str, pd.DataFrame],
        entry_price: float,
        stop_price: float,
        target_price: float,
        future_candles: pd.DataFrame,
    ) -> dict[str, object]:
        mtf_result = self.mtf_engine.analyze(timeframe_data)

        gate_result = self.trade_gate.evaluate(
            mtf_result=mtf_result,
            account_equity=self.account_equity,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )

        if not gate_result["demo_authorized"]:
            return {
                "executed": False,
                "trade_status": gate_result["trade_status"],
                "gate": gate_result,
                "mtf": mtf_result,
            }

        trade = self.paper.open_trade(
            gate_result=gate_result,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )

        closed_or_open = self.backtest.run_trade(
            trade=trade,
            candles=future_candles,
            start_index=0,
        )

        return {
            "executed": True,
            "trade_status": closed_or_open["status"],
            "trade": closed_or_open,
            "gate": gate_result,
            "mtf": mtf_result,
        }

    def summarize_cases(
        self,
        cases: list[dict[str, object]],
    ) -> dict[str, object]:
        result = OrchestratorResult()

        for case in cases:
            case_result = self.run_case(**case)

            if not case_result["executed"]:
                status = case_result["trade_status"]

                if status == "RISK_REJECTED":
                    result.rejected += 1
                else:
                    result.no_trade += 1

                continue

            trade = case_result["trade"]

            if trade.get("status") == "CLOSED":
                result.trades.append(trade)

        return result.summary()
