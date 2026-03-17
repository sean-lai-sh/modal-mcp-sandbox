"""Utilities for loading and resolving workspace tool manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_tools(manifest_path: str) -> list[dict[str, Any]]:
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Tool manifest not found: {manifest_path}")

    content = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(content, list):
        tools = content
    elif isinstance(content, dict):
        tools = content.get("tools", [])
    else:
        raise ValueError("Manifest content must be an object or list")

    if not isinstance(tools, list):
        raise ValueError("Manifest tools must be a list")

    return [tool for tool in tools if isinstance(tool, dict)]


def find_tool(tools: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    for tool in tools:
        if tool.get("name") == tool_name:
            return tool
    raise KeyError(f"Tool '{tool_name}' not found")


def render_command(tool: dict[str, Any], params: dict[str, Any]) -> str:
    command = tool.get("command")
    template = tool.get("command_template")

    if isinstance(command, str) and command:
        return command
    if isinstance(template, str) and template:
        return template.format(**params)

    raise ValueError("Tool must define 'command' or 'command_template'")
