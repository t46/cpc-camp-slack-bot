from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from campbot.brain import Brain
from campbot.config import BotConfig
from campbot.persona import load_persona
from campbot.session import SessionManager
from campbot.slack_app import create_slack_app, register_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def periodic_response(
    app,
    session_mgr: SessionManager,
    brain: Brain,
    config: BotConfig,
) -> None:
    """Periodically generate and post comments."""
    logger.info(
        "Periodic response task started (interval=%ds)",
        config.response_interval_seconds,
    )
    while True:
        await asyncio.sleep(config.response_interval_seconds)

        if not session_mgr.current_session:
            continue

        if not session_mgr.has_enough_new_context():
            logger.debug("Not enough new context, skipping")
            continue

        context = session_mgr.get_context_for_prompt()
        comment = await brain.generate_comment(context)

        if comment:
            try:
                await app.client.chat_postMessage(
                    channel=config.bot_channel_id,
                    text=comment,
                )
                session_mgr.current_session.last_bot_post_at = datetime.now()
                logger.info("Posted comment to bot channel")
            except Exception:
                logger.exception("Failed to post comment")


async def main() -> None:
    """Entry point for the camp bot."""
    config = BotConfig()
    persona = load_persona(config.persona_file)
    logger.info("Loaded persona: %s (%s)", persona.name, persona.style)

    app = create_slack_app(config)
    session_mgr = SessionManager()
    brain = Brain(config, persona)

    register_handlers(app, session_mgr, brain, config)

    # Start audio capture if enabled
    if config.enable_audio:
        from campbot.audio_capture import AudioTranscriber

        transcriber = AudioTranscriber(config)

        async def on_transcript(text: str) -> None:
            session_mgr.add_transcript(text, source="audio")

        asyncio.create_task(transcriber.start(on_transcript))
        logger.info("Audio capture enabled (device=%s)", config.audio_device or "default")

    # Start periodic response task
    asyncio.create_task(periodic_response(app, session_mgr, brain, config))

    # Start Slack Socket Mode connection
    handler = AsyncSocketModeHandler(app, config.slack_app_token)
    logger.info("Starting bot: %s", persona.name)
    await handler.start_async()


def cli() -> None:
    """CLI entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
