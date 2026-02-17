"""Tool plugin registry — types, autodiscovery, and dispatch."""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared types (moved from llm.py to avoid circular imports)
# ---------------------------------------------------------------------------

RetrieveFn = Callable[..., Awaitable[list[dict]]]


@dataclass
class ToolContext:
    retrieve_fn: RetrieveFn | None = None
    user_token: str = ""
    user_id: str = ""
    has_documents: bool = False


@dataclass
class ToolEvent:
    tool_name: str
    data: Any


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------


def _always_enabled(_ctx: ToolContext) -> bool:
    return True


@dataclass
class ToolPlugin:
    definition: dict
    handler: Callable[..., Awaitable[str | dict]]
    enabled: Callable[[ToolContext], bool] = field(default=_always_enabled)
