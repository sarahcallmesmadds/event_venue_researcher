"""Configuration management for the event research agent."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env from project root
load_dotenv(Path(__file__).parent.parent.parent / ".env")


class Config(BaseModel):
    """Agent configuration — loaded from env vars or config file."""

    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    notion_api_key: str = Field(default_factory=lambda: os.getenv("NOTION_API_KEY", ""))
    notion_database_id: str = Field(default_factory=lambda: os.getenv("NOTION_DATABASE_ID", ""))
    model: str = "claude-sonnet-4-20250514"
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
