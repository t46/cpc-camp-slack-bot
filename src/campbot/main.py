from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from campbot.brain import Brain
from campbot.config import BotConfig
from campbot.persona import Persona, load_persona
from campbot.session import SessionManager
from campbot.slack_app import create_slack_app, register_handlers, safe_post

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
    persona: Persona,
) -> None:
    """Periodically generate and post comments."""
    # Random initial delay (0-60s) to stagger multiple bots
    initial_delay = random.uniform(0, 60)
    logger.info(
        "[%s] Periodic response task started (interval=%ds, initial_delay=%.0fs)",
        persona.name,
        config.response_interval_seconds,
        initial_delay,
    )
    await asyncio.sleep(initial_delay)
    while True:
        # Add jitter (±30s) to avoid synchronized posting
        jitter = random.uniform(-30, 30)
        # Use shorter interval for free discussion mode
        if session_mgr.current_session and session_mgr.current_session.mode == "free":
            interval = config.free_discussion_interval_seconds
        else:
            interval = config.response_interval_seconds
        await asyncio.sleep(interval + jitter)

        if not session_mgr.current_session:
            continue

        if not session_mgr.has_enough_new_context(persona_name=persona.name):
            logger.debug("[%s] Not enough new context, skipping", persona.name)
            continue

        context = session_mgr.get_context_for_prompt(persona_name=persona.name)
        comment = await brain.generate_comment(context)

        if comment:
            try:
                thread_ts = session_mgr.pick_thread_target(persona.name, config)
                await safe_post(
                    app.client, config, comment,
                    persona=persona, thread_ts=thread_ts,
                )
                now = datetime.now()
                session_mgr.current_session.last_bot_post_at = now
                session_mgr.current_session._persona_last_post_at[persona.name] = now
                session_mgr.record_api_call()
                if thread_ts:
                    logger.info("[%s] Posted comment to bot channel (thread)", persona.name)
                else:
                    logger.info("[%s] Posted comment to bot channel", persona.name)
            except Exception:
                logger.exception("[%s] Failed to post comment", persona.name)


async def spontaneous_posting(
    app,
    session_mgr: SessionManager,
    brain: Brain,
    config: BotConfig,
    persona: Persona,
) -> None:
    """Periodically generate spontaneous topics even without a session."""
    initial_delay = random.uniform(60, 180)
    logger.info(
        "[%s] Spontaneous posting task started (interval=%ds)",
        persona.name,
        config.spontaneous_interval_seconds,
    )
    await asyncio.sleep(initial_delay)
    while True:
        jitter = random.uniform(-300, 300)
        await asyncio.sleep(max(60, config.spontaneous_interval_seconds + jitter))

        # Skip if presentation session is active (let reactive handle it)
        if session_mgr.current_session and session_mgr.current_session.mode == "presentation":
            continue

        if not session_mgr.has_spontaneous_opportunity(config):
            continue

        if not session_mgr.can_make_api_call(config):
            logger.debug("[%s] Daily API call limit reached, skipping", persona.name)
            continue

        context = session_mgr.get_spontaneous_context()
        comment = await brain.generate_spontaneous_topic(context)
        session_mgr.record_api_call()

        if comment:
            try:
                await safe_post(app.client, config, comment, persona=persona)
                session_mgr.record_spontaneous_post()
                logger.info("[%s] Posted spontaneous topic", persona.name)
            except Exception:
                logger.exception("[%s] Failed to post spontaneous topic", persona.name)


def load_personas(config: BotConfig) -> list[Persona]:
    """Load personas from config. Uses persona_files if set, otherwise persona_file."""
    if config.persona_files:
        paths = [p.strip() for p in config.persona_files.split(",") if p.strip()]
    else:
        paths = [config.persona_file]
    return [load_persona(p) for p in paths]


async def main() -> None:
    """Entry point for the camp bot."""
    config = BotConfig()
    personas = load_personas(config)

    for p in personas:
        logger.info("Loaded persona: %s (%s)", p.name, p.style)

    app = create_slack_app(config)
    session_mgr = SessionManager()
    persona_names = {p.name for p in personas}

    # Create a Brain for each persona
    brains = [Brain(config, persona) for persona in personas]

    # Register Slack event handlers (once, shared)
    register_handlers(app, session_mgr, config, persona_names=persona_names)

    # Start audio capture if enabled
    if config.enable_audio:
        from campbot.audio_capture import AudioTranscriber

        transcriber = AudioTranscriber(config)

        async def on_transcript(text: str) -> None:
            session_mgr.add_transcript(text, source="audio")

        asyncio.create_task(transcriber.start(on_transcript))
        logger.info("Audio capture enabled (device=%s)", config.audio_device or "default")

    # Start periodic response and spontaneous posting tasks for each persona
    for brain, persona in zip(brains, personas):
        asyncio.create_task(periodic_response(app, session_mgr, brain, config, persona))
        asyncio.create_task(spontaneous_posting(app, session_mgr, brain, config, persona))

    # Start Slack Socket Mode connection
    handler = AsyncSocketModeHandler(app, config.slack_app_token)
    names = ", ".join(p.name for p in personas)
    logger.info("Starting bot(s): %s", names)
    await handler.start_async()


def cli() -> None:
    """CLI entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    cli()
