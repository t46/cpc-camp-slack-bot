from __future__ import annotations

from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    """Bot configuration loaded from environment variables."""

    slack_bot_token: str
    slack_app_token: str
    anthropic_api_key: str
    bot_channel_id: str
    persona_file: str = "personas/ada.md"
    model_name: str = "claude-sonnet-4-20250514"
    response_interval_seconds: int = 120
    enable_audio: bool = False
    audio_device: str | None = None
    whisper_model: str = "large-v3"
    whisper_language: str = "ja"

    model_config = {"env_file": ".env", "extra": "ignore"}
