from build_live_dashboard import calculate_target_statistics


def trade(source, reason, hits):
    return {
        "source": source,
        "reason": reason,
        "closed_at": "2026-09-19T12:00:00+00:00",
        "target_plan": [
            {
                "name": name,
                "price": price,
                "hit_at": "2026-09-19T11:00:00+00:00" if name in hits else None,
            }
            for name, price in (("TP1", 110), ("TP2", 115), ("TP3", 120))
        ],
    }


def test_target_statistics_are_cumulative_and_separated_by_source():
    trades = [
        trade("MANUAL", "TAKE_PROFIT", {"TP1", "TP2", "TP3"}),
        trade("MANUAL", "STOP_LOSS", set()),
        trade("AUTO", "MANUAL_CLOSE", {"TP1"}),
        {"source": "MANUAL", "reason": "STOP_LOSS"},
    ]

    manual = calculate_target_statistics(trades, "MANUAL")
    auto = calculate_target_statistics(trades, "AUTO")

    assert manual["total"] == 2
    assert manual["TP1"] == {"count": 1, "rate": 50.0}
    assert manual["TP2"] == {"count": 1, "rate": 50.0}
    assert manual["TP3"] == {"count": 1, "rate": 50.0}
    assert manual["SL"] == {"count": 1, "rate": 50.0}
    assert auto["total"] == 1
    assert auto["TP1"]["rate"] == 100.0
