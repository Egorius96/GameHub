from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Реальный IP клиента за nginx.
    - X-Forwarded-For: берём первый (клиент)
    - X-Real-IP: fallback
    - request.client.host: последний fallback
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    xr = request.headers.get("x-real-ip", "").strip()
    if xr:
        return xr
    return (request.client.host if request.client else "") or "unknown"

