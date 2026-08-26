import pytest

from paper_state import PaperState


def test_initial_state(tmp_path):
    state_file = tmp_path / "paper_state.json"

    state = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    assert state.balance == 10000.0
    assert state.position is None
    assert state.has_open_position is False
    assert state.status()["closed_trades"] == 0


def test_open_position_is_saved_and_reloaded(tmp_path):
    state_file = tmp_path / "paper_state.json"

    state = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    state.open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=64000.0,
        quantity=0.01,
        stop_loss=63500.0,
        take_profit=65000.0,
    )

    assert state_file.exists()
    assert state.has_open_position is True

    reloaded = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    assert reloaded.has_open_position is True
    assert reloaded.position["symbol"] == "BTCUSDT"
    assert reloaded.position["direction"] == "LONG"
    assert reloaded.position["entry_price"] == 64000.0
    assert reloaded.position["stop_loss"] == 63500.0
    assert reloaded.position["take_profit"] == 65000.0


def test_long_take_profit_updates_balance(tmp_path):
    state_file = tmp_path / "paper_state.json"

    state = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    state.open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=64000.0,
        quantity=0.01,
        stop_loss=63500.0,
        take_profit=65000.0,
    )

    result = state.close_position(
        exit_price=65000.0,
        reason="TAKE_PROFIT",
    )

    assert result["pnl"] == pytest.approx(10.0)
    assert result["balance"] == pytest.approx(10010.0)
    assert result["reason"] == "TAKE_PROFIT"
    assert state.has_open_position is False

    reloaded = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    assert reloaded.balance == pytest.approx(10010.0)
    assert reloaded.position is None
    assert reloaded.status()["closed_trades"] == 1


def test_short_take_profit_updates_balance(tmp_path):
    state_file = tmp_path / "paper_state.json"

    state = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    state.open_position(
        symbol="BTCUSDT",
        direction="SHORT",
        entry_price=64000.0,
        quantity=0.01,
        stop_loss=64500.0,
        take_profit=63000.0,
    )

    result = state.close_position(
        exit_price=63000.0,
        reason="TAKE_PROFIT",
    )

    assert result["pnl"] == pytest.approx(10.0)
    assert result["balance"] == pytest.approx(10010.0)
    assert state.has_open_position is False


def test_auto_v3_paper_trade_deducts_fees_and_slippage(tmp_path):
    state = PaperState(
        file_path=tmp_path / "paper_state.json",
        initial_balance=10000.0,
    )
    position = state.open_position(
        symbol="ETHUSDT",
        direction="LONG",
        entry_price=100.0,
        quantity=1.0,
        stop_loss=97.0,
        take_profit=110.0,
        source="AUTO",
        fee_rate=0.001,
        slippage_rate=0.001,
    )

    result = state.close_position(
        exit_price=110.0,
        reason="TAKE_PROFIT",
    )

    assert position["entry_price"] == pytest.approx(100.1)
    assert result["raw_exit_price"] == pytest.approx(110.0)
    assert result["exit_price"] == pytest.approx(109.89)
    assert result["gross_pnl"] == pytest.approx(9.79)
    assert result["fees"] == pytest.approx(0.20999)
    assert result["pnl"] == pytest.approx(9.58001)
    assert result["balance"] == pytest.approx(10009.58001)


def test_second_position_is_blocked(tmp_path):
    state_file = tmp_path / "paper_state.json"

    state = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    state.open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=64000.0,
        quantity=0.01,
        stop_loss=63500.0,
        take_profit=65000.0,
    )

    with pytest.raises(ValueError):
        state.open_position(
            symbol="BTCUSDT",
            direction="SHORT",
            entry_price=64000.0,
            quantity=0.01,
            stop_loss=64500.0,
            take_profit=63000.0,
        )


def test_reset_restores_initial_state(tmp_path):
    state_file = tmp_path / "paper_state.json"

    state = PaperState(
        file_path=state_file,
        initial_balance=10000.0,
    )

    state.open_position(
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=64000.0,
        quantity=0.01,
        stop_loss=63500.0,
        take_profit=65000.0,
    )

    state.close_position(
        exit_price=65000.0,
        reason="TAKE_PROFIT",
    )

    state.reset()

    assert state.balance == 10000.0
    assert state.position is None
    assert state.status()["closed_trades"] == 0
