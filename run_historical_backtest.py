"""
PROJECT EDGE - Backtest histórico de la estrategia propia v3

Descarga velas públicas 5M, construye temporalidades cerradas y ejecuta
un backtest walk-forward de las señales AUTO. Genera JSON y CSV.

No usa claves privadas ni ejecuta órdenes reales.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from engine.data.binance_historical_data import BinanceHistoricalData
from engine.data.historical_dataset import HistoricalDataset
from engine.execution.backtest_report import BacktestReport
from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktestResult,
    HistoricalBacktester,
)
from trading_mode import require_paper_mode


DEFAULT_SYMBOLS = ("ETHUSDT",)
BACKTEST_WARMUP_DAYS = 90
LIVE_ANALYSIS_WINDOW_BARS = 500


def reference_now_for_years_ago(
    years_ago: int,
    current: datetime | None = None,
) -> datetime:
    """Fija el final de un bloque histórico sin cambiar la estrategia."""
    years_ago = int(years_ago)
    if not 0 <= years_ago <= 5:
        raise ValueError("years_ago debe estar entre 0 y 5.")

    reference = current or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)

    return reference - timedelta(days=365 * years_ago)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _max_drawdown_pct(
    trades: list[dict[str, Any]],
    initial_balance: float,
) -> float:
    equity = initial_balance
    peak = equity
    maximum = 0.0

    for trade in trades:
        equity += float(trade["pnl"])
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, (peak - equity) / peak)

    return maximum


def combined_report(
    results: dict[str, HistoricalBacktestResult],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trades = [
        trade
        for result in results.values()
        for trade in result.trades
    ]
    trades.sort(key=lambda trade: str(trade["exit_time"]))

    initial_balance = sum(
        float(result.report["initial_balance"])
        for result in results.values()
    )
    final_balance = sum(
        float(result.report["final_balance"])
        for result in results.values()
    )
    metrics = BacktestReport().generate(trades=trades)

    return (
        {
            "symbols": list(results),
            "mode": "PAPER_BACKTEST",
            "source": "AUTO_ONLY",
            "manual_trades_included": False,
            "initial_balance": initial_balance,
            "final_balance": final_balance,
            "return_pct": final_balance / initial_balance - 1.0,
            "max_drawdown_pct": _max_drawdown_pct(trades, initial_balance),
            "total_fees": sum(float(trade["fees"]) for trade in trades),
            "ready_signals": sum(
                int(result.report["ready_signals"])
                for result in results.values()
            ),
            **metrics,
        },
        trades,
    )


def write_outputs(
    output_dir: Path,
    payload: dict[str, Any],
    trades: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "backtest_report.json"
    csv_path = output_dir / "backtest_trades.csv"

    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    fields = [
        "symbol",
        "source",
        "mode",
        "direction",
        "signal_time",
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "stop_price",
        "target_price",
        "position_size",
        "strategy",
        "risk_budget",
        "estimated_risk",
        "estimated_net_reward_risk",
        "leverage",
        "close_reason",
        "gross_pnl",
        "fees",
        "pnl",
        "balance",
        "real_order_sent",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)


def _format_profit_factor(value: Any) -> str:
    number = float(value)
    if math.isinf(number):
        return "INF"
    return f"{number:.2f}"


def print_report(report: dict[str, Any]) -> None:
    print(f"Operaciones:       {report['total_trades']}")
    print(f"Ganadas/perdidas:  {report['winners']} / {report['losers']}")
    print(f"Win rate:          {float(report['win_rate']) * 100:.2f}%")
    print(f"PnL neto:          {float(report['total_pnl']):.2f} USDT")
    print(f"Retorno:           {float(report['return_pct']) * 100:.2f}%")
    print(f"Drawdown máximo:   {float(report['max_drawdown_pct']) * 100:.2f}%")
    print(f"Profit factor:     {_format_profit_factor(report['profit_factor'])}")
    print(f"Costos incluidos:  {float(report['total_fees']):.2f} USDT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest walk-forward PAPER de PROJECT EDGE."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Cantidad de días históricos (1 a 365).",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=list(DEFAULT_SYMBOLS),
        help="Símbolos públicos de Binance.",
    )
    parser.add_argument(
        "--years-ago",
        type=int,
        default=0,
        help=(
            "Desplaza el bloque completo hacia atrás en años de 365 días "
            "(0 a 5)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/backtest",
        help="Carpeta para el reporte JSON y el detalle CSV.",
    )
    return parser.parse_args()


def main() -> None:
    require_paper_mode()
    args = parse_args()
    if not 1 <= args.days <= 365:
        raise ValueError("days debe estar entre 1 y 365.")
    reference_now = reference_now_for_years_ago(args.years_ago)
    loader = BinanceHistoricalData(timeout=30)
    dataset = HistoricalDataset()
    results: dict[str, HistoricalBacktestResult] = {}

    print("=" * 68)
    print("PROJECT EDGE v3 - BACKTEST HISTÓRICO AUTO PAPER")
    print("=" * 68)
    print(f"Período solicitado: {args.days} días")
    print(f"Bloque desplazado:  {args.years_ago} año(s) hacia atrás")
    print(f"Fecha de referencia: {reference_now.isoformat()}")
    print("Metodología: walk-forward, entrada en vela siguiente, sin look-ahead")
    print("Costos: comisión 0.10% y deslizamiento 0.02% por lado")
    print("Riesgo: 0.50% por trade, sin apalancamiento, SL por ATR")
    print("Protecciones: cooldown 30m y pausa 4h tras 3 pérdidas")
    print(
        "Consistencia: 90 días de calentamiento y ventana estructural "
        "de 500 velas"
    )
    print("Operaciones MANUALES: excluidas")

    for raw_symbol in args.symbols:
        symbol = str(raw_symbol).upper().replace("/", "")
        print("-")
        print(f"Descargando velas públicas de {symbol}...")
        candles_5m = loader.fetch_recent(
            symbol=symbol,
            interval="5m",
            days=args.days + BACKTEST_WARMUP_DAYS,
            now=reference_now,
        )
        if candles_5m.empty:
            raise RuntimeError(f"Binance no devolvió datos para {symbol}.")

        timeframe_data = dataset.build(candles_5m)
        backtester = HistoricalBacktester(
            HistoricalBacktestConfig(
                symbol=symbol,
                analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
            )
        )
        evaluation_start = (
            pd.Timestamp(candles_5m["open_time"].max())
            - pd.Timedelta(days=args.days)
        )
        result = backtester.run(
            timeframe_data,
            evaluation_start=evaluation_start,
        )
        results[symbol] = result

        print(f"RESULTADO {symbol}")
        print_report(result.report)

    combined, trades = combined_report(results)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_days": args.days,
        "years_ago": args.years_ago,
        "reference_now": reference_now.isoformat(),
        "methodology": {
            "type": "walk_forward_project_edge_v3",
            "parameter_policy": "fixed_project_edge_v3_no_optimization",
            "signal_time": "cierre de vela 5M",
            "entry_time": "apertura de la siguiente vela 5M",
            "intrabar_policy": "STOP primero si STOP y TARGET coinciden",
            "fee_rate_per_side": 0.001,
            "slippage_rate_per_side": 0.0002,
            "manual_trades_included": False,
            "real_orders": False,
            "auto_symbol": "ETHUSDT",
            "risk_pct": 0.005,
            "leverage": 1,
            "warmup_days": BACKTEST_WARMUP_DAYS,
            "analysis_window_bars": LIVE_ANALYSIS_WINDOW_BARS,
        },
        "symbols": {
            symbol: result.report
            for symbol, result in results.items()
        },
        "combined": combined,
    }
    write_outputs(Path(args.output_dir), payload, trades)

    print("=" * 68)
    print("RESULTADO COMBINADO")
    print_report(combined)
    print("-")
    print(f"Reporte: {Path(args.output_dir) / 'backtest_report.json'}")
    print(f"Trades:  {Path(args.output_dir) / 'backtest_trades.csv'}")
    print("MODO REAL: BLOQUEADO. No se envió ninguna orden.")
    print("=" * 68)


if __name__ == "__main__":
    main()
