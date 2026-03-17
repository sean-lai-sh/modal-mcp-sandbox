# MCP2CLI Base Skill (Pinned Snapshot)

Use the MCP2CLI runtime to interact with MCP servers through a command-line bridge.

Core behavior:
- Keep MCP server definitions in one registry.
- Discover tools from servers before use.
- Run tools with structured JSON arguments.
- Keep auth out of prompts and source credentials from runtime configuration.

Guidelines:
- Prefer narrow, task-specific calls.
- List available tools before invoking unfamiliar servers.
- Surface stderr/exit codes when a call fails.
