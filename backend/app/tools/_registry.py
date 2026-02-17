"""Tool plugin registry — types, autodiscovery, and dispatch."""
from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable
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


def _always_enabled(_ctx: ToolContext) -> bool:
    return True


@dataclass
class ToolPlugin:
    definition: dict
    handler: Callable[..., Awaitable[str | dict]]
    enabled: Callable[[ToolContext], bool] = field(default=_always_enabled)


# ---------------------------------------------------------------------------
# Internal plugin store (populated at import time by _discover)
# ---------------------------------------------------------------------------

_plugins: dict[str, ToolPlugin] = {}


def _discover() -> None:
    """Glob app/tools/*.py, import each, register module.plugin if present."""
    tools_dir = Path(__file__).parent
    for path in sorted(tools_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"app.tools.{path.stem}"
        try:
            mod = importlib.import_module(module_name)
            plugin: ToolPlugin | None = getattr(mod, "plugin", None)
            if plugin is None:
                logger.warning("tools/%s.py has no 'plugin' attribute — skipped", path.stem)
                continue
            if not isinstance(plugin, ToolPlugin):
                logger.warning("tools/%s.py plugin is not a ToolPlugin — skipped", path.stem)
                continue
            name = plugin.definition["function"]["name"]
            _plugins[name] = plugin
            logger.info("Loaded tool: %s", name)
        except Exception:
            logger.exception("Failed to load tools/%s.py", path.stem)


_discover()


# ---------------------------------------------------------------------------
# Public API used by llm.py
# ---------------------------------------------------------------------------

def get_tools(ctx: ToolContext) -> list[dict]:
    """Return OpenAI tool definitions for all enabled plugins."""
    return [p.definition for p in _plugins.values() if p.enabled(ctx)]


async def execute_tool(
    name: str,
    args: dict,
    ctx: ToolContext,
    on_status: Callable[[str], Awaitable[None]] | None = None,
) -> str | Any:
    """Dispatch to the matching plugin's handler, or return an error string."""
    plugin = _plugins.get(name)
    if plugin is None:
        return f"Unknown tool: {name}"
    return await plugin.handler(args, ctx, on_status=on_status)
