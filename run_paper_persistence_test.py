"""
PROJECT EDGE
Paper Persistence Test

Prueba controlada de persistencia entre ejecuciones.

NO conecta con Binance.
NO usa dinero real.
NO modifica paper_state.json.
"""

from pathlib import Path

from paper_state import PaperState


TEST_STATE_FILE = "paper_state_persistence_test.json"
INITIAL_BALANCE = 10000.0


def main():
    state_file = Path(TEST_STATE_FILE)

    print("=" * 60)
    print("PROJECT EDGE - PAPER PERSISTENCE TEST")
    print("=" * 60)

    existed_before = state_file.exists()

    state = PaperState(
        file_path=TEST_STATE_FILE,
        initial_balance=INITIAL_BALANCE,
    )

    print(f"Archivo existia: {existed_before}")
    print(f"Saldo cargado:   {state.balance:.2f} USDT")
    print(f"Posicion abierta:{state.has_open_position}")
    print(f"Trades cerrados: {state.status()['closed_trades']}")
    print("")

    # PRIMERA EJECUCION:
    # crea y guarda una posicion demo.
    if not existed_before:
        position = state.open_position(
            symbol="BTCUSDT",
            direction="LONG",
            entry_price=64000.0,
            quantity=0.01,
            stop_loss=63500.0,
            take_profit=65000.0,
        )

        print("ETAPA 1 - POSICION CREADA Y GUARDADA")
        print(f"Activo:      {position['symbol']}")
        print(f"Direccion:   {position['direction']}")
        print(f"Entrada:     {position['entry_price']}")
        print(f"Stop Loss:   {position['stop_loss']}")
        print(f"Take Profit: {position['take_profit']}")
        print("")
        print(
            "En la proxima ejecucion esta posicion "
            "debe ser recuperada."
        )
        print("=" * 60)
        return

    # SEGUNDA EJECUCION:
    # comprueba que GitHub recupero la posicion anterior.
    if state.has_open_position:
        position = state.position

        print("ETAPA 2 - POSICION RECUPERADA")
        print(f"Activo:      {position['symbol']}")
        print(f"Direccion:   {position['direction']}")
        print(f"Entrada:     {position['entry_price']}")
        print(f"Stop Loss:   {position['stop_loss']}")
        print(f"Take Profit: {position['take_profit']}")
        print("")

        result = state.close_position(
            exit_price=65000.0,
            reason="PERSISTENCE_TEST_TAKE_PROFIT",
        )

        print("POSICION CERRADA EN PRUEBA")
        print(f"Salida:      {result['exit_price']}")
        print(f"PnL:         {result['pnl']:.2f} USDT")
        print(f"Saldo final: {result['balance']:.2f} USDT")
        print("")
        print("PERSISTENCIA ENTRE EJECUCIONES: OK")
        print("=" * 60)
        return

    # TERCERA EJECUCION O POSTERIORES:
    # confirma que tambien quedo guardado el cierre.
    print("ETAPA 3 - ESTADO FINAL RECUPERADO")
    print(f"Saldo:          {state.balance:.2f} USDT")
    print(f"Posicion:       {state.position}")
    print(
        f"Trades cerrados:{state.status()['closed_trades']}"
    )
    print("")
    print("PERSISTENCIA COMPLETA: OK")
    print("=" * 60)


if __name__ == "__main__":
    main()
