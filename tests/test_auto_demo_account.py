from pathlib import Path

import pytest

from build_live_dashboard import calculate_performance


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
AUTO_RUNNER = (ROOT / "run_btc_paper.py").read_text(encoding="utf-8")


def test_auto_performance_reports_return_profit_factor_and_drawdown():
    trades = [
        {
            "source": "AUTO",
            "pnl": 100.0,
            "fees": 2.0,
            "closed_at": "2026-08-29T10:00:00+00:00",
        },
        {
            "source": "AUTO",
            "pnl": -50.0,
            "fees": 1.0,
            "closed_at": "2026-08-29T11:00:00+00:00",
        },
        {
            "source": "MANUAL",
            "pnl": 200.0,
            "closed_at": "2026-08-29T12:00:00+00:00",
        },
    ]

    metrics = calculate_performance(
        trades,
        "AUTO",
        initial_balance=1000.0,
    )

    assert metrics["total"] == 2
    assert metrics["pnl"] == pytest.approx(50.0)
    assert metrics["fees"] == pytest.approx(3.0)
    assert metrics["profit_factor"] == pytest.approx(2.0)
    assert metrics["return_pct"] == pytest.approx(5.0)
    assert metrics["max_drawdown_pct"] == pytest.approx(50 / 1100 * 100)


def test_auto_performance_can_start_a_clean_measurement_window():
    metrics = calculate_performance(
        [
            {
                "source": "AUTO",
                "pnl": 90.0,
                "closed_at": "2026-08-28T23:59:59+00:00",
            },
            {
                "source": "AUTO",
                "pnl": -10.0,
                "closed_at": "2026-08-29T00:01:00+00:00",
            },
        ],
        "AUTO",
        initial_balance=1000.0,
        started_at="2026-08-29T00:00:00+00:00",
    )

    assert metrics["total"] == 1
    assert metrics["pnl"] == pytest.approx(-10.0)


def test_auto_runner_risks_only_the_separate_demo_capital():
    assert "account_equity=state.auto_demo_balance" in AUTO_RUNNER
    assert "notify_auto_entry(position, balance=state.auto_demo_balance)" in AUTO_RUNNER


def test_dashboard_labels_the_separate_paper_accounts_and_metrics():
    assert "Capital AUTO DEMO" in HTML
    assert 'id="manualBalance"' in HTML
    assert 'id="autoPerfReturn"' in HTML
    assert 'id="autoPerfProfitFactor"' in HTML
    assert 'id="autoPerfDrawdown"' in HTML
    assert "AUTO DEMO comienza con 1.000 USDT propios" in HTML
