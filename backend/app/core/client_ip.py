from __future__ import annotations

from starlette.requests import Request


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if xff:
        part = xff.split(",")[0].strip()
        return part[:64] if part else ""
    if request.client and request.client.host:
        return str(request.client.host)[:64]
    return ""
