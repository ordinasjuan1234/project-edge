import json
from datetime import datetime


def build_dashboard_data(
    symbol,
    btc_price,
    analysis,
    decision,
    readiness,
    structural_levels=None,
):
    """
    Convierte la salida de PROJECT EDGE en datos preparados
    para ser mostrados por el dashboard.
    """

    structural_levels = structural_levels or {}

    dashboard = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "price": btc_price,

        "timeframes": {
            "4H": analysis.get("4H", "UNKNOWN"),
            "1H": analysis.get("1H", "UNKNOWN"),
            "30M": analysis.get("30M", "UNKNOWN"),
            "15M": analysis.get("15M", "UNKNOWN"),
            "5M": analysis.get("5M", "UNKNOWN"),
        },

        "decision": {
            "alignment": decision.get("alignment", "NO_DIRECTION"),
            "action": decision.get("decision", "WAIT"),
            "direction": decision.get("direction"),
            "can_execute": decision.get("can_execute", False),
        },

        "readiness": {
            "status": readiness.get("status", "NOT_READY"),
            "bias": readiness.get("bias"),
            "message": readiness.get("message", ""),
            "missing_conditions": readiness.get(
                "missing_conditions", []
            ),
        },

        "structural_levels": structural_levels,
    }

    return dashboard


def save_dashboard_data(data, filename="dashboard_data.json"):
    """
    Guarda los datos para que posteriormente
    la interfaz visual pueda leerlos.
    """

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    return filename
