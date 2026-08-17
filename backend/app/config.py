from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _BACKEND_DIR.parent

# Local files only fill gaps. Vercel dashboard / process env always wins.
load_dotenv(_BACKEND_DIR / ".env", override=False)
load_dotenv(_ROOT_DIR / ".env", override=False)

_ON_VERCEL = bool(os.getenv("VERCEL"))


def _default_database_url() -> str:
    if _ON_VERCEL:
        # Serverless filesystem is read-only except /tmp.
        return "sqlite:////tmp/trips.db"
    return "sqlite:///./trips.db"


class Settings(BaseSettings):
    """Reads OPENROUTER_*, DATABASE_URL, FRONTEND_ORIGIN from the process environment.

    Local: copy .env.example to .env
    Vercel: Project → Settings → Environment Variables (production + preview)
    """

    model_config = SettingsConfigDict(
        env_file=None if _ON_VERCEL else (".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        env_ignore_empty=True,
    )

    openrouter_api_key: str = Field(default="")
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    database_url: str = Field(default_factory=_default_database_url)
    frontend_origin: str = "*"

    @field_validator(
        "openrouter_api_key",
        "openrouter_model",
        "openrouter_base_url",
        "database_url",
        "frontend_origin",
        mode="before",
    )
    @classmethod
    def strip_quotes(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip('"').strip("'")
        return value

    @model_validator(mode="after")
    def vercel_writable_sqlite(self) -> "Settings":
        # Vercel Lambda FS is read-only except /tmp. A dashboard DATABASE_URL
        # copied from .env.example (sqlite:///./trips.db) 500s every request.
        if not os.getenv("VERCEL"):
            return self
        url = self.database_url
        if url.startswith("sqlite") and ":memory:" not in url and "/tmp/" not in url:
            self.database_url = "sqlite:////tmp/trips.db"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
