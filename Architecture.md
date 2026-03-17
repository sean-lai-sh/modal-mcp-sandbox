# Architecture

## System Goal
Provide a VM-like agent runtime over Modal primitives: persistent workspace filesystem, long-running execution context, MCP-first tool access, and lightweight session resume.

## High-Level Architecture
- Control plane:
  - Deployed Modal app functions manage session lifecycle and routing.
  - Owns `ensure_session(workspace_id, session_id?)`, endpoint discovery, and cleanup.
- Runtime plane:
  - A Modal sandbox hosts the MCP server and executes commands with `sandbox.exec`.
  - Agent/tool traffic hits MCP first, not a generic CLI surface.
- Persistence plane:
  - Named Modal Volume stores workspace files.
  - `modal.Dict` stores session metadata for reattach/recreate decisions.

## Why These Modal Primitives
- `modal.Sandbox`:
  - Chosen for long-running isolated process execution.
  - Provides direct `.exec` capability for MCP tool handlers.
- `modal.Volume`:
  - Chosen for durable workspace filesystem across sandbox restarts.
  - Allows recreate-on-death behavior while preserving project state.
- Tunnels:
  - Chosen to expose the in-sandbox MCP server as an external HTTP/SSE endpoint.
  - Keeps MCP as the primary runtime interface for agents.
- `modal.Dict`:
  - Chosen as a lightweight state store for `workspace_id/session_id -> sandbox` mapping.
  - Supports fast reattach checks and heartbeat-based expiry.

## Session Lifecycle
- Entry point:
  - `ensure_session(workspace_id, session_id?)`
- Behavior:
  - Reattach-if-alive:
    - If `session_id` maps to a live sandbox, return existing session metadata.
  - Recreate-if-dead:
    - If sandbox is gone, create a new sandbox and mount the same workspace volume.
    - Return updated session metadata.
- Runtime health:
  - Track heartbeat and `last_heartbeat` in `modal.Dict`.
  - Idle sessions are expired by a reaper process/function.

## MCP Tool Runtime Model
- Tool source:
  - Tool definitions live in the workspace volume (for example `/workspace/.agent/tools.json`).
- Load model:
  - MCP server loads definitions at startup (and can reload on session restart).
- Invocation path:
  - Agent -> MCP tool call -> tool definition resolution -> `sandbox.exec` command execution -> response.

## Tradeoffs and Risks
- Why no end-user CLI:
  - The product interface is MCP-first; CLI passthrough adds extra surface area without improving agent interoperability.
- Why light resume instead of full checkpointing:
  - Light resume is enough for MVP UX while keeping orchestration simple.
  - Full process snapshot/restore introduces major complexity and operational risk.
- Container-isolation-only implications:
  - V1 assumes sandbox isolation as the main boundary.
  - Raw command execution can still be risky if tool definitions are too permissive.

## Future Hardening
- Command policies:
  - Move from permissive execution to allowlisted/template-based policies.
- Argument validation:
  - Add typed schemas and strict command rendering for tools.
- Audit and tenancy controls:
  - Add structured execution logs, stronger access control, and stricter multi-tenant guarantees.
