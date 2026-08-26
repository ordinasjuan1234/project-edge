# PROJECT EDGE - Instrucciones permanentes

Estas reglas son obligatorias para cualquier persona o agente que trabaje en este repositorio.

## Seguridad

- PAPER es el unico modo de ejecucion habilitado.
- REAL debe permanecer bloqueado hasta una autorizacion futura, explicita y posterior a la validacion completa de PAPER.
- No agregar claves privadas de Binance, credenciales de exchange ni funciones que muevan dinero real.
- Todo punto de entrada capaz de abrir, modificar o cerrar operaciones debe ejecutar `require_paper_mode()` antes de consultar precios o modificar estado.
- Nunca editar manualmente `paper_state.json` ni `dashboard_data.json` para simular resultados; esos archivos son estado operativo y los actualizan los workflows.

## Arquitectura

- Mantener separado el motor de analisis de la ejecucion.
- El AUTO actual ejecuta solamente BTCUSDT en PAPER.
- El control manual PAPER admite BTCUSDT y ETHUSDT.
- SOLUSDT permanece planificado, no habilitado en la ejecucion actual.
- Conservar una sola posicion o una sola orden LIMIT pendiente a la vez.
- PAUSE AUTO y EMERGENCY STOP bloquean nuevas entradas automaticas, pero no deben abandonar la proteccion de posiciones abiertas ni la gestion de una LIMIT pendiente.

## Forma de trabajo

- Leer `PROJECT_STATUS.md` antes de modificar el proyecto.
- Trabajar un solo hito verificable por vez.
- Agregar o actualizar tests para cada cambio funcional.
- Antes de publicar, ejecutar `python -m pytest -q` y las pruebas PAPER indicadas en `PROJECT_STATUS.md`.
- Actualizar `PROJECT_STATUS.md` al cerrar cada hito.
- Los commits automaticos `Update paper trading state and dashboard` son cambios de estado, no nuevos hitos de desarrollo.
