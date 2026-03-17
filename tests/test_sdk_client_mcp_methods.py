from __future__ import annotations

import json

from modal_vm_sdk.client import ModalVMClient


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []

    def call(self, function_name: str, **kwargs):
        self.calls.append((function_name, kwargs))
        if function_name == "list_mcp_definitions":
            return {
                "definitions": [
                    {
                        "id": "public_docs",
                        "url": "https://example.com/sse",
                        "auth": {"type": "none"},
                    }
                ]
            }
        if function_name == "sync_mcp_tools":
            return {
                "workspace_id": kwargs["workspace_id"],
                "session_id": "sess-1",
                "registry_path": "/workspace/.agent/mcp_cli/registry.json",
                "servers": 1,
                "tools": 2,
                "errors": [],
                "skill_path": "/workspace/.agent/skills/mcp_cli_gateway.SKILL.md",
            }
        if function_name == "run_mcp_tool":
            return {
                "workspace_id": kwargs["workspace_id"],
                "session_id": "sess-1",
                "exit_code": 0,
                "stdout": "ok",
                "stderr": "",
                "duration_ms": 10,
            }
        if function_name == "get_workspace_mcp_skill":
            return {
                "workspace_id": kwargs["workspace_id"],
                "session_id": "sess-1",
                "path": "/workspace/.agent/skills/mcp_cli_gateway.SKILL.md",
                "text": "skill text",
            }
        return {}


def _client() -> tuple[ModalVMClient, FakeTransport]:
    client = ModalVMClient(app_name="modal-vm-primitive")
    transport = FakeTransport()
    client._transport = transport  # type: ignore[attr-defined]
    return client, transport


def test_register_definition_path_and_payload(tmp_path):
    client, transport = _client()
    p = tmp_path / "definition.json"
    p.write_text(
        json.dumps(
            {
                "id": "public_docs",
                "url": "https://example.com/sse",
                "auth": {"type": "none"},
            }
        ),
        encoding="utf-8",
    )

    client.register_mcp_definition(workspace_id="ws", definition_path=str(p))

    fn, kwargs = transport.calls[-1]
    assert fn == "register_mcp_definition"
    payload = json.loads(kwargs["definition_json"])
    assert payload["id"] == "public_docs"


def test_list_sync_run_and_workspace_skill():
    client, _ = _client()

    defs = client.list_mcp_definitions("ws")
    assert defs[0].id == "public_docs"

    sync = client.sync_mcp_tools("ws")
    assert sync.tools == 2

    run = client.run_mcp_tool("ws", "public_docs", "search", args={"q": "x"})
    assert run.exit_code == 0

    skill = client.workspace_mcp_skill("ws")
    assert skill.text == "skill text"
