# PROJECT EDGE - Estado permanente

Ultima revision tecnica: 25 de agosto de 2026.

Este archivo es la memoria operativa del proyecto. Debe consultarse al iniciar un chat nuevo y actualizarse al terminar cada hito.

## Restriccion principal

PROJECT EDGE opera exclusivamente en PAPER. El modo REAL esta bloqueado por `trading_mode.py`, no hay API privada de Binance conectada y ninguna funcion actual puede mover dinero real.

## Ultimo punto verificado

- Ultimo commit humano anterior a esta revision: `8ba65c5` (`Agregar bloqueo central PAPER REAL`).
- El runner AUTO PAPER continua ejecutandose aproximadamente cada cinco minutos mediante GitHub Actions.
- El ultimo workflow AUTO consultado finalizo correctamente.
- Los commits automaticos posteriores solo actualizaron `paper_state.json` y `dashboard_data.json`.
- Snapshot observado durante esta revision: saldo PAPER 9943.64 USDT, 16 operaciones cerradas, sin posicion abierta, sin LIMIT pendiente y AUTO habilitado. Este snapshot cambia con la operacion del bot y no representa un hito de desarrollo.

## Funciones terminadas

- Swing Detector causal, HH/HL/LH/LL, BOS/CHoCH, soportes/resistencias e impulso/correccion.
- Motor estructural multitemporal para 4H, 1H, 30M, 15M y 5M.
- Fair Value Gap integrado al motor de decision y visible en el dashboard.
- `DecisionEngine` y `EntryReadiness` con bloqueo cuando falta alineacion.
- AUTO PAPER para BTCUSDT con datos publicos reales y estado persistente.
- Control manual PAPER para BTCUSDT y ETHUSDT.
- Ordenes MARKET y LIMIT PAPER.
- Stop Loss, Take Profit, cierres parciales 25/50/75/100, break-even y trailing stop.
- PAUSE AUTO, RESUME AUTO y EMERGENCY STOP AUTO.
- Scanner manual BTC/ETH, dashboard GitHub Pages y alertas Telegram PAPER.
- Workflows de tests, persistencia, demostracion PAPER y validacion completa.

## Ultimo hito completado

La barrera central PAPER/REAL quedo cerrada:

- `require_paper_mode()` esta conectado al runner AUTO y al control manual.
- La barrera se ejecuta antes de consultar precios o modificar estado.
- Hay pruebas para PAPER por defecto, REAL bloqueado, modo invalido y puntos de entrada protegidos.
- Verificacion local: 111 tests superados y demostracion PAPER completada.
- Prueba directa: AUTO y MANUAL rechazan `PROJECT_EDGE_MODE=REAL` antes de realizar cualquier operacion.

## Hito actual

Validacion historica realista del motor antes de considerar Testnet o REAL:

- Ejecutar el backtest con datos historicos reales de BTCUSDT y ETHUSDT.
- Separar operaciones AUTO de las pruebas y operaciones MANUALES.
- Informar cantidad de operaciones, PnL, win rate, drawdown maximo y profit factor.
- Revisar si existen suficientes entradas confirmadas; no flexibilizar reglas solo para aumentar operaciones.
- Mantener REAL bloqueado independientemente del resultado hasta una decision explicita posterior.

## Verificacion obligatoria

```bash
python -m pytest -q
python run_paper_trade_test.py
```

La prueba de persistencia debe ejecutarse en su workflow controlado porque utiliza un archivo de estado entre ejecuciones.
