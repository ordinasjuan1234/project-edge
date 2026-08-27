import csv
from datetime import datetime, timezone

import pytest

from run_historical_backtest import (
    reference_now_for_years_ago,
    write_outputs,
)


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


def test_csv_output_preserves_diagnostic_columns(tmp_path):
    write_outputs(
        tmp_path,
        payload={"diagnostic_only": True},
        trades=[
            {
                "diag_adx_1h": 31.5,
                "diag_efficiency_ratio_1h": 0.42,
                "diag_fvg_confluence": True,
                "holding_minutes": 75.0,
            }
        ],
    )

    with (tmp_path / "backtest_trades.csv").open(
        newline="",
        encoding="utf-8",
    ) as handle:
        row = next(csv.DictReader(handle))

    assert row["diag_adx_1h"] == "31.5"
    assert row["diag_efficiency_ratio_1h"] == "0.42"
    assert row["diag_fvg_confluence"] == "True"
    assert row["holding_minutes"] == "75.0"
