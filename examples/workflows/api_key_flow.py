"""Workflow: register API-key MCP, sync tools, then run a synced tool."""

from __future__ import annotations

from pathlib import Path

from modal_vm_sdk import ModalVMClient


WORKSPACE_ID = "demo-workspace"
DEFINITION_PATH = Path(__file__).parent / "definitions" / "private_data.json"


def main() -> None:
    client = ModalVMClient(app_name="modal-vm-primitive")

    # Attach a Modal secret name if you want env-backed credentials in sandbox.
    session = client.ensure_session(
        workspace_id=WORKSPACE_ID,
        secret_names=["private-data-mcp-secret"],
    )

    client.register_mcp_definition(
        workspace_id=WORKSPACE_ID,
        session_id=session.session_id,
        definition_path=str(DEFINITION_PATH),
    )

    sync = client.sync_mcp_tools(workspace_id=WORKSPACE_ID, session_id=session.session_id)
    print("sync errors:", sync.errors)

    # Replace with a real tool name discovered from your private MCP endpoint.
    result = client.run_mcp_tool(
        workspace_id=WORKSPACE_ID,
        session_id=session.session_id,
        server_id="private_data",
        tool_name="health",
        args={},
    )
    print("exit:", result.exit_code)
    print(result.stdout)


if __name__ == "__main__":
    main()
