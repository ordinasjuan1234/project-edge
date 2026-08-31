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

import math
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
    if not math.isfinite(number):
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


def _number(value: Any) -> float | None:
    """No inventar importes cuando un registro antiguo no contiene el dato."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _signed(value: Any, decimals: int = 4) -> str:
    number = _number(value)
    if number is None:
        return "—"
    if number == 0:
        return _format_number(0, decimals)
    # No convertir una pequeña ganancia/pérdida en un engañoso ±0,0000.
    while round(number, decimals) == 0 and decimals < 8:
        decimals += 1
    if round(number, decimals) == 0:
        return ("−" if number < 0 else "+") + "<0,00000001"
    return ("+" if number > 0 else "") + _format_number(number, decimals)


def _result_label(value: Any) -> tuple[str, str, str]:
    number = _number(value)
    if number is None:
        return "⚪", "RESULTADO NO DISPONIBLE", "Resultado no disponible"
    if number > 0:
        return "🟢", "GANANCIA", "GANASTE"
    if number < 0:
        return "🔴", "PÉRDIDA", "PERDISTE"
    return "⚪", "SIN GANANCIA NI PÉRDIDA", "SIN GANANCIA NI PÉRDIDA"


def _source(record: dict[str, Any], default: str) -> str:
    return str(record.get("source") or default).upper()


def _account_label(source: str) -> str:
    return {
        "AUTO": "Saldo AUTO DEMO",
        "MANUAL": "Saldo MANUAL / legado",
    }.get(source, "Saldo PAPER (origen sin clasificar)")


def _symbol_label(symbol: Any) -> str:
    symbol = str(symbol or "—")
    if symbol in {"BTCUSDT", "ETHUSDT"}:
        return symbol.replace("USDT", "/USDT")
    return symbol


def _amounts(record: dict[str, Any], source: str) -> tuple[float | None, float | None, float | None]:
    """Capital usado, multiplicador y exposición; nunca el saldo de la cuenta."""
    leverage = _number(record.get("leverage"))
    if leverage is None and source == "AUTO":
        leverage = 1.0  # AUTO PAPER vigente opera siempre x1.
    if leverage is not None and leverage <= 0:
        leverage = None
    partial = "closed_quantity" in record
    capital = None if partial else _number(record.get("capital"))
    exposure = None if partial else _number(record.get("exposure"))
    quantity = _number(record.get("closed_quantity" if partial else "quantity"))
    entry = _number(record.get("entry_price"))
    if exposure is None and capital is not None and leverage is not None:
        exposure = capital * leverage
    if exposure is None and quantity is not None and entry is not None:
        exposure = quantity * entry
    if capital is None and exposure is not None and leverage is not None:
        capital = exposure / leverage
    return capital, leverage, exposure


def _amount_lines(record: dict[str, Any], source: str) -> list[str]:
    capital, leverage, exposure = _amounts(record, source)
    lines = []
    if capital is not None and capital > 0:
        label = "Capital de la parte cerrada" if "closed_quantity" in record else "Capital utilizado"
        lines.append(f"{label}: {_format_number(capital)} USDT")
    if leverage is not None:
        lines.append(f"Apalancamiento: x{leverage:g}")
    if exposure is not None and exposure > 0:
        lines.append(f"Exposición: {_format_number(exposure)} USDT")
    return lines


def _cost_lines(record: dict[str, Any], *, closed: bool) -> list[str]:
    fee_rate = _number(record.get("fee_rate"))
    slippage = _number(record.get("slippage_rate"))
    fees = _number(record.get("fees"))
    if (fees == 0 if closed else fee_rate == 0) and slippage == 0:
        return ["⚠️ Sin comisiones ni deslizamiento simulados; resultado sin esos costos."]
    if closed:
        commission = (
            f"Comisión simulada: {_signed(-fees)} USDT (ya descontada)."
            if fees is not None and fees >= 0
            else "Comisiones: no informadas en este registro."
        )
    else:
        commission = (
            f"Comisión simulada: {_format_number(fee_rate * 100, 4)}% por lado; se descuenta al cerrar."
            if fee_rate is not None and fee_rate >= 0
            else "Comisiones: no informadas en este registro."
        )
    if slippage is None or slippage < 0:
        slip_text = "Deslizamiento: no informado en este registro."
    elif slippage == 0:
        slip_text = "Deslizamiento: no simulado."
    else:
        slip_text = f"Deslizamiento simulado: {_format_number(slippage * 100, 4)}% por lado"
        slip_text += " (ya aplicado en los precios)." if closed else "."
    return [commission, slip_text]


def _balance_lines(source: str, balance: Any, change: Any = None) -> list[str]:
    current = _number(balance)
    if current is None:
        return []
    label = _account_label(source)
    change = _number(change)
    if change is None:
        return [f"{label}: {_format_number(current)} USDT"]
    return [
        f"{label} antes → después: "
        f"{_format_number(current - change)} → {_format_number(current)} USDT",
        f"Cambio de saldo en este cierre: {_signed(change)} USDT",
    ]


def _message_footer(record: dict[str, Any]) -> list[str]:
    lines = []
    if record.get("trade_id"):
        lines.append(f"Trade ID: {record['trade_id']}")
    return ["", *lines, "ℹ️ PAPER / DEMO · sin orden real"]


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
            "STOP LOSS · stop alcanzado"
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


def _format_entry_message(position: dict[str, Any], balance: Any, default: str) -> str:
    source = _source(position, default)
    icon = "🤖" if source == "AUTO" else "🧑"
    lines = [
        f"{icon} PROJECT EDGE · ENTRADA {source} PAPER",
        "",
        f"Activo: {_symbol_label(position.get('symbol'))}",
        f"Dirección: {_direction_label(position.get('direction'))}",
        f"Tipo: {position.get('order_type', 'MARKET')}",
        f"Entrada: {_format_number(position.get('entry_price'))} USDT",
        f"STOP LOSS: {_format_number(position.get('stop_loss'))} USDT",
        f"TAKE PROFIT: {_format_number(position.get('take_profit'))} USDT",
        "",
        *_amount_lines(position, source),
        *_cost_lines(position, closed=False),
        "",
        *_balance_lines(source, balance),
        "El capital utilizado no es la ganancia; el resultado depende del movimiento del precio.",
        *_message_footer(position),
    ]
    return "\n".join(lines)


def format_auto_entry_message(position: dict[str, Any], balance: Any = None) -> str:
    """Construye el aviso de una entrada AUTO PAPER."""
    return _format_entry_message(position, balance, "AUTO")


def format_manual_entry_message(
    position: dict[str, Any],
    balance: Any = None,
) -> str:
    """Construye el aviso de una entrada MANUAL PAPER."""
    return _format_entry_message(position, balance, "MANUAL")


def _format_exit_message(trade: dict[str, Any], default: str) -> str:
    source = _source(trade, default)
    pnl = _number(trade.get("pnl"))
    icon, title, verb = _result_label(pnl)
    partials = trade.get("partial_closes") or []
    has_partials = bool(partials) or (_number(trade.get("partial_count")) or 0) > 0
    realized = _number(trade.get("realized_pnl_before_final"))
    final_pnl = _number(trade.get("final_leg_pnl"))
    if final_pnl is None and pnl is not None:
        if realized is not None:
            final_pnl = pnl - realized
        elif not has_partials:
            final_pnl = pnl
    label = source if source in {"AUTO", "MANUAL"} else "ORIGEN SIN CLASIFICAR"
    lines = [
        f"{icon} PROJECT EDGE · SALIDA {label} PAPER · {title}",
        "",
        f"{verb}: {_signed(pnl)} USDT",
    ]
    capital, _, _ = _amounts(trade, source)
    if capital is not None and capital > 0 and pnl is not None:
        lines.append(f"Rendimiento sobre capital utilizado: {_signed(pnl / capital * 100, 2)}%")
    if has_partials:
        lines.append("Resultado TOTAL de la operación: incluye los parciales, sin sumarlos otra vez.")
        if realized is not None:
            lines.append(f"Ya contabilizado en parciales: {_signed(realized)} USDT")
    lines.extend([
        "",
        f"Activo: {_symbol_label(trade.get('symbol'))}",
        f"Dirección: {_direction_label(trade.get('direction'))}",
        f"Entrada: {_format_number(trade.get('entry_price'))} → "
        f"Salida{' final' if has_partials else ''}: {_format_number(trade.get('exit_price'))} USDT",
        f"Motivo: {_reason_label(trade.get('reason'))}",
        *_amount_lines(trade, source),
        "",
        *_cost_lines(trade, closed=True),
        "",
        *_balance_lines(source, trade.get("balance"), final_pnl),
        *_message_footer(trade),
    ])
    return "\n".join(lines)


def format_auto_exit_message(trade: dict[str, Any]) -> str:
    """Construye el aviso de una salida AUTO PAPER."""
    return _format_exit_message(trade, "AUTO")


def format_manual_exit_message(
    trade: dict[str, Any],
) -> str:
    """Construye el aviso de una salida PAPER no rotulada como AUTO."""
    # Una acción manual también puede cerrar una posición originada por AUTO.
    return _format_exit_message(trade, "UNCLASSIFIED")


def _format_partial_message(payload: dict[str, Any], balance: Any) -> str:
    source = _source(payload, "MANUAL")
    pnl = _number(payload.get("pnl"))
    icon, title, verb = _result_label(pnl)
    capital, _, _ = _amounts(payload, source)
    lines = [
        f"{icon} PROJECT EDGE · CIERRE PARCIAL {source} PAPER · {title}",
        "",
        f"{verb} EN ESTE PARCIAL: {_signed(pnl)} USDT",
    ]
    if capital is not None and capital > 0 and pnl is not None:
        lines.append(f"Rendimiento sobre capital de la parte cerrada: {_signed(pnl / capital * 100, 2)}%")
    lines.extend([
        "",
        f"Activo: {_symbol_label(payload.get('symbol'))}",
        f"Dirección: {_direction_label(payload.get('direction'))}",
        f"Porcentaje cerrado: {_format_number(payload.get('percent'), 0)}% de lo que seguía abierto",
        f"Entrada: {_format_number(payload.get('entry_price'))} → "
        f"Salida parcial: {_format_number(payload.get('exit_price'))} USDT",
        *_amount_lines(payload, source),
        f"Cantidad restante: {_format_number(payload.get('remaining_quantity'), 8)}",
        *_cost_lines(payload, closed=True),
        "",
        *_balance_lines(source, balance if balance is not None else payload.get("balance"), pnl),
        "La posición sigue abierta. Este parcial no cuenta como una operación nueva.",
        *_message_footer(payload),
    ])
    return "\n".join(lines)


def format_manual_action_message(
    action: str,
    payload: dict[str, Any] | None = None,
    balance: Any = None,
) -> str:
    """Construye avisos de controles manuales que no cierran un trade."""
    payload = payload or {}
    action = str(action).upper()
    if action == "PARTIAL_CLOSE":
        return _format_partial_message(payload, balance)
    source = _source(payload, "MANUAL")
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
        ("remaining_quantity", "Cantidad restante", 8, ""),
        ("stop_loss", "Stop Loss", 2, " USDT"),
        ("take_profit", "Take Profit", 2, " USDT"),
        ("trailing_pct", "Trailing", 2, "%"),
    )
    for key, label, decimals, suffix in fields:
        value = payload.get(key)
        if value is None:
            continue
        if key == "symbol":
            rendered = _symbol_label(value)
        elif key == "direction":
            rendered = _direction_label(value)
        else:
            rendered = _format_number(value, decimals)
        lines.append(f"{label}: {rendered}{suffix}")

    if action == "LIMIT_CREATED":
        lines.extend(_amount_lines(payload, source))
        lines.append("PENDIENTE: todavía no es una entrada ejecutada ni una ganancia/pérdida.")
    lines.extend(_balance_lines(source, balance))

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
            "Saldo AUTO DEMO: "
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
            "breakeven": sum(float(trade.get("pnl", 0.0)) == 0 for trade in subset),
            "win_rate": wins / total * 100.0 if total else 0.0,
            "pnl": pnl,
            "fees": sum(_number(trade.get("fees")) or 0.0 for trade in subset),
            "without_costs": sum(
                _number(trade.get("fees")) == 0
                and _number(trade.get("slippage_rate")) == 0
                for trade in subset
            ),
            "unknown_costs": sum(
                _number(trade.get("fees")) is None
                or _number(trade.get("slippage_rate")) is None
                for trade in subset
            ),
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
    """Resultados por fecha de cierre, no un flujo de caja diario inferido."""
    lines = [
        "📊 PROJECT EDGE · RESUMEN DIARIO PAPER",
        f"Fecha: {summary.get('date', '—')}",
        f"Zona horaria: {summary.get('timezone', DEFAULT_REPORT_TIMEZONE)}",
        "",
    ]
    for label, key in (("TOTAL", "all"), ("AUTO", "auto"), ("MANUAL", "manual")):
        metrics = summary.get(key, {})
        count = metrics.get("total", 0)
        wins = metrics.get("wins", 0)
        losses = metrics.get("losses", 0)
        closed_label = "operación cerrada" if count == 1 else "operaciones cerradas"
        won_label = "ganada" if wins == 1 else "ganadas"
        lost_label = "perdida" if losses == 1 else "perdidas"
        flat_text = (
            f" · {metrics['breakeven']} sin ganancia/pérdida"
            if metrics.get("breakeven", 0) else ""
        )
        lines.append(
            f"{label}: {count} {closed_label} · "
            f"{wins} {won_label} / {losses} {lost_label}{flat_text} · "
            f"acierto {_format_number(metrics.get('win_rate', 0.0))}%"
        )
        if metrics.get("total", 0):
            icon, title, _ = _result_label(metrics.get("pnl"))
            lines.append(f"{icon} {title}: {_signed(metrics.get('pnl'))} USDT")
        else:
            lines.append("Sin operaciones cerradas; resultado: 0,0000 USDT.")
        lines.append("")
    total = summary.get("all", {})
    if total.get("total", 0):
        lines.append(f"Comisiones registradas: {_signed(-total.get('fees', 0.0))} USDT (ya descontadas).")
        if total.get("without_costs", 0):
            count = total["without_costs"]
            lines.append(f"⚠️ {count} {'cierre' if count == 1 else 'cierres'} sin comisiones ni deslizamiento simulados.")
        if total.get("unknown_costs", 0):
            count = total["unknown_costs"]
            lines.append(f"⚠️ {count} {'cierre' if count == 1 else 'cierres'} con información de costos incompleta.")
    lines.extend(
        [
            "",
            "Saldos actuales al enviar este resumen:",
            "Capital AUTO DEMO: "
            f"{_format_number(auto_balance)} USDT",
            "Saldo MANUAL / legado: "
            f"{_format_number(manual_balance)} USDT",
            "",
            "Se cuentan cierres, no entradas. Los parciales se incluyen una sola vez, al cierre total, aunque sean de otro día.",
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
