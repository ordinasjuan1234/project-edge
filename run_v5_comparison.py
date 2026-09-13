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
- filtro costo/riesgo v5: 12%.
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
) -> HistoricalBacktester:
    """Fuerza las reglas actuales sobre la estrategia historica.

    HistoricalBacktestConfig transporta riesgo, exposicion y costos,
    pero la distancia minima real del stop vive dentro de la config
    de ProjectEdgeV3/ProjectEdgeV5.

    Se reemplaza solo la config del objeto historico.
    No modifica ningun runner PAPER activo.
    """

    backtester.selected_strategy.config = replace(
        backtester.selected_strategy.config,
        risk_pct=RISK_PCT,
        max_exposure_pct=MAX_EXPOSURE_PCT,
        minimum_stop_pct=MINIMUM_STOP_PCT,
        fee_rate=FEE_RATE,
        slippage_rate=SLIPPAGE_RATE,
    )

    return backtester


def _historical_backtester(
    *,
    symbol: str,
    strategy: str,
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
        backtester
    )


def _portfolio_backtester() -> PortfolioHistoricalBacktester:
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
            backtester
        )

    return portfolio


def _enrich_report(
    report: dict[str, Any],
    *,
    candidate: str,
    requested_days: int,
) -> dict[str, Any]:
    result = dict(report)

    result["candidate"] = candidate
    result["requested_days"] = requested_days

    result["trades_per_day"] = (
        float(
            result.get(
                "total_trades",
                0,
            )
        )
        / requested_days
    )

    result["cost_per_trade"] = (
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

    result["test_risk_pct"] = RISK_PCT
    result["test_max_exposure_pct"] = (
        MAX_EXPOSURE_PCT
    )
    result["test_minimum_stop_pct"] = (
        MINIMUM_STOP_PCT
    )
    result["test_fee_rate"] = FEE_RATE
    result["test_slippage_rate"] = (
        SLIPPAGE_RATE
    )

    return result


def _format_pf(
    value: Any,
) -> str:
    number = float(value)

    return (
        "INF"
        if math.isinf(number)
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
        f"{'Candidata':<26} "
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
        report = reports[key]

        print(
            f"{report['candidate']:<26} "
            f"{int(report['total_trades']):>7} "
            f"{float(report['trades_per_day']):>8.3f} "
            f"{float(report['return_pct']) * 100:>8.2f}% "
            f"{_format_pf(report['profit_factor']):>7} "
            f"{float(report['max_drawdown_pct']) * 100:>8.2f}% "
            f"{float(report['total_fees']):>10.2f}"
        )


def write_outputs(
    output_dir: Path,
    payload: dict[str, Any],
    trades_by_candidate: dict[
        str,
        list[dict[str, Any]],
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
            _json_safe(payload),
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
                    "symbols": symbols,
                }
            )

    fields = [
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
            fieldnames=fields,
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
                        "candidate": candidate,
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
        "--output-dir",
        default=(
            "artifacts/"
            "v5-comparison"
        ),
    )

    return parser.parse_args()


def main() -> None:
    # El bloqueo ocurre antes de descargar
    # mercado o crear artefactos.
    require_paper_mode()

    args = parse_args()

    if not 1 <= args.days <= 365:
        raise ValueError(
            "days debe estar entre "
            "1 y 365."
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

    dataset = HistoricalDataset()

    timelines: dict[
        str,
        Any,
    ] = {}

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
        "maximo 12%"
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

        # v5 agrega breakout 30M;
        # v3 usa un subconjunto
        # de los mismos campos.
        preparation_backtester = (
            _historical_backtester(
                symbol=symbol,
                strategy=V5_STRATEGY,
            )
        )

        timelines[symbol] = (
            preparation_backtester
            .prepare_timeline(
                timeframe_data
            )
        )

    v3_backtester = (
        _historical_backtester(
            symbol="ETHUSDT",
            strategy="PROJECT_EDGE_V3",
        )
    )

    v3 = v3_backtester.run_prepared(
        timelines["ETHUSDT"],
        evaluation_start=(
            evaluation_start
        ),
    )

    v5_eth_backtester = (
        _historical_backtester(
            symbol="ETHUSDT",
            strategy=V5_STRATEGY,
        )
    )

    v5_eth = (
        v5_eth_backtester
        .run_prepared(
            timelines["ETHUSDT"],
            evaluation_start=(
                evaluation_start
            ),
        )
    )

    portfolio_backtester = (
        _portfolio_backtester()
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

    reports = {
        "v3_eth": _enrich_report(
            v3.report,
            candidate=(
                "V3_ETH_ACTUAL"
            ),
            requested_days=(
                args.days
            ),
        ),

        "v5_eth": _enrich_report(
            v5_eth.report,
            candidate=(
                "V5_ETH_DUAL_SETUP"
            ),
            requested_days=(
                args.days
            ),
        ),

        "v5_portfolio":
            _enrich_report(
                portfolio.report,
                candidate=(
                    "V5_BTC_ETH_"
                    "UNA_POSICION"
                ),
                requested_days=(
                    args.days
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
                0.12,
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
                    "costo estimado "
                    "<=12% del presupuesto "
                    "de riesgo"
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

            "V5_ETH_DUAL_SETUP":
                v5_eth.trades,

            "V5_BTC_ETH_UNA_POSICION":
                portfolio.trades,
        },
    )

    print_comparison(
        reports
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
