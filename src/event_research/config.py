"""Configuration management for the event research agent."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env — check current working directory, then project root
# override=True ensures env vars get set even if already partially loaded
load_dotenv(Path.cwd() / ".env", override=True)
load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)


class Config(BaseModel):
    """Agent configuration — loaded from env vars or config file."""

    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    notion_api_key: str = Field(default_factory=lambda: os.getenv("NOTION_API_KEY", ""))
    notion_database_id: str = Field(default_factory=lambda: os.getenv("NOTION_DATABASE_ID", ""))
    model: str = Field(default_factory=lambda: os.getenv("MODEL", "claude-sonnet-4-20250514"))
    max_venues_per_search: int = 8

    def validate_keys(self) -> list[str]:
        """Return list of missing required keys."""
        missing = []
        if not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")
        if not self.notion_api_key:
            missing.append("NOTION_API_KEY")
        if not self.notion_database_id:
            missing.append("NOTION_DATABASE_ID")
        return missing


def load_config() -> Config:
    return Config()
