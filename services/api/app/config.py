"""Runtime settings for the Nexus API.

Values come from the environment, or from a `.env` file at the repo root. No defaults
contain real credentials. City-specific settings are read from the city pack chosen by
`CITY` (engg/docs/CITY_PACKS.md).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

# Model ids that hand routing to Nightshift. Rule R2 forbids them, because the
# model that answered must be known and logged.
FORBIDDEN_MODELS = frozenset({"meterless/auto"})


class Settings(BaseSettings):
    """Typed view of the environment (see .env.example)."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    city: str = "chennai"

    zetaris_rest_url: str = "http://localhost:8888/api/v1.0"
    zetaris_org_id: str = "1"
    zetaris_api_key: str = ""
    zetaris_timeout_seconds: float = 60.0

    meterless_base_url: str = "http://127.0.0.1:8088/v1"
    meterless_runtime_token: str = ""
    meterless_app: str = "nexus-chennai"
    nightshift_timeout_seconds: float = 180.0
    lane_fast: str = ""
    lane_vision: str = ""
    lane_reason: str = ""
    lane_audio: str = ""
    lane_guard: str = ""
    lane_tiny: str = ""
    lane_embed: str = ""

    supabase_url: str = ""
    supabase_service_role_key: str = ""

    sample_mode: bool = False
    max_agent_rounds: int = 3
    run_deadline_seconds: int = 300
    log_level: str = "INFO"
    port: int = 8000

    # Secrets may be given as a path instead of a value: <NAME>_FILE=/path/to/file.
    # The file wins over an inline value, so no secret needs to live in a repo .env.
    zetaris_api_key_file: str = ""
    meterless_runtime_token_file: str = ""
    supabase_service_role_key_file: str = ""

    def model_post_init(self, __context: Any) -> None:
        for name in ("zetaris_api_key", "meterless_runtime_token", "supabase_service_role_key"):
            path = getattr(self, f"{name}_file")
            if path:
                value = Path(path).expanduser().read_text(encoding="utf-8").strip()
                object.__setattr__(self, name, value)

    @property
    def lanes(self) -> dict[str, str]:
        """Configured lanes only (empty lanes are optional and stay off)."""
        all_lanes = {
            "fast": self.lane_fast,
            "vision": self.lane_vision,
            "reason": self.lane_reason,
            "audio": self.lane_audio,
            "guard": self.lane_guard,
            "tiny": self.lane_tiny,
            "embed": self.lane_embed,
        }
        return {k: v for k, v in all_lanes.items() if v}

    @property
    def logs_dir(self) -> Path:
        return REPO_ROOT / "logs"

    @property
    def sample_dir(self) -> Path:
        return REPO_ROOT / "data" / "sample"


def load_city(name: str, root: Path = REPO_ROOT) -> dict[str, Any]:
    """Load `cities/<name>/city.yaml`; fails loudly if the pack is missing."""
    path = root / "cities" / name / "city.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"City pack not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache
def get_settings() -> Settings:
    return Settings()
