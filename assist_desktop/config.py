"""Runtime configuration. Environment overrides, sane defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Read a .env beside the repo, without adding a dependency for it.

    setup.ps1 writes ASSIST_DEVKIT_URL here so a fresh machine does not have to
    pass --devkit on every run. Real environment variables always win.
    """
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


# Whatever address the devkit has on your network: .env, ASSIST_DEVKIT_URL, or
# --devkit. See the README.
DEFAULT_DEVKIT_URL = os.environ.get("ASSIST_DEVKIT_URL",
                                    "http://192.168.94.180:8090")


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
