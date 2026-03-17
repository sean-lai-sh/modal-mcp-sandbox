"""In-sandbox tool runner for workspace-defined tool manifests."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def _load_manifest(path: Path) -> list[dict[str, Any]]:
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


def _find_tool(tools: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for tool in tools:
        if tool.get("name") == name:
            return tool
    raise KeyError(f"Tool '{name}' not found in manifest")


def _render_command(tool: dict[str, Any], params: dict[str, Any]) -> str:
    command = tool.get("command")
    template = tool.get("command_template")

    if command and isinstance(command, str):
        return command
    if template and isinstance(template, str):
        return template.format(**params)

    raise ValueError("Tool definition must include 'command' or 'command_template'")


def run_tool(
    manifest_path: str,
    tool_name: str,
    params: dict[str, Any],
    cwd: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.time()
    tools = _load_manifest(Path(manifest_path))
    tool = _find_tool(tools, tool_name)
    command = _render_command(tool, params)

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a workspace-defined tool")
    parser.add_argument("--manifest", required=True, help="Path to tool manifest JSON")
    parser.add_argument("--tool", required=True, help="Tool name")
    parser.add_argument("--params", default="{}", help="JSON object with tool params")
    parser.add_argument("--cwd", default="/workspace", help="Execution working directory")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Maximum command runtime",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        params = json.loads(args.params)
        if not isinstance(params, dict):
            raise ValueError("params must decode to a JSON object")

        result = run_tool(
            manifest_path=args.manifest,
            tool_name=args.tool,
            params=params,
            cwd=args.cwd,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - CLI error boundary
        result = {
            "tool": args.tool,
            "command": None,
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": 0,
        }

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
