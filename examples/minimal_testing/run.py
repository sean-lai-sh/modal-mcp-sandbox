"""Minimal testing flow: ensure session, endpoint, simple invoke, stop."""

from __future__ import annotations

from modal_vm_sdk import ModalVMClient


WORKSPACE_ID = "demo-workspace"


def main() -> None:
    client = ModalVMClient(app_name="modal-vm-primitive")

    session = client.ensure_session(workspace_id=WORKSPACE_ID)
    endpoint = client.get_mcp_endpoint(
        workspace_id=WORKSPACE_ID,
        session_id=session.session_id,
    )
    result = client.invoke_tool(
        workspace_id=WORKSPACE_ID,
        session_id=session.session_id,
        tool_name="list_workspace",
        params={},
    )

    print("session:", session.session_id, "resumed:", session.resumed)
    print("mcp_url:", endpoint.url)
    print("invoke exit:", result.exit_code)
    print(result.stdout)

    stop = client.stop_session(workspace_id=WORKSPACE_ID, session_id=session.session_id)
    print("stopped:", stop.stopped)


if __name__ == "__main__":
    main()
