"""Compara v3 actual contra v3 con salida protegida, sin tocar el AUTO PAPER."""

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
from engine.execution.v3_protected_exit_backtest import (
    V3ProtectedExitHistoricalBacktester,
)
from run_historical_backtest import (
    BACKTEST_WARMUP_DAYS,
    LIVE_ANALYSIS_WINDOW_BARS,
    reference_now_for_years_ago,
)
from trading_mode import require_paper_mode


SYMBOL = "ETHUSDT"


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _enrich(
    report: dict[str, Any],
    trades: list[dict[str, Any]],
    *,
    candidate: str,
    days: int,
) -> dict[str, Any]:
    result = dict(report)
    result["candidate"] = candidate
    result["trades_per_day"] = float(result.get("total_trades", 0)) / days
    result["tp1_reached"] = sum(bool(t.get("tp1_reached")) for t in trades)
    result["tp2_reached"] = sum(bool(t.get("tp2_reached")) for t in trades)
    result["protected_stop_exits"] = sum(
        str(t.get("close_reason", "")).startswith("PROTECTED_")
        for t in trades
    )
    result["protected_nonnegative_exits"] = sum(
        str(t.get("close_reason", "")).startswith("PROTECTED_")
        and float(t.get("pnl", 0.0)) >= -1e-9
        for t in trades
    )
    return result


def _matched_losses_avoided(
    baseline: list[dict[str, Any]],
    protected: list[dict[str, Any]],
) -> int:
    baseline_by_signal = {
        (str(t.get("signal_time")), str(t.get("direction"))): t
        for t in baseline
    }
    avoided = 0
    for trade in protected:
        key = (str(trade.get("signal_time")), str(trade.get("direction")))
        original = baseline_by_signal.get(key)
        if original is None:
            continue
        if float(original.get("pnl", 0.0)) < 0 and float(trade.get("pnl", 0.0)) >= 0:
            avoided += 1
    return avoided


def _format_pf(value: Any) -> str:
    number = float(value)
    return "INF" if math.isinf(number) else f"{number:.2f}"


def write_outputs(
    output_dir: Path,
    payload: dict[str, Any],
    trades_by_candidate: dict[str, list[dict[str, Any]]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "v3_protected_exit_report.json").write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary_fields = [
        "candidate", "symbol", "total_trades", "trades_per_day",
        "winners", "losers", "win_rate", "total_pnl", "return_pct",
        "profit_factor", "max_drawdown_pct", "total_fees",
        "tp1_reached", "tp2_reached", "protected_stop_exits",
        "protected_nonnegative_exits", "matched_baseline_losses_avoided",
    ]
    with (output_dir / "v3_protected_exit_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=summary_fields, extrasaction="ignore")
        writer.writeheader()
        for report in payload["reports"].values():
            writer.writerow(report)

    trade_fields = [
        "candidate", "symbol", "strategy", "direction", "signal_time",
        "entry_time", "exit_time", "entry_price", "exit_price",
        "stop_price", "target_price", "tp1_price", "tp2_price",
        "tp1_reached", "tp2_reached", "protected_stop_stage",
        "protected_stop_price", "close_reason", "holding_minutes",
        "gross_pnl", "fees", "pnl", "balance", "real_order_sent",
    ]
    with (output_dir / "v3_protected_exit_trades.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=trade_fields, extrasaction="ignore")
        writer.writeheader()
        for candidate, trades in trades_by_candidate.items():
            for trade in trades:
                writer.writerow({**trade, "candidate": candidate})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comparador PAPER v3 actual vs v3 con salida protegida."
    )
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--years-ago", type=int, default=0)
    parser.add_argument("--output-dir", default="artifacts/v3-protected-exit")
    return parser.parse_args()


def main() -> None:
    require_paper_mode()
    args = parse_args()
    if not 1 <= args.days <= 365:
        raise ValueError("days debe estar entre 1 y 365.")

    reference_now = reference_now_for_years_ago(args.years_ago)
    evaluation_start = reference_now - timedelta(days=args.days)
    loader = BinanceHistoricalData(timeout=30)
    dataset = HistoricalDataset()

    candles = loader.fetch_recent(
        symbol=SYMBOL,
        interval="5m",
        days=args.days + BACKTEST_WARMUP_DAYS,
        now=reference_now,
    )
    if candles.empty:
        raise RuntimeError(f"Binance no devolvió datos para {SYMBOL}.")
    timeframe_data = dataset.build(candles)

    base_config = HistoricalBacktestConfig(
        symbol=SYMBOL,
        strategy="PROJECT_EDGE_V3",
        analysis_window_bars=LIVE_ANALYSIS_WINDOW_BARS,
    )
    timeline = HistoricalBacktester(base_config).prepare_timeline(timeframe_data)

    baseline = HistoricalBacktester(base_config).run_prepared(
        timeline, evaluation_start=evaluation_start
    )
    protected = V3ProtectedExitHistoricalBacktester(base_config).run_prepared(
        timeline, evaluation_start=evaluation_start
    )

    reports = {
        "baseline": _enrich(
            baseline.report, baseline.trades, candidate="V3_ACTUAL", days=args.days
        ),
        "protected": _enrich(
            protected.report,
            protected.trades,
            candidate="V3_PROTECTED_EXIT",
            days=args.days,
        ),
    }
    reports["protected"]["matched_baseline_losses_avoided"] = _matched_losses_avoided(
        baseline.trades, protected.trades
    )

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
        "entry_logic_changed": False,
        "risk_plan_changed": False,
        "protected_exit_rules": {
            "tp1": "50% del recorrido entrada-TP3; mover SL a break-even neto de costos",
            "tp2": "75% del recorrido entrada-TP3; mover SL a TP1",
            "tp3": "objetivo final v3 sin cambios",
            "intrabar": "si stop y objetivo coinciden, se asume stop primero",
        },
        "reports": reports,
    }

    output_dir = Path(args.output_dir)
    write_outputs(
        output_dir,
        payload,
        {"V3_ACTUAL": baseline.trades, "V3_PROTECTED_EXIT": protected.trades},
    )

    print("=" * 88)
    print("PROJECT EDGE - v3 ACTUAL vs v3 SALIDA PROTEGIDA (SOLO PAPER BACKTEST)")
    print("=" * 88)
    print(f"Periodo: {args.days} dias · bloque {args.years_ago} ano(s) atras")
    print("Entradas y riesgo: identicos a v3; solo cambia la gestion tras TP1/TP2")
    print("TP1 -> break-even + costos · TP2 -> SL en TP1 · TP3 -> cierre final")
    print("-")
    print(
        f"{'Candidata':<22} {'Trades':>7} {'Retorno':>9} "
        f"{'PF':>7} {'DD max':>9} {'Costos':>10}"
    )
    for key in ("baseline", "protected"):
        report = reports[key]
        print(
            f"{report['candidate']:<22} "
            f"{int(report['total_trades']):>7} "
            f"{float(report['return_pct']) * 100:>8.2f}% "
            f"{_format_pf(report['profit_factor']):>7} "
            f"{float(report['max_drawdown_pct']) * 100:>8.2f}% "
            f"{float(report['total_fees']):>10.2f}"
        )
    print("-")
    print(
        "Protecciones: "
        f"TP1={reports['protected']['tp1_reached']} · "
        f"TP2={reports['protected']['tp2_reached']} · "
        f"salidas protegidas={reports['protected']['protected_stop_exits']} · "
        f"pérdidas baseline evitadas={reports['protected']['matched_baseline_losses_avoided']}"
    )
    print(f"Reporte: {output_dir / 'v3_protected_exit_report.json'}")
    print(f"Resumen: {output_dir / 'v3_protected_exit_summary.csv'}")
    print(f"Trades: {output_dir / 'v3_protected_exit_trades.csv'}")
    print("REAL: BLOQUEADO. No se modificaron saldos, runner AUTO ni Telegram.")
    print("=" * 88)


if __name__ == "__main__":
    main()
