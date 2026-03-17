"""Modal control plane for VM-like agent sandboxes."""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import modal

from .config import (
    APP_NAME,
    DEFAULT_EXEC_TIMEOUT_SECONDS,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_REAPER_MAX_IDLE_SECONDS,
)
from .mcp_runtime import ensure_mcp_url, start_mcp_server
from .sandbox_manager import (
    create_sandbox,
    create_session_record,
    invoke_tool_in_sandbox,
    is_sandbox_alive,
    parse_tool_runner_output,
    sandbox_from_id,
    terminate_sandbox,
)
from .state_store import SessionStateStore
from .volume_manager import (
    get_tooling_volume,
    get_workspace_volume,
    safe_commit,
    safe_reload,
    workspace_volume_name,
)

app = modal.App(APP_NAME)
control_plane_image = modal.Image.debian_slim().add_local_python_source(
    "modal_vm_primitive"
)
sandbox_image = modal.Image.debian_slim()


store = SessionStateStore()


def _as_session_response(record: dict[str, Any], resumed: bool) -> dict[str, Any]:
    return {
        "workspace_id": record["workspace_id"],
        "session_id": record["session_id"],
        "sandbox_id": record["sandbox_id"],
        "volume_name": record["volume_name"],
        "mcp_url": record.get("mcp_url"),
        "status": record.get("status", "active"),
        "resumed": resumed,
        "last_heartbeat_epoch": record.get("last_heartbeat_epoch", int(time.time())),
    }


def _resolve_existing_record(
    workspace_id: str,
    session_id: Optional[str],
) -> Optional[dict[str, Any]]:
    by_workspace = store.get_by_workspace(workspace_id)
    if not by_workspace:
        return None

    if session_id and by_workspace.get("session_id") != session_id:
        # V1 supports one active session per workspace.
        return None
    return by_workspace


def _ensure_session_internal(
    workspace_id: str,
    session_id: Optional[str],
    idle_timeout_seconds: int,
) -> dict[str, Any]:
    existing = _resolve_existing_record(workspace_id=workspace_id, session_id=session_id)

    if existing:
        try:
            sandbox = sandbox_from_id(existing["sandbox_id"])
        except Exception:  # noqa: BLE001 - stale ID or unavailable object
            sandbox = None

        if sandbox and is_sandbox_alive(sandbox):
            if not existing.get("mcp_url"):
                start_mcp_server(sandbox)
                existing["mcp_url"] = ensure_mcp_url(sandbox)

            store.touch_session(existing["session_id"])
            refreshed = store.get_by_session(existing["session_id"]) or existing
            return _as_session_response(refreshed, resumed=True)

        store.delete_session(existing["session_id"])

    workspace_volume = get_workspace_volume(workspace_id)
    tooling_volume = get_tooling_volume()
    safe_reload(workspace_volume)

    sandbox = create_sandbox(
        app=app,
        image=sandbox_image,
        workspace_volume=workspace_volume,
        tooling_volume=tooling_volume,
        idle_timeout_seconds=idle_timeout_seconds,
    )

    start_mcp_server(sandbox)
    mcp_url = ensure_mcp_url(sandbox)

    record = create_session_record(
        workspace_id=workspace_id,
        sandbox_id=sandbox.object_id,
        volume_name=workspace_volume_name(workspace_id),
        mcp_url=mcp_url,
        resumed=False,
    )
    store.put_session(record)
    return _as_session_response(record, resumed=False)


def _stop_session_internal(
    workspace_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    existing = _resolve_existing_record(workspace_id=workspace_id, session_id=session_id)
    if not existing:
        return {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "stopped": False,
            "reason": "session_not_found",
        }

    try:
        sandbox = sandbox_from_id(existing["sandbox_id"])
        terminate_sandbox(sandbox)
    except Exception:  # noqa: BLE001 - stale IDs should still be cleaned from state
        pass

    workspace_volume = get_workspace_volume(workspace_id)
    safe_commit(workspace_volume)
    store.delete_session(existing["session_id"])

    return {
        "workspace_id": workspace_id,
        "session_id": existing["session_id"],
        "stopped": True,
    }


@app.function(image=control_plane_image)
def ensure_session(
    workspace_id: str,
    session_id: Optional[str] = None,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Create or reattach to a workspace session."""
    return _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=idle_timeout_seconds,
    )


@app.function(image=control_plane_image)
def get_mcp_endpoint(
    workspace_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Return MCP endpoint details for a workspace session."""
    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )

    return {
        "workspace_id": workspace_id,
        "session_id": ensured["session_id"],
        "url": ensured.get("mcp_url"),
        "transport": "http_sse",
        "status": ensured.get("status", "active"),
    }


@app.function(image=control_plane_image)
def invoke_tool(
    workspace_id: str,
    tool_name: str,
    params_json: str = "{}",
    session_id: Optional[str] = None,
    cwd: str = "/workspace",
    timeout_seconds: int = DEFAULT_EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Invoke a workspace-defined tool through sandbox execution."""
    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )

    try:
        params: dict[str, Any] = json.loads(params_json)
        if not isinstance(params, dict):
            raise ValueError("params_json must decode to a JSON object")
    except Exception as exc:  # noqa: BLE001 - request validation boundary
        return {
            "workspace_id": workspace_id,
            "session_id": ensured["session_id"],
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Invalid params_json: {exc}",
            "duration_ms": 0,
        }

    sandbox = sandbox_from_id(ensured["sandbox_id"])
    result = invoke_tool_in_sandbox(
        sandbox=sandbox,
        tool_name=tool_name,
        params=params,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )

    parsed = parse_tool_runner_output(result)
    parsed["workspace_id"] = workspace_id
    parsed["session_id"] = ensured["session_id"]

    workspace_volume = get_workspace_volume(workspace_id)
    safe_commit(workspace_volume)
    store.touch_session(ensured["session_id"])
    return parsed


@app.function(image=control_plane_image)
def stop_session(
    workspace_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Terminate a workspace session."""
    return _stop_session_internal(workspace_id=workspace_id, session_id=session_id)


@app.function(image=control_plane_image)
def reap_idle_sessions(
    max_idle_seconds: int = DEFAULT_REAPER_MAX_IDLE_SECONDS,
) -> dict[str, Any]:
    """Stop sessions that have exceeded idle timeout."""
    now = int(time.time())
    reaped: list[str] = []

    for record in store.list_sessions():
        last_seen = int(record.get("last_heartbeat_epoch", 0))
        if now - last_seen <= max_idle_seconds:
            continue

        workspace_id = record["workspace_id"]
        session_id = record["session_id"]
        _stop_session_internal(workspace_id=workspace_id, session_id=session_id)
        reaped.append(session_id)

    return {"reaped_count": len(reaped), "session_ids": reaped}
