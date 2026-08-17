"""
PROJECT EDGE
Primera prueba de Paper Trading

Operacion simulada.
NO conecta con Binance.
NO ejecuta dinero real.
"""

from paper_trader import PaperTrader


def main():
    trader = PaperTrader(initial_balance=10000.0)

    print("=" * 60)
    print("PROJECT EDGE - PAPER TRADING DEMO")
    print("=" * 60)

    position = trader.open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=64000.0,
        quantity=0.01,
        stop_loss=63500.0,
        take_profit=65000.0,
    )

    print("")
    print("OPERACION ABIERTA")
    print(f"Activo:       {position.symbol}")
    print(f"Direccion:    {position.direction}")
    print(f"Entrada:      {position.entry_price}")
    print(f"Cantidad:     {position.quantity}")
    print(f"Stop Loss:    {position.stop_loss}")
    print(f"Take Profit:  {position.take_profit}")
    print(f"Saldo demo:   {trader.balance:.2f}")
    print("")

    print("Simulando movimiento del precio...")

    result = trader.update_price(65000.0)

    print("")

    if result:
        print("OPERACION CERRADA")
        print(f"Motivo:       {result['reason']}")
        print(f"Entrada:      {result['entry_price']}")
        print(f"Salida:       {result['exit_price']}")
        print(f"PnL:          {result['pnl']:.2f}")
        print(f"Saldo final:  {result['balance']:.2f}")
    else:
        print("La operacion continua abierta.")

    print("")
    print("=" * 60)
    print("FIN DE PRUEBA DEMO")
    print("=" * 60)


if __name__ == "__main__":
    main()
