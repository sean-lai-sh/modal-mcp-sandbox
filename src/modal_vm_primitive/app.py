"""Modal control plane for VM-like agent sandboxes."""

from __future__ import annotations

import json
import shlex
import time
from pathlib import Path
from typing import Any, Optional

import modal

from .config import (
    APP_NAME,
    DEFAULT_EXEC_TIMEOUT_SECONDS,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_REAPER_MAX_IDLE_SECONDS,
    MCP2CLI_BIN,
    MCP2CLI_SPEC,
    MCP_CLI_DIR,
    MCP_DEFINITIONS_PATH,
    MCP_REGISTRY_PATH,
    MCP_SKILL_PATH,
)
from .mcp_definitions import (
    merge_definitions,
    parse_definition_payload,
)
from .mcp_runtime import ensure_mcp_url, start_mcp_server
from .mcp_skill import render_workspace_skill
from .sandbox_manager import (
    create_sandbox,
    create_session_record,
    invoke_tool_in_sandbox,
    is_sandbox_alive,
    parse_tool_runner_output,
    sandbox_from_id,
    terminate_sandbox,
    exec_in_sandbox,
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

_DEFINITIONS_SCRIPT = """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--definitions-path", required=True)
parser.add_argument("--action", required=True, choices=["list", "merge"])
parser.add_argument("--definition-json")
args = parser.parse_args()

path = Path(args.definitions_path)
path.parent.mkdir(parents=True, exist_ok=True)

if path.exists():
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
else:
    payload = {}

definitions = payload.get("definitions", []) if isinstance(payload, dict) else []
if not isinstance(definitions, list):
    definitions = []

def write_defs(items):
    out = {
        "version": 1,
        "updated_at_epoch": __import__("time").time_ns() // 1_000_000_000,
        "definitions": items,
    }
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

if args.action == "list":
    print(json.dumps({"definitions": definitions}))
    raise SystemExit(0)

incoming = json.loads(args.definition_json)
incoming_id = str(incoming.get("id", "")).strip()
if not incoming_id:
    raise SystemExit("definition id is required")

merged = []
replaced = False
for item in definitions:
    if isinstance(item, dict) and str(item.get("id", "")).strip() == incoming_id:
        merged.append(incoming)
        replaced = True
    elif isinstance(item, dict):
        merged.append(item)

if not replaced:
    merged.append(incoming)

merged.sort(key=lambda x: str(x.get("id", "")))
write_defs(merged)
print(json.dumps({"definitions": merged, "updated": incoming_id, "count": len(merged)}))
""".strip()

_REGISTRY_SCRIPT = """
import argparse
import json
import os
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--definitions-path", required=True)
parser.add_argument("--registry-path", required=True)
parser.add_argument("--mcp2cli-bin", required=True)
args = parser.parse_args()


def parse_tools(payload):
    if isinstance(payload, list):
        tools = payload
    elif isinstance(payload, dict):
        tools = payload.get("tools", [])
    else:
        tools = []
    if not isinstance(tools, list):
        tools = []

    out = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or tool.get("id") or tool.get("title") or "").strip()
        if not name:
            continue
        out.append(
            {
                "name": name,
                "description": str(tool.get("description", "")).strip(),
                "input_schema": tool.get("input_schema") or tool.get("inputSchema") or {},
            }
        )
    return out


def resolve_auth(auth):
    if not isinstance(auth, dict):
        return {}, None

    auth_type = str(auth.get("type", "none")).strip().lower()
    if auth_type != "api_key":
        return {}, None

    header = str(auth.get("header", "Authorization")).strip() or "Authorization"
    token = None
    env_var = auth.get("env_var")
    if isinstance(env_var, str) and env_var.strip():
        token = os.environ.get(env_var.strip())

    if not token:
        value = auth.get("value")
        if isinstance(value, str) and value.strip():
            token = value.strip()

    if not token:
        return {}, "api_key configured but no value found"

    if header.lower() == "authorization" and not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    return {header: token}, None


def tools_url(server_url):
    return server_url.rstrip("/") + "/tools"


def load_definitions(path):
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    defs = raw.get("definitions", []) if isinstance(raw, dict) else []
    return defs if isinstance(defs, list) else []


def main():
    defs = load_definitions(args.definitions_path)
    servers = []
    errors = []

    for item in defs:
        if not isinstance(item, dict):
            continue

        server_id = str(item.get("id", "")).strip()
        server_url = str(item.get("url", "")).strip()
        if not server_id or not server_url:
            continue

        headers, auth_err = resolve_auth(item.get("auth"))
        if auth_err:
            errors.append({"server_id": server_id, "error": auth_err})

        req = urllib.request.Request(tools_url(server_url), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            parsed_tools = parse_tools(payload)
            servers.append(
                {
                    "id": server_id,
                    "url": server_url,
                    "auth": item.get("auth", {"type": "none"}),
                    "tools": parsed_tools,
                }
            )
        except Exception as exc:
            errors.append({"server_id": server_id, "error": str(exc)})

    out = {
        "version": 1,
        "updated_at_epoch": __import__("time").time_ns() // 1_000_000_000,
        "mcp2cli_bin": args.mcp2cli_bin,
        "servers": servers,
        "errors": errors,
    }

    reg_path = Path(args.registry_path)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(json.dumps({
        "servers": len(servers),
        "tools": sum(len(s.get("tools", [])) for s in servers),
        "errors": errors,
        "registry_path": str(reg_path),
    }))


if __name__ == "__main__":
    main()
""".strip()

_RUN_MCP_TOOL_SCRIPT = """
import argparse
import json
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--registry-path", required=True)
parser.add_argument("--server-id", required=True)
parser.add_argument("--tool-name", required=True)
parser.add_argument("--args-json", default="{}")
parser.add_argument("--mcp2cli-bin", required=True)
parser.add_argument("--timeout-seconds", type=int, default=120)
args = parser.parse_args()

registry = json.loads(Path(args.registry_path).read_text(encoding="utf-8"))
servers = registry.get("servers", []) if isinstance(registry, dict) else []
if not isinstance(servers, list):
    servers = []

server = next((s for s in servers if isinstance(s, dict) and s.get("id") == args.server_id), None)
if not server:
    raise SystemExit(f"Unknown server_id: {args.server_id}")

tools = server.get("tools", []) if isinstance(server.get("tools"), list) else []
tool = next((t for t in tools if isinstance(t, dict) and t.get("name") == args.tool_name), None)
if not tool:
    raise SystemExit(f"Unknown tool_name '{args.tool_name}' for server '{args.server_id}'")

try:
    tool_args = json.loads(args.args_json)
except Exception as exc:
    raise SystemExit(f"Invalid args_json: {exc}")
if not isinstance(tool_args, dict):
    raise SystemExit("args_json must decode to a JSON object")

server_url = str(server.get("url", "")).strip()
auth = server.get("auth", {}) if isinstance(server.get("auth"), dict) else {}
header = str(auth.get("header", "Authorization")).strip() or "Authorization"
token = None
if str(auth.get("type", "none")).strip().lower() == "api_key":
    env_var = auth.get("env_var")
    if isinstance(env_var, str) and env_var.strip():
        token = os.environ.get(env_var.strip())
    if not token:
        value = auth.get("value")
        if isinstance(value, str) and value.strip():
            token = value.strip()

if header.lower() == "authorization" and token and not token.lower().startswith("bearer "):
    token = f"Bearer {token}"

cmd_variants = []
cmd_variants.append([
    args.mcp2cli_bin,
    "call",
    "--server",
    server_url,
    "--tool",
    args.tool_name,
    "--args",
    json.dumps(tool_args, separators=(",", ":")),
])
cmd_variants.append([
    args.mcp2cli_bin,
    "tool",
    "call",
    "--server",
    server_url,
    args.tool_name,
    json.dumps(tool_args, separators=(",", ":")),
])

env = dict(os.environ)
if token:
    env["MCP2CLI_AUTH_HEADER"] = header
    env["MCP2CLI_AUTH_VALUE"] = token

last = None
for cmd in cmd_variants:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=args.timeout_seconds,
            check=False,
            env=env,
        )
        last = proc
        if proc.returncode == 0:
            print(json.dumps({
                "server_id": args.server_id,
                "tool": args.tool_name,
                "command": " ".join(cmd),
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }))
            raise SystemExit(0)
    except FileNotFoundError:
        raise SystemExit(f"mcp2cli binary not found: {args.mcp2cli_bin}")

if last is None:
    raise SystemExit("No command variant executed")

print(json.dumps({
    "server_id": args.server_id,
    "tool": args.tool_name,
    "command": " ".join(cmd_variants[-1]),
    "exit_code": last.returncode,
    "stdout": last.stdout,
    "stderr": last.stderr,
}))
raise SystemExit(last.returncode)
""".strip()


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
        "secret_names": record.get("secret_names", []),
    }


def _exec_python_script(
    sandbox: modal.Sandbox,
    script: str,
    args: list[str],
    cwd: str = "/workspace",
    timeout_seconds: int = DEFAULT_EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    arg_text = " ".join(shlex.quote(arg) for arg in args)
    cmd = (
        "cat > /tmp/modal_vm_exec.py <<'PY'\n"
        f"{script}\n"
        "PY\n"
        f"python /tmp/modal_vm_exec.py {arg_text}"
    )
    return exec_in_sandbox(
        sandbox=sandbox,
        command=cmd,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )


def _parse_last_json(stdout: str) -> dict[str, Any]:
    lines = stdout.strip().splitlines()
    if not lines:
        return {}
    try:
        parsed = json.loads(lines[-1])
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {}


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


def _ensure_mcp2cli_runtime(sandbox: modal.Sandbox) -> None:
    cmd = (
        "mkdir -p /tmp/modal-vm-bin && "
        f"if [ ! -x {shlex.quote(MCP2CLI_BIN)} ]; then "
        f"python -m pip install --disable-pip-version-check --no-input -q {shlex.quote(MCP2CLI_SPEC)} && "
        "MCP2CLI_PATH=\"$(command -v mcp2cli || true)\" && "
        "if [ -z \"$MCP2CLI_PATH\" ]; then echo 'mcp2cli binary not found after install' >&2; exit 1; fi && "
        f"ln -sf \"$MCP2CLI_PATH\" {shlex.quote(MCP2CLI_BIN)}; "
        "fi"
    )
    result = exec_in_sandbox(sandbox=sandbox, command=cmd, cwd="/", timeout_seconds=300)
    if int(result.get("exit_code", 1)) != 0:
        raise RuntimeError(result.get("stderr") or "Failed to bootstrap mcp2cli")


def _list_definitions(sandbox: modal.Sandbox) -> list[dict[str, Any]]:
    result = _exec_python_script(
        sandbox=sandbox,
        script=_DEFINITIONS_SCRIPT,
        args=[
            "--definitions-path",
            MCP_DEFINITIONS_PATH,
            "--action",
            "list",
        ],
    )
    payload = _parse_last_json(result.get("stdout", ""))
    defs = payload.get("definitions", [])
    if not isinstance(defs, list):
        return []
    return [item for item in defs if isinstance(item, dict)]


def _register_definition(sandbox: modal.Sandbox, definition: dict[str, Any]) -> dict[str, Any]:
    result = _exec_python_script(
        sandbox=sandbox,
        script=_DEFINITIONS_SCRIPT,
        args=[
            "--definitions-path",
            MCP_DEFINITIONS_PATH,
            "--action",
            "merge",
            "--definition-json",
            json.dumps(definition, separators=(",", ":")),
        ],
    )
    payload = _parse_last_json(result.get("stdout", ""))
    if int(result.get("exit_code", 1)) != 0:
        raise RuntimeError(result.get("stderr") or "Failed to register definition")
    return payload


def _sync_registry(sandbox: modal.Sandbox) -> dict[str, Any]:
    _ensure_mcp2cli_runtime(sandbox)
    result = _exec_python_script(
        sandbox=sandbox,
        script=_REGISTRY_SCRIPT,
        args=[
            "--definitions-path",
            MCP_DEFINITIONS_PATH,
            "--registry-path",
            MCP_REGISTRY_PATH,
            "--mcp2cli-bin",
            MCP2CLI_BIN,
        ],
    )
    payload = _parse_last_json(result.get("stdout", ""))
    if int(result.get("exit_code", 1)) != 0:
        raise RuntimeError(result.get("stderr") or "Failed to sync registry")
    return payload


def _read_registry(sandbox: modal.Sandbox) -> dict[str, Any]:
    cmd = (
        "python - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        f"p = Path({MCP_REGISTRY_PATH!r})\n"
        "if not p.exists():\n"
        "    print('{}')\n"
        "else:\n"
        "    print(p.read_text(encoding='utf-8'))\n"
        "PY"
    )
    out = exec_in_sandbox(sandbox=sandbox, command=cmd)
    payload = _parse_last_json(out.get("stdout", ""))
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_workspace_skill(sandbox: modal.Sandbox, text: str) -> None:
    cmd = (
        "python - <<'PY'\n"
        "from pathlib import Path\n"
        "import json\n"
        "payload = json.loads('''"
        + json.dumps({"text": text})
        + "''')\n"
        f"path = Path({MCP_SKILL_PATH!r})\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        "path.write_text(payload['text'], encoding='utf-8')\n"
        "print('{\"ok\": true}')\n"
        "PY"
    )
    result = exec_in_sandbox(sandbox=sandbox, command=cmd)
    if int(result.get("exit_code", 1)) != 0:
        raise RuntimeError(result.get("stderr") or "Failed to write workspace skill")


def _read_workspace_skill(sandbox: modal.Sandbox) -> str:
    cmd = (
        "python - <<'PY'\n"
        "from pathlib import Path\n"
        f"path = Path({MCP_SKILL_PATH!r})\n"
        "if not path.exists():\n"
        "    print('')\n"
        "else:\n"
        "    print(path.read_text(encoding='utf-8'))\n"
        "PY"
    )
    result = exec_in_sandbox(sandbox=sandbox, command=cmd)
    return str(result.get("stdout", ""))


def _refresh_workspace_skill(sandbox: modal.Sandbox, workspace_id: str) -> dict[str, Any]:
    registry = _read_registry(sandbox)
    text = render_workspace_skill(workspace_id=workspace_id, registry=registry)
    _write_workspace_skill(sandbox=sandbox, text=text)
    return {
        "workspace_id": workspace_id,
        "path": MCP_SKILL_PATH,
        "text": text,
        "servers": len(registry.get("servers", [])) if isinstance(registry.get("servers"), list) else 0,
    }


def _ensure_session_internal(
    workspace_id: str,
    session_id: Optional[str],
    idle_timeout_seconds: int,
    secret_names: Optional[list[str]] = None,
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

            if secret_names:
                existing["secret_names"] = sorted(
                    set(existing.get("secret_names", []) + secret_names)
                )
                store.put_session(existing)
            else:
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
        secret_names=secret_names,
    )

    start_mcp_server(sandbox)
    mcp_url = ensure_mcp_url(sandbox)

    record = create_session_record(
        workspace_id=workspace_id,
        sandbox_id=sandbox.object_id,
        volume_name=workspace_volume_name(workspace_id),
        mcp_url=mcp_url,
        resumed=False,
        secret_names=secret_names,
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
    secret_names_json: str = "[]",
) -> dict[str, Any]:
    """Create or reattach to a workspace session."""
    try:
        secret_names = json.loads(secret_names_json)
        if not isinstance(secret_names, list):
            raise ValueError("secret_names_json must decode to a list")
        secret_names = [str(name).strip() for name in secret_names if str(name).strip()]
    except Exception as exc:  # noqa: BLE001
        return {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "status": "error",
            "error": f"Invalid secret_names_json: {exc}",
        }

    return _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=idle_timeout_seconds,
        secret_names=secret_names,
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
def register_mcp_definition(
    workspace_id: str,
    definition_json: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Register or update a single MCP definition for a workspace."""
    normalized = parse_definition_payload(definition_json).to_dict()

    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    sandbox = sandbox_from_id(ensured["sandbox_id"])

    existing = _list_definitions(sandbox)
    merged = merge_definitions(existing=existing, new_definition=parse_definition_payload(definition_json))
    # Keep merge order deterministic in control plane and persist once.
    payload = _register_definition(sandbox=sandbox, definition=normalized)

    workspace_volume = get_workspace_volume(workspace_id)
    safe_commit(workspace_volume)
    store.touch_session(ensured["session_id"])

    return {
        "workspace_id": workspace_id,
        "session_id": ensured["session_id"],
        "updated": payload.get("updated"),
        "count": len(merged),
        "definitions_path": MCP_DEFINITIONS_PATH,
    }


@app.function(image=control_plane_image)
def list_mcp_definitions(
    workspace_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """List MCP definitions for a workspace."""
    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    sandbox = sandbox_from_id(ensured["sandbox_id"])
    definitions = _list_definitions(sandbox)

    store.touch_session(ensured["session_id"])
    return {
        "workspace_id": workspace_id,
        "session_id": ensured["session_id"],
        "definitions": definitions,
        "definitions_path": MCP_DEFINITIONS_PATH,
    }


@app.function(image=control_plane_image)
def sync_mcp_tools(
    workspace_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Sync tool metadata from registered MCP definitions into workspace registry."""
    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    sandbox = sandbox_from_id(ensured["sandbox_id"])

    payload = _sync_registry(sandbox)
    skill_payload = _refresh_workspace_skill(sandbox=sandbox, workspace_id=workspace_id)

    workspace_volume = get_workspace_volume(workspace_id)
    safe_commit(workspace_volume)
    store.touch_session(ensured["session_id"])

    return {
        "workspace_id": workspace_id,
        "session_id": ensured["session_id"],
        "registry_path": MCP_REGISTRY_PATH,
        "servers": int(payload.get("servers", 0)),
        "tools": int(payload.get("tools", 0)),
        "errors": payload.get("errors", []),
        "skill_path": skill_payload["path"],
    }


@app.function(image=control_plane_image)
def run_mcp_tool(
    workspace_id: str,
    server_id: str,
    tool_name: str,
    args_json: str = "{}",
    session_id: Optional[str] = None,
    timeout_seconds: int = DEFAULT_EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run a synced MCP tool through mcp2cli gateway."""
    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    sandbox = sandbox_from_id(ensured["sandbox_id"])

    _ensure_mcp2cli_runtime(sandbox)
    result = _exec_python_script(
        sandbox=sandbox,
        script=_RUN_MCP_TOOL_SCRIPT,
        args=[
            "--registry-path",
            MCP_REGISTRY_PATH,
            "--server-id",
            server_id,
            "--tool-name",
            tool_name,
            "--args-json",
            args_json,
            "--mcp2cli-bin",
            MCP2CLI_BIN,
            "--timeout-seconds",
            str(timeout_seconds),
        ],
        timeout_seconds=timeout_seconds,
    )
    payload = _parse_last_json(result.get("stdout", ""))

    workspace_volume = get_workspace_volume(workspace_id)
    safe_commit(workspace_volume)
    store.touch_session(ensured["session_id"])

    return {
        "workspace_id": workspace_id,
        "session_id": ensured["session_id"],
        "server_id": server_id,
        "tool": tool_name,
        "command": payload.get("command"),
        "exit_code": int(payload.get("exit_code", result.get("exit_code", 1))),
        "stdout": str(payload.get("stdout", result.get("stdout", ""))),
        "stderr": str(payload.get("stderr", result.get("stderr", ""))),
    }


@app.function(image=control_plane_image)
def refresh_workspace_mcp_skill(
    workspace_id: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Refresh workspace gateway skill text artifact from current registry."""
    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    sandbox = sandbox_from_id(ensured["sandbox_id"])
    payload = _refresh_workspace_skill(sandbox=sandbox, workspace_id=workspace_id)

    workspace_volume = get_workspace_volume(workspace_id)
    safe_commit(workspace_volume)
    store.touch_session(ensured["session_id"])

    return {
        "workspace_id": workspace_id,
        "session_id": ensured["session_id"],
        "path": payload["path"],
        "text": payload["text"],
        "servers": payload["servers"],
    }


@app.function(image=control_plane_image)
def get_workspace_mcp_skill(
    workspace_id: str,
    session_id: Optional[str] = None,
    refresh_if_missing: bool = True,
) -> dict[str, Any]:
    """Get workspace skill text used for prompt injection."""
    ensured = _ensure_session_internal(
        workspace_id=workspace_id,
        session_id=session_id,
        idle_timeout_seconds=DEFAULT_IDLE_TIMEOUT_SECONDS,
    )
    sandbox = sandbox_from_id(ensured["sandbox_id"])

    text = _read_workspace_skill(sandbox)
    if refresh_if_missing and not text.strip():
        payload = _refresh_workspace_skill(sandbox=sandbox, workspace_id=workspace_id)
        text = payload["text"]

    store.touch_session(ensured["session_id"])
    return {
        "workspace_id": workspace_id,
        "session_id": ensured["session_id"],
        "path": MCP_SKILL_PATH,
        "text": text,
    }


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
