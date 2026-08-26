# PROJECT EDGE - Estado permanente

Ultima revision tecnica: 26 de agosto de 2026.

Este archivo es la memoria operativa del proyecto. Debe consultarse al iniciar un chat nuevo y actualizarse al terminar cada hito.

## Restriccion principal

PROJECT EDGE opera exclusivamente en PAPER. El modo REAL esta bloqueado por `trading_mode.py`, no hay API privada de Binance conectada y ninguna funcion actual puede mover dinero real.

## Ultimo punto verificado

- Ultimo commit humano anterior a esta revision: `1ec3978` (`Aplicar enfriamiento AUTO de 30 minutos`).
- El runner AUTO PAPER continua ejecutandose aproximadamente cada cinco minutos mediante GitHub Actions.
- El ultimo workflow AUTO consultado finalizo correctamente.
- Los commits automaticos posteriores solo actualizaron `paper_state.json` y `dashboard_data.json`.
- Snapshot observado durante esta revision: saldo PAPER 9943.64 USDT, 16 operaciones cerradas, sin posicion abierta, sin LIMIT pendiente y AUTO habilitado. Este snapshot cambia con la operacion del bot y no representa un hito de desarrollo.

## Funciones terminadas

- Swing Detector causal, HH/HL/LH/LL, BOS/CHoCH, soportes/resistencias e impulso/correccion.
- Motor estructural multitemporal para 4H, 1H, 30M, 15M y 5M.
- Fair Value Gap integrado al motor de decision y visible en el dashboard.
- `DecisionEngine` y `EntryReadiness` con bloqueo cuando falta alineacion.
- AUTO PAPER v3 para ETHUSDT con datos publicos reales y estado persistente.
- Control manual PAPER para BTCUSDT y ETHUSDT.
- Ordenes MARKET y LIMIT PAPER.
- Stop Loss, Take Profit, cierres parciales 25/50/75/100, break-even y trailing stop.
- PAUSE AUTO, RESUME AUTO y EMERGENCY STOP AUTO.
- Scanner manual BTC/ETH, dashboard GitHub Pages y alertas Telegram PAPER.
- Workflows de tests, persistencia, demostracion PAPER y validacion completa.

## Ultimo hito completado

Se implemento la primera candidata de la estrategia propia PROJECT EDGE v3:

- AUTO inicial limitado a ETHUSDT; BTC queda disponible solo en manual/scanner.
- Contexto 4H/1H con estructura, EMA 20/50 y pendiente de EMA.
- ADX 14 minimo 25 y creciente para evitar tendencias sin fuerza.
- Retroceso reciente en 15M y recuperacion/BOS/CHoCH como gatillo 5M.
- FVG se conserva como confluencia visible, pero no crea una señal por si solo.
- Stop adaptativo de 1,5 ATR 15M, con piso 0,3% y bloqueo sobre 3%.
- Objetivo minimo 2R bruto y 1,5R neto estimado despues de costos.
- Riesgo maximo 0,5% del saldo y exposicion maxima 100%, siempre x1.
- Cooldown de 30 minutos y bloqueo de 4 horas tras 3 perdidas AUTO consecutivas.
- El runner PAPER y el backtest usan el mismo modulo de decision y riesgo.
- El backtest precarga 90 dias de calentamiento y replica la ventana estructural de 500 velas del runner PAPER.
- El saldo AUTO PAPER descuenta comision y deslizamiento simulados al cerrar.
- El dashboard principal pasa a mostrar ETHUSDT y la decision v3.
- Verificacion local: 139 tests superados y demostracion PAPER completada.
- Prueba directa: `PROJECT_EDGE_MODE=REAL` sigue bloqueando el runner antes de consultar datos o estado.

## Hito actual

Validacion historica realista del motor antes de considerar Testnet o REAL:

- Ejecutar el backtest v3 con datos historicos reales de ETHUSDT.
- Separar operaciones AUTO de las pruebas y operaciones MANUALES.
- Informar cantidad de operaciones, PnL, win rate, drawdown maximo y profit factor.
- Revisar si existen suficientes entradas confirmadas; no flexibilizar reglas solo para aumentar operaciones.
- Mantener REAL bloqueado independientemente del resultado hasta una decision explicita posterior.

### Avance implementado y resultados de referencia v2

- Se agrego un backtest walk-forward conjunto para BTCUSDT y ETHUSDT.
- Las temporalidades 4H, 1H, 30M, 15M y 5M se construyen desde un unico historial 5M y solo usan velas cerradas.
- Los swings quedan disponibles recien en su vela de confirmacion para evitar look-ahead bias.
- Las entradas se simulan en la apertura de la vela 5M posterior a la señal.
- Se conserva la politica conservadora de asumir STOP primero cuando STOP y TARGET aparecen en la misma vela.
- El calculo incluye comision de 0,10% y deslizamiento de 0,02% por lado.
- Los resultados incluyen solo señales AUTO; las operaciones MANUALES y de prueba quedan excluidas.
- El reporte informa operaciones, PnL neto, win rate, drawdown maximo, profit factor, costos y detalle CSV.
- El workflow historico permite elegir 30, 60, 90 o 180 dias y publica el reporte como artefacto descargable.
- Verificacion local del nuevo modulo: 120 tests superados, prueba PAPER completada y recorrido historico sintetico de punta a punta superado.

### Hallazgo del backtest de 90 dias

- El workflow historico completo correctamente con 87 operaciones AUTO simuladas.
- Resultado conjunto: -8,53%, win rate 34,48% y profit factor 0,58.
- El bruto antes de comisiones quedo practicamente neutro (+3,83 USDT), pero las comisiones sumaron 1710,28 USDT.
- Se detectaron 42 reentradas en el mismo simbolo y direccion dentro de los cinco minutos posteriores a un cierre.
- El enfriamiento AUTO de 30 minutos solicitado no estaba implementado en el runner ni en el backtest.
- Se agrego el mismo bloqueo persistente al AUTO PAPER y al backtest para evitar reentradas inmediatas. REAL continua bloqueado.
- Verificacion local de la correccion: 125 tests superados, demostracion PAPER completada y rechazo directo de REAL confirmado antes de consultar precios.
- Esta repeticion se completo y su resultado queda registrado a continuacion; v2 se descarto como candidata.

### Resultado posterior con cooldown sobre v2

- 90 dias: 55 operaciones, retorno -5,45%, costos 1082 USDT y cero reentradas inmediatas.
- 180 dias: 93 operaciones, win rate 36,56%, retorno -7,71%, profit factor 0,63 y drawdown 8,47%.
- Costos 180 dias: 1818,56 USDT; el bruto fue +277,14 USDT, pero el neto termino en -1541,42 USDT.
- BTC perdio aproximadamente 1157 USDT y ETH aproximadamente 384 USDT.
- Veredicto: v2 no tiene ventaja neta suficiente. No se habilita REAL ni se intenta recuperar aumentando riesgo.

### Proximo paso verificable

- Ejecutar `PROJECT EDGE v3 - Backtest historico ETH` con 90 dias.
- Si completa correctamente, repetir con 180 dias sin cambiar parametros entre ambas corridas.
- Comparar operaciones, retorno neto, costos, profit factor y drawdown con v2.
- Mantener el bot exclusivamente en PAPER aunque v3 resulte positivo.

## Verificacion obligatoria

```bash
python -m pytest -q
python run_paper_trade_test.py
```

La prueba de persistencia debe ejecutarse en su workflow controlado porque utiliza un archivo de estado entre ejecuciones.
