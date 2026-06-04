from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def api_error(status_code: int, code: str, *, params: dict[str, Any] | None = None, message: str | None = None) -> HTTPException:
    detail: dict[str, Any] = {"code": code}
    if params:
        detail["params"] = params
    if message:
        detail["message"] = message
    return HTTPException(status_code=status_code, detail=detail)
