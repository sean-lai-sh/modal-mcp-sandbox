# Modal VM Wrapper (MCP-First)

## Project Purpose
Modal VM wrapper for agent sandboxes with MCP-first access.

This project packages a small control plane on Modal that creates VM-like sandbox sessions for agents, with persistent filesystem state and an MCP endpoint as the primary interface.

## Inspiration
Most agent workflows want something that feels like bare-metal: a stable filesystem, resumable runtime context, and programmable tools. This project uses Modal serverless primitives to get that experience without managing your own VM fleet.

## What It Does (MVP)
- Deploy a control-plane Modal app once.
- Create or reuse a workspace session.
- Execute tools through MCP, which runs commands via `sandbox.exec`.
- Persist workspace files in a named Modal Volume.
- Resume with an optional `session_id` when the sandbox is still alive, or recreate from the same volume when it is not.
- Register non-standard MCP definitions and sync their tools into a workspace MCP-CLI registry.
- Generate a compact workspace skill to expose MCP-CLI usage without context bloat.

## Core Concepts
- Control plane app vs runtime sandbox:
  - The deployed Modal app manages lifecycle (`ensure_session`, lookup, stop, reap).
  - The sandbox is the VM-like runtime where MCP and commands execute.
- Workspace volume vs tooling/bootstrap layer:
  - Workspace Volume stores durable project state.
  - Tooling/bootstrap layer starts MCP runtime and loads tool definitions.

## Quick Usage (Conceptual Flow)
1. Deploy control plane:
   - `PYTHONPATH=src python3 -m modal deploy -m modal_vm_primitive.app`
2. Ensure session:
   - SDK call `ensure_session(workspace_id, session_id=None)`
3. Get MCP URL:
   - SDK call `get_mcp_endpoint(workspace_id, session_id)`
4. Invoke tools:
   - MCP tool call maps to sandbox command execution through `sandbox.exec`
5. Stop or reap:
   - Explicit `stop_session(...)` or automatic idle reaping

### Python SDK Example
```python
from modal_vm_sdk import ModalVMClient

client = ModalVMClient(app_name="modal-vm-primitive")
session = client.ensure_session(workspace_id="demo-workspace")
endpoint = client.get_mcp_endpoint(
    workspace_id="demo-workspace",
    session_id=session.session_id,
)
result = client.invoke_tool(
    workspace_id="demo-workspace",
    session_id=session.session_id,
    tool_name="list_workspace",
)
print(endpoint.url)
print(result.stdout)
```

### MCP Definition Workflow Example
```python
from modal_vm_sdk import ModalVMClient

client = ModalVMClient(app_name="modal-vm-primitive")
session = client.ensure_session(
    workspace_id="demo-workspace",
    secret_names=["my-private-mcp-secret"],  # optional
)

client.register_mcp_definition(
    workspace_id="demo-workspace",
    session_id=session.session_id,
    definition={
        "id": "public_docs",
        "url": "https://example.com/sse",
        "auth": {"type": "none"},
    },
)

client.register_mcp_definition(
    workspace_id="demo-workspace",
    session_id=session.session_id,
    definition={
        "id": "private_data",
        "url": "https://private.example.com/sse",
        "auth": {
            "type": "api_key",
            "header": "Authorization",
            "env_var": "PRIVATE_DATA_API_KEY",  # preferred
            # "value": "sk-live-...",           # fallback for MVP
        },
    },
)

sync = client.sync_mcp_tools("demo-workspace", session_id=session.session_id)
print(sync.registry_path, sync.tools)

skill_text = client.base_mcp_skill()
workspace_skill = client.workspace_mcp_skill(
    "demo-workspace",
    session_id=session.session_id,
).text

result = client.run_mcp_tool(
    workspace_id="demo-workspace",
    session_id=session.session_id,
    server_id="public_docs",
    tool_name="search_docs",
    args={"query": "sandbox volume behavior"},
)
print(result.exit_code, result.stdout)
```

## MVP Constraints
- Security model is container-isolation-only in V1.
- No full process checkpoint/restore (light resume only).
- No general end-user CLI passthrough product surface.

## Roadmap
- Add stronger command policy and tool-level restrictions.
- Add argument schemas/sanitization for tool definitions.
- Add richer lifecycle controls beyond light resume.

## Documentation
For design rationale and primitive-level decisions, see [Architecture.md](Architecture.md).
