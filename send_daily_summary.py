"""Envía por Telegram el resumen PAPER del día anterior en Argentina."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from paper_state import PaperState
from telegram_notifier import (
    DEFAULT_REPORT_TIMEZONE,
    notify_daily_summary,
)
from trading_mode import require_paper_mode


def main() -> None:
    require_paper_mode()
    local_now = datetime.now(
        ZoneInfo(DEFAULT_REPORT_TIMEZONE)
    )
    report_date = local_now.date() - timedelta(days=1)
    state = PaperState()
    sent = notify_daily_summary(
        state.data,
        report_date=report_date,
    )
    if sent:
        print(
            "TELEGRAM: resumen PAPER enviado para "
            f"{report_date.isoformat()}."
        )
    else:
        print(
            "TELEGRAM: el resumen PAPER no pudo enviarse; "
            "el estado del bot no fue modificado."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
