"""Volume helpers for workspace and tooling state."""

from __future__ import annotations

import re

import modal

from .config import TOOLING_VOLUME_NAME, WORKSPACE_VOLUME_PREFIX

_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9-]+")


def _sanitize_workspace_id(workspace_id: str) -> str:
    cleaned = _SANITIZE_RE.sub("-", workspace_id).strip("-").lower()
    return cleaned or "default"


def workspace_volume_name(workspace_id: str) -> str:
    return f"{WORKSPACE_VOLUME_PREFIX}-{_sanitize_workspace_id(workspace_id)}"


def get_workspace_volume(workspace_id: str) -> modal.Volume:
    return modal.Volume.from_name(workspace_volume_name(workspace_id), create_if_missing=True)


def get_tooling_volume() -> modal.Volume:
    return modal.Volume.from_name(TOOLING_VOLUME_NAME, create_if_missing=True)


def safe_reload(volume: modal.Volume) -> None:
    reload_fn = getattr(volume, "reload", None)
    if callable(reload_fn):
        try:
            reload_fn()
        except RuntimeError as exc:
            # In control-plane functions the Volume object is not mounted directly.
            # Modal raises in that case; treat reload as best-effort.
            if "has no attached volumes" not in str(exc):
                raise


def safe_commit(volume: modal.Volume) -> None:
    commit_fn = getattr(volume, "commit", None)
    if callable(commit_fn):
        try:
            commit_fn()
        except RuntimeError as exc:
            # In control-plane functions the Volume object is not mounted directly.
            # Modal raises in that case; treat commit as best-effort.
            if "has no attached volumes" not in str(exc):
                raise
