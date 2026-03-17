from __future__ import annotations

from modal_vm_sdk.models import McpEndpoint, SessionInfo, StopResult, ToolInvocationResult


def test_session_info_from_dict():
    payload = {
        "workspace_id": "ws-1",
        "session_id": "sess-1",
        "sandbox_id": "sb-1",
        "volume_name": "vol-1",
        "mcp_url": "https://example.com",
        "status": "active",
        "resumed": True,
        "last_heartbeat_epoch": 100,
    }
    model = SessionInfo.from_dict(payload)

    assert model.workspace_id == "ws-1"
    assert model.resumed is True


def test_tool_invocation_result_from_dict_defaults():
    payload = {
        "workspace_id": "ws-1",
        "session_id": "sess-1",
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "duration_ms": 1,
    }
    model = ToolInvocationResult.from_dict(payload)

    assert model.exit_code == 0
    assert model.command is None


def test_endpoint_and_stop_models_from_dict():
    endpoint = McpEndpoint.from_dict(
        {
            "workspace_id": "ws-1",
            "session_id": "sess-1",
            "url": "https://example.com",
            "transport": "http_sse",
            "status": "active",
        }
    )
    stop = StopResult.from_dict(
        {
            "workspace_id": "ws-1",
            "session_id": "sess-1",
            "stopped": True,
        }
    )

    assert endpoint.transport == "http_sse"
    assert stop.stopped is True
