"""Adaptadores de backtest exclusivos para PROJECT EDGE v6-SCALP.

No modifica el backtester historico compartido ni el runner AUTO vigente.
Reutiliza su simulacion de costos, riesgo y causalidad, pero inyecta la
estrategia v6 y agrega una salida temporal maxima de cuatro horas.

Este modulo solo simula PAPER. No consulta claves privadas ni envia ordenes.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from engine.decision.project_edge_v6 import ProjectEdgeV6, ProjectEdgeV6Config
from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktestResult,
    HistoricalBacktester,
)
from engine.execution.portfolio_historical_backtest import (
    PortfolioHistoricalBacktester,
    PortfolioHistoricalConfig,
)


V6_STRATEGY = "PROJECT_EDGE_V6_SCALP"


class V6HistoricalBacktester(HistoricalBacktester):
    """Backtester individual v6 sin tocar HistoricalBacktester compartido."""

    def __init__(
        self,
        symbol: str,
        *,
        initial_balance: float = 10000.0,
        fee_rate: float = 0.001,
        slippage_rate: float = 0.0002,
        cooldown_minutes: int = 15,
        risk_pct: float = 0.003,
        max_exposure_pct: float = 1.0,
        loss_guard_losses: int = 3,
        loss_guard_minutes: int = 180,
        analysis_window_bars: int = 500,
        max_holding_minutes: int = 240,
    ) -> None:
        if not 30 <= int(max_holding_minutes) <= 360:
            raise ValueError("max_holding_minutes debe estar entre 30 y 360.")

        # Se usa el identificador v3 solo internamente para reutilizar la ruta
        # historica de features y position sizing. La estrategia seleccionada
        # se reemplaza inmediatamente por ProjectEdgeV6.
        super().__init__(
            HistoricalBacktestConfig(
                symbol=symbol,
                initial_balance=initial_balance,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                cooldown_minutes=cooldown_minutes,
                strategy="PROJECT_EDGE_V3",
                risk_pct=risk_pct,
                max_exposure_pct=max_exposure_pct,
                loss_guard_losses=loss_guard_losses,
                loss_guard_minutes=loss_guard_minutes,
                analysis_window_bars=analysis_window_bars,
            )
        )
        self.selected_strategy = ProjectEdgeV6(
            ProjectEdgeV6Config(
                risk_pct=risk_pct,
                max_exposure_pct=max_exposure_pct,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                cooldown_minutes=cooldown_minutes,
                loss_guard_losses=loss_guard_losses,
                loss_guard_minutes=loss_guard_minutes,
            )
        )
        self.max_holding_minutes = int(max_holding_minutes)

    def _decision_for_row(self, row: pd.Series) -> dict[str, Any]:
        decision = dict(self.selected_strategy.decide_snapshot(row))
        if decision.get("strategy") == V6_STRATEGY:
            # HistoricalBacktester usa este valor para entrar por su rama de
            # gestion de riesgo. El resultado final se vuelve a etiquetar v6.
            decision["candidate_strategy"] = V6_STRATEGY
            decision["strategy"] = "PROJECT_EDGE_V3"
        return decision

    def _raw_exit(
        self,
        position: dict[str, Any],
        candle: pd.Series,
    ) -> tuple[float, str] | None:
        hit = HistoricalBacktester._raw_exit(position, candle)
        if hit is not None:
            return hit

        entry_time = pd.Timestamp(position["entry_time"])
        current_close = pd.Timestamp(candle["close_time"])
        holding_minutes = (
            current_close - entry_time
        ).total_seconds() / 60.0
        if holding_minutes >= self.max_holding_minutes:
            return float(candle["close"]), "TIME_EXIT"
        return None

    def run_prepared(
        self,
        timeline: pd.DataFrame,
        evaluation_start: Any | None = None,
    ) -> HistoricalBacktestResult:
        result = super().run_prepared(
            timeline,
            evaluation_start=evaluation_start,
        )
        for trade in result.trades:
            trade["strategy"] = V6_STRATEGY
            trade["setup_type"] = trade.get("diag_setup_type")

        counts = Counter(
            str(trade.get("direction", "UNKNOWN")) for trade in result.trades
        )
        setups = Counter(
            str(trade.get("setup_type") or "UNSPECIFIED")
            for trade in result.trades
        )
        ready = result.report.get("decision_counts", {})
        result.report.update(
            {
                "candidate": "V6_SINGLE_SYMBOL",
                "strategy": V6_STRATEGY,
                "max_holding_minutes": self.max_holding_minutes,
                "real_orders": False,
                "trades_by_direction": dict(counts),
                "trades_by_setup": dict(setups),
                "ready_signals_by_direction": {
                    "LONG": int(ready.get("READY_LONG", 0)),
                    "SHORT": int(ready.get("READY_SHORT", 0)),
                },
            }
        )
        if isinstance(result.report.get("config"), dict):
            result.report["config"]["strategy"] = V6_STRATEGY
            result.report["config"]["max_holding_minutes"] = (
                self.max_holding_minutes
            )
        return result


class V6PortfolioHistoricalBacktester(PortfolioHistoricalBacktester):
    """BTC y ETH compiten por una sola posicion usando v6-SCALP."""

    def __init__(
        self,
        *,
        symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
        initial_balance: float = 10000.0,
        fee_rate: float = 0.001,
        slippage_rate: float = 0.0002,
        cooldown_minutes: int = 15,
        risk_pct: float = 0.003,
        max_exposure_pct: float = 1.0,
        loss_guard_losses: int = 3,
        loss_guard_minutes: int = 180,
        analysis_window_bars: int = 500,
        max_holding_minutes: int = 240,
    ) -> None:
        super().__init__(
            PortfolioHistoricalConfig(
                symbols=symbols,
                initial_balance=initial_balance,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                cooldown_minutes=cooldown_minutes,
                risk_pct=risk_pct,
                max_exposure_pct=max_exposure_pct,
                loss_guard_losses=loss_guard_losses,
                loss_guard_minutes=loss_guard_minutes,
                analysis_window_bars=analysis_window_bars,
            )
        )
        self.backtesters = {
            symbol: V6HistoricalBacktester(
                symbol,
                initial_balance=initial_balance,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                cooldown_minutes=cooldown_minutes,
                risk_pct=risk_pct,
                max_exposure_pct=max_exposure_pct,
                loss_guard_losses=loss_guard_losses,
                loss_guard_minutes=loss_guard_minutes,
                analysis_window_bars=analysis_window_bars,
                max_holding_minutes=max_holding_minutes,
            )
            for symbol in self.symbols
        }
        self.max_holding_minutes = int(max_holding_minutes)

    def run_prepared(
        self,
        timelines: dict[str, pd.DataFrame],
        evaluation_start: Any | None = None,
    ) -> HistoricalBacktestResult:
        result = super().run_prepared(
            timelines,
            evaluation_start=evaluation_start,
        )
        for trade in result.trades:
            trade["strategy"] = V6_STRATEGY
            trade["setup_type"] = trade.get("diag_setup_type")

        direction_counts = Counter(
            str(trade.get("direction", "UNKNOWN")) for trade in result.trades
        )
        setup_counts = Counter(
            str(trade.get("setup_type") or "UNSPECIFIED")
            for trade in result.trades
        )

        decision_counts = result.report.get("decision_counts", {})
        ready_by_direction = {"LONG": 0, "SHORT": 0}
        for key, value in decision_counts.items():
            if str(key).endswith(":READY_LONG"):
                ready_by_direction["LONG"] += int(value)
            elif str(key).endswith(":READY_SHORT"):
                ready_by_direction["SHORT"] += int(value)

        result.report.update(
            {
                "candidate": "V6_PORTFOLIO_BTC_ETH",
                "strategy": V6_STRATEGY,
                "max_holding_minutes": self.max_holding_minutes,
                "real_orders": False,
                "trades_by_direction": dict(direction_counts),
                "trades_by_setup": dict(setup_counts),
                "ready_signals_by_direction": ready_by_direction,
            }
        )
        return result
