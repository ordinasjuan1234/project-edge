from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from run_btc_paper import auto_cooldown_remaining_minutes


NOW = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def state_with_trades(trades):
    return SimpleNamespace(data={"closed_trades": trades})


def test_recent_auto_close_activates_cooldown():
    state = state_with_trades(
        [
            {
                "source": "AUTO",
                "closed_at": "2026-08-26T11:45:00+00:00",
            }
        ]
    )

    remaining = auto_cooldown_remaining_minutes(state, now=NOW)

    assert remaining == pytest.approx(15.0)


def test_expired_auto_cooldown_allows_new_entry():
    state = state_with_trades(
        [
            {
                "source": "AUTO",
                "closed_at": "2026-08-26T11:29:00+00:00",
            }
        ]
    )

    assert auto_cooldown_remaining_minutes(state, now=NOW) == 0.0


def test_manual_close_does_not_activate_auto_cooldown():
    state = state_with_trades(
        [
            {
                "source": "AUTO",
                "closed_at": "2026-08-26T11:00:00+00:00",
            },
            {
                "source": "MANUAL",
                "closed_at": "2026-08-26T11:55:00+00:00",
            },
        ]
    )

    assert auto_cooldown_remaining_minutes(state, now=NOW) == 0.0
