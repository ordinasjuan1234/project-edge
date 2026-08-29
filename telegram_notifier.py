"""
PROJECT EDGE - Telegram Notifier v2

Módulo de alertas Telegram para PROJECT EDGE.

Objetivo:
- avisar entradas y salidas AUTO/MANUAL PAPER;
- avisar controles de riesgo y cierres parciales;
- avisar pausa, reanudación y emergencia AUTO;
- enviar un resumen diario PAPER;
- NO enviar señales por sí mismo;
- NO abrir ni cerrar operaciones;
- NO guardar credenciales en el repositorio.

Credenciales esperadas como variables de entorno:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Si faltan las credenciales, el trading sigue funcionando
y Telegram queda simplemente desactivado.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
TELEGRAM_TIMEOUT_SECONDS = 10
DEFAULT_REPORT_TIMEZONE = "America/Argentina/Buenos_Aires"


def telegram_is_configured() -> bool:
    """Devuelve True solo si token y chat_id están disponibles."""
    return bool(
        os.getenv(BOT_TOKEN_ENV)
        and os.getenv(CHAT_ID_ENV)
    )


def _format_number(
    value: Any,
    decimals: int = 2,
) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"

    return f"{number:,.{decimals}f}".replace(
        ",",
        "_",
    ).replace(
        ".",
        ",",
    ).replace(
        "_",
        ".",
    )


def _direction_label(
    direction: Any,
) -> str:
    direction = str(
        direction or ""
    ).upper()

    if direction == "LONG":
        return "LONG · compra esperando suba"

    if direction == "SHORT":
        return "SHORT · operación esperando baja"

    return direction or "—"


def _reason_label(
    reason: Any,
) -> str:
    reason = str(
        reason or "—"
    ).upper()

    labels = {
        "TAKE_PROFIT": (
            "TAKE PROFIT · toma de ganancia"
        ),
        "STOP_LOSS": (
            "STOP LOSS · corte de pérdida"
        ),
        "TRAILING_STOP": (
            "TRAILING STOP · stop dinámico"
        ),
        "MANUAL_CLOSE": (
            "CIERRE MANUAL"
        ),
        "TIME_CLOSE": (
            "CIERRE POR TIEMPO"
        ),
        "TIME_EXIT": (
            "CIERRE POR TIEMPO"
        ),
    }

    return labels.get(
        reason,
        reason,
    )


def send_telegram_message(
    text: str,
) -> bool:
    """
    Envía un mensaje de texto a Telegram.

    Seguridad:
    - nunca imprime el token;
    - si Telegram falla, devuelve False;
    - un fallo de Telegram NO debe detener el bot.
    """
    token = os.getenv(
        BOT_TOKEN_ENV
    )
    chat_id = os.getenv(
        CHAT_ID_ENV
    )

    if not token or not chat_id:
        print(
            "TELEGRAM: desactivado "
            "(faltan secrets)."
        )
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode(
        "utf-8"
    )

    request = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": (
                "application/"
                "x-www-form-urlencoded"
            ),
            "User-Agent": (
                "PROJECT-EDGE/"
                "telegram-notifier-v2"
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=(
                TELEGRAM_TIMEOUT_SECONDS
            ),
        ) as response:
            status = int(
                response.getcode()
            )

        if 200 <= status < 300:
            print(
                "TELEGRAM: mensaje enviado."
            )
            return True

        print(
            "TELEGRAM: respuesta "
            f"HTTP {status}."
        )
        return False

    except urllib.error.HTTPError as exc:
        print(
            "TELEGRAM: error HTTP "
            f"{exc.code}."
        )
        return False

    except urllib.error.URLError as exc:
        reason = getattr(
            exc,
            "reason",
            "sin detalle",
        )
        print(
            "TELEGRAM: error de conexión "
            f"({reason})."
        )
        return False

    except Exception as exc:
        print(
            "TELEGRAM: error inesperado "
            f"({type(exc).__name__})."
        )
        return False


def format_auto_entry_message(
    position: dict[str, Any],
    balance: Any = None,
) -> str:
    """Construye el aviso de una entrada AUTO PAPER."""
    lines = [
        "🤖 PROJECT EDGE · ENTRADA AUTO PAPER",
        "",
        (
            "Activo: "
            f"{position.get('symbol', '—')}"
        ),
        (
            "Dirección: "
            f"{_direction_label(position.get('direction'))}"
        ),
        (
            "Tipo: "
            f"{position.get('order_type', 'MARKET')}"
        ),
        (
            "Entrada: "
            f"{_format_number(position.get('entry_price'))} USDT"
        ),
        (
            "STOP LOSS (corte de pérdida): "
            f"{_format_number(position.get('stop_loss'))} USDT"
        ),
        (
            "TAKE PROFIT (toma de ganancia): "
            f"{_format_number(position.get('take_profit'))} USDT"
        ),
    ]

    capital = position.get(
        "capital"
    )
    leverage = position.get(
        "leverage"
    )
    exposure = position.get(
        "exposure"
    )

    if capital is not None:
        lines.append(
            "Capital: "
            f"{_format_number(capital)} USDT"
        )

    if leverage is not None:
        lines.append(
            "Apalancamiento: "
            f"x{int(float(leverage))}"
        )

    if exposure is not None:
        lines.append(
            "Exposición: "
            f"{_format_number(exposure)} USDT"
        )

    if balance is not None:
        lines.append(
            "Saldo PAPER: "
            f"{_format_number(balance)} USDT"
        )

    trade_id = position.get(
        "trade_id"
    )
    if trade_id:
        lines.extend(
            [
                "",
                (
                    "Trade ID: "
                    f"{trade_id}"
                ),
            ]
        )

    lines.extend(
        [
            "",
            (
                "ℹ️ PAPER / DEMO · "
                "sin orden real"
            ),
        ]
    )

    return "\n".join(
        lines
    )


def format_manual_entry_message(
    position: dict[str, Any],
    balance: Any = None,
) -> str:
    """Construye el aviso de una entrada MANUAL PAPER."""
    message = format_auto_entry_message(
        position,
        balance=balance,
    )
    return message.replace(
        "ENTRADA AUTO PAPER",
        "ENTRADA MANUAL PAPER",
        1,
    ).replace(
        "🤖 PROJECT EDGE",
        "🧑 PROJECT EDGE",
        1,
    )


def format_auto_exit_message(
    trade: dict[str, Any],
) -> str:
    """Construye el aviso de una salida AUTO PAPER."""
    pnl = float(
        trade.get(
            "pnl",
            0.0,
        )
    )

    result_icon = (
        "🟢"
        if pnl > 0
        else (
            "🔴"
            if pnl < 0
            else "⚪"
        )
    )

    lines = [
        (
            f"{result_icon} PROJECT EDGE · "
            "SALIDA AUTO PAPER"
        ),
        "",
        (
            "Activo: "
            f"{trade.get('symbol', '—')}"
        ),
        (
            "Dirección: "
            f"{_direction_label(trade.get('direction'))}"
        ),
        (
            "Entrada: "
            f"{_format_number(trade.get('entry_price'))} USDT"
        ),
        (
            "Salida: "
            f"{_format_number(trade.get('exit_price'))} USDT"
        ),
        (
            "Motivo: "
            f"{_reason_label(trade.get('reason'))}"
        ),
        (
            "P&L (ganancia/pérdida): "
            f"{_format_number(pnl, 4)} USDT"
        ),
    ]

    if trade.get(
        "balance"
    ) is not None:
        lines.append(
            "Saldo PAPER: "
            f"{_format_number(trade.get('balance'))} USDT"
        )

    trade_id = trade.get(
        "trade_id"
    )
    if trade_id:
        lines.extend(
            [
                "",
                (
                    "Trade ID: "
                    f"{trade_id}"
                ),
            ]
        )

    lines.extend(
        [
            "",
            (
                "ℹ️ PAPER / DEMO · "
                "sin orden real"
            ),
        ]
    )

    return "\n".join(
        lines
    )


def format_manual_exit_message(
    trade: dict[str, Any],
) -> str:
    """Construye el aviso de una salida PAPER no rotulada como AUTO."""
    message = format_auto_exit_message(
        trade
    )
    message = message.replace(
        "SALIDA AUTO PAPER",
        "SALIDA PAPER",
        1,
    )
    lines = message.splitlines()
    lines.insert(
        2,
        "Origen de la posición: "
        f"{str(trade.get('source', 'UNCLASSIFIED')).upper()}",
    )
    return "\n".join(lines)


def format_manual_action_message(
    action: str,
    payload: dict[str, Any] | None = None,
    balance: Any = None,
) -> str:
    """Construye avisos de controles manuales que no cierran un trade."""
    payload = payload or {}
    action = str(action).upper()
    labels = {
        "LIMIT_CREATED": "ORDEN LIMIT CREADA",
        "LIMIT_CANCELLED": "ORDEN LIMIT CANCELADA",
        "PARTIAL_CLOSE": "CIERRE PARCIAL",
        "RISK_UPDATED": "SL / TP ACTUALIZADOS",
        "BREAK_EVEN": "BREAK-EVEN ACTIVADO",
        "TRAILING_ON": "TRAILING ACTIVADO",
        "TRAILING_OFF": "TRAILING DESACTIVADO",
    }
    title = labels.get(action, action)
    lines = [
        f"🛠️ PROJECT EDGE · {title} · PAPER",
    ]

    fields = (
        ("symbol", "Activo", 2, ""),
        ("direction", "Dirección", 2, ""),
        ("limit_price", "Precio LIMIT", 2, " USDT"),
        ("entry_price", "Entrada", 2, " USDT"),
        ("exit_price", "Salida", 2, " USDT"),
        ("percent", "Porcentaje", 0, "%"),
        ("pnl", "P&L parcial", 4, " USDT"),
        ("remaining_quantity", "Cantidad restante", 8, ""),
        ("stop_loss", "Stop Loss", 2, " USDT"),
        ("take_profit", "Take Profit", 2, " USDT"),
        ("trailing_pct", "Trailing", 2, "%"),
    )
    for key, label, decimals, suffix in fields:
        value = payload.get(key)
        if value is None:
            continue
        if key in {"symbol", "direction"}:
            rendered = str(value)
        else:
            rendered = _format_number(value, decimals)
        lines.append(f"{label}: {rendered}{suffix}")

    if balance is not None:
        lines.append(
            "Saldo PAPER: "
            f"{_format_number(balance)} USDT"
        )

    lines.extend(
        [
            "",
            "ℹ️ PAPER / DEMO · sin orden real",
        ]
    )
    return "\n".join(lines)


def format_auto_control_message(
    action: str,
    state: dict[str, Any],
    balance: Any = None,
) -> str:
    """Construye avisos de pausa, reanudación y emergencia AUTO."""
    action = str(action).upper()
    labels = {
        "PAUSE_AUTO": "⏸️ AUTO PAPER PAUSADO",
        "RESUME_AUTO": "▶️ AUTO PAPER REANUDADO",
        "EMERGENCY_STOP_AUTO": "⛔ EMERGENCY STOP AUTO",
    }
    lines = [
        f"{labels.get(action, action)}",
        "",
        (
            "Nuevas entradas: "
            + (
                "PERMITIDAS"
                if state.get("auto_enabled")
                else "BLOQUEADAS"
            )
        ),
        "Posiciones abiertas: siguen protegidas",
        "LIMIT pendientes: siguen gestionándose",
    ]
    if balance is not None:
        lines.append(
            "Saldo PAPER: "
            f"{_format_number(balance)} USDT"
        )
    lines.extend(
        [
            "",
            "ℹ️ PAPER / DEMO · no mueve dinero real",
        ]
    )
    return "\n".join(lines)


def _parse_closed_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def calculate_daily_summary(
    trades: list[dict[str, Any]],
    report_date: date | None = None,
    timezone_name: str = DEFAULT_REPORT_TIMEZONE,
) -> dict[str, Any]:
    """Resume los trades cerrados durante un día local."""
    local_tz = ZoneInfo(timezone_name)
    target_date = report_date or datetime.now(local_tz).date()
    selected = []
    for trade in trades:
        closed_at = _parse_closed_at(trade.get("closed_at"))
        if closed_at and closed_at.astimezone(local_tz).date() == target_date:
            selected.append(trade)

    def metrics(source: str | None = None) -> dict[str, Any]:
        subset = [
            trade
            for trade in selected
            if source is None
            or str(trade.get("source", "UNCLASSIFIED")).upper() == source
        ]
        wins = sum(float(trade.get("pnl", 0.0)) > 0 for trade in subset)
        losses = sum(float(trade.get("pnl", 0.0)) < 0 for trade in subset)
        pnl = sum(float(trade.get("pnl", 0.0)) for trade in subset)
        total = len(subset)
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total * 100.0 if total else 0.0,
            "pnl": pnl,
        }

    return {
        "date": target_date.isoformat(),
        "timezone": timezone_name,
        "all": metrics(),
        "auto": metrics("AUTO"),
        "manual": metrics("MANUAL"),
    }


def format_daily_summary_message(
    summary: dict[str, Any],
    auto_balance: Any,
    manual_balance: Any,
) -> str:
    """Construye el resumen diario AUTO/MANUAL."""
    lines = [
        "📊 PROJECT EDGE · RESUMEN DIARIO PAPER",
        f"Fecha: {summary.get('date', '—')}",
        "",
    ]
    for label, key in (("TOTAL", "all"), ("AUTO", "auto"), ("MANUAL", "manual")):
        metrics = summary.get(key, {})
        lines.append(
            f"{label}: {metrics.get('total', 0)} operaciones · "
            f"{metrics.get('wins', 0)} G / {metrics.get('losses', 0)} P · "
            f"acierto {_format_number(metrics.get('win_rate', 0.0))}% · "
            f"P&L {_format_number(metrics.get('pnl', 0.0), 4)} USDT"
        )
    lines.extend(
        [
            "",
            "Capital AUTO DEMO: "
            f"{_format_number(auto_balance)} USDT",
            "Saldo MANUAL / legado: "
            f"{_format_number(manual_balance)} USDT",
            "ℹ️ PAPER / DEMO · sin dinero real",
        ]
    )
    return "\n".join(lines)


def notify_auto_entry(
    position: dict[str, Any],
    balance: Any = None,
) -> bool:
    """Envía alerta solo si la posición es de origen AUTO."""
    if str(
        position.get(
            "source",
            "",
        )
    ).upper() != "AUTO":
        return False

    return send_telegram_message(
        format_auto_entry_message(
            position,
            balance=balance,
        )
    )


def notify_manual_entry(
    position: dict[str, Any],
    balance: Any = None,
) -> bool:
    """Envía alerta solo si la posición es de origen MANUAL."""
    if str(position.get("source", "")).upper() != "MANUAL":
        return False
    return send_telegram_message(
        format_manual_entry_message(position, balance=balance)
    )


def notify_auto_exit(
    trade: dict[str, Any],
) -> bool:
    """Envía alerta solo si el trade cerrado es de origen AUTO."""
    if str(
        trade.get(
            "source",
            "",
        )
    ).upper() != "AUTO":
        return False

    return send_telegram_message(
        format_auto_exit_message(
            trade
        )
    )


def notify_position_exit(
    trade: dict[str, Any],
) -> bool:
    """Envía la salida gestionada con el rótulo AUTO o MANUAL correcto."""
    if str(trade.get("source", "")).upper() == "AUTO":
        return notify_auto_exit(trade)
    return send_telegram_message(format_manual_exit_message(trade))


def notify_manual_exit(
    trade: dict[str, Any],
) -> bool:
    """Avisa un cierre solicitado desde el control manual."""
    return send_telegram_message(format_manual_exit_message(trade))


def notify_manual_action(
    action: str,
    payload: dict[str, Any] | None = None,
    balance: Any = None,
) -> bool:
    return send_telegram_message(
        format_manual_action_message(action, payload, balance=balance)
    )


def notify_auto_control(
    action: str,
    state: dict[str, Any],
    balance: Any = None,
) -> bool:
    return send_telegram_message(
        format_auto_control_message(action, state, balance=balance)
    )


def notify_daily_summary(
    state_data: dict[str, Any],
    report_date: date | None = None,
    timezone_name: str = DEFAULT_REPORT_TIMEZONE,
) -> bool:
    summary = calculate_daily_summary(
        list(state_data.get("closed_trades", [])),
        report_date=report_date,
        timezone_name=timezone_name,
    )
    return send_telegram_message(
        format_daily_summary_message(
            summary,
            auto_balance=state_data.get(
                "auto_demo_balance",
                1000.0,
            ),
            manual_balance=state_data.get("balance"),
        )
    )
