from __future__ import annotations

import json

from modal_vm_primitive.mcp_definitions import (
    merge_definitions,
    parse_definition_payload,
)


def test_parse_definition_with_env_auth():
    raw = {
        "id": "private_data",
        "url": "https://private.example.com/sse",
        "auth": {
            "type": "api_key",
            "header": "Authorization",
            "env_var": "PRIVATE_DATA_API_KEY",
        },
    }

    parsed = parse_definition_payload(json.dumps(raw))

    assert parsed.id == "private_data"
    assert parsed.auth.type == "api_key"
    assert parsed.auth.env_var == "PRIVATE_DATA_API_KEY"


def test_merge_definitions_replaces_by_id():
    existing = [
        {"id": "public", "url": "https://a", "auth": {"type": "none"}},
        {"id": "private", "url": "https://b", "auth": {"type": "none"}},
    ]
    incoming = parse_definition_payload(
        json.dumps(
            {
                "id": "private",
                "url": "https://new",
                "auth": {"type": "none"},
            }
        )
    )

    merged = merge_definitions(existing=existing, new_definition=incoming)

    assert len(merged) == 2
    private = next(item for item in merged if item["id"] == "private")
    assert private["url"] == "https://new"
