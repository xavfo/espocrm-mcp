#!/usr/bin/env python3
"""Read-only probe of a live EspoCRM instance.

Checks, without writing anything, the assumptions `docs/DESARROLLO-7.5.6.md` makes
about the API: version, authentication, entity access, and whether metadata requires
an administrator (the open question behind P0-4).

Usage (PowerShell):

    $env:ESPO_URL = "https://crm.example.com"
    $env:ESPO_API_KEY = "..."
    python scripts/live_check.py

If `X-Api-Key` is rejected, set `ESPO_USERNAME` / `ESPO_PASSWORD` and rerun: the
script falls back to HTTP Basic, which is what EspoCRM uses for username+password
API access.
"""
from __future__ import annotations

import base64
import os
import sys

import httpx

TIMEOUT = 30.0


def _auth_headers() -> dict[str, str]:
    api_key = os.environ.get("ESPO_API_KEY", "").strip()
    if api_key:
        return {"X-Api-Key": api_key}
    username = os.environ.get("ESPO_USERNAME", "").strip()
    password = os.environ.get("ESPO_PASSWORD", "")
    if username and password:
        raw = f"{username}:{password}".encode()
        return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}
    print("Set ESPO_API_KEY, or ESPO_USERNAME + ESPO_PASSWORD.", file=sys.stderr)
    raise SystemExit(2)


def _probe(client: httpx.Client, label: str, path: str, expect: str) -> None:
    try:
        response = client.get(path)
    except httpx.HTTPError as exc:
        print(f"{label:<28} ERROR   {type(exc).__name__}: {exc}")
        return

    detail = ""
    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            if "version" in payload.get("settings", {}):
                detail = f"version={payload['settings']['version']}"
            elif path == "/Metadata":
                detail = f"{len(payload)} top-level keys"
            elif "list" in payload:
                detail = f"{len(payload['list'])} record(s)"
            elif "id" in payload:
                detail = f"user={payload.get('userName')} type={payload.get('type')}"
    else:
        detail = response.text[:160].replace("\n", " ")

    verdict = "OK     " if response.status_code < 400 else "FAIL   "
    print(f"{label:<28} {verdict} {response.status_code}  {detail}  (esperado: {expect})")


def main() -> int:
    base = os.environ.get("ESPO_URL", "").rstrip("/")
    if not base:
        print("ESPO_URL is not set.", file=sys.stderr)
        return 2

    headers = {"Content-Type": "application/json", **_auth_headers()}
    with httpx.Client(base_url=f"{base}/api/v1", headers=headers, timeout=TIMEOUT) as client:
        print(f"Instancia: {base}\n")
        _probe(client, "App/user", "/App/user", "200 + settings.version")
        _probe(client, "Metadata (sin key)", "/Metadata", "200 sin admin")
        _probe(client, "Metadata?key=scopes", "/Metadata?key=scopes", "403 sin admin")
        _probe(client, "Settings", "/Settings", "200")
        _probe(client, "Account (1 registro)", "/Account?maxSize=1", "200 si hay scope")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
