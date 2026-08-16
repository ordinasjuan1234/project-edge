"""
PROJECT EDGE
BTC Real Decision + Entry Readiness

Datos públicos de BTCUSDT.
No usa API key.
No accede a saldo.
No ejecuta órdenes.
"""
import os
import urllib.parse
import urllib.request
from engine.data.binance_historical_data import BinanceHistoricalData
from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)
from engine.decision.decision_engine import DecisionEngine
from engine.decision.entry_readiness import EntryReadiness
from engine.structure.swing_detector import detect_swings
from engine.structure.support_resistance import calculate_structural_levels
def send_telegram_message(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram: credenciales no configuradas")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
    }).encode("utf-8")

    try:
        with urllib.request.urlopen(url, data=data, timeout=15) as response:
            if response.status == 200:
                print("Telegram: mensaje enviado correctamente")
            else:
                print(f"Telegram: error HTTP {response.status}")
    except Exception as error:
        print(f"Telegram: error al enviar mensaje: {error}")
def main():
    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        "BTCUSDT",
        limit=500,
    )

    btc_price = float(data["5M"]["close"].iloc[-1])

    structural_levels = {}

    for timeframe in ("30M", "15M"):
        swings = detect_swings(data[timeframe].copy())
        levels = calculate_structural_levels(swings)
        structural_levels[timeframe] = levels.iloc[-1]

    mtf = MultiTimeframeStructureEngine(
        structure_engine_kwargs={
            "pivot_left": 2,
            "pivot_right": 2,
            "atr_period": 14,
            "atr_multiplier": 1.5,
            "min_move_pct": 0.0025,
            "max_move_pct": 0.05,
        }
    ).analyze(data)

    decision = DecisionEngine().decide(mtf)

    readiness = EntryReadiness().evaluate(
        mtf_result=mtf,
        decision_result=decision,
    )

    print("=" * 60)
    print("PROJECT EDGE - BTCUSDT REAL DECISION + READINESS")
    print("=" * 60)

    for timeframe, state in mtf["states"].items():
        print(f"{timeframe:>3}: {state}")

    print("-" * 60)
    print(f"Alignment:   {mtf['alignment']['alignment']}")
    print(f"Entry ready: {mtf['alignment']['entry_ready']}")
    print(f"BTC price:   {btc_price}")

    print("-" * 60)
    print(f"Decision:    {decision.get('decision')}")
    print(f"Direction:   {decision.get('direction')}")
    print(f"Can execute: {decision.get('can_execute')}")

    print("-" * 60)
    print("ENTRY READINESS")
    print(f"Status:      {readiness.get('status')}")
    print(f"Bias:        {readiness.get('bias')}")
    print(f"Message:     {readiness.get('message')}")

    missing = readiness.get("missing_conditions", [])

    if missing:
        print("Missing conditions:")
        for condition in missing:
            print(f"- {condition}")
    else:
        print("Missing conditions: none")

    print("=" * 60)
    print("STRUCTURAL LEVELS")

    for timeframe, levels in structural_levels.items():
        print(
            f"{timeframe}: "
            f"Support={levels.get('structural_support')} | "
            f"Resistance={levels.get('structural_resistance')}"
        )

    print("=" * 60)
    status = readiness.get("status")
    bias = readiness.get("bias")

    if status == "NOT_READY":
        estado_operativo = f"{bias} EN ESPERA"
    else:
        estado_operativo = status

    missing = readiness.get("missing_conditions", [])
    missing_text = "\n".join(f"- {item}" for item in missing) if missing else "- Sin condiciones pendientes"

    nivel_30m = structural_levels.get("30M", {})
    nivel_15m = structural_levels.get("15M", {})
    def simbolo_estado(estado):
        if estado == "TRANSITION":
            return "⏳"

        if bias == "SHORT":
            return "✅" if estado == "BEARISH" else "❌"

        if bias == "LONG":
            return "✅" if estado == "BULLISH" else "❌"

        return "⏳"

    s4h = simbolo_estado(mtf["states"].get("4H"))
    s1h = simbolo_estado(mtf["states"].get("1H"))
    s30m = simbolo_estado(mtf["states"].get("30M"))
    s15m = simbolo_estado(mtf["states"].get("15M"))
    s5m = simbolo_estado(mtf["states"].get("5M"))
    entrada_confirmada = (
        status == "READY"
        and decision.get("decision") != "BLOCKED"
        and decision.get("direction") in ("LONG", "SHORT")
    )
    
    telegram_message = (
        "PROJECT EDGE - BTCUSDT\n\n"
        f"Precio: {btc_price:.2f}\n\n"
        f"Sesgo macro: {bias}\n"
        f"Estado: {estado_operativo}\n\n"
        f"4H: {mtf['states'].get('4H')} {s4h}\n"
        f"1H: {mtf['states'].get('1H')} {s1h}\n"
        f"30M: {mtf['states'].get('30M')} {s30m}\n"
        f"15M: {mtf['states'].get('15M')} {s15m}\n"
        f"5M: {mtf['states'].get('5M')} {s5m}\n\n"
        f"Decision: {decision.get('decision')}\n"
        f"Direction: {decision.get('direction')}\n"
        f"Readiness: {status}\n\n"
        f"Falta para habilitar entrada:\n{missing_text}\n\n"
        f"Niveles estructurales:\n"
        f"30M Soporte: {nivel_30m.get('structural_support')} | Resistencia: {nivel_30m.get('structural_resistance')}\n"
        f"15M Soporte: {nivel_15m.get('structural_support')} | Resistencia: {nivel_15m.get('structural_resistance')}\n\n"
        f"Mensaje: {readiness.get('message')}"
    )
    if entrada_confirmada:
        send_telegram_message(telegram_message)
    else:
        print("Telegram: sin entrada confirmada, no se envia mensaje")

    if __name__ == "__main__":
        main()
   
