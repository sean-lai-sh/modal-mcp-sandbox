"""Helpers to boot and inspect MCP runtime inside a sandbox."""

from __future__ import annotations

import shlex

from .config import MCP_LOG_PATH, MCP_PORT, TOOL_MANIFEST_PATH
from .sandbox_manager import exec_in_sandbox, get_tunnel_url

_INLINE_MCP_SERVER = """
import argparse
import json
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

def load_tools(manifest_path: str):
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Tool manifest not found: {manifest_path}")
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
    raise KeyError(f"Tool '{name}' not found")

def render_command(tool, params):
    command = tool.get("command")
    template = tool.get("command_template")
    if isinstance(command, str) and command:
        return command
    if isinstance(template, str) and template:
        return template.format(**params)
    raise ValueError("Tool must define 'command' or 'command_template'")

def run_tool(manifest_path: str, tool_name: str, params: dict, cwd: str, timeout_seconds: int):
    started = time.time()
    tools = load_tools(manifest_path)
    tool = find_tool(tools, tool_name)
    command = render_command(tool, params)
    proc = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "tool": tool_name,
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration_ms": int((time.time() - started) * 1000),
    }

class Handler(BaseHTTPRequestHandler):
    manifest_path = "/workspace/.agent/tools.json"

    def log_message(self, fmt, *args):
        return

    def _json(self, payload, status=HTTPStatus.OK):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        data = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("body must be a JSON object")
        return data

    def do_GET(self):
        if self.path == "/health":
            self._json({"status": "ok"})
            return
        if self.path == "/tools":
            self._json({"tools": load_tools(self.manifest_path)})
            return
        self._json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path != "/invoke":
            self._json({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._read()
            tool = str(body["tool"])
            params = body.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            out = run_tool(
                manifest_path=self.manifest_path,
                tool_name=tool,
                params=params,
                cwd=str(body.get("cwd", "/workspace")),
                timeout_seconds=int(body.get("timeout_seconds", 120)),
            )
            self._json(out)
        except KeyError as exc:
            self._json({"error": f"missing_field: {exc}"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    Handler.manifest_path = args.manifest
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()

if __name__ == "__main__":
    main()
""".strip()


def start_mcp_server(sandbox) -> None:
    cmd = (
        "cat > /tmp/modal_vm_mcp_server.py <<'PY'\n"
        f"{_INLINE_MCP_SERVER}\n"
        "PY\n"
        "pkill -f '/tmp/modal_vm_mcp_server.py' >/dev/null 2>&1 || true\n"
        "nohup python /tmp/modal_vm_mcp_server.py "
        f"--manifest {shlex.quote(TOOL_MANIFEST_PATH)} "
        f"--host 0.0.0.0 --port {MCP_PORT} "
        f"> {shlex.quote(MCP_LOG_PATH)} 2>&1 &"
    )
    exec_in_sandbox(sandbox=sandbox, command=cmd)


def ensure_mcp_url(sandbox) -> str | None:
    url = get_tunnel_url(sandbox, port=MCP_PORT)
    if url:
        return url
    return None
