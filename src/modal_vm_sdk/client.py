"""Public SDK client for interacting with the Modal VM control plane."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    McpDefinitionRecord,
    McpEndpoint,
    McpSyncResult,
    SessionInfo,
    StopResult,
    ToolInvocationResult,
    WorkspaceSkill,
)
from .skills import compose_base_mcp_skill
from .transport import ModalFunctionTransport


class ModalVMClient:
    def __init__(self, app_name: str = "modal-vm-primitive") -> None:
        self._transport = ModalFunctionTransport(app_name=app_name)

    def ensure_session(
        self,
        workspace_id: str,
        session_id: str | None = None,
        idle_timeout_seconds: int = 3600,
        secret_names: list[str] | None = None,
    ) -> SessionInfo:
        payload = self._transport.call(
            "ensure_session",
            workspace_id=workspace_id,
            session_id=session_id,
            idle_timeout_seconds=idle_timeout_seconds,
            secret_names_json=json.dumps(secret_names or []),
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

    def register_mcp_definition(
        self,
        workspace_id: str,
        definition: dict[str, Any] | None = None,
        definition_path: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if definition is None and definition_path is None:
            raise ValueError("One of definition or definition_path is required")

        payload_obj: dict[str, Any]
        if definition is not None:
            payload_obj = definition
        else:
            payload_obj = json.loads(Path(definition_path or "").read_text(encoding="utf-8"))

        payload = self._transport.call(
            "register_mcp_definition",
            workspace_id=workspace_id,
            definition_json=json.dumps(payload_obj),
            session_id=session_id,
        )
        return payload

    def list_mcp_definitions(
        self,
        workspace_id: str,
        session_id: str | None = None,
    ) -> list[McpDefinitionRecord]:
        payload = self._transport.call(
            "list_mcp_definitions",
            workspace_id=workspace_id,
            session_id=session_id,
        )
        definitions = payload.get("definitions", [])
        if not isinstance(definitions, list):
            return []
        return [
            McpDefinitionRecord.from_dict(item)
            for item in definitions
            if isinstance(item, dict)
        ]

    def sync_mcp_tools(
        self,
        workspace_id: str,
        session_id: str | None = None,
    ) -> McpSyncResult:
        payload = self._transport.call(
            "sync_mcp_tools",
            workspace_id=workspace_id,
            session_id=session_id,
        )
        return McpSyncResult.from_dict(payload)

    def run_mcp_tool(
        self,
        workspace_id: str,
        server_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        session_id: str | None = None,
        timeout_seconds: int = 120,
    ) -> ToolInvocationResult:
        payload = self._transport.call(
            "run_mcp_tool",
            workspace_id=workspace_id,
            server_id=server_id,
            tool_name=tool_name,
            args_json=json.dumps(args or {}, separators=(",", ":")),
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )
        return ToolInvocationResult.from_dict(payload)

    def refresh_workspace_mcp_skill(
        self,
        workspace_id: str,
        session_id: str | None = None,
    ) -> WorkspaceSkill:
        payload = self._transport.call(
            "refresh_workspace_mcp_skill",
            workspace_id=workspace_id,
            session_id=session_id,
        )
        return WorkspaceSkill.from_dict(payload)

    def workspace_mcp_skill(
        self,
        workspace_id: str,
        session_id: str | None = None,
        refresh_if_missing: bool = True,
    ) -> WorkspaceSkill:
        payload = self._transport.call(
            "get_workspace_mcp_skill",
            workspace_id=workspace_id,
            session_id=session_id,
            refresh_if_missing=refresh_if_missing,
        )
        return WorkspaceSkill.from_dict(payload)

    def base_mcp_skill(self) -> str:
        return compose_base_mcp_skill()
