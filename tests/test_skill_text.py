from __future__ import annotations

from modal_vm_sdk.skills import compose_base_mcp_skill


def test_compose_base_skill_contains_gateway_overlay():
    text = compose_base_mcp_skill()

    assert "MCP2CLI Base Skill" in text
    assert "ModalVM MCP CLI Gateway" in text
    assert "avoid context bloat" in text.lower()
