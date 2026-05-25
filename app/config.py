from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("API_HOST", "127.0.0.1")
    port: int = int(os.getenv("API_PORT", "18765"))
    flight_provider: str = os.getenv("FLIGHT_PROVIDER", "demo")
    default_top_n: int = int(os.getenv("DEFAULT_TOP_N", "10"))


settings = Settings()
