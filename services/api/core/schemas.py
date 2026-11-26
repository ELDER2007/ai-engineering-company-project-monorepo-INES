"""Response contracts that belong to no domain."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthOut(BaseModel):
    """``GET /health``: the liveness check. Says the process is up, nothing about its internals."""

    status: Literal["ok"]
