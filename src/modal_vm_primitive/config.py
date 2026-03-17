"""Configuration values for the Modal VM primitive."""

from __future__ import annotations

import os

APP_NAME = os.environ.get("MODAL_VM_APP_NAME", "modal-vm-primitive")
SESSIONS_DICT_NAME = os.environ.get("MODAL_VM_SESSIONS_DICT", "modal-vm-sessions")
TOOLING_VOLUME_NAME = os.environ.get("MODAL_VM_TOOLING_VOLUME", "modal-vm-tooling")
WORKSPACE_VOLUME_PREFIX = os.environ.get("MODAL_VM_WORKSPACE_PREFIX", "modal-vm-workspace")

WORKSPACE_MOUNT_PATH = os.environ.get("MODAL_VM_WORKSPACE_MOUNT", "/workspace")
TOOLING_MOUNT_PATH = os.environ.get("MODAL_VM_TOOLING_MOUNT", "/tooling")
TOOL_MANIFEST_PATH = os.environ.get(
    "MODAL_VM_TOOL_MANIFEST", "/workspace/.agent/tools.json"
)
MCP_PORT = int(os.environ.get("MODAL_VM_MCP_PORT", "8080"))
MCP_LOG_PATH = os.environ.get("MODAL_VM_MCP_LOG", "/tmp/modal-vm-mcp.log")

DEFAULT_IDLE_TIMEOUT_SECONDS = int(
    os.environ.get("MODAL_VM_IDLE_TIMEOUT_SECONDS", "3600")
)
DEFAULT_EXEC_TIMEOUT_SECONDS = int(
    os.environ.get("MODAL_VM_EXEC_TIMEOUT_SECONDS", "120")
)
DEFAULT_REAPER_MAX_IDLE_SECONDS = int(
    os.environ.get("MODAL_VM_REAPER_MAX_IDLE_SECONDS", "3600")
)
