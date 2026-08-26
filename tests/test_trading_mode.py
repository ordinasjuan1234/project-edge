import pytest

import manual_paper_control
import run_btc_paper
from trading_mode import (
    MODE_ENV,
    PAPER,
    RealModeLockedError,
    current_mode,
    require_paper_mode,
)


def test_paper_is_the_safe_default(monkeypatch):
    monkeypatch.delenv(MODE_ENV, raising=False)

    assert current_mode() == PAPER
    assert require_paper_mode() == PAPER


def test_explicit_real_mode_is_blocked(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "REAL")

    with pytest.raises(RealModeLockedError, match="REAL bloqueado"):
        require_paper_mode()


def test_unknown_mode_is_rejected(monkeypatch):
    monkeypatch.setenv(MODE_ENV, "LIVE")

    with pytest.raises(ValueError, match="debe ser PAPER o REAL"):
        current_mode()


class GateReached(RuntimeError):
    pass


@pytest.mark.parametrize(
    "module",
    [run_btc_paper, manual_paper_control],
)
def test_trading_entrypoints_check_the_gate_first(monkeypatch, module):
    def stop_at_gate():
        raise GateReached

    monkeypatch.setattr(module, "require_paper_mode", stop_at_gate)

    with pytest.raises(GateReached):
        module.main()
