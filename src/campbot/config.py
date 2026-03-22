from __future__ import annotations

from pydantic_settings import BaseSettings


class BotConfig(BaseSettings):
    """Bot configuration loaded from environment variables."""

    slack_bot_token: str
    slack_app_token: str
    anthropic_api_key: str
    bot_channel_id: str
    persona_file: str = "personas/ada.md"
    persona_files: str = ""  # Comma-separated list for multi-persona mode
    model_name: str = "claude-sonnet-4-20250514"
    response_interval_seconds: int = 120
    enable_audio: bool = False
    audio_device: str | None = None
    whisper_model: str = "large-v3"
    whisper_language: str = "ja"
    free_discussion_interval_seconds: int = 60
    max_consecutive_bot_messages: int = 20
    spontaneous_interval_seconds: int = 1800  # 30 minutes
    max_daily_spontaneous_posts: int = 10
    max_daily_api_calls: int = 200
    thread_probability: float = 0.4
    max_thread_replies: int = 5
    thread_target_max_age_seconds: int = 300

    model_config = {"env_file": ".env", "extra": "ignore"}
