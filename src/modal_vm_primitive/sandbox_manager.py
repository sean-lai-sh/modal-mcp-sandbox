"""Sandbox lifecycle and command execution helpers."""

from __future__ import annotations

import json
import shlex
import time
import uuid
from collections.abc import Mapping
from typing import Any

import modal

from .config import (
    MCP_PORT,
    TOOLING_MOUNT_PATH,
    TOOL_MANIFEST_PATH,
    WORKSPACE_MOUNT_PATH,
)

_INLINE_TOOL_RUNNER = """
import argparse
import json
import subprocess
import time
from pathlib import Path

def load_manifest(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Tool manifest not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        tools = raw
    elif isinstance(raw, dict):
        tools = raw.get("tools", [])
    else:
        tools = []
    if not isinstance(tools, list):
        raise ValueError("Manifest 'tools' must be a list")
    return [tool for tool in tools if isinstance(tool, dict)]

def find_tool(tools, name: str):
    for tool in tools:
        if tool.get("name") == name:
            return tool
    raise KeyError(f"Tool '{name}' not found in manifest")

def render_command(tool, params):
    command = tool.get("command")
    template = tool.get("command_template")
    if isinstance(command, str) and command:
        return command
    if isinstance(template, str) and template:
        return template.format(**params)
    raise ValueError("Tool definition must include 'command' or 'command_template'")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--params", default="{}")
    parser.add_argument("--cwd", default="/workspace")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    started = time.time()
    try:
        params = json.loads(args.params)
        if not isinstance(params, dict):
            raise ValueError("params must decode to a JSON object")
        tools = load_manifest(Path(args.manifest))
        tool = find_tool(tools, args.tool)
        command = render_command(tool, params)
        proc = subprocess.run(
            command,
            shell=True,
            cwd=args.cwd,
            capture_output=True,
            text=True,
            timeout=args.timeout_seconds,
            check=False,
        )
        out = {
            "tool": args.tool,
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        out = {
            "tool": args.tool,
            "command": None,
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": int((time.time() - started) * 1000),
        }

    print(json.dumps(out))

if __name__ == "__main__":
    main()
""".strip()


def _ensure_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _read_stream(stream: Any) -> str:
    if stream is None:
        return ""
    read_fn = getattr(stream, "read", None)
    if callable(read_fn):
        return _ensure_text(read_fn())
    return _ensure_text(stream)


def create_session_record(
    workspace_id: str,
    sandbox_id: str,
    volume_name: str,
    mcp_url: str | None,
    resumed: bool,
) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "session_id": str(uuid.uuid4()),
        "sandbox_id": sandbox_id,
        "volume_name": volume_name,
        "mcp_url": mcp_url,
        "mcp_port": MCP_PORT,
        "status": "active",
        "resumed": resumed,
        "tool_manifest_path": TOOL_MANIFEST_PATH,
    }


def create_sandbox(
    app: modal.App,
    image: modal.Image,
    workspace_volume: modal.Volume,
    tooling_volume: modal.Volume,
    idle_timeout_seconds: int,
) -> modal.Sandbox:
    return modal.Sandbox.create(
        "bash",
        "-lc",
        "sleep infinity",
        app=app,
        image=image,
        timeout=idle_timeout_seconds,
        volumes={
            WORKSPACE_MOUNT_PATH: workspace_volume,
            TOOLING_MOUNT_PATH: tooling_volume,
        },
        encrypted_ports=[MCP_PORT],
    )


def sandbox_from_id(sandbox_id: str) -> modal.Sandbox:
    from_id = getattr(modal.Sandbox, "from_id", None)
    if not callable(from_id):
        raise RuntimeError("modal.Sandbox.from_id is unavailable in this Modal client")
    return from_id(sandbox_id)


def is_sandbox_alive(sandbox: modal.Sandbox) -> bool:
    poll_fn = getattr(sandbox, "poll", None)
    if callable(poll_fn):
        return poll_fn() is None

    returncode = getattr(sandbox, "returncode", None)
    if returncode is None:
        return True
    return returncode is None


def terminate_sandbox(sandbox: modal.Sandbox) -> None:
    terminate_fn = getattr(sandbox, "terminate", None)
    if callable(terminate_fn):
        terminate_fn()


def get_tunnel_url(sandbox: modal.Sandbox, port: int = MCP_PORT) -> str | None:
    tunnels_attr = getattr(sandbox, "tunnels", None)
    tunnels: Any = None

    if callable(tunnels_attr):
        tunnels = tunnels_attr()
    elif tunnels_attr is not None:
        tunnels = tunnels_attr

    if not tunnels:
        return None

    if isinstance(tunnels, Mapping):
        tunnel = tunnels.get(port)
    else:
        tunnel = None
        for item in tunnels:
            item_port = getattr(item, "container_port", None)
            if item_port == port:
                tunnel = item
                break

    if tunnel is None:
        return None

    for candidate_attr in ("url", "tcp_socket", "https_url"):
        candidate = getattr(tunnel, candidate_attr, None)
        if candidate:
            return _ensure_text(candidate)
    return None


def exec_in_sandbox(
    sandbox: modal.Sandbox,
    command: str,
    cwd: str = WORKSPACE_MOUNT_PATH,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    started = time.time()
    wrapped_command = command
    if cwd:
        wrapped_command = f"cd {shlex.quote(cwd)} && {command}"

    try:
        process = sandbox.exec(
            "bash",
            "-lc",
            wrapped_command,
            timeout=timeout_seconds,
        )
    except TypeError as exc:
        # Older Modal client/runtime combinations do not support timeout keyword.
        if "timeout" not in str(exc):
            raise
        process = sandbox.exec(
            "bash",
            "-lc",
            wrapped_command,
        )

    wait_fn = getattr(process, "wait", None)
    if callable(wait_fn):
        wait_fn()

    exit_code = getattr(process, "returncode", 0)
    stdout = _read_stream(getattr(process, "stdout", None))
    stderr = _read_stream(getattr(process, "stderr", None))

    return {
        "command": wrapped_command,
        "exit_code": int(exit_code or 0),
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": int((time.time() - started) * 1000),
    }


def invoke_tool_in_sandbox(
    sandbox: modal.Sandbox,
    tool_name: str,
    params: dict[str, Any],
    cwd: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    payload = json.dumps(params or {}, separators=(",", ":"))
    cmd = (
        "cat > /tmp/modal_vm_tool_runner.py <<'PY'\n"
        f"{_INLINE_TOOL_RUNNER}\n"
        "PY\n"
        "python /tmp/modal_vm_tool_runner.py "
        f"--manifest {shlex.quote(TOOL_MANIFEST_PATH)} "
        f"--tool {shlex.quote(tool_name)} "
        f"--params {shlex.quote(payload)} "
        f"--cwd {shlex.quote(cwd)} "
        f"--timeout-seconds {timeout_seconds}"
    )
    return exec_in_sandbox(
        sandbox=sandbox,
        command=cmd,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )


def parse_tool_runner_output(exec_result: dict[str, Any]) -> dict[str, Any]:
    stdout = exec_result.get("stdout", "")
    candidate = stdout.strip().splitlines()
    raw = candidate[-1] if candidate else ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "exit_code": exec_result.get("exit_code", 1),
            "stdout": stdout,
            "stderr": (
                f"Unable to parse tool runner output as JSON: {exc}. "
                f"Original stderr: {exec_result.get('stderr', '')}"
            ),
            "duration_ms": exec_result.get("duration_ms", 0),
            "session_id": None,
        }

    if not isinstance(parsed, dict):
        return {
            "exit_code": 1,
            "stdout": stdout,
            "stderr": "Tool runner returned non-object JSON",
            "duration_ms": exec_result.get("duration_ms", 0),
            "session_id": None,
        }
    return parsed
