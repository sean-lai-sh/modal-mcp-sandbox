"""Run a simple Python command through workspace tool execution."""

from __future__ import annotations

import json

from modal_vm_sdk import ModalVMClient


WORKSPACE_ID = "demo-workspace"


def main() -> None:
    client = ModalVMClient(app_name="modal-vm-primitive")
    session = client.ensure_session(workspace_id=WORKSPACE_ID)

    # Register a small command template tool and invoke it.
    client.register_mcp_definition(
        workspace_id=WORKSPACE_ID,
        session_id=session.session_id,
        definition={
            "id": "public_docs",
            "url": "https://example.com/sse",
            "auth": {"type": "none"},
            "metadata": {"note": "placeholder endpoint for example structure"},
        },
    )

    result = client.invoke_tool(
        workspace_id=WORKSPACE_ID,
        session_id=session.session_id,
        tool_name="pwd",
        params={},
    )

    print(json.dumps({"exit_code": result.exit_code, "stdout": result.stdout}, indent=2))


if __name__ == "__main__":
    main()
