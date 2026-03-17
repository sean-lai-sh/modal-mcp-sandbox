"""Workflow: register no-auth MCP, sync tools, generate workspace skill."""

from __future__ import annotations

from pathlib import Path

from modal_vm_sdk import ModalVMClient


WORKSPACE_ID = "demo-workspace"
DEFINITION_PATH = Path(__file__).parent / "definitions" / "public_docs.json"


def main() -> None:
    client = ModalVMClient(app_name="modal-vm-primitive")
    session = client.ensure_session(workspace_id=WORKSPACE_ID)

    client.register_mcp_definition(
        workspace_id=WORKSPACE_ID,
        session_id=session.session_id,
        definition_path=str(DEFINITION_PATH),
    )

    sync = client.sync_mcp_tools(workspace_id=WORKSPACE_ID, session_id=session.session_id)
    skill = client.workspace_mcp_skill(workspace_id=WORKSPACE_ID, session_id=session.session_id)

    print("synced servers:", sync.servers)
    print("synced tools:", sync.tools)
    print("skill path:", skill.path)
    print(skill.text)


if __name__ == "__main__":
    main()
