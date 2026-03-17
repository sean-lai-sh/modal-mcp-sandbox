from __future__ import annotations

import json

from modal_vm_primitive.tool_runner import run_tool


def test_run_tool_with_static_command(tmp_path):
    manifest = {
        "tools": [
            {"name": "say", "command": "echo hello"},
        ]
    }
    manifest_path = tmp_path / "tools.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_tool(
        manifest_path=str(manifest_path),
        tool_name="say",
        params={},
        cwd=str(tmp_path),
        timeout_seconds=30,
    )

    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "hello"


def test_run_tool_with_template_command(tmp_path):
    manifest = {
        "tools": [
            {"name": "echo_name", "command_template": "echo {name}"},
        ]
    }
    manifest_path = tmp_path / "tools.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_tool(
        manifest_path=str(manifest_path),
        tool_name="echo_name",
        params={"name": "modal"},
        cwd=str(tmp_path),
        timeout_seconds=30,
    )

    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "modal"
