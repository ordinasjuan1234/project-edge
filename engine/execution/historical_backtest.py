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
            analysis["causal_market_structure"] = self.causal_market_states(
                analysis
            )
            analyses[timeframe] = analysis

        timeline = analyses["5M"][
            ["open_time", "close_time", "open", "high", "low", "close"]
        ].copy()
        timeline = timeline.sort_values("close_time").reset_index(drop=True)

        for timeframe in self.REQUIRED_TIMEFRAMES:
            analysis = analyses[timeframe]
            columns = ["close_time", "causal_market_structure"]

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

        return {
            **position,
            "opened": False,
            "status": "CLOSED",
            "exit_price": exit_price,
            "exit_index": int(exit_index),
            "exit_time": pd.Timestamp(exit_time).isoformat(),
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

    def run_prepared(self, timeline: pd.DataFrame) -> HistoricalBacktestResult:
        required = {"open_time", "close_time", "open", "high", "low", "close"}
        required.update(f"state_{tf}" for tf in self.REQUIRED_TIMEFRAMES)
        missing = required.difference(timeline.columns)
        if missing:
            raise ValueError(f"Faltan columnas en el timeline: {sorted(missing)}")
        if len(timeline) < 2:
            raise ValueError("Se necesitan al menos dos velas 5M.")

        balance = float(self.config.initial_balance)
        position: dict[str, Any] | None = None
        trades: list[dict[str, Any]] = []
        decision_counts: Counter[str] = Counter()
        ready_signals = 0
        evaluated_bars = 0

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

            if position is not None or candle_index + 1 >= len(timeline):
                continue

            evaluated_bars += 1
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

            if direction == "LONG":
                stop_price = entry_price * (1.0 - self.config.stop_pct)
                target_price = entry_price * (1.0 + self.config.target_pct)
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
                "real_order_sent": False,
            }

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
    ) -> HistoricalBacktestResult:
        return self.run_prepared(self.prepare_timeline(timeframe_data))
