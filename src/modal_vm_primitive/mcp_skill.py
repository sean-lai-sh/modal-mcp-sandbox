"""Skill composition helpers for MCP CLI gateway."""

from __future__ import annotations

from importlib import resources
from typing import Any


def load_base_skill_text() -> str:
    return resources.files("modal_vm_primitive.assets").joinpath(
        "mcp2cli_base_skill.md"
    ).read_text(encoding="utf-8")


def render_overlay(workspace_id: str, registry: dict[str, Any] | None = None) -> str:
    server_count = 0
    tool_count = 0
    if isinstance(registry, dict):
        servers = registry.get("servers", [])
        if isinstance(servers, list):
            server_count = len(servers)
            for server in servers:
                if isinstance(server, dict):
                    tools = server.get("tools", [])
                    if isinstance(tools, list):
                        tool_count += len(tools)

    lines = [
        "# Workspace MCP CLI Gateway",
        "",
        f"Workspace: `{workspace_id}`",
        f"Synced servers: `{server_count}`",
        f"Synced tools: `{tool_count}`",
        "",
        "For non-standard MCPs, use the workspace gateway CLI flow instead of adding large tool",
        "catalogs to prompt context.",
        "",
        "Recommended flow:",
        "1. Sync definitions before first use or after server changes.",
        "2. List available server/tool names from the generated registry.",
        "3. Execute tools via the gateway runner with JSON args.",
        "",
        "Notes:",
        "- Prefer env/secret-backed API keys over literals.",
        "- Keep prompts minimal; discover capabilities at runtime.",
    ]
    return "\n".join(lines)


def render_workspace_skill(workspace_id: str, registry: dict[str, Any] | None = None) -> str:
    base = load_base_skill_text().strip()
    overlay = render_overlay(workspace_id=workspace_id, registry=registry).strip()
    return f"{base}\n\n---\n\n{overlay}\n"
