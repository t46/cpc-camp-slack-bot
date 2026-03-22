from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TranscriptChunk:
    timestamp: datetime
    text: str
    source: str  # "audio" or "vtt"


@dataclass
class Message:
    user: str
    text: str
    timestamp: datetime
    is_bot: bool = False


@dataclass
class Session:
    name: str
    channel_id: str
    slide_texts: list[str] = field(default_factory=list)
    transcript_chunks: list[TranscriptChunk] = field(default_factory=list)
    discussion_messages: list[Message] = field(default_factory=list)
    bot_messages: list[Message] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    last_bot_post_at: datetime | None = None
    _last_context_hash: str = field(default="", repr=False)


class SessionManager:
    """Manages the lifecycle of presentation sessions."""

    def __init__(self) -> None:
        self.current_session: Session | None = None
        self._sessions: dict[str, Session] = {}

    def start_session(self, name: str, channel_id: str) -> Session:
        """Start a new session, ending any current one."""
        if self.current_session:
            logger.info("Ending previous session: %s", self.current_session.name)
        session = Session(name=name, channel_id=channel_id)
        self._sessions[channel_id] = session
        self.current_session = session
        logger.info("Started session: %s (channel: %s)", name, channel_id)
        return session

    def end_session(self) -> None:
        """End the current session."""
        if self.current_session:
            logger.info("Ended session: %s", self.current_session.name)
            self.current_session = None

    def is_session_channel(self, channel_id: str) -> bool:
        """Check if a channel is a tracked session channel."""
        return (
            self.current_session is not None
            and self.current_session.channel_id == channel_id
        )

    def add_transcript(self, text: str, source: str = "audio") -> None:
        """Add a transcript chunk to the current session."""
        if not self.current_session or not text.strip():
            return
        chunk = TranscriptChunk(
            timestamp=datetime.now(),
            text=text.strip(),
            source=source,
        )
        self.current_session.transcript_chunks.append(chunk)
        logger.debug("Added transcript chunk (%s): %s", source, text[:50])

    def add_slides(self, slide_texts: list[str]) -> None:
        """Set slide texts for the current session."""
        if not self.current_session:
            return
        self.current_session.slide_texts = slide_texts
        logger.info("Added %d slides to session", len(slide_texts))

    def add_discussion(self, channel_id: str, msg: Message) -> None:
        """Add a discussion message from a session channel."""
        if not self.current_session or self.current_session.channel_id != channel_id:
            return
        self.current_session.discussion_messages.append(msg)

    def add_bot_message(self, msg: Message) -> None:
        """Add a bot channel message to the current session."""
        if not self.current_session:
            return
        self.current_session.bot_messages.append(msg)

    def has_enough_new_context(self) -> bool:
        """Check if there's enough new context since the last bot post to warrant a response."""
        session = self.current_session
        if not session:
            return False

        # Need at least slides or transcript
        if not session.slide_texts and not session.transcript_chunks:
            return False

        # Check if context has changed since last response
        current_hash = self._compute_context_hash(session)
        if current_hash == session._last_context_hash:
            return False

        # If never posted, post if we have some content
        if session.last_bot_post_at is None:
            return len(session.transcript_chunks) >= 3 or len(session.slide_texts) > 0

        # Count new content since last post
        new_chunks = [
            c for c in session.transcript_chunks
            if c.timestamp > session.last_bot_post_at
        ]
        new_discussion = [
            m for m in session.discussion_messages
            if m.timestamp > session.last_bot_post_at
        ]
        new_bot_msgs = [
            m for m in session.bot_messages
            if m.timestamp > session.last_bot_post_at
        ]
        # Respond if: new transcript, new discussion, or other bots said something
        return len(new_chunks) >= 3 or len(new_discussion) >= 1 or len(new_bot_msgs) >= 1

    def get_context_for_prompt(self) -> str:
        """Assemble context string for the Claude API prompt."""
        session = self.current_session
        if not session:
            return ""

        parts: list[str] = []

        # Slides
        if session.slide_texts:
            parts.append(f"## 発表スライド（{len(session.slide_texts)}ページ）")
            for i, text in enumerate(session.slide_texts, 1):
                if text.strip():
                    parts.append(f"### スライド {i}")
                    parts.append(text.strip())
            parts.append("")

        # Transcript (last 30 chunks max)
        if session.transcript_chunks:
            recent_transcript = session.transcript_chunks[-30:]
            parts.append(f"## トランスクリプト（最新{len(recent_transcript)}件）")
            for chunk in recent_transcript:
                ts = chunk.timestamp.strftime("%H:%M:%S")
                parts.append(f"[{ts}] {chunk.text}")
            parts.append("")

        # Discussion messages (last 20)
        if session.discussion_messages:
            recent_discussion = session.discussion_messages[-20:]
            parts.append(f"## セッションチャンネルの議論（最新{len(recent_discussion)}件）")
            for msg in recent_discussion:
                prefix = "[bot] " if msg.is_bot else ""
                parts.append(f"{prefix}{msg.user}: {msg.text}")
            parts.append("")

        # Bot channel messages (last 15)
        if session.bot_messages:
            recent_bot = session.bot_messages[-15:]
            parts.append(f"## bot チャンネルの議論（最新{len(recent_bot)}件）")
            for msg in recent_bot:
                parts.append(f"{msg.user}: {msg.text}")
            parts.append("")

        # Instruction
        parts.append(
            "上記の発表内容と議論を踏まえて、あなたらしいコメントや質問を1つ投稿してください。\n"
            "他の bot が興味深い発言をしていたら、それに応答しても構いません。\n"
            "言うべきことが特にない場合は「SKIP」とだけ返してください。"
        )

        # Update hash
        context = "\n".join(parts)
        session._last_context_hash = self._compute_context_hash(session)
        return context

    @staticmethod
    def _compute_context_hash(session: Session) -> str:
        """Compute a hash of the current context to detect changes."""
        content = (
            str(len(session.transcript_chunks))
            + str(len(session.discussion_messages))
            + str(len(session.bot_messages))
            + str(len(session.slide_texts))
        )
        return hashlib.md5(content.encode()).hexdigest()
