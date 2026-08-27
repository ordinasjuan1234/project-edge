from datetime import datetime, timezone

import pytest

from run_historical_backtest import reference_now_for_years_ago


def test_reference_now_moves_in_fixed_365_day_blocks():
    current = datetime(2026, 8, 27, 12, 30, tzinfo=timezone.utc)

    assert reference_now_for_years_ago(0, current) == current
    assert reference_now_for_years_ago(1, current) == datetime(
        2025,
        8,
        27,
        12,
        30,
        tzinfo=timezone.utc,
    )
    assert reference_now_for_years_ago(2, current) == datetime(
        2024,
        8,
        27,
        12,
        30,
        tzinfo=timezone.utc,
    )


def test_reference_now_rejects_unsupported_year_offset():
    with pytest.raises(ValueError, match="0 y 5"):
        reference_now_for_years_ago(6)


def test_reference_now_assigns_utc_to_naive_timestamp():
    current = datetime(2026, 8, 27, 12, 30)

    result = reference_now_for_years_ago(1, current)

    assert result.tzinfo == timezone.utc
