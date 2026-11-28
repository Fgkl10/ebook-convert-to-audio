"""Pairing token for /api/v1 (D-037).

The server listens on every interface, so anyone who can reach the PC (the local network, or a ZeroTier network)
could otherwise list, download, upload and delete books. A random token is made once and kept in the data folder;
the QR code on the PC carries it. Requests from the PC itself (loopback) need none, so the page on the PC just works.
A request passes with `Authorization: Bearer <token>`, or `?token=<token>` for URLs a browser loads by itself
(<audio src>, <img src>, download links), which can't carry a header.
"""
from __future__ import annotations

import ipaddress
import os
import secrets
from pathlib import Path

from fastapi import HTTPException, Request

from . import service

TOKEN_FILE = "server-token"
PAIR_MESSAGE = "Pair this device: scan the QR code shown on the PC"
_tokens: dict[Path, str] = {}  # data folder file -> token (tests point the data folder elsewhere)


def token_path() -> Path:
    return service.LIBRARY.parent / TOKEN_FILE


def token(new: bool = False) -> str:
    """The server's token, made on first use and kept in <data>/server-token. new=True replaces it, which unpairs
    every device."""
    path = token_path()
    if not new and path in _tokens:
        return _tokens[path]
    value = "" if new else (path.read_text(encoding="utf-8").strip() if path.exists() else "")
    if not value:
        value = secrets.token_urlsafe(24)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(value, encoding="utf-8")
        os.replace(tmp, path)
    _tokens[path] = value
    return value


def is_local(request: Request) -> bool:
    """A request from the PC itself. "testclient" is Starlette's TestClient, which stands in for the PC's browser."""
    host = request.client.host if request.client else ""
    if host in ("testclient", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def supplied_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return request.query_params.get("token", "")


def require_pairing(request: Request) -> None:
    """FastAPI dependency on every /api/v1 route."""
    if is_local(request):
        return
    given = supplied_token(request)
    if given and secrets.compare_digest(given.encode(), token().encode()):
        return
    raise HTTPException(status_code=401, detail=PAIR_MESSAGE)
