from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter


@dataclass
class Persona:
    name: str
    style: str
    avatar_emoji: str
    system_prompt: str


def load_persona(path: str | Path) -> Persona:
    """Load persona definition from a Markdown file with YAML frontmatter."""
    post = frontmatter.load(str(path))
    return Persona(
        name=post.get("name", "Bot"),
        style=post.get("style", ""),
        avatar_emoji=post.get("avatar_emoji", ":robot_face:"),
        system_prompt=post.content,
    )
