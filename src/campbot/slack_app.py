from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from slack_bolt.app.async_app import AsyncApp

from campbot.session import Message
from campbot.slides import download_file_from_slack, extract_slide_texts
from campbot.transcript import parse_vtt

if TYPE_CHECKING:
    from campbot.brain import Brain
    from campbot.config import BotConfig
    from campbot.session import SessionManager

logger = logging.getLogger(__name__)


async def safe_post(client, config: BotConfig, text: str) -> None:
    """Post a message only to the bot channel. All writes go through here."""
    await client.chat_postMessage(channel=config.bot_channel_id, text=text)


def create_slack_app(config: BotConfig) -> AsyncApp:
    """Create and configure the Slack AsyncApp with Socket Mode."""
    app = AsyncApp(token=config.slack_bot_token)
    return app


def register_handlers(
    app: AsyncApp,
    session_mgr: SessionManager,
    brain: Brain,
    config: BotConfig,
) -> None:
    """Register all Slack event handlers."""
    # Track our own bot_id to ignore self-messages
    _self_bot_id: str | None = None

    @app.event("message")
    async def handle_message(event: dict, client) -> None:
        nonlocal _self_bot_id
        """Route incoming messages based on channel and content."""
        # Lazily fetch our own bot_id
        if _self_bot_id is None:
            try:
                auth = await client.auth_test()
                _self_bot_id = auth.get("bot_id", "")
                logger.info("Own bot_id: %s", _self_bot_id)
            except Exception:
                _self_bot_id = ""

        channel = event.get("channel", "")
        text = event.get("text", "")
        user = event.get("user", "unknown")
        subtype = event.get("subtype")
        bot_id = event.get("bot_id")

        # Ignore message edits, deletes, etc.
        if subtype in ("message_changed", "message_deleted"):
            return

        ts = event.get("ts", "")

        # --- Bot channel ---
        if channel == config.bot_channel_id:
            # Session management commands
            if text.startswith("!session start-free "):
                await _handle_session_start_free(text, client, config, session_mgr)
                return

            if text.startswith("!session start "):
                await _handle_session_start(text, client, config, session_mgr)
                return

            if text.strip() == "!session end":
                session_mgr.end_session()
                await safe_post(client, config, "セッションを終了しました。")
                return

            if text.strip() == "!session status":
                await _handle_session_status(client, config, session_mgr)
                return

            if text.strip() == "!moltbook":
                session_mgr.start_session("moltbook", config.bot_channel_id, mode="free")
                await safe_post(client, config, "Moltbook モードを開始しました。自由に議論します。")
                return

            # File attachments (PDF, VTT)
            files = event.get("files", [])
            for file_info in files:
                filetype = file_info.get("filetype", "")
                filename = file_info.get("name", "")

                if filetype == "pdf" or filename.endswith(".pdf"):
                    await _handle_pdf(file_info, client, config, session_mgr)

                elif filetype == "vtt" or filename.endswith(".vtt"):
                    await _handle_vtt(file_info, client, session_mgr)

            # Track bot messages from OTHER bots (ignore our own)
            if bot_id and bot_id != _self_bot_id:
                from datetime import datetime

                msg = Message(
                    user=event.get("username", bot_id),
                    text=text,
                    timestamp=datetime.fromtimestamp(float(ts)) if ts else datetime.now(),
                    is_bot=True,
                )
                session_mgr.add_bot_message(msg)
                session_mgr.add_channel_message(msg)
                logger.info("Other bot message from %s: %s", msg.user, text[:50])

            # Track all bot channel messages for spontaneous context
            if not bot_id and not text.startswith("!"):
                from datetime import datetime

                msg = Message(
                    user=user,
                    text=text,
                    timestamp=datetime.fromtimestamp(float(ts)) if ts else datetime.now(),
                    is_bot=False,
                )
                session_mgr.add_channel_message(msg)

        # --- Session channel (read only, no writing) ---
        elif session_mgr.is_session_channel(channel):
            from datetime import datetime

            msg = Message(
                user=user,
                text=text,
                timestamp=datetime.fromtimestamp(float(ts)) if ts else datetime.now(),
                is_bot=bool(bot_id),
            )
            session_mgr.add_discussion(channel, msg)
            logger.debug("Session discussion from %s: %s", user, text[:50])


async def _handle_session_start(
    text: str,
    client,
    config: BotConfig,
    session_mgr: SessionManager,
) -> None:
    """Handle !session start <name> <channel_id> command."""
    parts = text.split(maxsplit=3)
    if len(parts) < 4:
        await safe_post(
            client,
            config,
            "使い方: `!session start <セッション名> <チャンネルID>`\n"
            "例: `!session start 機械学習の基礎 C0123456789`",
        )
        return

    session_name = parts[2]
    session_channel = parts[3].strip().strip("<>#")

    session_mgr.start_session(session_name, session_channel)
    await safe_post(
        client,
        config,
        f"セッション「{session_name}」を開始しました。\n"
        f"チャンネル: <#{session_channel}> を監視中。",
    )


async def _handle_session_start_free(
    text: str,
    client,
    config: BotConfig,
    session_mgr: SessionManager,
) -> None:
    """Handle !session start-free <name> <channel_id> command."""
    parts = text.split(maxsplit=3)
    if len(parts) < 4:
        await safe_post(
            client,
            config,
            "使い方: `!session start-free <セッション名> <チャンネルID>`\n"
            "例: `!session start-free 自由議論 C0123456789`",
        )
        return

    session_name = parts[2]
    session_channel = parts[3].strip().strip("<>#")

    session_mgr.start_session(session_name, session_channel, mode="free")
    await safe_post(
        client,
        config,
        f"フリーセッション「{session_name}」を開始しました（自律議論モード）。\n"
        f"チャンネル: <#{session_channel}> を監視中。",
    )


async def _handle_session_status(
    client,
    config: BotConfig,
    session_mgr: SessionManager,
) -> None:
    """Handle !session status command."""
    session = session_mgr.current_session
    if not session:
        await safe_post(client, config, "現在アクティブなセッションはありません。")
        return

    await safe_post(
        client,
        config,
        f"*セッション: {session.name}*\n"
        f"モード: {session.mode}\n"
        f"チャンネル: <#{session.channel_id}>\n"
        f"スライド: {len(session.slide_texts)} ページ\n"
        f"トランスクリプト: {len(session.transcript_chunks)} チャンク\n"
        f"議論メッセージ: {len(session.discussion_messages)} 件\n"
        f"bot メッセージ: {len(session.bot_messages)} 件",
    )


async def _handle_pdf(
    file_info: dict,
    client,
    config: BotConfig,
    session_mgr: SessionManager,
) -> None:
    """Download and process a PDF file."""
    filename = file_info.get("name", "unknown.pdf")
    logger.info("Processing PDF: %s", filename)

    pdf_bytes = await download_file_from_slack(client, file_info)
    if not pdf_bytes:
        return

    slide_texts = extract_slide_texts(pdf_bytes)
    session_mgr.add_slides(slide_texts)

    await safe_post(
        client,
        config,
        f"PDF「{filename}」を読み込みました（{len(slide_texts)}ページ）。",
    )


async def _handle_vtt(
    file_info: dict,
    client,
    session_mgr: SessionManager,
) -> None:
    """Download and process a VTT transcript file."""
    filename = file_info.get("name", "unknown.vtt")
    logger.info("Processing VTT: %s", filename)

    vtt_bytes = await download_file_from_slack(client, file_info)
    if not vtt_bytes:
        return

    vtt_content = vtt_bytes.decode("utf-8", errors="replace")
    entries = parse_vtt(vtt_content)

    for entry in entries:
        text = f"{entry.speaker}: {entry.text}" if entry.speaker else entry.text
        session_mgr.add_transcript(text, source="vtt")

    logger.info("Processed %d VTT entries from %s", len(entries), filename)
