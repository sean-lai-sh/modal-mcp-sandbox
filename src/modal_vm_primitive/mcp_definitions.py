"""MCP definition schema helpers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class NormalizedAuth:
    type: str
    header: str = "Authorization"
    env_var: Optional[str] = None
    value: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "header": self.header,
        }
        if self.env_var:
            payload["env_var"] = self.env_var
        if self.value:
            payload["value"] = self.value
        return payload


@dataclass
class McpDefinition:
    id: str
    url: str
    auth: NormalizedAuth
    description: str = ""
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "url": self.url,
            "auth": self.auth.to_dict(),
        }
        if self.description:
            payload["description"] = self.description
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


def _normalize_auth(raw: dict[str, Any] | None) -> NormalizedAuth:
    if not raw:
        return NormalizedAuth(type="none")

    auth_type = str(raw.get("type", "none")).strip().lower()
    if auth_type == "none":
        return NormalizedAuth(type="none")

    if auth_type != "api_key":
        raise ValueError(f"Unsupported auth type: {auth_type}")

    header = str(raw.get("header", "Authorization")).strip() or "Authorization"
    env_var = raw.get("env_var")
    value = raw.get("value")

    if env_var is not None:
        env_var = str(env_var).strip() or None
    if value is not None:
        value = str(value).strip() or None

    if not env_var and not value:
        raise ValueError("api_key auth requires either env_var or value")

    return NormalizedAuth(
        type="api_key",
        header=header,
        env_var=env_var,
        value=value,
    )


def normalize_definition(raw: dict[str, Any]) -> McpDefinition:
    server_id = str(raw.get("id", "")).strip()
    url = str(raw.get("url", "")).strip()
    if not server_id:
        raise ValueError("Definition requires non-empty id")
    if not url:
        raise ValueError("Definition requires non-empty url")

    auth = _normalize_auth(raw.get("auth"))
    description = str(raw.get("description", "")).strip()

    metadata: dict[str, Any] | None = None
    if isinstance(raw.get("metadata"), dict):
        metadata = dict(raw["metadata"])

    return McpDefinition(
        id=server_id,
        url=url,
        auth=auth,
        description=description,
        metadata=metadata,
    )


def parse_definition_payload(definition_json: str) -> McpDefinition:
    try:
        payload = json.loads(definition_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid definition_json: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("definition_json must decode to an object")
    return normalize_definition(payload)


def parse_definitions_file_payload(definitions_json: str) -> list[McpDefinition]:
    try:
        payload = json.loads(definitions_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid definitions_json: {exc}") from exc

    if isinstance(payload, dict):
        raw_defs = payload.get("definitions", [])
    elif isinstance(payload, list):
        raw_defs = payload
    else:
        raise ValueError("definitions_json must decode to object or list")

    if not isinstance(raw_defs, list):
        raise ValueError("definitions field must be a list")

    out: list[McpDefinition] = []
    for item in raw_defs:
        if not isinstance(item, dict):
            raise ValueError("each definition must be an object")
        out.append(normalize_definition(item))
    return out


def merge_definitions(
    existing: list[dict[str, Any]],
    new_definition: McpDefinition,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    replaced = False
    for item in existing:
        if not isinstance(item, dict):
            continue
        if str(item.get("id", "")).strip() == new_definition.id:
            merged.append(new_definition.to_dict())
            replaced = True
        else:
            merged.append(item)

    if not replaced:
        merged.append(new_definition.to_dict())

    merged.sort(key=lambda x: str(x.get("id", "")))
    return merged


def wrap_definitions(definitions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at_epoch": int(time.time()),
        "definitions": definitions,
    }
