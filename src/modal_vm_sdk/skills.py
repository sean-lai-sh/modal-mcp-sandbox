"""SDK-side skill composition helpers."""

from __future__ import annotations

from importlib import resources


def load_base_skill_text() -> str:
    return resources.files("modal_vm_sdk.assets").joinpath("mcp2cli_base_skill.md").read_text(
        encoding="utf-8"
    )


def build_overlay() -> str:
    return """# ModalVM MCP CLI Gateway

Use this gateway for non-standard MCP servers to avoid context bloat.

- If an MCP tool is not directly attached, call through the workspace gateway.
- Keep prompts compact; rely on runtime discovery/sync instead of embedding large tool catalogs.
- Prefer env/secret-backed API keys over literals.
""".strip()


def compose_base_mcp_skill() -> str:
    base = load_base_skill_text().strip()
    overlay = build_overlay().strip()
    return f"{base}\n\n---\n\n{overlay}\n"
