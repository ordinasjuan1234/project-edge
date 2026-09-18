"""Compara v3 y la candidata v5 sin modificar el bot PAPER activo.

Genera tres resultados:
- v3 vigente sobre ETHUSDT;
- v5 dual setup sobre ETHUSDT;
- v5 dual setup con BTCUSDT + ETHUSDT, saldo compartido y una posicion maxima.

Solo descarga velas publicas y escribe artefactos de backtest.

Reglas de paridad experimental:
- riesgo maximo: 0,50%;
- exposicion maxima: 50%;
- apalancamiento: x1;
- stop minimo: 0,60%;
- comision: 0,10% por lado;
- slippage: 0,02% por lado;
- filtro costo/riesgo v5 configurable;
- modo direccional v5 configurable: BOTH, LONG_ONLY o SHORT_ONLY.

Este archivo NO cambia el runner PAPER activo ni habilita REAL.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from engine.data.binance_historical_data import BinanceHistoricalData
from engine.data.historical_dataset import HistoricalDataset
from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktester,
)
from engine.execution.portfolio_historical_backtest import (
    PortfolioHistoricalBacktester,
    PortfolioHistoricalConfig,
)
from run_historical_backtest import (
    BACKTEST_WARMUP_DAYS,
    LIVE_ANALYSIS_WINDOW_BARS,
    reference_now_for_years_ago,
)
from trading_mode import require_paper_mode


SYMBOLS = ("BTCUSDT", "ETHUSDT")
INITIAL_BALANCE = 10000.0
V5_STRATEGY = "PROJECT_EDGE_V5_DUAL_SETUP"

RISK_PCT = 0.005
MAX_EXPOSURE_PCT = 0.50
MINIMUM_STOP_PCT = 0.006
FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0002

DEFAULT_MAX_COST_RISK_RATIO = 0.12
DEFAULT_DIRECTION_MODE = "BOTH"
VALID_DIRECTION_MODES = ("BOTH", "LONG_ONLY", "SHORT_ONLY")


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None

    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _json_safe(item)
            for item in value
        ]

    return value


def _apply_strategy_parity(
    backtester: HistoricalBacktester,
    *,
    max_cost_risk_ratio: float,
    direction_mode: str = DEFAULT_DIRECTION_MODE,
) -> HistoricalBacktester:
    """Fuerza paridad de riesgo/costos y, en v5, el modo direccional."""

    config_changes: dict[str, Any] = {
        "risk_pct": RISK_PCT,
        "max_exposure_pct": MAX_EXPOSURE_PCT,
        "minimum_stop_pct": MINIMUM_STOP_PCT,
        "fee_rate": FEE_RATE,
        "slippage_rate": SLIPPAGE_RATE,
    }

    strategy_config = (
        backtester.selected_strategy.config
    )

    if hasattr(
        strategy_config,
        "max_cost_risk_ratio",
    ):
        config_changes[
            "max_cost_risk_ratio"
        ] = max_cost_risk_ratio

    if hasattr(
        strategy_config,
        "direction_mode",
    ):
        config_changes[
            "direction_mode"
        ] = direction_mode

    backtester.selected_strategy.config = replace(
        strategy_config,
        **config_changes,
    )

    return backtester


def _historical_backtester(
    *,
    symbol: str,
    strategy: str,
    max_cost_risk_ratio: float,
    direction_mode: str = DEFAULT_DIRECTION_MODE,
) -> HistoricalBacktester:

    backtester = HistoricalBacktester(
        HistoricalBacktestConfig(
            symbol=symbol,
            strategy=strategy,
            initial_balance=INITIAL_BALANCE,
            analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
            risk_pct=RISK_PCT,
            max_exposure_pct=MAX_EXPOSURE_PCT,
            stop_pct=MINIMUM_STOP_PCT,
            fee_rate=FEE_RATE,
            slippage_rate=SLIPPAGE_RATE,
        )
    )

    return _apply_strategy_parity(
        backtester,
        max_cost_risk_ratio=max_cost_risk_ratio,
        direction_mode=direction_mode,
    )


def _portfolio_backtester(
    *,
    max_cost_risk_ratio: float,
    direction_mode: str = DEFAULT_DIRECTION_MODE,
) -> PortfolioHistoricalBacktester:

    portfolio = PortfolioHistoricalBacktester(
        PortfolioHistoricalConfig(
            symbols=SYMBOLS,
            initial_balance=INITIAL_BALANCE,
            strategy=V5_STRATEGY,
            analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
            risk_pct=RISK_PCT,
            max_exposure_pct=MAX_EXPOSURE_PCT,
            fee_rate=FEE_RATE,
            slippage_rate=SLIPPAGE_RATE,
        )
    )

    for backtester in portfolio.backtesters.values():
        _apply_strategy_parity(
            backtester,
            max_cost_risk_ratio=max_cost_risk_ratio,
            direction_mode=direction_mode,
        )

    return portfolio


def _slice_evaluation_window(
    timeline: pd.DataFrame,
    evaluation_start: Any | None,
) -> pd.DataFrame:

    result = timeline.copy()

    if evaluation_start is None:
        return result.reset_index(
            drop=True
        )

    cutoff = pd.Timestamp(
        evaluation_start
    )

    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize(
            "UTC"
        )
    else:
        cutoff = cutoff.tz_convert(
            "UTC"
        )

    open_times = pd.to_datetime(
        result["open_time"],
        utc=True,
    )

    return result[
        open_times >= cutoff
    ].reset_index(
        drop=True
    )


def _setup_context_diagnostics(
    backtester: HistoricalBacktester,
    timeline: pd.DataFrame,
    *,
    evaluation_start: Any | None,
) -> dict[str, Any]:
    """Cuenta A/B, overlap y B-only sin ejecutar operaciones."""

    window = _slice_evaluation_window(
        timeline,
        evaluation_start,
    )

    counts = {
        "evaluated_rows": 0,
        "regime_rows": 0,
        "long_regime_rows": 0,
        "short_regime_rows": 0,
        "direction_allowed_rows": 0,
        "setup_a_contexts": 0,
        "setup_b_contexts": 0,
        "setup_overlap_contexts": 0,
        "setup_b_only_contexts": 0,
        "any_setup_contexts": 0,
        "ready_rows": 0,
        "ready_long_rows": 0,
        "ready_short_rows": 0,
    }

    by_direction = {
        "LONG": {
            "setup_a_contexts": 0,
            "setup_b_contexts": 0,
            "setup_overlap_contexts": 0,
            "setup_b_only_contexts": 0,
            "ready_rows": 0,
        },
        "SHORT": {
            "setup_a_contexts": 0,
            "setup_b_contexts": 0,
            "setup_overlap_contexts": 0,
            "setup_b_only_contexts": 0,
            "ready_rows": 0,
        },
    }

    for _, row in window.iterrows():

        counts[
            "evaluated_rows"
        ] += 1

        decision = (
            backtester
            .selected_strategy
            .decide_snapshot(
                row
            )
        )

        direction = decision.get(
            "direction"
        )

        if direction in {
            "LONG",
            "SHORT",
        }:

            counts[
                "regime_rows"
            ] += 1

            counts[
                f"{direction.lower()}_regime_rows"
            ] += 1

        checks = decision.get(
            "checks",
            {},
        )

        if not isinstance(
            checks,
            dict,
        ):
            checks = {}

        direction_allowed = bool(
            checks.get(
                "direction_allowed",
                direction
                in {
                    "LONG",
                    "SHORT",
                },
            )
        )

        if direction_allowed:
            counts[
                "direction_allowed_rows"
            ] += 1

        setup_a = bool(
            decision.get(
                "setup_a_context",
                checks.get(
                    "setup_a_context",
                    False,
                ),
            )
        )

        setup_b = bool(
            decision.get(
                "setup_b_context",
                checks.get(
                    "setup_b_context",
                    False,
                ),
            )
        )

        overlap = bool(
            decision.get(
                "setup_overlap",
                setup_a
                and setup_b,
            )
        )

        b_only = bool(
            decision.get(
                "setup_b_only",
                setup_b
                and not setup_a,
            )
        )

        if setup_a:
            counts[
                "setup_a_contexts"
            ] += 1

        if setup_b:
            counts[
                "setup_b_contexts"
            ] += 1

        if overlap:
            counts[
                "setup_overlap_contexts"
            ] += 1

        if b_only:
            counts[
                "setup_b_only_contexts"
            ] += 1

        if setup_a or setup_b:
            counts[
                "any_setup_contexts"
            ] += 1

        can_execute = bool(
            decision.get(
                "can_execute",
                False,
            )
        )

        if can_execute:

            counts[
                "ready_rows"
            ] += 1

            if direction == "LONG":
                counts[
                    "ready_long_rows"
                ] += 1

            elif direction == "SHORT":
                counts[
                    "ready_short_rows"
                ] += 1

        if direction in by_direction:

            bucket = by_direction[
                str(direction)
            ]

            if setup_a:
                bucket[
                    "setup_a_contexts"
                ] += 1

            if setup_b:
                bucket[
                    "setup_b_contexts"
                ] += 1

            if overlap:
                bucket[
                    "setup_overlap_contexts"
                ] += 1

            if b_only:
                bucket[
                    "setup_b_only_contexts"
                ] += 1

            if can_execute:
                bucket[
                    "ready_rows"
                ] += 1

    return {
        **counts,
        "by_direction":
            by_direction,
    }


def _combine_setup_diagnostics(
    diagnostics_by_symbol: dict[
        str,
        dict[str, Any],
    ],
) -> dict[str, Any]:

    scalar_fields = (
        "evaluated_rows",
        "regime_rows",
        "long_regime_rows",
        "short_regime_rows",
        "direction_allowed_rows",
        "setup_a_contexts",
        "setup_b_contexts",
        "setup_overlap_contexts",
        "setup_b_only_contexts",
        "any_setup_contexts",
        "ready_rows",
        "ready_long_rows",
        "ready_short_rows",
    )

    total = {
        field: sum(
            int(
                diagnostics.get(
                    field,
                    0,
                )
            )
            for diagnostics
            in diagnostics_by_symbol.values()
        )
        for field
        in scalar_fields
    }

    total[
        "by_symbol"
    ] = diagnostics_by_symbol

    total[
        "by_direction"
    ] = {
        direction: {
            field: sum(
                int(
                    diagnostics
                    .get(
                        "by_direction",
                        {},
                    )
                    .get(
                        direction,
                        {},
                    )
                    .get(
                        field,
                        0,
                    )
                )
                for diagnostics
                in diagnostics_by_symbol.values()
            )
            for field in (
                "setup_a_contexts",
                "setup_b_contexts",
                "setup_overlap_contexts",
                "setup_b_only_contexts",
                "ready_rows",
            )
        }
        for direction in (
            "LONG",
            "SHORT",
        )
    }

    return total


def _enrich_report(
    report: dict[str, Any],
    *,
    candidate: str,
    requested_days: int,
    max_cost_risk_ratio: float,
    direction_mode: str = DEFAULT_DIRECTION_MODE,
    setup_diagnostics: dict[
        str,
        Any,
    ] | None = None,
) -> dict[str, Any]:

    result = dict(
        report
    )

    result[
        "candidate"
    ] = candidate

    result[
        "requested_days"
    ] = requested_days

    result[
        "trades_per_day"
    ] = (
        float(
            result.get(
                "total_trades",
                0,
            )
        )
        / requested_days
    )

    result[
        "cost_per_trade"
    ] = (
        float(
            result.get(
                "total_fees",
                0.0,
            )
        )
        / float(
            result.get(
                "total_trades",
                0,
            )
        )
        if result.get(
            "total_trades",
            0,
        )
        else 0.0
    )

    result[
        "test_risk_pct"
    ] = RISK_PCT

    result[
        "test_max_exposure_pct"
    ] = MAX_EXPOSURE_PCT

    result[
        "test_minimum_stop_pct"
    ] = MINIMUM_STOP_PCT

    result[
        "test_fee_rate"
    ] = FEE_RATE

    result[
        "test_slippage_rate"
    ] = SLIPPAGE_RATE

    result[
        "test_max_cost_risk_ratio"
    ] = max_cost_risk_ratio

    result[
        "test_direction_mode"
    ] = direction_mode

    if setup_diagnostics:

        result[
            "setup_a_contexts"
        ] = int(
            setup_diagnostics.get(
                "setup_a_contexts",
                0,
            )
        )

        result[
            "setup_b_contexts"
        ] = int(
            setup_diagnostics.get(
                "setup_b_contexts",
                0,
            )
        )

        result[
            "setup_overlap_contexts"
        ] = int(
            setup_diagnostics.get(
                "setup_overlap_contexts",
                0,
            )
        )

        result[
            "setup_b_only_contexts"
        ] = int(
            setup_diagnostics.get(
                "setup_b_only_contexts",
                0,
            )
        )

        result[
            "setup_ready_rows"
        ] = int(
            setup_diagnostics.get(
                "ready_rows",
                0,
            )
        )

    return result


def _format_pf(
    value: Any,
) -> str:

    number = float(
        value
    )

    return (
        "INF"
        if math.isinf(
            number
        )
        else f"{number:.2f}"
    )


def print_comparison(
    reports: dict[
        str,
        dict[str, Any],
    ],
) -> None:

    print("-")

    print(
        "COMPARACION "
        "(todos los resultados incluyen costos simulados)"
    )

    print(
        f"{'Candidata':<34} "
        f"{'Trades':>7} "
        f"{'Por dia':>8} "
        f"{'Retorno':>9} "
        f"{'PF':>7} "
        f"{'DD max':>9} "
        f"{'Costos':>10}"
    )

    for key in (
        "v3_eth",
        "v5_eth",
        "v5_portfolio",
    ):

        report = reports[
            key
        ]

        print(
            f"{report['candidate']:<34} "
            f"{int(report['total_trades']):>7} "
            f"{float(report['trades_per_day']):>8.3f} "
            f"{float(report['return_pct']) * 100:>8.2f}% "
            f"{_format_pf(report['profit_factor']):>7} "
            f"{float(report['max_drawdown_pct']) * 100:>8.2f}% "
            f"{float(report['total_fees']):>10.2f}"
        )


def write_outputs(
    output_dir: Path,
    payload: dict[
        str,
        Any,
    ],
    trades_by_candidate: dict[
        str,
        list[
            dict[str, Any]
        ],
    ],
) -> None:

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        output_dir
        / "v5_comparison_report.json"
    ).write_text(
        json.dumps(
            _json_safe(
                payload
            ),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary_fields = [
        "candidate",
        "symbols",
        "total_trades",
        "trades_per_day",
        "winners",
        "losers",
        "win_rate",
        "total_pnl",
        "return_pct",
        "profit_factor",
        "max_drawdown_pct",
        "total_fees",
        "cost_per_trade",
        "shared_balance",
        "one_position_at_a_time",
        "test_risk_pct",
        "test_max_exposure_pct",
        "test_minimum_stop_pct",
        "test_fee_rate",
        "test_slippage_rate",
        "test_max_cost_risk_ratio",
        "test_direction_mode",
        "setup_a_contexts",
        "setup_b_contexts",
        "setup_overlap_contexts",
        "setup_b_only_contexts",
        "setup_ready_rows",
    ]

    with (
        output_dir
        / "v5_comparison_summary.csv"
    ).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=summary_fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        for report in payload[
            "reports"
        ].values():

            symbols = report.get(
                "symbols",
                report.get(
                    "symbol",
                    "",
                ),
            )

            if isinstance(
                symbols,
                list,
            ):
                symbols = "+".join(
                    str(symbol)
                    for symbol
                    in symbols
                )

            writer.writerow(
                {
                    **report,
                    "symbols":
                        symbols,
                }
            )

    trade_fields = [
        "candidate",
        "symbol",
        "strategy",
        "setup_type",
        "direction",
        "signal_time",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "stop_price",
        "target_price",
        "position_size",
        "quality_score",
        "risk_budget",
        "estimated_risk",
        "estimated_net_reward_risk",
        "leverage",
        "stop_distance_pct",
        "target_distance_pct",
        "exposure_pct",
        "estimated_cost_risk_ratio",
        "diag_setup_a_context",
        "diag_setup_b_context",
        "diag_setup_overlap",
        "diag_setup_b_only",
        "diag_direction_allowed",
        "diag_breakout_30m",
        "close_reason",
        "holding_minutes",
        "gross_pnl",
        "fees",
        "pnl",
        "balance",
        "real_order_sent",
    ]

    with (
        output_dir
        / "v5_comparison_trades.csv"
    ).open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=trade_fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        for (
            candidate,
            trades,
        ) in trades_by_candidate.items():

            for trade in trades:

                writer.writerow(
                    {
                        **trade,
                        "candidate":
                            candidate,
                    }
                )


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Comparador PAPER "
            "v3 vs v5 dual setup."
        )
    )

    parser.add_argument(
        "--days",
        type=int,
        default=365,
    )

    parser.add_argument(
        "--years-ago",
        type=int,
        default=6,
    )

    parser.add_argument(
        "--max-cost-risk-ratio",
        type=float,
        default=(
            DEFAULT_MAX_COST_RISK_RATIO
        ),
        help=(
            "Limite costo/riesgo v5. "
            "Ejemplo: 0.12 equivale a 12%%."
        ),
    )

    parser.add_argument(
        "--direction-mode",
        type=str.upper,
        choices=VALID_DIRECTION_MODES,
        default=(
            DEFAULT_DIRECTION_MODE
        ),
        help=(
            "Modo direccional experimental v5: "
            "BOTH, LONG_ONLY o SHORT_ONLY."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=(
            "artifacts/"
            "v5-comparison"
        ),
    )

    return parser.parse_args()


def main() -> None:

    # El bloqueo REAL ocurre antes de
    # descargar mercado o crear artefactos.
    require_paper_mode()

    args = parse_args()

    if not (
        1
        <= args.days
        <= 365
    ):
        raise ValueError(
            "days debe estar entre "
            "1 y 365."
        )

    if not (
        0
        < args.max_cost_risk_ratio
        < 1
    ):
        raise ValueError(
            "max-cost-risk-ratio debe estar "
            "entre 0 y 1."
        )

    direction_mode = str(
        args.direction_mode
    ).upper()

    if (
        direction_mode
        not in VALID_DIRECTION_MODES
    ):
        raise ValueError(
            "direction-mode debe ser "
            "BOTH, LONG_ONLY o SHORT_ONLY."
        )

    reference_now = (
        reference_now_for_years_ago(
            args.years_ago
        )
    )

    evaluation_start = (
        reference_now
        - timedelta(
            days=args.days
        )
    )

    loader = BinanceHistoricalData(
        timeout=30
    )

    dataset = (
        HistoricalDataset()
    )

    timelines: dict[
        str,
        Any,
    ] = {}

    preparation_backtesters: dict[
        str,
        HistoricalBacktester,
    ] = {}

    cost_risk_pct = (
        args.max_cost_risk_ratio
        * 100
    )

    print("=" * 78)

    print(
        "PROJECT EDGE - "
        "COMPARADOR v3 vs v5 "
        "DUAL SETUP "
        "(SOLO PAPER BACKTEST)"
    )

    print("=" * 78)

    print(
        f"Periodo: {args.days} dias "
        f"· bloque "
        f"{args.years_ago} "
        "ano(s) atras"
    )

    print(
        "Datos: velas publicas; "
        "entrada en la vela 5M "
        "siguiente; sin look-ahead"
    )

    print(
        "Costos: comision 0,10% "
        "+ deslizamiento 0,02% "
        "por lado"
    )

    print(
        "Riesgo: 0,50% maximo "
        "· exposicion maxima 50% "
        "· x1"
    )

    print(
        "Stop minimo: 0,60%"
    )

    print(
        "Filtro v5 costo/riesgo: "
        f"maximo {cost_risk_pct:.0f}%"
    )

    print(
        "Modo direccional v5: "
        f"{direction_mode}"
    )

    print(
        "El runner AUTO v3, "
        "los saldos y "
        "paper_state.json "
        "NO se modifican"
    )

    for symbol in SYMBOLS:

        print(
            f"Descargando y preparando "
            f"{symbol}..."
        )

        candles = loader.fetch_recent(
            symbol=symbol,
            interval="5m",
            days=(
                args.days
                + BACKTEST_WARMUP_DAYS
            ),
            now=reference_now,
        )

        if candles.empty:
            raise RuntimeError(
                "Binance no devolvio "
                f"datos para {symbol}."
            )

        timeframe_data = (
            dataset.build(
                candles
            )
        )

        preparation_backtester = (
            _historical_backtester(
                symbol=symbol,
                strategy=V5_STRATEGY,
                max_cost_risk_ratio=(
                    args.max_cost_risk_ratio
                ),
                direction_mode=(
                    direction_mode
                ),
            )
        )

        preparation_backtesters[
            symbol
        ] = preparation_backtester

        timelines[
            symbol
        ] = (
            preparation_backtester
            .prepare_timeline(
                timeframe_data
            )
        )

    setup_diagnostics_by_symbol = {
        symbol:
            _setup_context_diagnostics(
                preparation_backtesters[
                    symbol
                ],
                timelines[
                    symbol
                ],
                evaluation_start=(
                    evaluation_start
                ),
            )
        for symbol
        in SYMBOLS
    }

    portfolio_setup_diagnostics = (
        _combine_setup_diagnostics(
            setup_diagnostics_by_symbol
        )
    )

    v3_backtester = (
        _historical_backtester(
            symbol="ETHUSDT",
            strategy=(
                "PROJECT_EDGE_V3"
            ),
            max_cost_risk_ratio=(
                args.max_cost_risk_ratio
            ),
            direction_mode="BOTH",
        )
    )

    v3 = (
        v3_backtester
        .run_prepared(
            timelines[
                "ETHUSDT"
            ],
            evaluation_start=(
                evaluation_start
            ),
        )
    )

    v5_eth_backtester = (
        _historical_backtester(
            symbol="ETHUSDT",
            strategy=V5_STRATEGY,
            max_cost_risk_ratio=(
                args.max_cost_risk_ratio
            ),
            direction_mode=(
                direction_mode
            ),
        )
    )

    v5_eth = (
        v5_eth_backtester
        .run_prepared(
            timelines[
                "ETHUSDT"
            ],
            evaluation_start=(
                evaluation_start
            ),
        )
    )

    portfolio_backtester = (
        _portfolio_backtester(
            max_cost_risk_ratio=(
                args.max_cost_risk_ratio
            ),
            direction_mode=(
                direction_mode
            ),
        )
    )

    portfolio = (
        portfolio_backtester
        .run_prepared(
            timelines,
            evaluation_start=(
                evaluation_start
            ),
        )
    )

    v5_eth_candidate = (
        "V5_ETH_"
        f"{direction_mode}"
    )

    v5_portfolio_candidate = (
        "V5_BTC_ETH_"
        f"{direction_mode}_"
        "UNA_POSICION"
    )

    reports = {

        "v3_eth":
            _enrich_report(
                v3.report,
                candidate=(
                    "V3_ETH_ACTUAL"
                ),
                requested_days=(
                    args.days
                ),
                max_cost_risk_ratio=(
                    args.max_cost_risk_ratio
                ),
                direction_mode=(
                    "BOTH_REFERENCE"
                ),
            ),

        "v5_eth":
            _enrich_report(
                v5_eth.report,
                candidate=(
                    v5_eth_candidate
                ),
                requested_days=(
                    args.days
                ),
                max_cost_risk_ratio=(
                    args.max_cost_risk_ratio
                ),
                direction_mode=(
                    direction_mode
                ),
                setup_diagnostics=(
                    setup_diagnostics_by_symbol[
                        "ETHUSDT"
                    ]
                ),
            ),

        "v5_portfolio":
            _enrich_report(
                portfolio.report,
                candidate=(
                    v5_portfolio_candidate
                ),
                requested_days=(
                    args.days
                ),
                max_cost_risk_ratio=(
                    args.max_cost_risk_ratio
                ),
                direction_mode=(
                    direction_mode
                ),
                setup_diagnostics=(
                    portfolio_setup_diagnostics
                ),
            ),
    }

    payload = {

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "requested_days":
            args.days,

        "years_ago":
            args.years_ago,

        "reference_now":
            reference_now.isoformat(),

        "evaluation_start":
            evaluation_start.isoformat(),

        "mode":
            "PAPER_BACKTEST_ONLY",

        "real_orders":
            False,

        "live_strategy_changed":
            False,

        "paper_state_changed":
            False,

        "test_configuration": {

            "initial_balance":
                INITIAL_BALANCE,

            "risk_pct":
                RISK_PCT,

            "max_exposure_pct":
                MAX_EXPOSURE_PCT,

            "minimum_stop_pct":
                MINIMUM_STOP_PCT,

            "leverage":
                1,

            "fee_rate":
                FEE_RATE,

            "slippage_rate":
                SLIPPAGE_RATE,

            "max_cost_risk_ratio":
                args.max_cost_risk_ratio,

            "direction_mode":
                direction_mode,
        },

        "setup_context_diagnostics": {

            "ETHUSDT":
                setup_diagnostics_by_symbol[
                    "ETHUSDT"
                ],

            "BTCUSDT":
                setup_diagnostics_by_symbol[
                    "BTCUSDT"
                ],

            "PORTFOLIO_AGGREGATE":
                portfolio_setup_diagnostics,
        },

        "rules_frozen_before_out_of_sample": {

            "regime":
                (
                    "EMA20/50 + pendiente 1H; "
                    "estructura 1H no opuesta"
                ),

            "macro_4h":
                (
                    "bloquea solo oposicion "
                    "estructural + EMA clara"
                ),

            "setup_a":
                (
                    "PULLBACK_CONTINUATION "
                    "con 30M estructura+EMA "
                    "alineadas"
                ),

            "setup_b":
                (
                    "BREAKOUT_RETEST con "
                    "BOS/CHoCH 30M reciente "
                    "y pendiente compatible"
                ),

            "setup_priority":
                (
                    "si A y B coinciden, "
                    "A conserva prioridad; "
                    "se registra overlap "
                    "para diagnostico"
                ),

            "direction_mode":
                direction_mode,

            "adx":
                (
                    ">=25 y "
                    "(creciente o >=30)"
                ),

            "pullback":
                "15M obligatorio",

            "trigger":
                (
                    "5M obligatorio, "
                    "maximo 0,75 ATR "
                    "desde EMA20"
                ),

            "fvg":
                (
                    "puntuacion, "
                    "no requisito"
                ),

            "cost_risk":
                (
                    "costo estimado <="
                    f"{cost_risk_pct:.0f}% "
                    "del presupuesto de riesgo"
                ),

            "risk":
                (
                    "0,5%, x1, "
                    "exposicion maxima 50%, "
                    "SL minimo 0,60%, "
                    "objetivo neto minimo "
                    "1,5R"
                ),
        },

        "acceptance_targets": {

            "net_return_gt":
                0.0,

            "profit_factor_gte":
                1.20,

            "max_drawdown_lte":
                0.10,

            "portfolio_trades_per_day_gte":
                1.00,
        },

        "reports":
            reports,
    }

    write_outputs(
        Path(
            args.output_dir
        ),
        payload,
        {

            "V3_ETH_ACTUAL":
                v3.trades,

            v5_eth_candidate:
                v5_eth.trades,

            v5_portfolio_candidate:
                portfolio.trades,
        },
    )

    print_comparison(
        reports
    )

    print("-")

    print(
        "DIAGNOSTICO SETUPS "
        f"({direction_mode})"
    )

    for symbol in SYMBOLS:

        diagnostics = (
            setup_diagnostics_by_symbol[
                symbol
            ]
        )

        print(
            f"{symbol}: "
            f"A={diagnostics['setup_a_contexts']} · "
            f"B={diagnostics['setup_b_contexts']} · "
            f"A+B={diagnostics['setup_overlap_contexts']} · "
            f"B-only={diagnostics['setup_b_only_contexts']} · "
            f"READY={diagnostics['ready_rows']}"
        )

    print("-")

    print(
        "Reporte: "
        f"{Path(args.output_dir) / 'v5_comparison_report.json'}"
    )

    print(
        "Resumen: "
        f"{Path(args.output_dir) / 'v5_comparison_summary.csv'}"
    )

    print(
        "Trades:  "
        f"{Path(args.output_dir) / 'v5_comparison_trades.csv'}"
    )

    print(
        "MODO REAL: BLOQUEADO. "
        "No se envio ninguna orden "
        "ni Telegram."
    )

    print("=" * 78)


if __name__ == "__main__":
    main()
