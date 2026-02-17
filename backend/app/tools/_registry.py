"""Tool plugin registry — types, autodiscovery, and dispatch."""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from pathlib import Path
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

@dataclass
class ToolPlugin:
    definition: dict
    handler: Callable  # async def handler(args: dict, ctx: ToolContext, on_status=None) -> str | dict
    enabled: Callable[[ToolContext], bool] = field(default=lambda _: True)
