# PROJECT EDGE

## Motor de Trading Multitemporal

Proyecto independiente de desarrollo de un sistema de análisis y trading algorítmico.

### Objetivo

Detectar estructuras de mercado, tendencias, impulsos, correcciones,
soportes, resistencias y cambios de estructura mediante análisis
multitemporal.

### Modos disponibles

- Solo señales
- Manual PAPER
- AUTO PAPER

El modo REAL está bloqueado por código y no hay claves privadas de Binance.

### Activos

- AUTO v3: ETH/USDT
- Manual y scanner: BTC/USDT y ETH/USDT

### Arquitectura

El motor de análisis será independiente de la ejecución de órdenes.

### Principio de desarrollo

Primero diseñar y validar.
Después backtest.
Después simulación.
Después Testnet.
Finalmente, y solo si los resultados lo justifican, operar en real.

## Estado

Fase: PAPER integrado y en validacion.

El AUTO PAPER, el control manual, el dashboard y las protecciones de riesgo ya estan construidos. El modo REAL permanece bloqueado.

Consultar [PROJECT_STATUS.md](PROJECT_STATUS.md) para ver el ultimo punto verificado, las funciones terminadas y el proximo hito.

Proyecto independiente de SIGNAL BOT.

## Backtest histórico AUTO PAPER

El proyecto incluye un backtest walk-forward para la estrategia propia v3 que:

- utiliza únicamente velas cerradas y confirma los swings sin mirar el futuro;
- entra en la apertura 5M posterior a la señal;
- exige tendencia 4H/1H, EMA 20/50, ADX 14, retroceso 15M y gatillo 5M;
- usa ETHUSDT como activo AUTO inicial;
- arriesga como máximo 0,5% por operación y no usa apalancamiento;
- calcula el STOP con ATR 15M y el objetivo con costos y riesgo/beneficio;
- aplica cooldown de 30 minutos y pausa de 4 horas tras 3 pérdidas seguidas;
- precarga 90 días de calentamiento que no cuentan en el resultado;
- limita la estructura a 500 velas por temporalidad, igual que el bot PAPER;
- incluye comisión de 0,10% y deslizamiento de 0,02% por lado tanto en el backtest como en el saldo AUTO PAPER;
- evalúa exclusivamente señales AUTO y excluye operaciones MANUALES;
- informa operaciones, PnL neto, win rate, drawdown máximo y profit factor.

Ejecución local:

```bash
python run_historical_backtest.py --days 90
```

También puede ejecutarse manualmente desde el workflow
`PROJECT EDGE v3 - Backtest histórico ETH`. El resultado queda disponible
como un artefacto descargable con un resumen JSON y el detalle CSV.

Para una comparación investigativa opcional, sin cambiar el activo AUTO:

```bash
python run_historical_backtest.py --days 90 --symbols BTCUSDT ETHUSDT
```
