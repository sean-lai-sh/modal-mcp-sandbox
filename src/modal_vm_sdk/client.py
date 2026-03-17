"""Public SDK client for interacting with the Modal VM control plane."""

from __future__ import annotations

import json
from typing import Any

from .models import McpEndpoint, SessionInfo, StopResult, ToolInvocationResult
from .transport import ModalFunctionTransport


class ModalVMClient:
    def __init__(self, app_name: str = "modal-vm-primitive") -> None:
        self._transport = ModalFunctionTransport(app_name=app_name)

    def ensure_session(
        self,
        workspace_id: str,
        session_id: str | None = None,
        idle_timeout_seconds: int = 3600,
    ) -> SessionInfo:
        payload = self._transport.call(
            "ensure_session",
            workspace_id=workspace_id,
            session_id=session_id,
            idle_timeout_seconds=idle_timeout_seconds,
        )
        return SessionInfo.from_dict(payload)

    def get_mcp_endpoint(
        self,
        workspace_id: str,
        session_id: str | None = None,
    ) -> McpEndpoint:
        payload = self._transport.call(
            "get_mcp_endpoint",
            workspace_id=workspace_id,
            session_id=session_id,
        )
        return McpEndpoint.from_dict(payload)

    def invoke_tool(
        self,
        workspace_id: str,
        tool_name: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
        cwd: str = "/workspace",
        timeout_seconds: int = 120,
    ) -> ToolInvocationResult:
        payload = self._transport.call(
            "invoke_tool",
            workspace_id=workspace_id,
            tool_name=tool_name,
            params_json=json.dumps(params or {}, separators=(",", ":")),
            session_id=session_id,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
        return ToolInvocationResult.from_dict(payload)

    def stop_session(
        self,
        workspace_id: str,
        session_id: str | None = None,
    ) -> StopResult:
        payload = self._transport.call(
            "stop_session",
            workspace_id=workspace_id,
            session_id=session_id,
        )
        return StopResult.from_dict(payload)

    def reap_idle_sessions(self, max_idle_seconds: int = 3600) -> dict[str, Any]:
        return self._transport.call(
            "reap_idle_sessions",
            max_idle_seconds=max_idle_seconds,
        )
