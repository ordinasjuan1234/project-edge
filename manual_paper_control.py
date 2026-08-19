"""
PROJECT EDGE - Manual PAPER Control

Permite abrir/cerrar posiciones simuladas desde un workflow manual.
NO envia ordenes reales. NO usa API privada de Binance.
"""

from __future__ import annotations

import argparse

from engine.data.binance_historical_data import BinanceHistoricalData
from paper_state import PaperState


SYMBOL = "BTCUSDT"
INITIAL_BALANCE = 10000.0
STOP_PCT = 0.005
TAKE_PROFIT_PCT = 0.01


def current_price() -> float:
    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        SYMBOL,
        limit=100,
    )
    return float(data["5M"]["close"].iloc[-1])


def levels(direction: str, entry_price: float) -> tuple[float, float]:
    if direction == "LONG":
        return (
            entry_price * (1.0 - STOP_PCT),
            entry_price * (1.0 + TAKE_PROFIT_PCT),
        )

    return (
        entry_price * (1.0 + STOP_PCT),
        entry_price * (1.0 - TAKE_PROFIT_PCT),
    )


def open_manual(state: PaperState, direction: str, price: float) -> None:
    if state.has_open_position:
        pos = state.position
        print(
            "NO SE ABRE OTRA POSICION: ya existe una "
            f"{pos['direction']} en {pos['entry_price']:.2f}."
        )
        return

    stop_loss, take_profit = levels(direction, price)
    quantity = state.balance / price

    position = state.open_position(
        symbol=SYMBOL,
        direction=direction,
        entry_price=price,
        quantity=quantity,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    print("=" * 60)
    print("PROJECT EDGE - ENTRADA MANUAL PAPER")
    print("=" * 60)
    print(f"Activo:      {position['symbol']}")
    print(f"Direccion:   {position['direction']}")
    print(f"Entrada:     {position['entry_price']:.2f}")
    print(f"Cantidad:    {position['quantity']:.8f}")
    print(f"Stop Loss:   {position['stop_loss']:.2f}")
    print(f"Take Profit: {position['take_profit']:.2f}")
    print(f"Saldo PAPER: {state.balance:.2f} USDT")
    print("NO se envio ninguna orden real.")


def close_manual(state: PaperState, price: float) -> None:
    if not state.has_open_position:
        print("NO HAY POSICION PAPER ABIERTA PARA CERRAR.")
        return

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
    args = parser.parse_args()

    state = PaperState(initial_balance=INITIAL_BALANCE)
    price = current_price()

    print(f"BTC actual: {price:.2f}")

    if args.action in {"LONG", "SHORT"}:
        open_manual(state, args.action, price)
    else:
        close_manual(state, price)


if __name__ == "__main__":
    main()
