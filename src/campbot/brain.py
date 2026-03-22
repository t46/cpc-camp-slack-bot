from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from campbot.config import BotConfig
    from campbot.persona import Persona

logger = logging.getLogger(__name__)


class Brain:
    """Generates AI-powered comments using Claude API."""

    def __init__(self, config: BotConfig, persona: Persona) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
        self.persona = persona
        self.config = config

    async def generate_comment(self, context: str) -> str | None:
        """Generate a comment based on session context.

        Args:
            context: The assembled context string from SessionManager.

        Returns:
            Comment text, or None if nothing worth saying.
        """
        if not context.strip():
            return None

        try:
            response = await self.client.messages.create(
                model=self.config.model_name,
                max_tokens=512,
                system=self.persona.system_prompt,
                messages=[{"role": "user", "content": context}],
            )
            text = response.content[0].text.strip()

            if text == "SKIP":
                logger.debug("Brain decided to SKIP")
                return None

            logger.info(
                "Generated comment (%s): %s",
                self.persona.name,
                text[:80],
            )
            return text

        except anthropic.APIError:
            logger.exception("Claude API error")
            return None
