"""Minimal HTTP MCP-like server for workspace tool invocation."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from modal_vm_primitive.tool_runner import run_tool

from tool_manifest_loader import load_tools


class ToolServer(BaseHTTPRequestHandler):
    manifest_path = "/workspace/.agent/tools.json"

    def _json_response(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        decoded = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(decoded, dict):
            raise ValueError("JSON body must be an object")
        return decoded

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003 - BaseHTTPRequestHandler API
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/health":
            self._json_response({"status": "ok"})
            return

        if self.path == "/tools":
            tools = load_tools(self.manifest_path)
            self._json_response({"tools": tools})
            return

        self._json_response({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/invoke":
            self._json_response({"error": "not_found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            body = self._read_json_body()
            tool_name = str(body["tool"])
            params = body.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("params must be an object")

            result = run_tool(
                manifest_path=self.manifest_path,
                tool_name=tool_name,
                params=params,
                cwd=str(body.get("cwd", "/workspace")),
                timeout_seconds=int(body.get("timeout_seconds", 120)),
            )
            self._json_response(result)
        except KeyError as exc:
            self._json_response({"error": f"missing_field: {exc}"}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - server boundary
            self._json_response({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a tool invocation HTTP server")
    parser.add_argument("--manifest", required=True, help="Path to workspace tool manifest")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    ToolServer.manifest_path = args.manifest
    server = ThreadingHTTPServer((args.host, args.port), ToolServer)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
