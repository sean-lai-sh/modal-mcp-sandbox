"""Session state persistence backed by modal.Dict."""

from __future__ import annotations

import time
from typing import Any

import modal

from .config import SESSIONS_DICT_NAME

_WORKSPACES_KEY = "_workspaces"


class SessionStateStore:
    def __init__(self) -> None:
        self._store = modal.Dict.from_name(SESSIONS_DICT_NAME, create_if_missing=True)

    def _workspace_key(self, workspace_id: str) -> str:
        return f"workspace::{workspace_id}"

    def _session_key(self, session_id: str) -> str:
        return f"session::{session_id}"

    def _get(self, key: str, default: Any = None) -> Any:
        get_fn = getattr(self._store, "get", None)
        if callable(get_fn):
            return get_fn(key, default)

        try:
            return self._store[key]
        except KeyError:
            return default

    def _set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def _delete(self, key: str) -> None:
        try:
            del self._store[key]
        except KeyError:
            pass

    def _list_workspaces(self) -> list[str]:
        workspaces = self._get(_WORKSPACES_KEY, [])
        if isinstance(workspaces, list):
            return workspaces
        return []

    def _save_workspaces(self, workspaces: list[str]) -> None:
        self._set(_WORKSPACES_KEY, sorted(set(workspaces)))

    def get_by_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        return self._get(self._workspace_key(workspace_id), None)

    def get_by_session(self, session_id: str) -> dict[str, Any] | None:
        return self._get(self._session_key(session_id), None)

    def put_session(self, record: dict[str, Any]) -> None:
        workspace_id = record["workspace_id"]
        session_id = record["session_id"]

        existing = self.get_by_workspace(workspace_id)
        if existing and existing.get("session_id") != session_id:
            self._delete(self._session_key(existing["session_id"]))

        record["last_heartbeat_epoch"] = int(time.time())
        self._set(self._workspace_key(workspace_id), record)
        self._set(self._session_key(session_id), record)

        workspaces = self._list_workspaces()
        if workspace_id not in workspaces:
            workspaces.append(workspace_id)
            self._save_workspaces(workspaces)

    def touch_session(self, session_id: str) -> dict[str, Any] | None:
        record = self.get_by_session(session_id)
        if not record:
            return None
        record["last_heartbeat_epoch"] = int(time.time())
        self.put_session(record)
        return record

    def delete_session(self, session_id: str) -> None:
        record = self.get_by_session(session_id)
        if not record:
            return

        workspace_id = record["workspace_id"]
        self._delete(self._session_key(session_id))
        self._delete(self._workspace_key(workspace_id))

        workspaces = self._list_workspaces()
        if workspace_id in workspaces:
            workspaces.remove(workspace_id)
            self._save_workspaces(workspaces)

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions: list[dict[str, Any]] = []
        for workspace_id in self._list_workspaces():
            record = self.get_by_workspace(workspace_id)
            if record:
                sessions.append(record)
        return sessions
