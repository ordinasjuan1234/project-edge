"""
PROJECT EDGE
AUTO Paper Trading v7 - estrategia propia v3

Paper Trading con estado persistente.

Funciones:
- Lee datos publicos reales de ETHUSDT.
- Usa el motor multi-timeframe de PROJECT EDGE.
- Solo abre una operacion AUTO cuando hay confirmacion real.
- Recuerda una posicion PAPER abierta.
- Controla Stop Loss y Take Profit.
- Gestiona Trailing Stop persistente.
- Puede gestionar una posicion manual BTC o ETH.
- Gestiona una orden LIMIT PAPER pendiente.
- Mientras haya una LIMIT pendiente, bloquea nuevas entradas AUTO.
- Convierte la LIMIT en posicion cuando el precio muestreado
  alcanza o cruza el precio LIMIT.
- Respeta PAUSE AUTO para impedir NUEVAS entradas automaticas.
- Respeta 30 minutos de enfriamiento despues de cerrar una operacion AUTO.
- Aunque AUTO este pausado, sigue protegiendo posiciones abiertas.
- Aunque AUTO este pausado, sigue gestionando una LIMIT pendiente.
- Actualiza el saldo demo al cerrar.

IMPORTANTE:
- NO ejecuta ordenes reales.
- NO usa API key privada.
- NO mueve dinero real.
- El control de precio se realiza por ciclos, no tick a tick.
"""

from datetime import datetime, timedelta, timezone
from math import ceil

from engine.data.binance_historical_data import (
    BinanceHistoricalData,
)
from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)
from engine.decision.project_edge_v3 import (
    ProjectEdgeV3,
    ProjectEdgeV3Config,
    loss_guard_remaining_minutes,
)

from paper_state import PaperState
from telegram_notifier import (
    notify_auto_entry,
    notify_manual_entry,
    notify_position_exit,
)
from trading_mode import require_paper_mode

SYMBOL = "ETHUSDT"
INITIAL_BALANCE = 10000.0

STOP_PCT = 0.005
TAKE_PROFIT_PCT = 0.01
AUTO_COOLDOWN_MINUTES = 30
AUTO_LOSS_GUARD_LOSSES = 3
AUTO_LOSS_GUARD_MINUTES = 240

STRATEGY = ProjectEdgeV3(
    ProjectEdgeV3Config(
        risk_pct=0.005,
        max_exposure_pct=0.50,
        cooldown_minutes=AUTO_COOLDOWN_MINUTES,
        loss_guard_losses=AUTO_LOSS_GUARD_LOSSES,
        loss_guard_minutes=AUTO_LOSS_GUARD_MINUTES,
    )
)


def auto_cooldown_remaining_minutes(
    state,
    now=None,
    cooldown_minutes=AUTO_COOLDOWN_MINUTES,
):
    """Devuelve los minutos restantes desde el ultimo cierre AUTO."""
    cooldown_minutes = int(cooldown_minutes)
    if cooldown_minutes <= 0:
        return 0.0

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    for trade in reversed(
        state.data.get("closed_trades", [])
    ):
        if str(trade.get("source", "")).upper() != "AUTO":
            continue

        closed_at = trade.get("closed_at")
        if not closed_at:
            continue

        try:
            closed_time = datetime.fromisoformat(
                str(closed_at).replace("Z", "+00:00")
            )
        except ValueError:
            continue

        if closed_time.tzinfo is None:
            closed_time = closed_time.replace(tzinfo=timezone.utc)

        cooldown_end = closed_time + timedelta(
            minutes=cooldown_minutes
        )
        remaining = (
            cooldown_end - current_time
        ).total_seconds() / 60.0
        return max(0.0, remaining)

    return 0.0


def fetch_symbol_data(
    symbol,
    limit=100,
):
    return (
        BinanceHistoricalData()
        .fetch_project_edge_timeframes(
            symbol,
            limit=limit,
        )
    )


def latest_price(
    data,
):
    return float(
        data["5M"]["close"].iloc[-1]
    )


def current_price_for_symbol(
    symbol,
    auto_data=None,
):
    if (
        symbol == SYMBOL
        and auto_data is not None
    ):
        return latest_price(
            auto_data
        )

    data = fetch_symbol_data(
        symbol,
        limit=100,
    )

    return latest_price(
        data
    )


def calculate_levels(
    direction,
    entry_price,
):
    if direction == "LONG":
        stop_loss = (
            entry_price
            * (1.0 - STOP_PCT)
        )

        take_profit = (
            entry_price
            * (1.0 + TAKE_PROFIT_PCT)
        )

    elif direction == "SHORT":
        stop_loss = (
            entry_price
            * (1.0 + STOP_PCT)
        )

        take_profit = (
            entry_price
            * (1.0 - TAKE_PROFIT_PCT)
        )

    else:
        raise ValueError(
            "Direccion invalida."
        )

    return (
        stop_loss,
        take_profit,
    )


def calculate_unrealized_pnl(
    position,
    current_price,
):
    entry_price = float(
        position["entry_price"]
    )

    quantity = float(
        position["quantity"]
    )

    direction = position[
        "direction"
    ]

    if direction == "LONG":
        return (
            current_price
            - entry_price
        ) * quantity

    if direction == "SHORT":
        return (
            entry_price
            - current_price
        ) * quantity

    raise ValueError(
        "Direccion invalida."
    )


def print_auto_state(
    state,
):
    print("")
    print("-" * 60)

    if state.auto_enabled:
        print(
            "AUTO: ACTIVO - nuevas entradas permitidas."
        )
    else:
        print(
            "AUTO: PAUSADO - nuevas entradas bloqueadas."
        )

        reason = state.data.get(
            "auto_pause_reason"
        )

        if reason:
            print(
                f"Motivo pausa: {reason}"
            )

    print("-" * 60)


def manage_pending_order(
    state,
    current_price,
):
    """
    Gestiona una orden LIMIT PAPER pendiente.

    LONG LIMIT:
    se ejecuta si el precio muestreado
    es <= al precio LIMIT.

    SHORT LIMIT:
    se ejecuta si el precio muestreado
    es >= al precio LIMIT.

    IMPORTANTE:
    una LIMIT pendiente sigue gestionandose
    aunque AUTO este pausado, porque no es
    una NUEVA decision automatica del motor.
    """
    order = state.pending_order

    if order is None:
        return False

    direction = order[
        "direction"
    ]

    limit_price = float(
        order["limit_price"]
    )

    current_price = float(
        current_price
    )

    if direction == "LONG":
        triggered = (
            current_price
            <= limit_price
        )

    elif direction == "SHORT":
        triggered = (
            current_price
            >= limit_price
        )

    else:
        raise ValueError(
            "Direccion invalida "
            "en orden LIMIT."
        )

    print("")
    print("=" * 60)
    print(
        "PAPER LIMIT - PENDIENTE"
    )
    print("=" * 60)

    print(
        f"Order ID:       "
        f"{order.get('order_id', '—')}"
    )

    print(
        f"Activo:         "
        f"{order['symbol']}"
    )

    print(
        f"Origen:         "
        f"{order.get('source', 'MANUAL')}"
    )

    print(
        f"Direccion:      "
        f"{direction}"
    )

    print(
        f"Precio LIMIT:   "
        f"{limit_price:.2f}"
    )

    print(
        f"Precio actual:  "
        f"{current_price:.2f}"
    )

    print(
        f"Capital:        "
        f"{float(order['capital']):.2f} USDT"
    )

    print(
        f"Apalancamiento: "
        f"x{int(order['leverage'])}"
    )

    print(
        f"Exposicion:     "
        f"{float(order['exposure']):.2f} USDT"
    )

    if not triggered:
        print("")
        print(
            "LIMIT todavia NO ejecutada."
        )

        print(
            "La orden queda pendiente "
            "para el proximo ciclo."
        )

        print(
            "No se abre otra operacion "
            "mientras exista esta LIMIT."
        )

        print("=" * 60)
        return True

    position = (
        state.fill_pending_order(
            fill_price=limit_price,
        )
    )
    notify_manual_entry(
        position,
        balance=state.balance,
    )

    print("")
    print(
        "PAPER LIMIT - EJECUTADA"
    )
    print("-" * 60)

    print(
        f"Trade ID:       "
        f"{position['trade_id']}"
    )

    print(
        f"Order ID:       "
        f"{position.get('order_id', '—')}"
    )

    print(
        f"Activo:         "
        f"{position['symbol']}"
    )

    print(
        f"Direccion:      "
        f"{position['direction']}"
    )

    print(
        f"Entrada LIMIT:  "
        f"{float(position['entry_price']):.2f}"
    )

    print(
        f"Cantidad:       "
        f"{float(position['quantity']):.8f}"
    )

    print(
        f"Stop Loss:      "
        f"{float(position['stop_loss']):.2f}"
    )

    print(
        f"Take Profit:    "
        f"{float(position['take_profit']):.2f}"
    )

    print(
        f"Capital:        "
        f"{float(position['capital']):.2f} USDT"
    )

    print(
        f"Exposicion:     "
        f"{float(position['exposure']):.2f} USDT"
    )

    print(
        "Trailing:       DESACTIVADO"
    )

    print("")
    print(
        "La LIMIT ya se convirtio "
        "en posicion PAPER abierta."
    )

    print(
        "SL / TP se controlaran "
        "desde el proximo ciclo."
    )

    print(
        "NO se envio ninguna "
        "orden real."
    )

    print("=" * 60)
    return True


def update_trailing_stop(
    state,
    current_price,
):
    """
    Actualiza el Trailing Stop si esta activado.

    LONG:
    - el ancla solo puede subir
    - el Stop Loss solo puede subir

    SHORT:
    - el ancla solo puede bajar
    - el Stop Loss solo puede bajar

    Nunca afloja un Stop Loss existente.
    """
    position = state.position

    if position is None:
        return False

    trailing_enabled = bool(
        position.get(
            "trailing_enabled",
            False,
        )
    )

    if not trailing_enabled:
        return False

    trailing_pct = position.get(
        "trailing_pct"
    )

    if trailing_pct is None:
        print(
            "TRAILING activo sin porcentaje. "
            "No se modifica el Stop."
        )
        return False

    trailing_pct = float(
        trailing_pct
    )

    if trailing_pct <= 0:
        print(
            "TRAILING con porcentaje invalido. "
            "No se modifica el Stop."
        )
        return False

    direction = position[
        "direction"
    ]

    current_stop = float(
        position["stop_loss"]
    )

    anchor_value = position.get(
        "trailing_anchor"
    )

    if anchor_value is None:
        old_anchor = float(
            current_price
        )
    else:
        old_anchor = float(
            anchor_value
        )

    distance = (
        trailing_pct
        / 100.0
    )

    if direction == "LONG":
        new_anchor = max(
            old_anchor,
            float(current_price),
        )

        candidate_stop = (
            new_anchor
            * (1.0 - distance)
        )

        new_stop = max(
            current_stop,
            candidate_stop,
        )

    elif direction == "SHORT":
        new_anchor = min(
            old_anchor,
            float(current_price),
        )

        candidate_stop = (
            new_anchor
            * (1.0 + distance)
        )

        new_stop = min(
            current_stop,
            candidate_stop,
        )

    else:
        raise ValueError(
            "Direccion invalida "
            "en Trailing Stop."
        )

    anchor_changed = (
        abs(
            new_anchor
            - old_anchor
        ) > 0.00000001
    )

    stop_changed = (
        abs(
            new_stop
            - current_stop
        ) > 0.00000001
    )

    if not (
        anchor_changed
        or stop_changed
    ):
        print("")
        print(
            "TRAILING STOP: "
            "sin nuevo avance."
        )

        print(
            f"Ancla:        "
            f"{old_anchor:.2f}"
        )

        print(
            f"Stop actual:  "
            f"{current_stop:.2f}"
        )

        return False

    position[
        "trailing_anchor"
    ] = new_anchor

    position[
        "stop_loss"
    ] = new_stop

    state.data[
        "position"
    ] = position

    state.save()

    print("")
    print("-" * 60)
    print(
        "TRAILING STOP - ACTUALIZADO"
    )
    print("-" * 60)

    print(
        f"Direccion:    "
        f"{direction}"
    )

    print(
        f"Precio:       "
        f"{current_price:.2f}"
    )

    print(
        f"Trailing:     "
        f"{trailing_pct:.2f}%"
    )

    print(
        f"Ancla previa: "
        f"{old_anchor:.2f}"
    )

    print(
        f"Nueva ancla:  "
        f"{new_anchor:.2f}"
    )

    print(
        f"Stop previo:  "
        f"{current_stop:.2f}"
    )

    print(
        f"Nuevo Stop:   "
        f"{new_stop:.2f}"
    )

    return True


def manage_open_position(
    state,
    current_price,
):
    """
    Gestiona una posicion ya abierta.

    Esta funcion SIEMPRE sigue funcionando
    aunque AUTO este pausado.

    Eso permite que:
    - SL siga protegiendo;
    - TP siga protegiendo;
    - Trailing siga funcionando;
    - una posicion MANUAL no dependa de
      que las nuevas entradas AUTO esten activas.
    """
    position = state.position

    if position is None:
        return False

    update_trailing_stop(
        state,
        current_price,
    )

    position = state.position

    if position is None:
        return False

    direction = position[
        "direction"
    ]

    stop_loss = float(
        position["stop_loss"]
    )

    take_profit = float(
        position["take_profit"]
    )

    trailing_enabled = bool(
        position.get(
            "trailing_enabled",
            False,
        )
    )

    trailing_pct = position.get(
        "trailing_pct"
    )

    trailing_anchor = position.get(
        "trailing_anchor"
    )

    print("")
    print("=" * 60)
    print(
        "PAPER POSITION - ABIERTA"
    )
    print("=" * 60)

    print(
        f"Activo:       "
        f"{position['symbol']}"
    )

    print(
        f"Origen:       "
        f"{position.get('source', 'UNCLASSIFIED')}"
    )

    print(
        f"Tipo:         "
        f"{position.get('order_type', 'MARKET')}"
    )

    print(
        f"Direccion:    "
        f"{direction}"
    )

    print(
        f"Entrada:      "
        f"{float(position['entry_price']):.2f}"
    )

    print(
        f"Precio actual:"
        f"{current_price:.2f}"
    )

    print(
        f"Cantidad:     "
        f"{float(position['quantity']):.8f}"
    )

    print(
        f"Stop Loss:    "
        f"{stop_loss:.2f}"
    )

    print(
        f"Take Profit:  "
        f"{take_profit:.2f}"
    )

    if trailing_enabled:
        print(
            "Trailing:     ACTIVO"
        )

        if trailing_pct is not None:
            print(
                f"Distancia:    "
                f"{float(trailing_pct):.2f}%"
            )

        if trailing_anchor is not None:
            print(
                f"Ancla:        "
                f"{float(trailing_anchor):.2f}"
            )

    else:
        print(
            "Trailing:     DESACTIVADO"
        )

    unrealized_pnl = (
        calculate_unrealized_pnl(
            position,
            current_price,
        )
    )

    print(
        f"PnL abierto:  "
        f"{unrealized_pnl:.2f} USDT"
    )

    print(
        f"Saldo:        "
        f"{state.balance_for_source(position.get('source', 'UNCLASSIFIED')):.2f} "
        "USDT"
    )

    if direction == "LONG":
        if current_price <= stop_loss:
            reason = (
                "TRAILING_STOP"
                if trailing_enabled
                else "STOP_LOSS"
            )

            result = (
                state.close_position(
                    exit_price=stop_loss,
                    reason=reason,
                )
            )
            notify_position_exit(result)

            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

        if current_price >= take_profit:
            result = (
                state.close_position(
                    exit_price=take_profit,
                    reason="TAKE_PROFIT",
                )
            )

            notify_position_exit(result)
            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

    if direction == "SHORT":
        if current_price >= stop_loss:
            reason = (
                "TRAILING_STOP"
                if trailing_enabled
                else "STOP_LOSS"
            )

            result = (
                state.close_position(
                    exit_price=stop_loss,
                    reason=reason,
                )
            )
            notify_position_exit(result)
            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

        if current_price <= take_profit:
            result = (
                state.close_position(
                    exit_price=take_profit,
                    reason="TAKE_PROFIT",
                )
            )
            notify_position_exit(result)
            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

    print("")
    print(
        "La posicion sigue abierta."
    )

    print(
        "No se abre una segunda operacion."
    )

    print("=" * 60)

    return True


def analyze_market(
    data,
    market_price,
):
    mtf = (
        MultiTimeframeStructureEngine(
            structure_engine_kwargs={
                "pivot_left": 2,
                "pivot_right": 2,
                "atr_period": 14,
                "atr_multiplier": 1.5,
                "min_move_pct": 0.0025,
                "max_move_pct": 0.05,
            }
        )
        .analyze(data)
    )

    decision = STRATEGY.decide_mtf(mtf)
    missing = [
        name
        for name, passed in decision.get("checks", {}).items()
        if name != "fvg_confluence" and not passed
    ]
    readiness = {
        "status": "READY" if decision.get("can_execute") else "NOT_READY",
        "bias": decision.get("direction"),
        "missing_conditions": missing,
        "message": decision.get("reason"),
    }

    print("")
    print(
        "ESTADO DEL MERCADO"
    )
    print("-" * 60)

    for (
        timeframe,
        market_state,
    ) in mtf["states"].items():

        print(
            f"{timeframe:>3}: "
            f"{market_state}"
        )

    print("-" * 60)

    print(
        f"{SYMBOL} price: "
        f"{market_price:.2f}"
    )

    print(
        f"Alignment:   "
        f"{mtf['alignment']['alignment']}"
    )

    print(
        f"Decision:    "
        f"{decision.get('decision')}"
    )

    print(
        f"Direction:   "
        f"{decision.get('direction')}"
    )

    print(
        f"Can execute: "
        f"{decision.get('can_execute')}"
    )

    print(
        f"Readiness:   "
        f"{readiness.get('status')}"
    )

    print(
        f"Bias:        "
        f"{readiness.get('bias')}"
    )

    missing = readiness.get(
        "missing_conditions",
        [],
    )

    if missing:
        print("")
        print(
            "Faltan confirmaciones:"
        )

        for condition in missing:
            print(
                f"- {condition}"
            )

    return (
        decision,
        readiness,
    )


def main():
    # Barrera de seguridad central: ninguna ejecucion de trading puede
    # continuar si el entorno intenta habilitar el modo REAL.
    require_paper_mode()

    print("=" * 60)
    print(
        "PROJECT EDGE - ETH AUTO PAPER v3"
    )
    print("=" * 60)

    state = PaperState(
        initial_balance=INITIAL_BALANCE,
    )

    print("")
    print(
        f"Capital AUTO DEMO: "
        f"{state.auto_demo_balance:.2f} USDT"
    )

    print_auto_state(
        state
    )

    print("")
    print(
        "Descargando datos reales "
        f"de {SYMBOL}..."
    )

    data = fetch_symbol_data(
        SYMBOL,
        limit=500,
    )

    auto_price = latest_price(
        data
    )

    print(
        f"{SYMBOL} actual: "
        f"{auto_price:.2f}"
    )

    # PRIORIDAD 1:
    # Si hay una LIMIT pendiente, se controla
    # incluso cuando AUTO esta pausado.
    #
    # PAUSE AUTO bloquea nuevas DECISIONES
    # automaticas; no abandona compromisos
    # ya creados.
    if state.has_pending_order:

        pending_symbol = (
            state.pending_order[
                "symbol"
            ]
        )

        pending_price = (
            current_price_for_symbol(
                pending_symbol,
                auto_data=data,
            )
        )

        print(
            f"Precio actual de "
            f"{pending_symbol}: "
            f"{pending_price:.2f}"
        )

        manage_pending_order(
            state,
            pending_price,
        )

        return

    # PRIORIDAD 2:
    # Si hay cualquier posicion abierta
    # (AUTO o MANUAL, BTC o ETH),
    # primero se gestiona esa posicion.
    #
    # Esto sigue activo aunque AUTO este
    # PAUSADO: SL / TP / Trailing NO se
    # desprotegen por pausar nuevas entradas.
    if state.has_open_position:

        position_symbol = (
            state.position[
                "symbol"
            ]
        )

        position_price = (
            current_price_for_symbol(
                position_symbol,
                auto_data=data,
            )
        )

        print(
            f"Precio actual de "
            f"{position_symbol}: "
            f"{position_price:.2f}"
        )

        manage_open_position(
            state,
            position_price,
        )

        return

    # PRIORIDAD 3:
    # Ya no hay posicion ni LIMIT.
    # Antes de analizar una NUEVA entrada
    # automatica, se respeta PAUSE AUTO.
    if not state.auto_enabled:
        print("")
        print("=" * 60)
        print(
            "PAPER AUTO - PAUSADO"
        )
        print("=" * 60)

        print(
            "No hay posicion abierta "
            "ni LIMIT pendiente."
        )

        print(
            "Las NUEVAS entradas AUTO "
            "estan bloqueadas."
        )

        print(
            "El estado PAPER se conserva "
            "sin cambios."
        )

        print(
            f"Capital AUTO DEMO: "
            f"{state.auto_demo_balance:.2f} USDT"
        )

        print("=" * 60)
        return

    # PRIORIDAD 4:
    # Despues de cerrar una operacion AUTO,
    # espera 30 minutos antes de permitir
    # otra entrada automatica.
    cooldown_remaining = (
        auto_cooldown_remaining_minutes(
            state
        )
    )

    if cooldown_remaining > 0:
        print("")
        print("=" * 60)
        print(
            "PAPER AUTO - ENFRIAMIENTO"
        )
        print("=" * 60)
        print(
            "No se permiten nuevas entradas "
            "automaticas todavia."
        )
        print(
            "Tiempo restante aproximado: "
            f"{ceil(cooldown_remaining)} minutos."
        )
        print(
            f"Capital AUTO DEMO: "
            f"{state.auto_demo_balance:.2f} USDT"
        )
        print("=" * 60)
        return

    # PRIORIDAD 5:
    # Tres perdidas AUTO consecutivas pausan nuevas entradas por cuatro horas.
    # Las posiciones abiertas siempre se protegen antes de llegar a este punto.
    loss_guard_remaining = loss_guard_remaining_minutes(
        state.data.get("closed_trades", []),
        consecutive_losses=AUTO_LOSS_GUARD_LOSSES,
        guard_minutes=AUTO_LOSS_GUARD_MINUTES,
    )
    if loss_guard_remaining > 0:
        print("")
        print("=" * 60)
        print("PAPER AUTO - PROTECCION POR PERDIDAS")
        print("=" * 60)
        print(
            f"Se detectaron {AUTO_LOSS_GUARD_LOSSES} perdidas AUTO consecutivas."
        )
        print(
            "Tiempo restante aproximado: "
            f"{ceil(loss_guard_remaining)} minutos."
        )
        print("REAL continua bloqueado.")
        print("=" * 60)
        return

    # PRIORIDAD 6:
    # Solo con AUTO activo y sin posicion
    # ni LIMIT pendiente, el motor puede
    # analizar una entrada nueva.
    decision, readiness = (
        analyze_market(
            data,
            auto_price,
        )
    )

    direction = decision.get(
        "direction"
    )

    decision_status = decision.get(
        "decision"
    )

    readiness_status = readiness.get(
        "status"
    )

    can_execute = bool(
        decision.get(
            "can_execute"
        )
    )

    entry_confirmed = (
        readiness_status == "READY"
        and decision_status != "BLOCKED"
        and direction in (
            "LONG",
            "SHORT",
        )
        and can_execute
    )

    print("")
    print("=" * 60)

    if not entry_confirmed:
        print(
            "PAPER TRADE: SIN ENTRADA"
        )

        print("")

        print(
            "PROJECT EDGE no confirmo "
            "una entrada."
        )

        print(
            "No se abre ninguna "
            "posicion simulada."
        )

        print(
            f"Capital AUTO DEMO: "
            f"{state.auto_demo_balance:.2f} USDT"
        )

        print("=" * 60)
        return

    entry_price = auto_price
    trade_plan = STRATEGY.build_trade_plan(
        decision=decision,
        entry_price=entry_price,
        account_equity=state.auto_demo_balance,
    )
    if not trade_plan.get("approved"):
        print("PAPER TRADE: RECHAZADA POR RIESGO")
        print(trade_plan.get("reason"))
        print("REAL continua bloqueado.")
        print("=" * 60)
        return

    stop_loss = float(trade_plan["stop_price"])
    take_profit = float(trade_plan["target_price"])
    quantity = float(trade_plan["quantity"])

    position = (
        state.open_position(
            symbol=SYMBOL,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source="AUTO",
            fee_rate=STRATEGY.config.fee_rate,
            slippage_rate=STRATEGY.config.slippage_rate,
        )
    )

    # Toda operacion AUTO nueva
    # comienza con Trailing apagado.
    position[
        "trailing_enabled"
    ] = False

    position[
        "trailing_pct"
    ] = None

    position[
        "trailing_anchor"
    ] = None

    position[
        "order_type"
    ] = "MARKET"

    position["strategy"] = "PROJECT_EDGE_V3"
    position["risk_pct"] = STRATEGY.config.risk_pct
    position["risk_budget"] = float(trade_plan["risk_budget"])
    position["estimated_risk"] = float(trade_plan["estimated_risk"])
    position["estimated_cost"] = float(trade_plan["estimated_cost"])
    position["estimated_net_reward_risk"] = float(
        trade_plan["estimated_net_reward_risk"]
    )
    position["leverage"] = 1

    state.data[
        "position"
    ] = position

    state.save()

    notify_auto_entry(position, balance=state.auto_demo_balance)
    risk_usdt = float(trade_plan["estimated_risk"])

    target_usdt = (
        abs(
            position["take_profit"]
            - position["entry_price"]
        )
        * position["quantity"]
    )

    print(
        "PAPER TRADE: "
        "ENTRADA CONFIRMADA"
    )

    print("-" * 60)

    print(
        f"Activo:       "
        f"{position['symbol']}"
    )

    print(
        f"Direccion:    "
        f"{position['direction']}"
    )

    print(
        "Tipo:         MARKET"
    )

    print(
        f"Entrada:      "
        f"{position['entry_price']:.2f}"
    )

    print(
        f"Cantidad:     "
        f"{position['quantity']:.8f}"
    )

    print(
        f"Stop Loss:    "
        f"{position['stop_loss']:.2f}"
    )

    print(
        f"Take Profit:  "
        f"{position['take_profit']:.2f}"
    )

    print(
        "Trailing:     DESACTIVADO"
    )

    print(
        f"Riesgo demo:  "
        f"{risk_usdt:.2f} USDT"
    )

    print(
        f"Objetivo:     "
        f"{target_usdt:.2f} USDT"
    )

    print(
        f"Costo estim.: "
        f"{float(trade_plan['estimated_cost']):.2f} USDT"
    )

    print(
        f"Capital AUTO DEMO: "
        f"{state.auto_demo_balance:.2f} USDT"
    )

    print("")
    print(
        "POSICION PAPER GUARDADA."
    )

    print(
        "En la proxima ejecucion "
        "se controlara SL / TP "
        "y Trailing si esta activo."
    )

    print("")
    print(
        "NO se envio ninguna "
        "orden real."
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
