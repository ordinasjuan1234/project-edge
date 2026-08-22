"""
PROJECT EDGE - Manual PAPER Control v5

Control manual simulado para BTC/USDT y ETH/USDT.

Permite:
- LONG / SHORT
- Cierre manual total
- Cierre parcial 25% / 50% / 75% / 100%
- Capital configurable
- Apalancamiento x1/x2/x3
- SL / TP personalizados
- Modificar SL / TP
- Break-even
- Activar / desactivar Trailing Stop

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

# El valor se expresa como porcentaje.
# 0.30 significa 0.30%.
DEFAULT_TRAILING_PCT = 0.30
MIN_TRAILING_PCT = 0.05
MAX_TRAILING_PCT = 5.00

ALLOWED_SYMBOLS = {
    "BTCUSDT",
    "ETHUSDT",
}

ALLOWED_LEVERAGE = {
    1,
    2,
    3,
}

ALLOWED_PARTIAL_PCT = {
    25.0,
    50.0,
    75.0,
    100.0,
}


def current_price(symbol: str) -> float:
    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        symbol,
        limit=100,
    )

    return float(
        data["5M"]["close"].iloc[-1]
    )


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
                "En LONG, el Stop Loss debe estar debajo "
                "de la entrada."
            )

        if tp <= entry_price:
            raise ValueError(
                "En LONG, el Take Profit debe estar encima "
                "de la entrada."
            )

    else:

        if stop <= entry_price:
            raise ValueError(
                "En SHORT, el Stop Loss debe estar encima "
                "de la entrada."
            )

        if tp >= entry_price:
            raise ValueError(
                "En SHORT, el Take Profit debe estar debajo "
                "de la entrada."
            )

    return stop, tp


def open_manual(
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

    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(
            "Activo no permitido."
        )

    if leverage not in ALLOWED_LEVERAGE:
        raise ValueError(
            "El apalancamiento PAPER permitido es "
            "x1, x2 o x3."
        )

    capital = float(capital)

    if capital <= 0:
        raise ValueError(
            "El capital debe ser mayor que 0."
        )

    if capital > state.balance:
        raise ValueError(
            "Capital insuficiente. "
            f"Saldo PAPER disponible: "
            f"{state.balance:.2f} USDT."
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

    # Trailing inicialmente desactivado.
    position["trailing_enabled"] = False
    position["trailing_pct"] = None
    position["trailing_anchor"] = None

    state.data["position"] = position
    state.save()

    print("=" * 60)
    print("PROJECT EDGE - ENTRADA MANUAL PAPER")
    print("=" * 60)

    print(f"Trade ID:         {position['trade_id']}")
    print(f"Activo:           {position['symbol']}")
    print(f"Direccion:        {position['direction']}")
    print(f"Entrada:          {position['entry_price']:.2f}")
    print(f"Capital:          {capital:.2f} USDT")
    print(f"Apalancamiento:   x{leverage}")
    print(f"Exposicion:       {exposure:.2f} USDT")
    print(f"Cantidad:         {position['quantity']:.8f}")
    print(f"Stop Loss:        {position['stop_loss']:.2f}")
    print(f"Take Profit:      {position['take_profit']:.2f}")
    print("Trailing Stop:    DESACTIVADO")
    print(f"Saldo PAPER:      {state.balance:.2f} USDT")

    print(
        "NO se envio ninguna orden real."
    )


def close_manual(
    state: PaperState,
) -> None:

    if not state.has_open_position:
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
            "No hay una posicion PAPER abierta "
            "para realizar cierre parcial."
        )

    if partial_pct is None:
        raise ValueError(
            "Debes indicar el porcentaje de cierre parcial."
        )

    pct = float(partial_pct)

    if pct not in ALLOWED_PARTIAL_PCT:
        raise ValueError(
            "Cierre parcial permitido: "
            "25%, 50%, 75% o 100%."
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
            f"PnL total trade:  "
            f"{result['pnl']:.4f} USDT"
        )
        print(
            f"Saldo PAPER:      "
            f"{result['balance']:.2f} USDT"
        )
        print("Posicion:         CERRADA")

    else:
        print(
            f"Cierre solicitado: {pct:.0f}% "
            "de la cantidad abierta"
        )

        print(
            f"Cantidad cerrada:  "
            f"{result['closed_quantity']:.8f}"
        )

        print(
            f"Cantidad restante: "
            f"{result['remaining_quantity']:.8f}"
        )

        print(
            f"PnL parcial:       "
            f"{result['pnl']:.4f} USDT"
        )

        print(
            f"PnL realizado:     "
            f"{result['realized_pnl_total']:.4f} USDT"
        )

        print(
            f"Saldo PAPER:       "
            f"{result['balance']:.2f} USDT"
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
            "No hay una posicion PAPER abierta "
            "para modificar."
        )

    if stop_loss is None and take_profit is None:
        raise ValueError(
            "Ingresa un nuevo Stop Loss, "
            "Take Profit o ambos."
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
                "En LONG, el Stop Loss debe estar "
                "debajo del precio actual."
            )

        if new_tp <= price:
            raise ValueError(
                "En LONG, el Take Profit debe estar "
                "encima del precio actual."
            )

    else:

        if new_stop <= price:
            raise ValueError(
                "En SHORT, el Stop Loss debe estar "
                "encima del precio actual."
            )

        if new_tp >= price:
            raise ValueError(
                "En SHORT, el Take Profit debe estar "
                "debajo del precio actual."
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
            "No hay una posicion PAPER abierta "
            "para aplicar Break-even."
        )

    position = state.position

    symbol = position["symbol"]
    direction = position["direction"]

    entry_price = float(
        position["entry_price"]
    )

    price = current_price(symbol)

    if (
        direction == "LONG"
        and price <= entry_price
    ):
        raise ValueError(
            "Break-even LONG solo se habilita "
            "cuando el precio esta por encima "
            "de la entrada."
        )

    if (
        direction == "SHORT"
        and price >= entry_price
    ):
        raise ValueError(
            "Break-even SHORT solo se habilita "
            "cuando el precio esta por debajo "
            "de la entrada."
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
        f"TP actual:   "
        f"{position['take_profit']:.2f}"
    )


def enable_trailing(
    state: PaperState,
    trailing_pct: float | None,
) -> None:

    if not state.has_open_position:
        raise ValueError(
            "No hay una posicion PAPER abierta "
            "para activar Trailing Stop."
        )

    pct = (
        DEFAULT_TRAILING_PCT
        if trailing_pct is None
        else float(trailing_pct)
    )

    if (
        pct < MIN_TRAILING_PCT
        or pct > MAX_TRAILING_PCT
    ):
        raise ValueError(
            "Trailing Stop permitido: "
            f"{MIN_TRAILING_PCT:.2f}% a "
            f"{MAX_TRAILING_PCT:.2f}%."
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

        candidate_stop = (
            price * (1.0 - distance)
        )

        new_stop = max(
            current_stop,
            candidate_stop,
        )

    else:

        candidate_stop = (
            price * (1.0 + distance)
        )

        new_stop = min(
            current_stop,
            candidate_stop,
        )

    position["trailing_enabled"] = True
    position["trailing_pct"] = pct
    position["trailing_anchor"] = price

    # Nunca afloja un SL que ya estaba mejor.
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
            "No hay una posicion PAPER abierta "
            "para desactivar Trailing Stop."
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
        f"Activo:       "
        f"{position['symbol']}"
    )

    print(
        f"Stop actual:  "
        f"{float(position['stop_loss']):.2f}"
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
            "PARTIAL_CLOSE",
            "UPDATE_RISK",
            "BREAK_EVEN",
            "TRAILING_ON",
            "TRAILING_OFF",
        ],
    )

    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        choices=sorted(
            ALLOWED_SYMBOLS
        ),
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
        choices=sorted(
            ALLOWED_LEVERAGE
        ),
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
            "Distancia del Trailing Stop "
            "en porcentaje. "
            "Ejemplo: 0.30 = 0.30%%."
        ),
    )

    parser.add_argument(
        "--partial-pct",
        type=float,
        default=None,
        help=(
            "Porcentaje de la cantidad abierta "
            "a cerrar: 25, 50, 75 o 100."
        ),
    )

    args = parser.parse_args()

    state = PaperState(
        initial_balance=INITIAL_BALANCE
    )

    if args.action == "CLOSE":
        close_manual(state)
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

    price = current_price(
        args.symbol
    )

    print(
        f"{args.symbol} actual: "
        f"{price:.2f}"
    )

    open_manual(
        state=state,
        direction=args.action,
        symbol=args.symbol,
        price=price,
        capital=capital,
        leverage=args.leverage,
        stop_loss=args.stop_loss,
        take_profit=args.take_profit,
    )


if __name__ == "__main__":
    main()
