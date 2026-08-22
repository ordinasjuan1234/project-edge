"""
PROJECT EDGE - Manual PAPER Control v7

Control manual simulado para BTC/USDT y ETH/USDT.

Permite:
- LONG / SHORT MARKET
- LONG / SHORT LIMIT pendiente
- Cancelar LIMIT pendiente
- Cierre manual total
- Cierre parcial 25% / 50% / 75% / 100%
- Capital configurable
- Apalancamiento x1/x2/x3
- SL / TP personalizados
- Modificar SL / TP
- Break-even
- Activar / desactivar Trailing Stop
- PAUSE AUTO
- RESUME AUTO

NO envia ordenes reales.
NO usa API privada de Binance.
"""

from __future__ import annotations

import argparse

from engine.data.binance_historical_data import BinanceHistoricalData
from paper_state import PaperState


INITIAL_BALANCE = 10000.0

DEFAULT_STOP_PCT = 0.005
DEFAULT_TAKE_PROFIT_PCT = 0.01

# 0.30 significa 0.30%.
DEFAULT_TRAILING_PCT = 0.30
MIN_TRAILING_PCT = 0.05
MAX_TRAILING_PCT = 5.00

ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
ALLOWED_LEVERAGE = {1, 2, 3}
ALLOWED_PARTIAL_PCT = {25.0, 50.0, 75.0, 100.0}
ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT"}


def current_price(symbol: str) -> float:
    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        symbol,
        limit=100,
    )
    return float(data["5M"]["close"].iloc[-1])


def default_levels(
    direction: str,
    entry_price: float,
) -> tuple[float, float]:
    if direction == "LONG":
        return (
            entry_price * (1.0 - DEFAULT_STOP_PCT),
            entry_price * (1.0 + DEFAULT_TAKE_PROFIT_PCT),
        )

    return (
        entry_price * (1.0 + DEFAULT_STOP_PCT),
        entry_price * (1.0 - DEFAULT_TAKE_PROFIT_PCT),
    )


def resolve_levels(
    direction: str,
    entry_price: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[float, float]:
    default_stop, default_tp = default_levels(
        direction,
        entry_price,
    )

    stop = (
        float(stop_loss)
        if stop_loss is not None
        else default_stop
    )
    tp = (
        float(take_profit)
        if take_profit is not None
        else default_tp
    )

    if direction == "LONG":
        if stop >= entry_price:
            raise ValueError(
                "En LONG, el Stop Loss debe estar debajo de la entrada."
            )
        if tp <= entry_price:
            raise ValueError(
                "En LONG, el Take Profit debe estar encima de la entrada."
            )
    else:
        if stop <= entry_price:
            raise ValueError(
                "En SHORT, el Stop Loss debe estar encima de la entrada."
            )
        if tp >= entry_price:
            raise ValueError(
                "En SHORT, el Take Profit debe estar debajo de la entrada."
            )

    return stop, tp


def validate_capital_and_leverage(
    state: PaperState,
    capital: float,
    leverage: int,
) -> tuple[float, int]:
    capital = float(capital)
    leverage = int(leverage)

    if capital <= 0:
        raise ValueError(
            "El capital debe ser mayor que 0."
        )

    if capital > state.balance:
        raise ValueError(
            "Capital insuficiente. "
            f"Saldo PAPER disponible: {state.balance:.2f} USDT."
        )

    if leverage not in ALLOWED_LEVERAGE:
        raise ValueError(
            "El apalancamiento PAPER permitido es x1, x2 o x3."
        )

    return capital, leverage


def pause_auto(
    state: PaperState,
) -> None:
    """
    Pausa solamente NUEVAS entradas AUTO.

    No cierra posiciones.
    No cancela LIMIT pendientes.
    No cambia el saldo.
    """
    result = state.set_auto_enabled(
        False,
        reason="MANUAL_PAUSE",
    )

    print("=" * 60)
    print("PROJECT EDGE - AUTO PAPER PAUSADO")
    print("=" * 60)
    print("Estado AUTO:      PAUSADO")
    print("Nuevas entradas:  BLOQUEADAS")
    print(
        "Posiciones abiertas: SIGUEN protegidas por SL / TP / Trailing."
    )
    print(
        "LIMIT pendientes:    SIGUEN siendo gestionadas."
    )
    print(f"Saldo PAPER:      {state.balance:.2f} USDT")
    print(
        f"Actualizado:       {result.get('auto_updated_at') or '—'}"
    )
    print("NO se cerro ninguna posicion.")


def resume_auto(
    state: PaperState,
) -> None:
    """
    Reactiva las NUEVAS entradas AUTO.

    No abre una operacion inmediatamente.
    El runner decidira en cada ciclo si hay
    confirmacion suficiente para entrar.
    """
    result = state.set_auto_enabled(
        True
    )

    print("=" * 60)
    print("PROJECT EDGE - AUTO PAPER REANUDADO")
    print("=" * 60)
    print("Estado AUTO:      ACTIVO")
    print("Nuevas entradas:  PERMITIDAS")
    print(
        "El bot solo entrara si el motor confirma una oportunidad."
    )
    print(f"Saldo PAPER:      {state.balance:.2f} USDT")
    print(
        f"Actualizado:       {result.get('auto_updated_at') or '—'}"
    )
    print("NO se abrio ninguna posicion por reanudar.")


def open_market_manual(
    state: PaperState,
    direction: str,
    symbol: str,
    price: float,
    capital: float,
    leverage: int,
    stop_loss: float | None,
    take_profit: float | None,
) -> None:
    if state.has_open_position:
        pos = state.position
        print(
            "NO SE ABRE OTRA POSICION: ya existe una "
            f"{pos['direction']} en {pos['entry_price']:.2f}."
        )
        return

    if state.has_pending_order:
        order = state.pending_order
        print(
            "NO SE ABRE MARKET: existe una orden LIMIT "
            f"{order['direction']} pendiente en "
            f"{float(order['limit_price']):.2f}."
        )
        return

    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(
            "Activo no permitido."
        )

    capital, leverage = validate_capital_and_leverage(
        state=state,
        capital=capital,
        leverage=leverage,
    )

    stop, tp = resolve_levels(
        direction=direction,
        entry_price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    exposure = capital * leverage
    quantity = exposure / price

    position = state.open_position(
        symbol=symbol,
        direction=direction,
        entry_price=price,
        quantity=quantity,
        stop_loss=stop,
        take_profit=tp,
        source="MANUAL",
    )

    position["capital"] = capital
    position["initial_capital"] = capital
    position["leverage"] = leverage
    position["exposure"] = exposure
    position["initial_exposure"] = exposure
    position["order_type"] = "MARKET"
    position["trailing_enabled"] = False
    position["trailing_pct"] = None
    position["trailing_anchor"] = None

    state.data["position"] = position
    state.save()

    print("=" * 60)
    print("PROJECT EDGE - ENTRADA MARKET PAPER")
    print("=" * 60)
    print(f"Trade ID:         {position['trade_id']}")
    print(f"Activo:           {position['symbol']}")
    print(f"Direccion:        {position['direction']}")
    print("Tipo:             MARKET")
    print(f"Entrada:          {position['entry_price']:.2f}")
    print(f"Capital:          {capital:.2f} USDT")
    print(f"Apalancamiento:   x{leverage}")
    print(f"Exposicion:       {exposure:.2f} USDT")
    print(f"Cantidad:         {position['quantity']:.8f}")
    print(f"Stop Loss:        {position['stop_loss']:.2f}")
    print(f"Take Profit:      {position['take_profit']:.2f}")
    print("Trailing Stop:    DESACTIVADO")
    print(f"Saldo PAPER:      {state.balance:.2f} USDT")
    print("NO se envio ninguna orden real.")


def create_limit_manual(
    state: PaperState,
    direction: str,
    symbol: str,
    market_price: float,
    limit_price: float | None,
    capital: float,
    leverage: int,
    stop_loss: float | None,
    take_profit: float | None,
) -> None:
    if state.has_open_position:
        raise ValueError(
            "No se puede crear LIMIT: ya existe una posicion PAPER abierta."
        )

    if state.has_pending_order:
        raise ValueError(
            "Ya existe una orden LIMIT PAPER pendiente."
        )

    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(
            "Activo no permitido."
        )

    if limit_price is None:
        raise ValueError(
            "Para una orden LIMIT debes indicar el precio LIMIT."
        )

    limit_price = float(limit_price)

    if limit_price <= 0:
        raise ValueError(
            "El precio LIMIT debe ser mayor que 0."
        )

    if direction == "LONG" and limit_price >= market_price:
        raise ValueError(
            "Para dejar una LONG LIMIT pendiente, el precio LIMIT "
            "debe estar debajo del precio actual."
        )

    if direction == "SHORT" and limit_price <= market_price:
        raise ValueError(
            "Para dejar una SHORT LIMIT pendiente, el precio LIMIT "
            "debe estar encima del precio actual."
        )

    capital, leverage = validate_capital_and_leverage(
        state=state,
        capital=capital,
        leverage=leverage,
    )

    stop, tp = resolve_levels(
        direction=direction,
        entry_price=limit_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    order = state.create_pending_order(
        symbol=symbol,
        direction=direction,
        limit_price=limit_price,
        capital=capital,
        leverage=leverage,
        stop_loss=stop,
        take_profit=tp,
        source="MANUAL",
    )

    print("=" * 60)
    print("PROJECT EDGE - ORDEN LIMIT PAPER PENDIENTE")
    print("=" * 60)
    print(f"Order ID:         {order['order_id']}")
    print(f"Activo:           {order['symbol']}")
    print(f"Direccion:        {order['direction']}")
    print("Tipo:             LIMIT")
    print(f"Mercado actual:   {market_price:.2f}")
    print(f"Precio LIMIT:     {order['limit_price']:.2f}")
    print(f"Capital:          {order['capital']:.2f} USDT")
    print(f"Apalancamiento:   x{order['leverage']}")
    print(f"Exposicion:       {order['exposure']:.2f} USDT")
    print(f"Cantidad prevista:{order['quantity']:.8f}")
    print(f"Stop Loss:        {order['stop_loss']:.2f}")
    print(f"Take Profit:      {order['take_profit']:.2f}")
    print("Estado:           PENDING")
    print(
        "La posicion NO esta abierta todavia. "
        "El backend debe detectar el precio LIMIT."
    )
    print("NO se envio ninguna orden real.")


def cancel_limit_manual(
    state: PaperState,
) -> None:
    if not state.has_pending_order:
        raise ValueError(
            "No hay una orden LIMIT PAPER pendiente para cancelar."
        )

    order = state.cancel_pending_order(
        reason="MANUAL_CANCEL",
    )

    print("=" * 60)
    print("PROJECT EDGE - LIMIT PAPER CANCELADA")
    print("=" * 60)
    print(f"Order ID:     {order['order_id']}")
    print(f"Activo:       {order['symbol']}")
    print(f"Direccion:    {order['direction']}")
    print(f"Precio LIMIT: {float(order['limit_price']):.2f}")
    print("Estado:       CANCELLED")
    print(f"Saldo PAPER:  {state.balance:.2f} USDT")
    print(
        "La cancelacion no genero PnL porque la posicion nunca se abrio."
    )


def close_manual(
    state: PaperState,
) -> None:
    if not state.has_open_position:
        if state.has_pending_order:
            print(
                "NO HAY POSICION ABIERTA. Hay una LIMIT pendiente; "
                "usa CANCEL_LIMIT para cancelarla."
            )
            return

        print(
            "NO HAY POSICION PAPER ABIERTA PARA CERRAR."
        )
        return

    symbol = state.position["symbol"]
    price = current_price(symbol)

    trade = state.close_position(
        exit_price=price,
        reason="MANUAL_CLOSE",
    )

    print("=" * 60)
    print("PROJECT EDGE - CIERRE MANUAL PAPER")
    print("=" * 60)
    print(f"Activo:      {trade['symbol']}")
    print(f"Direccion:   {trade['direction']}")
    print(f"Entrada:     {trade['entry_price']:.2f}")
    print(f"Salida:      {trade['exit_price']:.2f}")
    print(f"PnL total:   {trade['pnl']:.4f} USDT")
    print(f"Saldo PAPER: {trade['balance']:.2f} USDT")

    if trade.get("partial_count", 0) > 0:
        print(
            f"Parciales:   {trade['partial_count']}"
        )

    print(
        "NO se envio ninguna orden real."
    )


def partial_close_manual(
    state: PaperState,
    partial_pct: float | None,
) -> None:
    if not state.has_open_position:
        raise ValueError(
            "No hay una posicion PAPER abierta para realizar cierre parcial."
        )

    if partial_pct is None:
        raise ValueError(
            "Debes indicar el porcentaje de cierre parcial."
        )

    pct = float(partial_pct)

    if pct not in ALLOWED_PARTIAL_PCT:
        raise ValueError(
            "Cierre parcial permitido: 25%, 50%, 75% o 100%."
        )

    position_before = state.position
    symbol = position_before["symbol"]
    quantity_before = float(
        position_before["quantity"]
    )
    price = current_price(symbol)

    result = state.partial_close_position(
        exit_price=price,
        percent=pct,
        reason=(
            "MANUAL_CLOSE"
            if pct == 100.0
            else f"PARTIAL_CLOSE_{int(pct)}"
        ),
    )

    print("=" * 60)

    if result.get("is_final") is True:
        print(
            "PROJECT EDGE - CIERRE 100% PAPER"
        )
    else:
        print(
            "PROJECT EDGE - CIERRE PARCIAL PAPER"
        )

    print("=" * 60)
    print(f"Activo:          {result['symbol']}")
    print(f"Direccion:       {result['direction']}")
    print(f"Entrada:         {result['entry_price']:.2f}")
    print(f"Salida:          {result['exit_price']:.2f}")

    if result.get("is_final") is True:
        print("Cierre:           100%")
        print(
            f"Cantidad cerrada: {quantity_before:.8f}"
        )
        print(
            f"PnL total trade:  {result['pnl']:.4f} USDT"
        )
        print(
            f"Saldo PAPER:      {result['balance']:.2f} USDT"
        )
        print("Posicion:         CERRADA")

    else:
        print(
            f"Cierre solicitado: {pct:.0f}% de la cantidad abierta"
        )
        print(
            f"Cantidad cerrada:  {result['closed_quantity']:.8f}"
        )
        print(
            f"Cantidad restante: {result['remaining_quantity']:.8f}"
        )
        print(
            f"PnL parcial:       {result['pnl']:.4f} USDT"
        )
        print(
            f"PnL realizado:     {result['realized_pnl_total']:.4f} USDT"
        )
        print(
            f"Saldo PAPER:       {result['balance']:.2f} USDT"
        )
        print(
            "Posicion:          SIGUE ABIERTA"
        )

    print(
        "NO se envio ninguna orden real."
    )


def update_manual_risk(
    state: PaperState,
    stop_loss: float | None,
    take_profit: float | None,
) -> None:
    if not state.has_open_position:
        raise ValueError(
            "No hay una posicion PAPER abierta para modificar."
        )

    if stop_loss is None and take_profit is None:
        raise ValueError(
            "Ingresa un nuevo Stop Loss, Take Profit o ambos."
        )

    position = state.position
    symbol = position["symbol"]
    direction = position["direction"]
    price = current_price(symbol)

    new_stop = (
        float(stop_loss)
        if stop_loss is not None
        else float(position["stop_loss"])
    )
    new_tp = (
        float(take_profit)
        if take_profit is not None
        else float(position["take_profit"])
    )

    if direction == "LONG":
        if new_stop >= price:
            raise ValueError(
                "En LONG, el Stop Loss debe estar debajo del precio actual."
            )
        if new_tp <= price:
            raise ValueError(
                "En LONG, el Take Profit debe estar encima del precio actual."
            )
    else:
        if new_stop <= price:
            raise ValueError(
                "En SHORT, el Stop Loss debe estar encima del precio actual."
            )
        if new_tp >= price:
            raise ValueError(
                "En SHORT, el Take Profit debe estar debajo del precio actual."
            )

    position["stop_loss"] = new_stop
    position["take_profit"] = new_tp

    state.data["position"] = position
    state.save()

    print("=" * 60)
    print("PROJECT EDGE - MODIFICAR SL/TP PAPER")
    print("=" * 60)
    print(f"Activo:      {symbol}")
    print(f"Direccion:   {direction}")
    print(f"Precio:      {price:.2f}")
    print(f"Nuevo SL:    {new_stop:.2f}")
    print(f"Nuevo TP:    {new_tp:.2f}")


def set_break_even(
    state: PaperState,
) -> None:
    if not state.has_open_position:
        raise ValueError(
            "No hay una posicion PAPER abierta para aplicar Break-even."
        )

    position = state.position
    symbol = position["symbol"]
    direction = position["direction"]
    entry_price = float(
        position["entry_price"]
    )
    price = current_price(symbol)

    if direction == "LONG" and price <= entry_price:
        raise ValueError(
            "Break-even LONG solo se habilita cuando el precio "
            "esta por encima de la entrada."
        )

    if direction == "SHORT" and price >= entry_price:
        raise ValueError(
            "Break-even SHORT solo se habilita cuando el precio "
            "esta por debajo de la entrada."
        )

    position["stop_loss"] = entry_price

    state.data["position"] = position
    state.save()

    print("=" * 60)
    print("PROJECT EDGE - BREAK EVEN PAPER")
    print("=" * 60)
    print(f"Activo:      {symbol}")
    print(f"Direccion:   {direction}")
    print(f"Entrada:     {entry_price:.2f}")
    print(f"Precio:      {price:.2f}")
    print(f"Nuevo SL:    {entry_price:.2f}")
    print(
        f"TP actual:   {position['take_profit']:.2f}"
    )


def enable_trailing(
    state: PaperState,
    trailing_pct: float | None,
) -> None:
    if not state.has_open_position:
        raise ValueError(
            "No hay una posicion PAPER abierta para activar Trailing Stop."
        )

    pct = (
        DEFAULT_TRAILING_PCT
        if trailing_pct is None
        else float(trailing_pct)
    )

    if pct < MIN_TRAILING_PCT or pct > MAX_TRAILING_PCT:
        raise ValueError(
            "Trailing Stop permitido: "
            f"{MIN_TRAILING_PCT:.2f}% a {MAX_TRAILING_PCT:.2f}%."
        )

    position = state.position
    symbol = position["symbol"]
    direction = position["direction"]
    price = current_price(symbol)
    current_stop = float(
        position["stop_loss"]
    )
    distance = pct / 100.0

    if direction == "LONG":
        candidate_stop = price * (1.0 - distance)
        new_stop = max(
            current_stop,
            candidate_stop,
        )
    else:
        candidate_stop = price * (1.0 + distance)
        new_stop = min(
            current_stop,
            candidate_stop,
        )

    position["trailing_enabled"] = True
    position["trailing_pct"] = pct
    position["trailing_anchor"] = price
    position["stop_loss"] = new_stop

    state.data["position"] = position
    state.save()

    print("=" * 60)
    print("PROJECT EDGE - TRAILING STOP ACTIVADO")
    print("=" * 60)
    print(f"Activo:       {symbol}")
    print(f"Direccion:    {direction}")
    print(f"Precio:       {price:.2f}")
    print(f"Trailing:     {pct:.2f}%")
    print(f"Ancla:        {price:.2f}")
    print(f"Stop actual:  {new_stop:.2f}")


def disable_trailing(
    state: PaperState,
) -> None:
    if not state.has_open_position:
        raise ValueError(
            "No hay una posicion PAPER abierta para desactivar Trailing Stop."
        )

    position = state.position
    position["trailing_enabled"] = False
    position["trailing_pct"] = None
    position["trailing_anchor"] = None

    state.data["position"] = position
    state.save()

    print("=" * 60)
    print("PROJECT EDGE - TRAILING STOP DESACTIVADO")
    print("=" * 60)
    print(
        f"Activo:       {position['symbol']}"
    )
    print(
        f"Stop actual:  {float(position['stop_loss']):.2f}"
    )
    print(
        "El Stop Loss actual se conserva."
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "LONG",
            "SHORT",
            "CLOSE",
            "CANCEL_LIMIT",
            "PARTIAL_CLOSE",
            "UPDATE_RISK",
            "BREAK_EVEN",
            "TRAILING_ON",
            "TRAILING_OFF",
            "PAUSE_AUTO",
            "RESUME_AUTO",
        ],
    )

    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        choices=sorted(ALLOWED_SYMBOLS),
    )

    parser.add_argument(
        "--capital",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--leverage",
        type=int,
        default=1,
        choices=sorted(ALLOWED_LEVERAGE),
    )

    parser.add_argument(
        "--order-type",
        default="MARKET",
        choices=sorted(ALLOWED_ORDER_TYPES),
    )

    parser.add_argument(
        "--limit-price",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--stop-loss",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--take-profit",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--trailing-pct",
        type=float,
        default=None,
        help=(
            "Distancia del Trailing Stop en porcentaje. "
            "Ejemplo: 0.30 = 0.30%%."
        ),
    )

    parser.add_argument(
        "--partial-pct",
        type=float,
        default=None,
        help=(
            "Porcentaje de la cantidad abierta a cerrar: "
            "25, 50, 75 o 100."
        ),
    )

    args = parser.parse_args()

    state = PaperState(
        initial_balance=INITIAL_BALANCE
    )

    # Estas acciones no necesitan consultar el mercado.
    if args.action == "PAUSE_AUTO":
        pause_auto(state)
        return

    if args.action == "RESUME_AUTO":
        resume_auto(state)
        return

    if args.action == "CLOSE":
        close_manual(state)
        return

    if args.action == "CANCEL_LIMIT":
        cancel_limit_manual(state)
        return

    if args.action == "PARTIAL_CLOSE":
        partial_close_manual(
            state=state,
            partial_pct=args.partial_pct,
        )
        return

    if args.action == "UPDATE_RISK":
        update_manual_risk(
            state=state,
            stop_loss=args.stop_loss,
            take_profit=args.take_profit,
        )
        return

    if args.action == "BREAK_EVEN":
        set_break_even(state)
        return

    if args.action == "TRAILING_ON":
        enable_trailing(
            state=state,
            trailing_pct=args.trailing_pct,
        )
        return

    if args.action == "TRAILING_OFF":
        disable_trailing(state)
        return

    capital = (
        state.balance
        if args.capital is None
        else args.capital
    )

    market_price = current_price(
        args.symbol
    )

    print(
        f"{args.symbol} actual: {market_price:.2f}"
    )

    if args.order_type == "LIMIT":
        create_limit_manual(
            state=state,
            direction=args.action,
            symbol=args.symbol,
            market_price=market_price,
            limit_price=args.limit_price,
            capital=capital,
            leverage=args.leverage,
            stop_loss=args.stop_loss,
            take_profit=args.take_profit,
        )
        return

    open_market_manual(
        state=state,
        direction=args.action,
        symbol=args.symbol,
        price=market_price,
        capital=capital,
        leverage=args.leverage,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit,
    )


if __name__ == "__main__":
    main()
