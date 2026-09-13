"""Backtest de cartera compartida para la candidata intradia v4.

BTC y ETH compiten por una unica entrada. La simulacion conserva un solo saldo
y como maximo una posicion, igual que la restriccion operativa de PROJECT EDGE.
No consulta mercado, no persiste estado y no puede enviar ordenes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from engine.execution.backtest_report import BacktestReport
from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktestResult,
    HistoricalBacktester,
)


@dataclass(frozen=True)
class PortfolioHistoricalConfig:
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    initial_balance: float = 10000.0
    strategy: str = "PROJECT_EDGE_V4_INTRADAY"
    fee_rate: float = 0.001
    slippage_rate: float = 0.0002
    cooldown_minutes: int = 30
    risk_pct: float = 0.005
    max_exposure_pct: float = 1.0
    loss_guard_losses: int = 3
    loss_guard_minutes: int = 240
    analysis_window_bars: int = 500

    def __post_init__(self) -> None:
        normalized = tuple(str(symbol).upper().replace("/", "") for symbol in self.symbols)
        if len(normalized) < 2 or len(set(normalized)) != len(normalized):
            raise ValueError("Se requieren al menos dos simbolos diferentes.")
        if str(self.strategy).upper() not in {
            "PROJECT_EDGE_V4_INTRADAY",
            "PROJECT_EDGE_V5_DUAL_SETUP",
        }:
            raise ValueError("strategy de cartera debe ser v4 o v5.")
        if self.initial_balance <= 0:
            raise ValueError("initial_balance debe ser mayor que cero.")
        if not 0 <= self.fee_rate < 0.1 or not 0 <= self.slippage_rate < 0.1:
            raise ValueError("Los costos configurados son invalidos.")
        if self.cooldown_minutes < 0:
            raise ValueError("cooldown_minutes no puede ser negativo.")
        if not 0 < self.risk_pct <= 0.05:
            raise ValueError("risk_pct debe estar entre 0 y 0.05.")
        if not 0 < self.max_exposure_pct <= 1:
            raise ValueError("max_exposure_pct debe estar entre 0 y 1.")
        if self.loss_guard_losses < 1 or self.loss_guard_minutes < 0:
            raise ValueError("La proteccion por perdidas es invalida.")
        if self.analysis_window_bars < 50:
            raise ValueError("analysis_window_bars debe ser >= 50.")


class PortfolioHistoricalBacktester:
    """Selecciona la mejor senal disponible sin posiciones simultaneas."""

    def __init__(self, config: PortfolioHistoricalConfig | None = None) -> None:
        self.config = config or PortfolioHistoricalConfig()
        self.symbols = tuple(
            str(symbol).upper().replace("/", "")
            for symbol in self.config.symbols
        )
        self.backtesters = {
            symbol: HistoricalBacktester(
                HistoricalBacktestConfig(
                    symbol=symbol,
                    initial_balance=self.config.initial_balance,
                    fee_rate=self.config.fee_rate,
                    slippage_rate=self.config.slippage_rate,
                    cooldown_minutes=self.config.cooldown_minutes,
                    strategy=self.config.strategy,
                    risk_pct=self.config.risk_pct,
                    max_exposure_pct=self.config.max_exposure_pct,
                    loss_guard_losses=self.config.loss_guard_losses,
                    loss_guard_minutes=self.config.loss_guard_minutes,
                    analysis_window_bars=self.config.analysis_window_bars,
                )
            )
            for symbol in self.symbols
        }

    @staticmethod
    def _normalize_timeline(
        timeline: pd.DataFrame,
        evaluation_start: Any | None,
    ) -> pd.DataFrame:
        required = {"open_time", "close_time", "open", "high", "low", "close"}
        required.update(
            f"state_{timeframe}"
            for timeframe in HistoricalBacktester.REQUIRED_TIMEFRAMES
        )
        missing = required.difference(timeline.columns)
        if missing:
            raise ValueError(f"Faltan columnas en el timeline: {sorted(missing)}")
        result = timeline.copy()
        result["open_time"] = pd.to_datetime(result["open_time"], utc=True)
        result["close_time"] = pd.to_datetime(result["close_time"], utc=True)
        result = result.sort_values("close_time").drop_duplicates("close_time")
        if evaluation_start is not None:
            cutoff = pd.Timestamp(evaluation_start)
            cutoff = (
                cutoff.tz_localize("UTC")
                if cutoff.tzinfo is None
                else cutoff.tz_convert("UTC")
            )
            result = result[result["open_time"] >= cutoff]
        return result.reset_index(drop=True)

    def prepare_timelines(
        self,
        timeframe_data: dict[str, dict[str, pd.DataFrame]],
    ) -> dict[str, pd.DataFrame]:
        missing = [symbol for symbol in self.symbols if symbol not in timeframe_data]
        if missing:
            raise ValueError(f"Faltan datos para: {missing}")
        return {
            symbol: self.backtesters[symbol].prepare_timeline(
                timeframe_data[symbol]
            )
            for symbol in self.symbols
        }

    def run_prepared(
        self,
        timelines: dict[str, pd.DataFrame],
        evaluation_start: Any | None = None,
    ) -> HistoricalBacktestResult:
        missing = [symbol for symbol in self.symbols if symbol not in timelines]
        if missing:
            raise ValueError(f"Faltan timelines para: {missing}")
        normalized = {
            symbol: self._normalize_timeline(
                timelines[symbol],
                evaluation_start,
            )
            for symbol in self.symbols
        }
        if any(len(timeline) < 2 for timeline in normalized.values()):
            raise ValueError("Cada simbolo necesita al menos dos velas 5M.")

        common_times = set(normalized[self.symbols[0]]["close_time"])
        for symbol in self.symbols[1:]:
            common_times.intersection_update(normalized[symbol]["close_time"])
        ordered_times = sorted(common_times)
        if len(ordered_times) < 2:
            raise ValueError("Los simbolos no comparten suficientes velas 5M.")
        rows = {
            symbol: timeline.set_index("close_time", drop=False)
            for symbol, timeline in normalized.items()
        }
        positions = {
            symbol: {
                timestamp: index
                for index, timestamp in enumerate(timeline["close_time"])
            }
            for symbol, timeline in normalized.items()
        }

        balance = float(self.config.initial_balance)
        position: dict[str, Any] | None = None
        trades: list[dict[str, Any]] = []
        decision_counts: Counter[str] = Counter()
        signals_by_symbol: Counter[str] = Counter()
        trades_by_symbol: Counter[str] = Counter()
        signals_by_direction: Counter[str] = Counter()
        signals_by_setup: Counter[str] = Counter()
        opportunity_bars = 0
        simultaneous_signal_bars = 0
        cooldown_until: pd.Timestamp | None = None
        loss_guard_until: pd.Timestamp | None = None
        consecutive_losses = 0

        for global_index, timestamp in enumerate(ordered_times):
            if position is not None:
                active_symbol = str(position["symbol"])
                candle = rows[active_symbol].loc[timestamp]
                if timestamp >= pd.Timestamp(position["entry_time"]):
                    hit = self.backtesters[active_symbol]._raw_exit(position, candle)
                    if hit is not None:
                        raw_exit, reason = hit
                        closed = self.backtesters[active_symbol]._close_trade(
                            position,
                            raw_exit_price=raw_exit,
                            reason=reason,
                            exit_index=global_index,
                            exit_time=candle["close_time"],
                        )
                        balance += float(closed["pnl"])
                        closed["balance"] = balance
                        trades.append(closed)
                        trades_by_symbol[active_symbol] += 1
                        position = None
                        cooldown_until = timestamp + pd.Timedelta(
                            minutes=self.config.cooldown_minutes
                        )
                        if float(closed["pnl"]) < 0:
                            consecutive_losses += 1
                        else:
                            consecutive_losses = 0
                        if consecutive_losses >= self.config.loss_guard_losses:
                            loss_guard_until = timestamp + pd.Timedelta(
                                minutes=self.config.loss_guard_minutes
                            )
                            consecutive_losses = 0

            if position is not None or global_index + 1 >= len(ordered_times):
                continue
            if loss_guard_until is not None and timestamp < loss_guard_until:
                decision_counts["LOSS_GUARD"] += 1
                continue
            if cooldown_until is not None and timestamp < cooldown_until:
                decision_counts["COOLDOWN"] += 1
                continue

            candidates: list[tuple[float, str, dict[str, Any]]] = []
            for symbol in self.symbols:
                decision = self.backtesters[symbol]._decision_for_row(
                    rows[symbol].loc[timestamp]
                )
                name = str(decision.get("decision", "WAIT"))
                decision_counts[f"{symbol}:{name}"] += 1
                direction = decision.get("direction")
                if (
                    name in {"READY_LONG", "READY_SHORT"}
                    and direction in {"LONG", "SHORT"}
                    and bool(decision.get("can_execute"))
                ):
                    signals_by_symbol[symbol] += 1
                    signals_by_direction[str(direction)] += 1
                    signals_by_setup[str(decision.get("setup_type") or "UNSPECIFIED")] += 1
                    candidates.append(
                        (float(decision.get("quality_score", 0.0)), symbol, decision)
                    )
            if not candidates:
                continue
            opportunity_bars += 1
            if len(candidates) > 1:
                simultaneous_signal_bars += 1
            _, symbol, decision = max(candidates, key=lambda item: (item[0], item[1]))
            symbol_position = positions[symbol].get(timestamp)
            if symbol_position is None or symbol_position + 1 >= len(normalized[symbol]):
                decision_counts["NO_NEXT_CANDLE"] += 1
                continue
            entry_candle = normalized[symbol].iloc[symbol_position + 1]
            direction = str(decision["direction"])
            backtester = self.backtesters[symbol]
            raw_entry = float(entry_candle["open"])
            entry_price = backtester._entry_price(raw_entry, direction)
            plan = backtester.selected_strategy.build_trade_plan(
                decision=decision,
                entry_price=entry_price,
                account_equity=balance,
            )
            if not plan.get("approved"):
                decision_counts["RISK_REJECTED"] += 1
                continue
            quantity = float(plan["quantity"])
            entry_fee = entry_price * quantity * self.config.fee_rate
            diagnostics = decision.get("diagnostics")
            if not isinstance(diagnostics, dict):
                diagnostics = {}
            position = {
                "symbol": symbol,
                "source": "AUTO",
                "mode": "PAPER_BACKTEST",
                "direction": direction,
                "opened": True,
                "status": "OPEN",
                "signal_index": global_index,
                "signal_time": timestamp.isoformat(),
                "entry_index": global_index + 1,
                "entry_time": pd.Timestamp(entry_candle["open_time"]).isoformat(),
                "entry_price": entry_price,
                "stop_price": float(plan["stop_price"]),
                "target_price": float(plan["target_price"]),
                "position_size": quantity,
                "entry_fee": entry_fee,
                "strategy": str(decision.get("strategy", self.config.strategy)),
                "setup_type": decision.get("setup_type"),
                "quality_score": float(decision.get("quality_score", 0.0)),
                "risk_budget": float(plan["risk_budget"]),
                "estimated_risk": float(plan["estimated_risk"]),
                "estimated_net_reward_risk": float(
                    plan["estimated_net_reward_risk"]
                ),
                "leverage": 1,
                "stop_distance_pct": float(plan["stop_distance"] / entry_price),
                "target_distance_pct": float(plan["target_distance"] / entry_price),
                "exposure_pct": float(plan["exposure"] / balance),
                "estimated_cost_risk_ratio": float(
                    plan["estimated_cost"] / plan["risk_budget"]
                ),
                **{
                    f"diag_{field}": diagnostics.get(field)
                    for field in backtester.selected_strategy.DIAGNOSTIC_FIELDS
                },
                "real_order_sent": False,
            }

        if position is not None:
            symbol = str(position["symbol"])
            last_time = ordered_times[-1]
            candle = rows[symbol].loc[last_time]
            closed = self.backtesters[symbol]._close_trade(
                position,
                raw_exit_price=float(candle["close"]),
                reason="END_OF_DATA",
                exit_index=len(ordered_times) - 1,
                exit_time=candle["close_time"],
            )
            balance += float(closed["pnl"])
            closed["balance"] = balance
            trades.append(closed)
            trades_by_symbol[symbol] += 1

        trades_by_direction = Counter(
            str(trade.get("direction", "UNKNOWN")) for trade in trades
        )
        trades_by_setup = Counter(
            str(trade.get("setup_type") or "UNSPECIFIED") for trade in trades
        )
        metrics = BacktestReport().generate(trades=trades)
        strategy_name = str(self.config.strategy).upper()
        candidate = (
            "V5_PORTFOLIO_BTC_ETH"
            if strategy_name == "PROJECT_EDGE_V5_DUAL_SETUP"
            else "V4_PORTFOLIO_BTC_ETH"
        )
        report = {
            "candidate": candidate,
            "strategy": strategy_name,
            "symbols": list(self.symbols),
            "mode": "PAPER_BACKTEST",
            "source": "AUTO_ONLY",
            "manual_trades_included": False,
            "shared_balance": True,
            "one_position_at_a_time": True,
            "real_orders": False,
            "start_time": ordered_times[0].isoformat(),
            "end_time": ordered_times[-1].isoformat(),
            "five_minute_candles": len(ordered_times),
            "opportunity_bars": opportunity_bars,
            "simultaneous_signal_bars": simultaneous_signal_bars,
            "ready_signals_by_symbol": dict(signals_by_symbol),
            "ready_signals_by_direction": dict(signals_by_direction),
            "ready_signals_by_setup": dict(signals_by_setup),
            "trades_by_symbol": dict(trades_by_symbol),
            "trades_by_direction": dict(trades_by_direction),
            "trades_by_setup": dict(trades_by_setup),
            "decision_counts": dict(decision_counts),
            "initial_balance": self.config.initial_balance,
            "final_balance": balance,
            "return_pct": balance / self.config.initial_balance - 1.0,
            "max_drawdown_pct": HistoricalBacktester._max_drawdown_pct(
                trades,
                self.config.initial_balance,
            ),
            "total_fees": sum(float(trade["fees"]) for trade in trades),
            "config": asdict(self.config),
            **metrics,
        }
        return HistoricalBacktestResult(report=report, trades=trades)

    def run(
        self,
        timeframe_data: dict[str, dict[str, pd.DataFrame]],
        evaluation_start: Any | None = None,
    ) -> HistoricalBacktestResult:
        return self.run_prepared(
            self.prepare_timelines(timeframe_data),
            evaluation_start=evaluation_start,
        )
