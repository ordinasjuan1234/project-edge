"""Comparador historico v3 vs PROJECT EDGE v6-SCALP.

Descarga un bloque historico publico y compara:
1) v3 actual sobre ETHUSDT;
2) v6-SCALP sobre ETHUSDT;
3) v6-SCALP BTCUSDT+ETHUSDT con saldo compartido y una sola posicion.

No modifica el runner AUTO vigente, no usa saldos reales y no envia ordenes.
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
from engine.execution.v6_historical_backtest import (
    V6HistoricalBacktester,
    V6PortfolioHistoricalBacktester,
)
from run_historical_backtest import (
    BACKTEST_WARMUP_DAYS,
    LIVE_ANALYSIS_WINDOW_BARS,
    reference_now_for_years_ago,
)
from trading_mode import require_paper_mode


SYMBOLS = ("BTCUSDT", "ETHUSDT")
INITIAL_BALANCE = 10000.0
V6_RISK_PCT = 0.003
V6_COOLDOWN_MINUTES = 30
V6_LOSS_GUARD_MINUTES = 180
V6_MAX_HOLDING_MINUTES = 240


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
        float(result.get("total_trades", 0)) / float(requested_days)
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
    print("COMPARACION v3 vs v6-SCALP (costos simulados incluidos)")
    print(
        f"{'Candidata':<24} {'Trades':>7} {'Por dia':>8} "
        f"{'Retorno':>9} {'PF':>7} {'DD max':>9} {'Costos':>10}"
    )
    for key in ("v3_eth", "v6_eth", "v6_portfolio"):
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
    (output_dir / "v6_comparison_report.json").write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary_fields = [
        "candidate",
        "symbol",
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
    ]
    with (output_dir / "v6_comparison_summary.csv").open(
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
        for report in payload["reports"].values():
            row = dict(report)
            if isinstance(row.get("symbols"), list):
                row["symbols"] = "+".join(row["symbols"])
            writer.writerow(row)

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
        "close_reason",
        "holding_minutes",
        "gross_pnl",
        "fees",
        "pnl",
        "balance",
        "real_order_sent",
    ]
    with (output_dir / "v6_comparison_trades.csv").open(
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
        for candidate, trades in trades_by_candidate.items():
            for trade in trades:
                writer.writerow({**trade, "candidate": candidate})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comparador historico PAPER v3 vs v6-SCALP."
    )
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--years-ago", type=int, default=2)
    parser.add_argument(
        "--output-dir",
        default="artifacts/v6-comparison",
    )
    return parser.parse_args()


def main() -> None:
    # Debe bloquear REAL antes de mercado, archivos o cualquier simulacion.
    require_paper_mode()
    args = parse_args()
    if not 1 <= args.days <= 365:
        raise ValueError("days debe estar entre 1 y 365.")

    reference_now = reference_now_for_years_ago(args.years_ago)
    evaluation_start = reference_now - timedelta(days=args.days)
    loader = BinanceHistoricalData(timeout=30)
    dataset = HistoricalDataset()

    timeframe_data: dict[str, dict[str, Any]] = {}
    v6_timelines: dict[str, Any] = {}

    print("=" * 78)
    print("PROJECT EDGE - COMPARADOR v3 vs v6-SCALP (SOLO PAPER)")
    print("=" * 78)
    print(f"Periodo: {args.days} dias · bloque {args.years_ago} ano(s) atras")
    print("Mercado: BTCUSDT + ETHUSDT · velas cerradas · sin look-ahead")
    print("Costos: comision 0,10% + deslizamiento 0,02% por lado")
    print("v6.1: riesgo 0,30% · x1 · maximo 4h · cooldown 30m")
    print("El AUTO vigente, paper_state.json y los saldos NO se modifican")

    for symbol in SYMBOLS:
        print(f"Descargando {symbol}...")
        candles = loader.fetch_recent(
            symbol=symbol,
            interval="5m",
            days=args.days + BACKTEST_WARMUP_DAYS,
            now=reference_now,
        )
        if candles.empty:
            raise RuntimeError(f"Binance no devolvio datos para {symbol}.")
        timeframe_data[symbol] = dataset.build(candles)
        v6_timelines[symbol] = V6HistoricalBacktester(
            symbol,
            initial_balance=INITIAL_BALANCE,
            risk_pct=V6_RISK_PCT,
            cooldown_minutes=V6_COOLDOWN_MINUTES,
            loss_guard_minutes=V6_LOSS_GUARD_MINUTES,
            analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
            max_holding_minutes=V6_MAX_HOLDING_MINUTES,
        ).prepare_timeline(timeframe_data[symbol])

    v3_backtester = HistoricalBacktester(
        HistoricalBacktestConfig(
            symbol="ETHUSDT",
            initial_balance=INITIAL_BALANCE,
            strategy="PROJECT_EDGE_V3",
            analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
        )
    )
    v3_eth = v3_backtester.run_prepared(
        v3_backtester.prepare_timeline(timeframe_data["ETHUSDT"]),
        evaluation_start=evaluation_start,
    )

    v6_eth = V6HistoricalBacktester(
        "ETHUSDT",
        initial_balance=INITIAL_BALANCE,
        risk_pct=V6_RISK_PCT,
        cooldown_minutes=V6_COOLDOWN_MINUTES,
        loss_guard_minutes=V6_LOSS_GUARD_MINUTES,
        analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
        max_holding_minutes=V6_MAX_HOLDING_MINUTES,
    ).run_prepared(
        v6_timelines["ETHUSDT"],
        evaluation_start=evaluation_start,
    )

    v6_portfolio = V6PortfolioHistoricalBacktester(
        initial_balance=INITIAL_BALANCE,
        risk_pct=V6_RISK_PCT,
        cooldown_minutes=V6_COOLDOWN_MINUTES,
        loss_guard_minutes=V6_LOSS_GUARD_MINUTES,
        analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
        max_holding_minutes=V6_MAX_HOLDING_MINUTES,
    ).run_prepared(
        v6_timelines,
        evaluation_start=evaluation_start,
    )

    reports = {
        "v3_eth": _enrich_report(
            v3_eth.report,
            candidate="V3_ETH_ACTUAL",
            requested_days=args.days,
        ),
        "v6_eth": _enrich_report(
            v6_eth.report,
            candidate="V6_ETH_SCALP",
            requested_days=args.days,
        ),
        "v6_portfolio": _enrich_report(
            v6_portfolio.report,
            candidate="V6_BTC_ETH_SCALP",
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
        "rules_frozen_before_test": {
            "context": "EMA20/50 + pendiente 1H alineadas; estructura 1H no opuesta",
            "macro_4h": (
                "solo veto si estructura y EMA 4H estan fuertemente opuestas"
            ),
            "setup_a": "SCALP_PULLBACK en 15M con EMA y pendiente alineadas",
            "setup_b": "SCALP_MOMENTUM en 15M",
            "adx_15m": ">=22 y (creciente o >=30)",
            "trigger": "5M obligatorio y no extendido >0,75 ATR",
            "fvg": "solo confluencia; no es requisito de entrada",
            "risk": "0,30% por operacion, x1; stop minimo 0,60%; costo/riesgo max 30%",
            "time_exit": "240 minutos maximo",
            "cooldown": "30 minutos",
            "loss_guard": "3 perdidas consecutivas -> pausa 180 minutos",
        },
        "initial_acceptance_targets": {
            "net_return_gt": 0.0,
            "profit_factor_gte": 1.15,
            "max_drawdown_lte": 0.10,
            "portfolio_trades_per_day_gte": 0.50,
            "portfolio_trades_per_day_lte": 3.00,
        },
        "reports": reports,
    }

    write_outputs(
        Path(args.output_dir),
        payload,
        {
            "V3_ETH_ACTUAL": v3_eth.trades,
            "V6_ETH_SCALP": v6_eth.trades,
            "V6_BTC_ETH_SCALP": v6_portfolio.trades,
        },
    )
    print_comparison(reports)
    print("-")
    print(f"Reporte: {Path(args.output_dir) / 'v6_comparison_report.json'}")
    print(f"Resumen: {Path(args.output_dir) / 'v6_comparison_summary.csv'}")
    print(f"Trades:  {Path(args.output_dir) / 'v6_comparison_trades.csv'}")
    print("REAL: BLOQUEADO. No se envio ninguna orden.")
    print("=" * 78)


if __name__ == "__main__":
    main()
