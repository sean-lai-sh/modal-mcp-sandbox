"""Typed SDK response models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SessionInfo:
    workspace_id: str
    session_id: str
    sandbox_id: str
    volume_name: str
    mcp_url: str | None
    status: str
    resumed: bool
    last_heartbeat_epoch: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionInfo":
        return cls(
            workspace_id=str(payload["workspace_id"]),
            session_id=str(payload["session_id"]),
            sandbox_id=str(payload["sandbox_id"]),
            volume_name=str(payload["volume_name"]),
            mcp_url=payload.get("mcp_url"),
            status=str(payload.get("status", "active")),
            resumed=bool(payload.get("resumed", False)),
            last_heartbeat_epoch=int(payload.get("last_heartbeat_epoch", 0)),
        )


@dataclass
class ToolInvocationResult:
    workspace_id: str
    session_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    command: str | None = None
    tool: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolInvocationResult":
        return cls(
            workspace_id=str(payload.get("workspace_id", "")),
            session_id=str(payload.get("session_id", "")),
            exit_code=int(payload.get("exit_code", 1)),
            stdout=str(payload.get("stdout", "")),
            stderr=str(payload.get("stderr", "")),
            duration_ms=int(payload.get("duration_ms", 0)),
            command=payload.get("command"),
            tool=payload.get("tool"),
        )


@dataclass
class McpEndpoint:
    workspace_id: str
    session_id: str
    url: str | None
    transport: str
    status: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "McpEndpoint":
        return cls(
            workspace_id=str(payload.get("workspace_id", "")),
            session_id=str(payload.get("session_id", "")),
            url=payload.get("url"),
            transport=str(payload.get("transport", "http_sse")),
            status=str(payload.get("status", "unknown")),
        )


@dataclass
class StopResult:
    workspace_id: str
    session_id: str | None
    stopped: bool
    reason: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StopResult":
        return cls(
            workspace_id=str(payload.get("workspace_id", "")),
            session_id=payload.get("session_id"),
            stopped=bool(payload.get("stopped", False)),
            reason=payload.get("reason"),
        )
