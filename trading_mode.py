"""
PROJECT EDGE - Control central de modo.

PAPER es el único modo habilitado.
REAL permanece bloqueado hasta su validación final.
"""

from __future__ import annotations

import os


MODE_ENV = "PROJECT_EDGE_MODE"
PAPER = "PAPER"
REAL = "REAL"


class RealModeLockedError(RuntimeError):
    """Impide iniciar cualquier componente en modo REAL."""


def current_mode() -> str:
    mode = os.getenv(
        MODE_ENV,
        PAPER,
    ).strip().upper()

    if mode not in {PAPER, REAL}:
        raise ValueError(
            f"{MODE_ENV} debe ser PAPER o REAL; "
            f"valor recibido: {mode!r}."
        )

    return mode


def require_paper_mode() -> str:
    mode = current_mode()

    if mode != PAPER:
        raise RealModeLockedError(
            "Modo REAL bloqueado. "
            "PROJECT EDGE solo puede operar en PAPER."
        )

    return mode
