"""Runtime configuration. Environment overrides, sane defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_DEVKIT_URL = "http://192.168.1.128:8090"


@dataclass(frozen=True)
class Config:
    devkit_url: str = DEFAULT_DEVKIT_URL
    timeout_s: float = 20.0
    top_k: int = 5

    @classmethod
    def load(cls) -> "Config":
        return cls(
            devkit_url=os.environ.get("ASSIST_DEVKIT_URL", DEFAULT_DEVKIT_URL),
            timeout_s=float(os.environ.get("ASSIST_TIMEOUT_S", "20")),
            top_k=int(os.environ.get("ASSIST_TOP_K", "5")),
        )
