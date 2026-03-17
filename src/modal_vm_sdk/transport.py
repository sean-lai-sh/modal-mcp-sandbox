"""Modal function transport utilities."""

from __future__ import annotations

from typing import Any

import modal


class ModalFunctionTransport:
    def __init__(self, app_name: str) -> None:
        self._app_name = app_name
        self._cache: dict[str, Any] = {}

    def _fn(self, function_name: str):
        if function_name not in self._cache:
            self._cache[function_name] = modal.Function.from_name(
                self._app_name,
                function_name,
            )
        return self._cache[function_name]

    def call(self, function_name: str, **kwargs: Any) -> dict[str, Any]:
        fn = self._fn(function_name)
        return fn.remote(**kwargs)
