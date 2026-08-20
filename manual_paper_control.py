"""
PROJECT EDGE - Manual PAPER Control v2

Control manual simulado para BTC/USDT y ETH/USDT.
Permite elegir capital, apalancamiento x1/x2/x3 y SL/TP.
NO envia ordenes reales. NO usa API privada de Binance.
"""

from __future__ import annotations

import argparse

from engine.data.binance_historical_data import BinanceHistoricalData
from paper_state import PaperState


INITIAL_BALANCE = 10000.0
DEFAULT_STOP_PCT = 0.005
DEFAULT_TAKE_PROFIT_PCT = 0.01
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
ALLOWED_LEVERAGE = {1, 2, 3}


def current_price(symbol: str) -> float:
    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        symbol,
        limit=100,
    )
    return float(data["5M"]["close"].iloc[-1])


def default_levels(direction: str, entry_price: float) -> tuple[float, float]:
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
    default_stop, default_tp = default_levels(direction, entry_price)

    stop = float(stop_loss) if stop_loss is not None else default_stop
    tp = float(take_profit) if take_profit is not None else default_tp

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
        raise ValueError("Activo no permitido.")

    if leverage not in ALLOWED_LEVERAGE:
        raise ValueError(
            "El apalancamiento PAPER permitido es x1, x2 o x3."
        )

    capital = float(capital)

    if capital <= 0:
        raise ValueError("El capital debe ser mayor que 0.")

    if capital > state.balance:
        raise ValueError(
            f"Capital insuficiente. Saldo PAPER disponible: "
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
    )

    position["capital"] = capital
    position["leverage"] = leverage
    position["exposure"] = exposure
    position["order_type"] = "MARKET"

    state.data["position"] = position
    state.save()

    print("=" * 60)
    print("PROJECT EDGE - ENTRADA MANUAL PAPER")
    print("=" * 60)
    print(f"Activo:          {position['symbol']}")
    print(f"Direccion:       {position['direction']}")
    print(f"Entrada:         {position['entry_price']:.2f}")
    print(f"Capital:         {capital:.2f} USDT")
    print(f"Apalancamiento:  x{leverage}")
    print(f"Exposicion:      {exposure:.2f} USDT")
    print(f"Cantidad:        {position['quantity']:.8f}")
    print(f"Stop Loss:       {position['stop_loss']:.2f}")
    print(f"Take Profit:     {position['take_profit']:.2f}")
    print(f"Saldo PAPER:     {state.balance:.2f} USDT")
    print("NO se envio ninguna orden real.")


def close_manual(state: PaperState) -> None:
    if not state.has_open_position:
        print("NO HAY POSICION PAPER ABIERTA PARA CERRAR.")
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
    print(f"PnL:         {trade['pnl']:.2f} USDT")
    print(f"Saldo PAPER: {trade['balance']:.2f} USDT")
    print("NO se envio ninguna orden real.")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--action",
        required=True,
        choices=["LONG", "SHORT", "CLOSE"],
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
        "--stop-loss",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--take-profit",
        type=float,
        default=None,
    )

    args = parser.parse_args()

    state = PaperState(initial_balance=INITIAL_BALANCE)

    if args.action == "CLOSE":
        close_manual(state)
        return

    capital = (
        state.balance
        if args.capital is None
        else args.capital
    )

    price = current_price(args.symbol)

    print(f"{args.symbol} actual: {price:.2f}")

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
