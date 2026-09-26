"""
PROJECT EDGE
Historical Backtest v1

Backtest walk-forward del motor estructural multitemporal.

Principios:
- usa únicamente velas cerradas;
- una señal conocida al cierre entra en la apertura 5M siguiente;
- los swings se vuelven visibles recién en su índice de confirmación;
- si STOP y TARGET aparecen en la misma vela, se asume STOP primero;
- incluye comisión y deslizamiento configurables;
- simula exclusivamente operaciones AUTO PAPER.

No usa API privada, no consulta saldos y no ejecuta órdenes reales.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from engine.decision.decision_engine import DecisionEngine
from engine.decision.project_edge_v3 import (
    ProjectEdgeV3,
    ProjectEdgeV3Config,
)
from engine.decision.project_edge_v4 import (
    ProjectEdgeV4,
    ProjectEdgeV4Config,
)
from engine.decision.project_edge_v5 import (
    ProjectEdgeV5,
    ProjectEdgeV5Config,
)
from engine.execution.backtest_report import BacktestReport
from engine.multitimeframe.multi_timeframe_engine import MultiTimeframeEngine
from engine.structure.structure_engine import StructureEngine


@dataclass(frozen=True)
class HistoricalBacktestConfig:
    symbol: str
    initial_balance: float = 10000.0
    stop_pct: float = 0.005
    target_pct: float = 0.01
    fee_rate: float = 0.001
    slippage_rate: float = 0.0002
    cooldown_minutes: int = 30
    strategy: str = "PROJECT_EDGE_V3"
    risk_pct: float = 0.005
    max_exposure_pct: float = 1.0
    loss_guard_losses: int = 3
    loss_guard_minutes: int = 240
    analysis_window_bars: int = 500

    def __post_init__(self) -> None:
        if not str(self.symbol).strip():
            raise ValueError("symbol no puede estar vacío.")
        if self.initial_balance <= 0:
            raise ValueError("initial_balance debe ser mayor que cero.")
        if not 0 < self.stop_pct < 1:
            raise ValueError("stop_pct debe estar entre 0 y 1.")
        if not 0 < self.target_pct < 1:
            raise ValueError("target_pct debe estar entre 0 y 1.")
        if not 0 <= self.fee_rate < 0.1:
            raise ValueError("fee_rate debe estar entre 0 y 0.1.")
        if not 0 <= self.slippage_rate < 0.1:
            raise ValueError("slippage_rate debe estar entre 0 y 0.1.")
        if self.cooldown_minutes < 0:
            raise ValueError("cooldown_minutes no puede ser negativo.")
        if str(self.strategy).upper() not in {
            "PROJECT_EDGE_V2",
            "PROJECT_EDGE_V3",
            "PROJECT_EDGE_V4_INTRADAY",
            "PROJECT_EDGE_V5_DUAL_SETUP",
        }:
            raise ValueError(
                "strategy debe ser PROJECT_EDGE_V2, PROJECT_EDGE_V3, "
                "PROJECT_EDGE_V4_INTRADAY o PROJECT_EDGE_V5_DUAL_SETUP."
            )
        if not 0 < self.risk_pct <= 0.05:
            raise ValueError("risk_pct debe estar entre 0 y 0.05.")
        if not 0 < self.max_exposure_pct <= 1:
            raise ValueError("max_exposure_pct debe estar entre 0 y 1.")
        if self.loss_guard_losses < 1 or self.loss_guard_minutes < 0:
            raise ValueError("La proteccion por perdidas es invalida.")
        if self.analysis_window_bars < 50:
            raise ValueError("analysis_window_bars debe ser >= 50.")


@dataclass
class HistoricalBacktestResult:
    report: dict[str, Any]
    trades: list[dict[str, Any]]


class HistoricalBacktester:
    REQUIRED_TIMEFRAMES = ("4H", "1H", "30M", "15M", "5M")
    FVG_FIELDS = (
        "active_fvg_type",
        "active_fvg_state",
        "active_fvg_distance_pct",
    )

    DEFAULT_STRUCTURE_KWARGS = {
        "pivot_left": 2,
        "pivot_right": 2,
        "atr_period": 14,
        "atr_multiplier": 1.5,
        "min_move_pct": 0.0025,
        "max_move_pct": 0.05,
    }

    def __init__(
        self,
        config: HistoricalBacktestConfig,
        structure_engine_kwargs: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.structure_engine_kwargs = {
            **self.DEFAULT_STRUCTURE_KWARGS,
            **(structure_engine_kwargs or {}),
        }
        self.decision_engine = DecisionEngine()
        self.mtf_engine = MultiTimeframeEngine()
        self.strategy_v3 = ProjectEdgeV3(
            ProjectEdgeV3Config(
                risk_pct=config.risk_pct,
                max_exposure_pct=config.max_exposure_pct,
                fee_rate=config.fee_rate,
                slippage_rate=config.slippage_rate,
                cooldown_minutes=config.cooldown_minutes,
                loss_guard_losses=config.loss_guard_losses,
                loss_guard_minutes=config.loss_guard_minutes,
            )
        )
        self.strategy_v4 = ProjectEdgeV4(
            ProjectEdgeV4Config(
                risk_pct=config.risk_pct,
                max_exposure_pct=config.max_exposure_pct,
                fee_rate=config.fee_rate,
                slippage_rate=config.slippage_rate,
                cooldown_minutes=config.cooldown_minutes,
                loss_guard_losses=config.loss_guard_losses,
                loss_guard_minutes=config.loss_guard_minutes,
            )
        )
        self.strategy_v5 = ProjectEdgeV5(
            ProjectEdgeV5Config(
                risk_pct=config.risk_pct,
                max_exposure_pct=config.max_exposure_pct,
                fee_rate=config.fee_rate,
                slippage_rate=config.slippage_rate,
                cooldown_minutes=config.cooldown_minutes,
                loss_guard_losses=config.loss_guard_losses,
                loss_guard_minutes=config.loss_guard_minutes,
            )
        )
        strategy_name = str(config.strategy).upper()
        if strategy_name == "PROJECT_EDGE_V5_DUAL_SETUP":
            self.selected_strategy = self.strategy_v5
        elif strategy_name == "PROJECT_EDGE_V4_INTRADAY":
            self.selected_strategy = self.strategy_v4
        else:
            self.selected_strategy = self.strategy_v3

    @staticmethod
    def _state_from_labels(labels: list[tuple[int, str]]) -> str:
        last_high: str | None = None
        last_low: str | None = None
        state = "UNDEFINED"

        for _, label in sorted(labels, key=lambda item: item[0]):
            if label in {"HH", "LH"}:
                last_high = label
            elif label in {"HL", "LL"}:
                last_low = label

            if last_high == "HH" and last_low == "HL":
                state = "BULLISH"
            elif last_high == "LH" and last_low == "LL":
                state = "BEARISH"
            elif last_high is not None and last_low is not None:
                state = "TRANSITION"

        return state

    @classmethod
    def causal_market_states(cls, analysis: pd.DataFrame) -> pd.Series:
        """Reconstruye el estado disponible en cada cierre sin look-ahead."""
        required = {"structure_label", "structure_known_at"}
        missing = required.difference(analysis.columns)
        if missing:
            raise ValueError(
                f"Faltan columnas estructurales: {sorted(missing)}"
            )

        events_by_confirmation: dict[int, list[tuple[int, str]]] = defaultdict(list)

        for pivot_index, row in analysis.iterrows():
            label = row.get("structure_label")
            known_at = row.get("structure_known_at")

            if pd.isna(label) or pd.isna(known_at):
                continue

            confirmation_index = int(known_at)
            if 0 <= confirmation_index < len(analysis):
                events_by_confirmation[confirmation_index].append(
                    (int(pivot_index), str(label).upper())
                )

        visible: list[tuple[int, str]] = []
        current_state = "UNDEFINED"
        states: list[str] = []

        for candle_index in range(len(analysis)):
            new_events = events_by_confirmation.get(candle_index, [])
            if new_events:
                visible.extend(new_events)
                current_state = cls._state_from_labels(visible)
            states.append(current_state)

        return pd.Series(states, index=analysis.index, dtype="object")

    def rolling_causal_market_states(
        self,
        analysis: pd.DataFrame,
    ) -> pd.Series:
        """Replica la ventana estructural finita usada por el bot PAPER.

        El bot en ejecucion analiza las ultimas 500 velas de cada
        temporalidad. El backtest no debe conservar swings anteriores a esa
        ventana porque produciria decisiones que el bot real nunca veria.
        """
        required = {
            "swing_confirmed",
            "swing_type",
            "swing_price",
            "swing_confirmation_index",
        }
        missing = required.difference(analysis.columns)
        if missing:
            raise ValueError(
                f"Faltan columnas de swings: {sorted(missing)}"
            )

        events_by_confirmation: dict[
            int,
            list[tuple[int, str, float]],
        ] = defaultdict(list)
        for pivot_index, row in analysis.iterrows():
            if not bool(row.get("swing_confirmed")):
                continue
            swing_type = str(row.get("swing_type", "")).upper()
            swing_price = row.get("swing_price")
            known_at = row.get("swing_confirmation_index")
            if (
                swing_type not in {"HIGH", "LOW"}
                or pd.isna(swing_price)
                or pd.isna(known_at)
            ):
                continue
            confirmation_index = int(known_at)
            if 0 <= confirmation_index < len(analysis):
                events_by_confirmation[confirmation_index].append(
                    (int(pivot_index), swing_type, float(swing_price))
                )

        lookback = int(self.config.analysis_window_bars)
        candidate_offset = max(
            int(self.structure_engine_kwargs["pivot_left"]),
            int(self.structure_engine_kwargs["atr_period"]) - 1,
        )
        active: list[tuple[int, int, str, float]] = []
        states: list[str] = []

        for candle_index in range(len(analysis)):
            for pivot_index, swing_type, price in sorted(
                events_by_confirmation.get(candle_index, []),
                key=lambda event: event[0],
            ):
                active.append(
                    (candle_index, pivot_index, swing_type, price)
                )

            window_start = max(0, candle_index - lookback + 1)
            earliest_candidate = window_start + candidate_offset
            active = [
                event
                for event in active
                if event[1] >= earliest_candidate
            ]

            previous_high: float | None = None
            previous_low: float | None = None
            labels: list[tuple[int, str]] = []
            for confirmation_index, pivot_index, swing_type, price in active:
                if swing_type == "HIGH":
                    if previous_high is not None:
                        if price > previous_high:
                            labels.append((pivot_index, "HH"))
                        elif price < previous_high:
                            labels.append((pivot_index, "LH"))
                    previous_high = price
                else:
                    if previous_low is not None:
                        if price > previous_low:
                            labels.append((pivot_index, "HL"))
                        elif price < previous_low:
                            labels.append((pivot_index, "LL"))
                    previous_low = price

            states.append(self._state_from_labels(labels))

        return pd.Series(states, index=analysis.index, dtype="object")

    @staticmethod
    def _validate_timeframes(
        timeframe_data: dict[str, pd.DataFrame],
    ) -> dict[str, pd.DataFrame]:
        normalized = {
            str(timeframe).upper(): data.copy()
            for timeframe, data in timeframe_data.items()
        }
        missing = [
            timeframe
            for timeframe in HistoricalBacktester.REQUIRED_TIMEFRAMES
            if timeframe not in normalized
        ]
        if missing:
            raise ValueError(f"Faltan temporalidades requeridas: {missing}")

        for timeframe in HistoricalBacktester.REQUIRED_TIMEFRAMES:
            data = normalized[timeframe]
            if data.empty:
                raise ValueError(f"La temporalidad {timeframe} está vacía.")
            required = {"open_time", "close_time", "open", "high", "low", "close"}
            absent = required.difference(data.columns)
            if absent:
                raise ValueError(
                    f"Faltan columnas en {timeframe}: {sorted(absent)}"
                )
            data["open_time"] = pd.to_datetime(data["open_time"], utc=True)
            data["close_time"] = pd.to_datetime(data["close_time"], utc=True)
            normalized[timeframe] = data.sort_values("open_time").reset_index(drop=True)

        return normalized

    def prepare_timeline(
        self,
        timeframe_data: dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """Precalcula estados causales y los alinea al cierre de cada vela 5M."""
        data = self._validate_timeframes(timeframe_data)
        analyses: dict[str, pd.DataFrame] = {}

        for timeframe in self.REQUIRED_TIMEFRAMES:
            analysis = StructureEngine(
                **self.structure_engine_kwargs
            ).analyze(data[timeframe])
            analysis["causal_market_structure"] = (
                self.rolling_causal_market_states(analysis)
            )
            if str(self.config.strategy).upper() in {
                "PROJECT_EDGE_V3",
                "PROJECT_EDGE_V4_INTRADAY",
                "PROJECT_EDGE_V5_DUAL_SETUP",
            }:
                analysis = self.selected_strategy.add_features(analysis)
            analyses[timeframe] = analysis

        timeline = analyses["5M"][
            ["open_time", "close_time", "open", "high", "low", "close"]
        ].copy()
        timeline = timeline.sort_values("close_time").reset_index(drop=True)

        for timeframe in self.REQUIRED_TIMEFRAMES:
            analysis = analyses[timeframe]
            columns = ["close_time", "causal_market_structure"]

            if str(self.config.strategy).upper() in {
                "PROJECT_EDGE_V3",
                "PROJECT_EDGE_V4_INTRADAY",
                "PROJECT_EDGE_V5_DUAL_SETUP",
            }:
                columns.extend(self.selected_strategy.FEATURE_FIELDS)

            if timeframe in {"15M", "5M"}:
                columns.extend(self.FVG_FIELDS)

            lookup = analysis[columns].copy()
            lookup = lookup.rename(
                columns={
                    "close_time": "available_at",
                    "causal_market_structure": f"state_{timeframe}",
                    **{
                        field: f"{field}_{timeframe}"
                        for field in self.FVG_FIELDS
                    },
                    **{
                        field: f"{field}_{timeframe}"
                        for field in self.selected_strategy.FEATURE_FIELDS
                    },
                }
            ).sort_values("available_at")

            timeline = pd.merge_asof(
                timeline.sort_values("close_time"),
                lookup,
                left_on="close_time",
                right_on="available_at",
                direction="backward",
            ).drop(columns=["available_at"])

        return timeline.reset_index(drop=True)

    def _decision_for_row(self, row: pd.Series) -> dict[str, Any]:
        if str(self.config.strategy).upper() in {
            "PROJECT_EDGE_V3",
            "PROJECT_EDGE_V4_INTRADAY",
            "PROJECT_EDGE_V5_DUAL_SETUP",
        }:
            return self.selected_strategy.decide_snapshot(row)

        states = {
            timeframe: str(row.get(f"state_{timeframe}", "UNDEFINED")).upper()
            for timeframe in self.REQUIRED_TIMEFRAMES
        }

        if any(state == "NAN" for state in states.values()):
            states = {
                timeframe: (
                    "UNDEFINED" if state == "NAN" else state
                )
                for timeframe, state in states.items()
            }

        analyses: dict[str, pd.DataFrame] = {}
        for timeframe in ("15M", "5M"):
            analyses[timeframe] = pd.DataFrame([
                {
                    field: row.get(f"{field}_{timeframe}")
                    for field in self.FVG_FIELDS
                }
            ])

        alignment = self.mtf_engine.analyze(states)
        return self.decision_engine.decide(
            {
                "states": states,
                "alignment": alignment,
                "analyses": analyses,
            }
        )

    def _entry_price(self, raw_price: float, direction: str) -> float:
        if direction == "LONG":
            return raw_price * (1.0 + self.config.slippage_rate)
        return raw_price * (1.0 - self.config.slippage_rate)

    def _exit_price(self, raw_price: float, direction: str) -> float:
        if direction == "LONG":
            return raw_price * (1.0 - self.config.slippage_rate)
        return raw_price * (1.0 + self.config.slippage_rate)

    @staticmethod
    def _raw_exit(
        position: dict[str, Any],
        candle: pd.Series,
    ) -> tuple[float, str] | None:
        direction = position["direction"]
        stop = float(position["stop_price"])
        target = float(position["target_price"])
        candle_open = float(candle["open"])
        candle_high = float(candle["high"])
        candle_low = float(candle["low"])

        if direction == "LONG":
            if candle_open <= stop:
                return candle_open, "STOP_GAP"
            stop_hit = candle_low <= stop
            target_hit = candle_high >= target
        else:
            if candle_open >= stop:
                return candle_open, "STOP_GAP"
            stop_hit = candle_high >= stop
            target_hit = candle_low <= target

        if stop_hit:
            return stop, "STOP"
        if target_hit:
            return target, "TARGET"
        return None

    def _close_trade(
        self,
        position: dict[str, Any],
        raw_exit_price: float,
        reason: str,
        exit_index: int,
        exit_time: Any,
    ) -> dict[str, Any]:
        direction = str(position["direction"])
        exit_price = self._exit_price(float(raw_exit_price), direction)
        entry_price = float(position["entry_price"])
        quantity = float(position["position_size"])

        if direction == "LONG":
            gross_pnl = (exit_price - entry_price) * quantity
        else:
            gross_pnl = (entry_price - exit_price) * quantity

        entry_fee = float(position["entry_fee"])
        exit_fee = exit_price * quantity * self.config.fee_rate
        fees = entry_fee + exit_fee
        net_pnl = gross_pnl - fees

        entry_time = pd.Timestamp(position["entry_time"])
        closed_time = pd.Timestamp(exit_time)
        holding_minutes = (
            closed_time - entry_time
        ).total_seconds() / 60.0

        return {
            **position,
            "opened": False,
            "status": "CLOSED",
            "exit_price": exit_price,
            "exit_index": int(exit_index),
            "exit_time": pd.Timestamp(exit_time).isoformat(),
            "holding_minutes": float(holding_minutes),
            "close_reason": reason,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "pnl": net_pnl,
            "real_order_sent": False,
        }

    @staticmethod
    def _max_drawdown_pct(
        trades: list[dict[str, Any]],
        initial_balance: float,
    ) -> float:
        equity = float(initial_balance)
        peak = equity
        maximum = 0.0

        for trade in trades:
            equity += float(trade["pnl"])
            peak = max(peak, equity)
            if peak > 0:
                maximum = max(maximum, (peak - equity) / peak)

        return maximum

    def run_prepared(
        self,
        timeline: pd.DataFrame,
        evaluation_start: Any | None = None,
    ) -> HistoricalBacktestResult:
        required = {"open_time", "close_time", "open", "high", "low", "close"}
        required.update(f"state_{tf}" for tf in self.REQUIRED_TIMEFRAMES)
        missing = required.difference(timeline.columns)
        if missing:
            raise ValueError(f"Faltan columnas en el timeline: {sorted(missing)}")
        timeline = timeline.copy()
        timeline["open_time"] = pd.to_datetime(timeline["open_time"], utc=True)
        timeline["close_time"] = pd.to_datetime(timeline["close_time"], utc=True)
        if evaluation_start is not None:
            cutoff = pd.Timestamp(evaluation_start)
            if cutoff.tzinfo is None:
                cutoff = cutoff.tz_localize("UTC")
            else:
                cutoff = cutoff.tz_convert("UTC")
            timeline = timeline[
                timeline["open_time"] >= cutoff
            ].reset_index(drop=True)
        if len(timeline) < 2:
            raise ValueError("Se necesitan al menos dos velas 5M.")

        balance = float(self.config.initial_balance)
        position: dict[str, Any] | None = None
        trades: list[dict[str, Any]] = []
        decision_counts: Counter[str] = Counter()
        ready_signals = 0
        evaluated_bars = 0
        cooldown_until: pd.Timestamp | None = None
        loss_guard_until: pd.Timestamp | None = None
        consecutive_losses = 0

        for candle_index in range(len(timeline)):
            candle = timeline.iloc[candle_index]

            if position is not None and candle_index >= position["entry_index"]:
                exit_hit = self._raw_exit(position, candle)
                if exit_hit is not None:
                    raw_exit, reason = exit_hit
                    closed = self._close_trade(
                        position,
                        raw_exit_price=raw_exit,
                        reason=reason,
                        exit_index=candle_index,
                        exit_time=candle["close_time"],
                    )
                    balance += float(closed["pnl"])
                    closed["balance"] = balance
                    trades.append(closed)
                    position = None
                    cooldown_until = (
                        pd.Timestamp(candle["close_time"])
                        + pd.Timedelta(minutes=self.config.cooldown_minutes)
                    )
                    if float(closed["pnl"]) < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    if consecutive_losses >= self.config.loss_guard_losses:
                        loss_guard_until = (
                            pd.Timestamp(candle["close_time"])
                            + pd.Timedelta(minutes=self.config.loss_guard_minutes)
                        )
                        consecutive_losses = 0

            if position is not None or candle_index + 1 >= len(timeline):
                continue

            evaluated_bars += 1
            candle_close = pd.Timestamp(candle["close_time"])
            if (
                loss_guard_until is not None
                and candle_close < loss_guard_until
            ):
                decision_counts["LOSS_GUARD"] += 1
                continue
            if (
                cooldown_until is not None
                and candle_close < cooldown_until
            ):
                decision_counts["COOLDOWN"] += 1
                continue

            decision = self._decision_for_row(candle)
            decision_name = str(decision.get("decision", "WAIT"))
            decision_counts[decision_name] += 1

            direction = decision.get("direction")
            confirmed = (
                decision_name in {"READY_LONG", "READY_SHORT"}
                and direction in {"LONG", "SHORT"}
                and bool(decision.get("can_execute"))
            )
            if not confirmed:
                continue

            ready_signals += 1
            entry_index = candle_index + 1
            entry_candle = timeline.iloc[entry_index]
            raw_entry = float(entry_candle["open"])
            entry_price = self._entry_price(raw_entry, str(direction))

            if decision.get("strategy") in {
                "PROJECT_EDGE_V3",
                "PROJECT_EDGE_V4_INTRADAY",
                "PROJECT_EDGE_V5_DUAL_SETUP",
            }:
                trade_plan = self.selected_strategy.build_trade_plan(
                    decision=decision,
                    entry_price=entry_price,
                    account_equity=balance,
                )
                if not trade_plan.get("approved"):
                    decision_counts["RISK_REJECTED"] += 1
                    continue
                stop_price = float(trade_plan["stop_price"])
                target_price = float(trade_plan["target_price"])
                position_size = float(trade_plan["quantity"])
            elif direction == "LONG":
                stop_price = entry_price * (1.0 - self.config.stop_pct)
                target_price = entry_price * (1.0 + self.config.target_pct)
                position_size = balance / entry_price
            else:
                stop_price = entry_price * (1.0 + self.config.stop_pct)
                target_price = entry_price * (1.0 - self.config.target_pct)
                position_size = balance / entry_price

            entry_fee = entry_price * position_size * self.config.fee_rate
            position = {
                "symbol": self.config.symbol.upper(),
                "source": "AUTO",
                "mode": "PAPER_BACKTEST",
                "direction": direction,
                "opened": True,
                "status": "OPEN",
                "signal_index": int(candle_index),
                "signal_time": pd.Timestamp(candle["close_time"]).isoformat(),
                "entry_index": int(entry_index),
                "entry_time": pd.Timestamp(entry_candle["open_time"]).isoformat(),
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "position_size": position_size,
                "entry_fee": entry_fee,
                "strategy": decision.get("strategy", "PROJECT_EDGE_V2"),
                "setup_type": decision.get("setup_type"),
                "real_order_sent": False,
            }
            if decision.get("strategy") in {
                "PROJECT_EDGE_V3",
                "PROJECT_EDGE_V4_INTRADAY",
                "PROJECT_EDGE_V5_DUAL_SETUP",
            }:
                diagnostics = decision.get("diagnostics")
                if not isinstance(diagnostics, dict):
                    diagnostics = {}
                position.update(
                    {
                        "risk_budget": float(trade_plan["risk_budget"]),
                        "estimated_risk": float(trade_plan["estimated_risk"]),
                        "estimated_net_reward_risk": float(
                            trade_plan["estimated_net_reward_risk"]
                        ),
                        "leverage": 1,
                        "stop_distance_pct": float(
                            trade_plan["stop_distance"] / entry_price
                        ),
                        "target_distance_pct": float(
                            trade_plan["target_distance"] / entry_price
                        ),
                        "exposure_pct": float(
                            trade_plan["exposure"] / balance
                        ),
                        "estimated_cost_risk_ratio": float(
                            trade_plan["estimated_cost"]
                            / trade_plan["risk_budget"]
                        ),
                        **{
                            f"diag_{field}": diagnostics.get(field)
                            for field in self.selected_strategy.DIAGNOSTIC_FIELDS
                        },
                    }
                )

        if position is not None:
            last_index = len(timeline) - 1
            last_candle = timeline.iloc[last_index]
            closed = self._close_trade(
                position,
                raw_exit_price=float(last_candle["close"]),
                reason="END_OF_DATA",
                exit_index=last_index,
                exit_time=last_candle["close_time"],
            )
            balance += float(closed["pnl"])
            closed["balance"] = balance
            trades.append(closed)

        basic = BacktestReport().generate(
            trades=trades,
            rejected=0,
            no_trade=evaluated_bars - ready_signals,
        )
        total_fees = sum(float(trade["fees"]) for trade in trades)
        report = {
            "symbol": self.config.symbol.upper(),
            "mode": "PAPER_BACKTEST",
            "source": "AUTO_ONLY",
            "manual_trades_included": False,
            "start_time": pd.Timestamp(timeline.iloc[0]["open_time"]).isoformat(),
            "end_time": pd.Timestamp(timeline.iloc[-1]["close_time"]).isoformat(),
            "five_minute_candles": int(len(timeline)),
            "evaluated_bars": evaluated_bars,
            "ready_signals": ready_signals,
            "cooldown_blocked_bars": int(
                decision_counts["COOLDOWN"]
            ),
            "loss_guard_blocked_bars": int(
                decision_counts["LOSS_GUARD"]
            ),
            "decision_counts": dict(decision_counts),
            "initial_balance": self.config.initial_balance,
            "final_balance": balance,
            "return_pct": (
                balance / self.config.initial_balance - 1.0
            ),
            "max_drawdown_pct": self._max_drawdown_pct(
                trades,
                self.config.initial_balance,
            ),
            "total_fees": total_fees,
            "config": asdict(self.config),
            **basic,
        }
        return HistoricalBacktestResult(report=report, trades=trades)

    def run(
        self,
        timeframe_data: dict[str, pd.DataFrame],
        evaluation_start: Any | None = None,
    ) -> HistoricalBacktestResult:
        return self.run_prepared(
            self.prepare_timeline(timeframe_data),
            evaluation_start=evaluation_start,
        )
