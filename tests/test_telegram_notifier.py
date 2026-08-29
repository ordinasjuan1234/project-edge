from datetime import date

import pytest

import telegram_notifier


def sample_position(source="MANUAL"):
    return {
        "trade_id": "trade-1",
        "symbol": "ETHUSDT",
        "direction": "LONG",
        "order_type": "MARKET",
        "entry_price": 2500.0,
        "stop_loss": 2475.0,
        "take_profit": 2550.0,
        "capital": 1000.0,
        "leverage": 1,
        "exposure": 1000.0,
        "source": source,
    }


def test_manual_entry_is_clearly_paper():
    message = telegram_notifier.format_manual_entry_message(
        sample_position(),
        balance=10000.0,
    )

    assert "ENTRADA MANUAL PAPER" in message
    assert "ETHUSDT" in message
    assert "sin orden real" in message


def test_time_close_reason_has_friendly_label():
    message = telegram_notifier.format_auto_exit_message(
        {
            "symbol": "ETHUSDT",
            "direction": "LONG",
            "entry_price": 2500.0,
            "exit_price": 2510.0,
            "reason": "TIME_CLOSE",
            "pnl": 4.0,
            "source": "AUTO",
        }
    )

    assert "CIERRE POR TIEMPO" in message


def test_daily_summary_separates_auto_and_manual_in_argentina():
    trades = [
        {
            "source": "AUTO",
            "pnl": 10.0,
            "closed_at": "2026-08-28T02:30:00+00:00",
        },
        {
            "source": "AUTO",
            "pnl": -4.0,
            "closed_at": "2026-08-28T15:00:00+00:00",
        },
        {
            "source": "MANUAL",
            "pnl": 2.0,
            "closed_at": "2026-08-28T20:00:00+00:00",
        },
    ]

    summary = telegram_notifier.calculate_daily_summary(
        trades,
        report_date=date(2026, 8, 28),
    )

    # 02:30 UTC todavía pertenece al 27 de agosto en Argentina.
    assert summary["all"]["total"] == 2
    assert summary["all"]["pnl"] == pytest.approx(-2.0)
    assert summary["auto"]["total"] == 1
    assert summary["manual"]["total"] == 1
    assert summary["manual"]["win_rate"] == pytest.approx(100.0)

    message = telegram_notifier.format_daily_summary_message(
        summary,
        auto_balance=1006.0,
        manual_balance=9943.64,
    )
    assert "Capital AUTO DEMO: 1.006,00 USDT" in message
    assert "Saldo MANUAL / legado: 9.943,64 USDT" in message


def test_auto_control_message_preserves_open_protection():
    message = telegram_notifier.format_auto_control_message(
        "EMERGENCY_STOP_AUTO",
        {"auto_enabled": False},
        balance=9990.0,
    )

    assert "EMERGENCY STOP" in message
    assert "Nuevas entradas: BLOQUEADAS" in message
    assert "Posiciones abiertas: siguen protegidas" in message
    assert "LIMIT pendientes: siguen gestionándose" in message


def test_manual_entry_notifier_ignores_auto_position(monkeypatch):
    called = []
    monkeypatch.setattr(
        telegram_notifier,
        "send_telegram_message",
        lambda message: called.append(message) or True,
    )

    assert telegram_notifier.notify_manual_entry(
        sample_position(source="AUTO")
    ) is False
    assert called == []


def test_position_exit_dispatches_auto(monkeypatch):
    called = []
    monkeypatch.setattr(
        telegram_notifier,
        "send_telegram_message",
        lambda message: called.append(message) or True,
    )

    sent = telegram_notifier.notify_position_exit(
        {
            "source": "AUTO",
            "symbol": "ETHUSDT",
            "direction": "SHORT",
            "entry_price": 2500.0,
            "exit_price": 2450.0,
            "reason": "TAKE_PROFIT",
            "pnl": 20.0,
        }
    )

    assert sent is True
    assert len(called) == 1
    assert "SALIDA AUTO PAPER" in called[0]
