"""Solo formateo y simulaciones temporales: nunca envía Telegram ni usa mercado."""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest

import build_live_dashboard
from paper_state import PaperState
import telegram_notifier as notifier


def closed_trade(**changes):
    trade = {
        "source": "MANUAL", "trade_id": "test-only",
        "symbol": "BTCUSDT", "direction": "LONG",
        "entry_price": 100.0, "exit_price": 101.0,
        "capital": 100.0, "leverage": 1, "exposure": 100.0,
        "pnl": 1.0, "final_leg_pnl": 1.0, "balance": 10001.0,
        "gross_pnl": 1.0, "fees": 0.0, "fee_rate": 0.0, "slippage_rate": 0.0,
        "reason": "TAKE_PROFIT", "closed_at": "2026-08-30T15:00:00+00:00",
    }
    trade.update(changes)
    return trade


@pytest.mark.parametrize("capital,leverage,entry,exit_price,pnl_text,return_text", [
    (100, 1, 77987.45, 78900, "+1,1701", "+1,17"),
    (10, 2, 77633.19, 77840.01, "+0,0533", "+0,53"),
    (10, 2, 77843.43, 77650, "-0,0497", "-0,50"),
    (100, 3, 77698, 77600, "-0,3784", "-0,38"),
])
def test_user_examples_report_result_capital_multiplier_and_exposure(
    capital, leverage, entry, exit_price, pnl_text, return_text
):
    exposure = capital * leverage
    pnl = (exit_price - entry) / entry * exposure
    message = notifier.format_manual_exit_message(closed_trade(
        capital=capital, leverage=leverage, exposure=exposure,
        entry_price=entry, exit_price=exit_price, pnl=pnl,
        final_leg_pnl=pnl, balance=9943.64 + pnl,
    ))
    assert ("GANASTE" if pnl > 0 else "PERDISTE") + f": {pnl_text} USDT" in message
    assert f"Rendimiento sobre capital utilizado: {return_text}%" in message
    assert f"Capital utilizado: {capital},00 USDT" in message
    assert f"Apalancamiento: x{leverage}" in message
    assert f"Exposición: {exposure},00 USDT" in message
    assert "Saldo MANUAL / legado antes → después: 9.943,64 →" in message
    assert "Sin comisiones ni deslizamiento simulados" in message
    assert "neto" not in message


@pytest.mark.parametrize("pnl,reason,direction,expected", [
    (1, "STOP_LOSS", "SHORT", "🟢"),
    (-1, "TAKE_PROFIT", "LONG", "🔴"),
    (0, "MANUAL_CLOSE", "LONG", "⚪"),
    (-0.0, "MANUAL_CLOSE", "SHORT", "⚪"),
])
def test_result_color_depends_on_pnl_not_direction_or_exit_reason(pnl, reason, direction, expected):
    message = notifier.format_manual_exit_message(closed_trade(
        pnl=pnl, final_leg_pnl=pnl, balance=10000 + pnl,
        reason=reason, direction=direction,
    ))
    assert message.startswith(expected)
    if pnl == 0:
        assert "SIN GANANCIA NI PÉRDIDA: 0,0000 USDT" in message
        assert "-0,0000" not in message
    if reason == "STOP_LOSS":
        assert "STOP LOSS · stop alcanzado" in message
        assert "corte de pérdida" not in message


def test_manual_close_of_auto_position_keeps_auto_account_and_included_fees():
    trade = closed_trade(source="AUTO", pnl=-0.36, final_leg_pnl=-0.36,
                         balance=785.18, gross_pnl=0.11, fees=0.47,
                         fee_rate=0.001, slippage_rate=0.0002,
                         reason="MANUAL_CLOSE")
    message = notifier.format_manual_exit_message(trade)
    assert "SALIDA AUTO PAPER" in message
    assert "PERDISTE: -0,3600 USDT" in message
    assert "Comisión simulada: -0,4700 USDT (ya descontada)" in message
    assert "Deslizamiento simulado: 0,0200% por lado (ya aplicado en los precios)" in message
    assert "Saldo AUTO DEMO antes → después: 785,54 → 785,18 USDT" in message
    assert "Saldo MANUAL" not in message


def test_zero_commission_does_not_hide_simulated_slippage():
    message = notifier.format_auto_exit_message(closed_trade(source="AUTO", slippage_rate=0.0002))
    assert "Comisión simulada: 0,0000 USDT" in message
    assert "ya aplicado en los precios" in message
    assert "Sin comisiones ni deslizamiento" not in message


@pytest.mark.parametrize("invalid", [None, "", "incorrecto", float("nan"), float("inf")])
def test_legacy_missing_amounts_are_not_invented(invalid):
    trade = {"source": "MANUAL", "pnl": 1.0, "balance": 10001.0, "capital": invalid}
    message = notifier.format_manual_exit_message(trade)
    assert "GANASTE: +1,0000 USDT" in message
    assert "Rendimiento sobre capital utilizado" not in message
    assert "Capital utilizado" not in message
    assert "Comisiones: no informadas" in message
    assert "Deslizamiento: no informado" in message
    assert "Sin comisiones ni deslizamiento" not in message
    assert "neto" not in message


def test_missing_pnl_is_not_reported_as_break_even():
    message = notifier.format_manual_exit_message({"balance": 123.0})
    assert "RESULTADO NO DISPONIBLE" in message
    assert "SIN GANANCIA NI PÉRDIDA" not in message
    assert "antes → después" not in message


def test_unclassified_legacy_records_do_not_claim_manual_or_auto():
    message = notifier.format_manual_exit_message(closed_trade(source="UNCLASSIFIED"))
    assert "SALIDA ORIGEN SIN CLASIFICAR PAPER" in message
    assert "Saldo PAPER (origen sin clasificar)" in message
    message = notifier.format_manual_exit_message({"pnl": 1, "balance": 10001})
    assert "SALIDA ORIGEN SIN CLASIFICAR PAPER" in message


@pytest.mark.parametrize("pnl,expected", [(0.000001, "+0,000001"), (-0.000001, "-0,000001")])
def test_small_results_keep_their_sign_without_rounding_to_zero(pnl, expected):
    message = notifier.format_manual_exit_message(closed_trade(pnl=pnl, final_leg_pnl=pnl))
    assert expected + " USDT" in message


def test_final_close_after_partials_reports_only_final_balance_change():
    trade = closed_trade(pnl=7.0, final_leg_pnl=-3.0, balance=10007.0,
                         partial_count=1, realized_pnl_before_final=10.0)
    message = notifier.format_manual_exit_message(trade)
    assert "GANASTE: +7,0000 USDT" in message
    assert "Ya contabilizado en parciales: +10,0000 USDT" in message
    assert "Saldo MANUAL / legado antes → después: 10.010,00 → 10.007,00" in message
    assert "Cambio de saldo en este cierre: -3,0000 USDT" in message
    assert "Resultado TOTAL de la operación" in message
    assert "Salida final:" in message


def test_legacy_partials_without_final_leg_do_not_invent_previous_balance():
    trade = {"source": "MANUAL", "pnl": 7, "balance": 10007, "partial_count": 1}
    message = notifier.format_manual_exit_message(trade)
    assert "Saldo MANUAL / legado: 10.007,00" in message
    assert "antes → después" not in message
    trade["realized_pnl_before_final"] = 10
    message = notifier.format_manual_exit_message(trade)
    assert "10.010,00 → 10.007,00" in message


def test_entry_explains_accounts_costs_and_auto_x1_quantity():
    position = {"source": "AUTO", "symbol": "ETHUSDT", "direction": "SHORT",
                "entry_price": 2500.0, "quantity": 0.2,
                "fee_rate": 0.001, "slippage_rate": 0.0002}
    message = notifier.format_auto_entry_message(position, balance=1000)
    assert "Capital utilizado: 500,00 USDT" in message
    assert "Exposición: 500,00 USDT" in message
    assert "Apalancamiento: x1" in message
    assert "Saldo AUTO DEMO: 1.000,00 USDT" in message
    assert "0,1000% por lado; se descuenta al cerrar" in message
    assert "SHORT" in message
    assert "El capital utilizado no es la ganancia" in message


def test_partial_round_trip_preserves_balances_and_only_counts_one_trade(tmp_path):
    state = PaperState(file_path=tmp_path / "state.json")
    pos = state.open_position("BTCUSDT", "LONG", 100, 3, 90, 120, source="MANUAL")
    pos.update(capital=100, initial_capital=100, leverage=3, exposure=300, initial_exposure=300)
    state.save()
    partial = state.partial_close_position(110, 50, "PARTIAL_CLOSE_50")
    original = deepcopy(partial)
    message = notifier.format_manual_action_message("PARTIAL_CLOSE", partial, partial["balance"])
    assert "GANASTE EN ESTE PARCIAL: +15,0000 USDT" in message
    assert "Capital de la parte cerrada: 50,00 USDT" in message
    assert "Rendimiento sobre capital de la parte cerrada: +30,00%" in message
    assert "50% de lo que seguía abierto" in message
    assert "10.000,00 → 10.015,00" in message
    assert "Sin comisiones ni deslizamiento simulados" in message
    assert partial == original
    assert state.status()["closed_trades"] == 0
    final = state.close_position(98, "MANUAL_CLOSE")
    original = deepcopy(final)
    message = notifier.format_manual_exit_message(final)
    assert "GANASTE: +12,0000 USDT" in message
    assert "Rendimiento sobre capital utilizado: +12,00%" in message
    assert "10.015,00 → 10.012,00" in message
    assert final == original
    assert state.balance == pytest.approx(10012)
    assert state.auto_demo_balance == pytest.approx(1000)
    assert state.status()["closed_trades"] == 1
    assert PaperState(file_path=tmp_path / "state.json").balance == pytest.approx(10012)


def test_auto_paper_cost_metadata_and_messages_do_not_change_execution(tmp_path):
    state = PaperState(file_path=tmp_path / "state.json")
    state.open_position("ETHUSDT", "LONG", 100, 1, 90, 110,
                        source="AUTO", fee_rate=0.001, slippage_rate=0.001)
    partial = state.partial_close_position(110, 50, "PARTIAL_CLOSE_50")
    final = state.close_position(110, "TAKE_PROFIT")
    expected = (109.89 - 100.1) - (100.1 + 109.89) * 0.001
    assert partial["source"] == final["source"] == "AUTO"
    assert partial["fee_rate"] == final["fee_rate"] == 0.001
    assert partial["slippage_rate"] == final["slippage_rate"] == 0.001
    assert final["pnl"] == pytest.approx(expected)
    assert state.auto_demo_balance == pytest.approx(1000 + expected)
    assert state.balance == pytest.approx(10000)
    assert "CIERRE PARCIAL AUTO PAPER" in notifier.format_manual_action_message("PARTIAL_CLOSE", partial)
    assert "Comisión simulada: -0,2100 USDT (ya descontada)" in notifier.format_auto_exit_message(final)


def test_daily_summary_reports_closed_trades_costs_and_no_duplicate_deduction():
    trades = [closed_trade(), closed_trade(source="AUTO", pnl=-0.36, fees=0.47, slippage_rate=0.0002),
              {"pnl": 2, "source": "MANUAL", "closed_at": "2026-08-30T18:00:00+00:00"}]
    original = deepcopy(trades)
    summary = notifier.calculate_daily_summary(trades, date(2026, 8, 30))
    assert summary["all"]["pnl"] == pytest.approx(2.64)
    assert summary["all"]["fees"] == pytest.approx(0.47)
    assert summary["all"]["without_costs"] == 1
    assert summary["all"]["unknown_costs"] == 1
    message = notifier.format_daily_summary_message(summary, 999.64, 10003)
    assert "TOTAL: 3 operaciones cerradas · 2 ganadas / 1 perdida" in message
    assert "GANANCIA: +2,6400 USDT" in message
    assert "PÉRDIDA: -0,3600 USDT" in message
    assert "Comisiones registradas: -0,4700 USDT (ya descontadas)" in message
    assert "1 cierre sin comisiones ni deslizamiento" in message
    assert "1 cierre con información de costos incompleta" in message
    assert "Saldos actuales al enviar" in message
    assert "Se cuentan cierres, no entradas" in message
    assert trades == original


def test_empty_day_does_not_claim_profit():
    summary = notifier.calculate_daily_summary([], date(2026, 8, 30))
    message = notifier.format_daily_summary_message(summary, 1000, 10000)
    assert message.count("Sin operaciones cerradas; resultado: 0,0000 USDT.") == 3
    assert "GANANCIA:" not in message
    assert "Comisiones registradas:" not in message


def test_day_with_break_even_closures_is_not_an_empty_day():
    summary = notifier.calculate_daily_summary([closed_trade(pnl=0)], date(2026, 8, 30))
    assert summary["manual"]["breakeven"] == 1
    message = notifier.format_daily_summary_message(summary, 1000, 10000)
    assert "MANUAL: 1 operación cerrada · 0 ganadas / 0 perdidas · 1 sin ganancia/pérdida" in message
    assert "⚪ SIN GANANCIA NI PÉRDIDA: 0,0000 USDT" in message


def test_summary_counts_partials_only_on_the_full_close_day():
    trade = closed_trade(pnl=7, partial_count=1, partial_closes=[
        {"pnl": 10, "closed_at": "2026-08-29T18:00:00+00:00"}
    ], realized_pnl_before_final=10, final_leg_pnl=-3)
    assert notifier.calculate_daily_summary([trade], date(2026, 8, 29))["all"]["total"] == 0
    summary = notifier.calculate_daily_summary([trade], date(2026, 8, 30))
    assert summary["all"]["total"] == 1
    assert summary["all"]["pnl"] == 7


def test_limit_message_distinguishes_pending_from_executed():
    message = notifier.format_manual_action_message("LIMIT_CREATED", {
        "source": "MANUAL", "symbol": "BTCUSDT", "direction": "SHORT",
        "capital": 10, "leverage": 2, "exposure": 20, "limit_price": 100,
    }, balance=1000)
    assert "PENDIENTE: todavía no es una entrada ejecutada" in message
    assert "Capital utilizado: 10,00 USDT" in message
    assert "Saldo MANUAL / legado: 1.000,00 USDT" in message


def test_dashboard_uses_full_history_count_but_keeps_recent_ten(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = PaperState()
    # Producir historia SOLO en el directorio temporal de tests.
    for index in range(14):
        state.open_position("ETHUSDT", "LONG", 100, 1, 90, 110, source="MANUAL")
        state.close_position(101 if index % 2 else 99, "MANUAL_CLOSE")
    for _ in range(6):
        state.open_position("ETHUSDT", "LONG", 100, 1, 90, 110, source="UNCLASSIFIED")
        state.close_position(100, "MANUAL_CLOSE")
    monkeypatch.setattr(build_live_dashboard, "build_manual_scanner", lambda: {
        "ETHUSDT": {"symbol": "ETHUSDT", "price": 100.0},
        "BTCUSDT": {"symbol": "BTCUSDT", "price": 70000.0},
    })
    before = deepcopy(state.data)
    build_live_dashboard.main()
    paper = json.loads((tmp_path / "dashboard_data.json").read_text())["paper"]
    assert paper["closed_trades_count"] == 20
    assert len(paper["closed_trades"]) == 10
    assert paper["manual_performance"]["total"] == 14
    assert paper["manual_performance"]["wins"] == 7
    assert paper["manual_performance"]["losses"] == 7
    assert PaperState().data == before
    html = (Path(__file__).resolve().parents[1] / "index.html").read_text()
    assert "textContent=p.closed_trades_count??'—'" in html
    assert "Últimas 10 operaciones cerradas" in html
    assert "total histórico" in html
