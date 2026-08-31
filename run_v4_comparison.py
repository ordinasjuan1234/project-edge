"""Compara v3 y la candidata v4 sin modificar el bot PAPER activo.

Genera tres resultados:
- v3 vigente sobre ETHUSDT;
- v4 intradia sobre ETHUSDT;
- v4 intradia con BTCUSDT + ETHUSDT, saldo compartido y una posicion maxima.

Solo descarga velas publicas y escribe artefactos de backtest.
"""

from __future__ import annotations

import argparse
import csv
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
)
from run_historical_backtest import (
    BACKTEST_WARMUP_DAYS,
    LIVE_ANALYSIS_WINDOW_BARS,
    reference_now_for_years_ago,
)
from trading_mode import require_paper_mode


SYMBOLS = ("BTCUSDT", "ETHUSDT")
INITIAL_BALANCE = 10000.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


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
        float(result.get("total_trades", 0)) / requested_days
    )
    result["cost_per_trade"] = (
        float(result.get("total_fees", 0.0))
        / float(result.get("total_trades", 0))
        if result.get("total_trades", 0)
        else 0.0
    )
    return result


def _format_pf(value: Any) -> str:
    number = float(value)
    return "INF" if math.isinf(number) else f"{number:.2f}"


def print_comparison(reports: dict[str, dict[str, Any]]) -> None:
    print("-")
    print("COMPARACION (todos los resultados incluyen costos simulados)")
    print(
        f"{'Candidata':<24} {'Trades':>7} {'Por dia':>8} "
        f"{'Retorno':>9} {'PF':>7} {'DD max':>9} {'Costos':>10}"
    )
    for key in ("v3_eth", "v4_eth", "v4_portfolio"):
        report = reports[key]
        print(
            f"{report['candidate']:<24} "
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
    trades_by_candidate: dict[str, list[dict[str, Any]]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "v4_comparison_report.json").write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary_fields = [
        "candidate", "symbols", "total_trades", "trades_per_day",
        "winners", "losers", "win_rate", "total_pnl", "return_pct",
        "profit_factor", "max_drawdown_pct", "total_fees",
        "cost_per_trade", "shared_balance", "one_position_at_a_time",
    ]
    with (output_dir / "v4_comparison_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=summary_fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        for report in payload["reports"].values():
            symbols = report.get("symbols", report.get("symbol", ""))
            if isinstance(symbols, list):
                symbols = "+".join(str(symbol) for symbol in symbols)
            writer.writerow({**report, "symbols": symbols})

    fields = [
        "candidate", "symbol", "strategy", "direction", "signal_time",
        "entry_time", "exit_time", "entry_price", "exit_price",
        "stop_price", "target_price", "position_size", "quality_score",
        "risk_budget", "estimated_risk", "estimated_net_reward_risk",
        "leverage", "stop_distance_pct", "target_distance_pct",
        "exposure_pct", "estimated_cost_risk_ratio", "close_reason",
        "holding_minutes", "gross_pnl", "fees", "pnl", "balance",
        "real_order_sent",
    ]
    with (output_dir / "v4_comparison_trades.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for candidate, trades in trades_by_candidate.items():
            for trade in trades:
                writer.writerow({**trade, "candidate": candidate})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comparador PAPER v3 vs v4 intradia."
    )
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--years-ago", type=int, default=3)
    parser.add_argument(
        "--output-dir",
        default="artifacts/v4-comparison",
    )
    return parser.parse_args()


def main() -> None:
    # El bloqueo ocurre antes de descargar mercado o crear artefactos.
    require_paper_mode()
    args = parse_args()
    if not 1 <= args.days <= 365:
        raise ValueError("days debe estar entre 1 y 365.")
    reference_now = reference_now_for_years_ago(args.years_ago)
    evaluation_start = reference_now - timedelta(days=args.days)
    loader = BinanceHistoricalData(timeout=30)
    dataset = HistoricalDataset()
    timelines = {}

    print("=" * 78)
    print("PROJECT EDGE - COMPARADOR v3 vs v4 INTRADIA (SOLO PAPER BACKTEST)")
    print("=" * 78)
    print(f"Periodo: {args.days} dias · bloque {args.years_ago} ano(s) atras")
    print("Datos: velas publicas; entrada en la vela 5M siguiente; sin look-ahead")
    print("Costos: comision 0,10% + deslizamiento 0,02% por lado")
    print("Riesgo: 0,50% maximo, x1; cooldown y proteccion por perdidas")
    print("El runner AUTO v3, los saldos y paper_state.json NO se modifican")

    for symbol in SYMBOLS:
        print(f"Descargando y preparando {symbol}...")
        candles = loader.fetch_recent(
            symbol=symbol,
            interval="5m",
            days=args.days + BACKTEST_WARMUP_DAYS,
            now=reference_now,
        )
        if candles.empty:
            raise RuntimeError(f"Binance no devolvio datos para {symbol}.")
        timeframe_data = dataset.build(candles)
        # v3 y v4 usan exactamente las mismas variables causales; solo cambia
        # la decision. Prepararlas una vez evita diferencias accidentales.
        timelines[symbol] = HistoricalBacktester(
            HistoricalBacktestConfig(
                symbol=symbol,
                strategy="PROJECT_EDGE_V3",
                analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
            )
        ).prepare_timeline(timeframe_data)

    v3 = HistoricalBacktester(
        HistoricalBacktestConfig(
            symbol="ETHUSDT",
            strategy="PROJECT_EDGE_V3",
            analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
        )
    ).run_prepared(timelines["ETHUSDT"], evaluation_start=evaluation_start)
    v4_eth = HistoricalBacktester(
        HistoricalBacktestConfig(
            symbol="ETHUSDT",
            strategy="PROJECT_EDGE_V4_INTRADAY",
            analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
        )
    ).run_prepared(timelines["ETHUSDT"], evaluation_start=evaluation_start)
    portfolio = PortfolioHistoricalBacktester().run_prepared(
        timelines,
        evaluation_start=evaluation_start,
    )

    reports = {
        "v3_eth": _enrich_report(
            v3.report,
            candidate="V3_ETH_ACTUAL",
            requested_days=args.days,
        ),
        "v4_eth": _enrich_report(
            v4_eth.report,
            candidate="V4_ETH_MISMO_ACTIVO",
            requested_days=args.days,
        ),
        "v4_portfolio": _enrich_report(
            portfolio.report,
            candidate="V4_BTC_ETH_UNA_POSICION",
            requested_days=args.days,
        ),
    }
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_days": args.days,
        "years_ago": args.years_ago,
        "reference_now": reference_now.isoformat(),
        "evaluation_start": evaluation_start.isoformat(),
        "mode": "PAPER_BACKTEST_ONLY",
        "real_orders": False,
        "live_strategy_changed": False,
        "paper_state_changed": False,
        "rules_frozen_before_out_of_sample": {
            "direction": "estructura + EMA 1H",
            "macro_4h": "bloquea solo oposicion estructural + EMA clara",
            "confirmation_30m": "sin estructura opuesta",
            "adx_1h_minimum": 30.0,
            "efficiency_1h_minimum": 0.30,
            "pullback": "15M",
            "trigger": "5M, maximo 1 ATR desde EMA20",
            "fvg": "puntuacion, no requisito",
            "risk": "mismo plan v3: 0,5%, x1, SL ATR, objetivo neto",
        },
        "reports": reports,
    }
    write_outputs(
        Path(args.output_dir),
        payload,
        {
            "V3_ETH_ACTUAL": v3.trades,
            "V4_ETH_MISMO_ACTIVO": v4_eth.trades,
            "V4_BTC_ETH_UNA_POSICION": portfolio.trades,
        },
    )
    print_comparison(reports)
    print("-")
    print(f"Reporte: {Path(args.output_dir) / 'v4_comparison_report.json'}")
    print(f"Resumen: {Path(args.output_dir) / 'v4_comparison_summary.csv'}")
    print(f"Trades:  {Path(args.output_dir) / 'v4_comparison_trades.csv'}")
    print("MODO REAL: BLOQUEADO. No se envio ninguna orden ni Telegram.")
    print("=" * 78)


if __name__ == "__main__":
    main()
