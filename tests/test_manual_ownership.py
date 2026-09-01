from copy import deepcopy

import pytest

import manual_paper_control
from paper_state import PaperState


AUTO_POSITION_ACTIONS = (
    ("close_manual", {}),
    ("partial_close_manual", {"partial_pct": 50}),
    (
        "update_manual_risk",
        {"stop_loss": 91, "take_profit": 109},
    ),
    ("set_break_even", {}),
    ("enable_trailing", {"trailing_pct": 0.3}),
    ("disable_trailing", {}),
)


def open_position(state: PaperState, source: str) -> None:
    state.open_position(
        symbol="ETHUSDT",
        direction="LONG",
        entry_price=100,
        quantity=1,
        stop_loss=90,
        take_profit=110,
        source=source,
    )


@pytest.mark.parametrize("action_name,kwargs", AUTO_POSITION_ACTIONS)
def test_manual_actions_cannot_mutate_auto_position(
    tmp_path,
    monkeypatch,
    action_name,
    kwargs,
):
    state = PaperState(file_path=tmp_path / "state.json")
    open_position(state, source="AUTO")
    before = deepcopy(state.data)

    def market_must_not_be_consulted(_symbol):
        raise AssertionError(
            "La proteccion AUTO debe ejecutarse antes de consultar mercado."
        )

    monkeypatch.setattr(
        manual_paper_control,
        "current_price",
        market_must_not_be_consulted,
    )

    action = getattr(manual_paper_control, action_name)

    with pytest.raises(ValueError, match="pertenece a AUTO"):
        action(state, **kwargs)

    assert state.data == before
    assert PaperState(file_path=tmp_path / "state.json").data == before


def test_manual_cancel_cannot_remove_auto_limit(tmp_path, monkeypatch):
    state = PaperState(file_path=tmp_path / "state.json")
    state.create_pending_order(
        symbol="ETHUSDT",
        direction="LONG",
        limit_price=100,
        capital=100,
        leverage=1,
        stop_loss=90,
        take_profit=110,
        source="AUTO",
    )
    before = deepcopy(state.data)

    monkeypatch.setattr(
        manual_paper_control,
        "notify_manual_action",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(ValueError, match="LIMIT pendiente pertenece a AUTO"):
        manual_paper_control.cancel_limit_manual(state)

    assert state.data == before
    assert PaperState(file_path=tmp_path / "state.json").data == before


def test_manual_close_still_closes_manual_position(tmp_path, monkeypatch):
    state = PaperState(file_path=tmp_path / "state.json")
    open_position(state, source="MANUAL")

    monkeypatch.setattr(
        manual_paper_control,
        "current_price",
        lambda _symbol: 105,
    )
    monkeypatch.setattr(
        manual_paper_control,
        "notify_manual_exit",
        lambda _trade: None,
    )

    manual_paper_control.close_manual(state)

    assert state.position is None
    assert state.data["closed_trades"][-1]["source"] == "MANUAL"
    assert state.data["closed_trades"][-1]["reason"] == "MANUAL_CLOSE"
