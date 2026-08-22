"""
PROJECT EDGE - Telegram Notifier v1

Módulo de alertas Telegram para PROJECT EDGE.

Objetivo:
- avisar entradas AUTO PAPER;
- avisar salidas AUTO PAPER;
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
from typing import Any


BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
TELEGRAM_TIMEOUT_SECONDS = 10


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
                "telegram-notifier-v1"
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
