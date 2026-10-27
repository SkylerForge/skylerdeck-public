"""Second layer on top of Tailscale: device key in a cookie, Host and Origin checks, CSP.

- Only Host headers we expect are served (the Tailscale IP, *.ts.net, loopback and
  AGENDA_HOSTS): a DNS-rebinding page always sends its own domain.
- Every device pairs once with `/?clave=<key>`; the key goes into an HttpOnly cookie
  and leaves the URL. Without it, everything answers 401. There is no loopback
  exemption, because `tailscale serve` reaches us over loopback for any tailnet device.
- Writes need JSON, the `X-Agenda: 1` header and an Origin equal to the Host, so
  another site open in the same browser cannot change anything.
"""
from __future__ import annotations

import hmac
import ipaddress
import logging
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, redirect, request

COOKIE = "agenda_clave"
registro = logging.getLogger("skylerdeck")
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def clave_path() -> Path:
    return Path(os.environ.get("AGENDA_CLAVE_FILE", "~/.config/skylerdeck/clave")).expanduser()


def leer_o_crear_clave(path: Path | None = None) -> str:
    """Reads the device key, creating it (0600) the first time. Never log it."""
    path = path or clave_path()
    if path.exists():
        key = path.read_text().strip()
        if len(key) >= 32:
            return key
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key + "\n")
    return key


def host_permitido(host: str, extra: set[str]) -> bool:
    name = urlsplit(f"//{host}").hostname or ""
    if name in extra or name == "localhost" or name.endswith(".ts.net"):
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    tailnet = ipaddress.ip_network("100.64.0.0/10")
    return ip.is_loopback or ip in tailnet


def instalar(app: Flask, clave: str, hosts_extra: set[str], demo: bool = False) -> None:
    """`demo`: made-up data on 127.0.0.1 only (bin/agenda-panel demo). No device key, and it may be
    framed, so it opens in the editor's preview. Host and write checks still apply."""

    @app.before_request
    def _guardia():
        if not host_permitido(request.host, hosts_extra):
            return Response("Host no permitido", status=421, mimetype="text/plain")
        if demo:
            return _escritura()

        pairing = request.args.get("clave")
        if request.path == "/" and pairing is not None:
            if not hmac.compare_digest(pairing.encode(), clave.encode()):
                return Response("Clave incorrecta", status=401, mimetype="text/plain")
            resp = redirect("/", code=303)
            # Lax, not Strict: Strict drops the cookie when the panel is opened from a link in another app
            # (notes, messages, the camera), and the device looks unpaired. Writes stay protected by the
            # X-Agenda header and the Origin check. Secure behind tailscale serve (HTTPS on *.ts.net).
            https = (request.headers.get("X-Forwarded-Proto") == "https" or request.is_secure
                     or (urlsplit(f"//{request.host}").hostname or "").endswith(".ts.net"))
            resp.set_cookie(COOKIE, clave, max_age=60 * 60 * 24 * 400, httponly=True, samesite="Lax", secure=https)
            return resp

        cookie = request.cookies.get(COOKIE, "")
        if not hmac.compare_digest(cookie.encode(), clave.encode()):
            if request.path.startswith("/api/"):
                return jsonify(error="Este dispositivo no está emparejado"), 401
            return Response(_NO_EMPAREJADO, status=401, mimetype="text/html")
        return _escritura()

    def _escritura():
        if request.method in WRITE_METHODS:
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                return jsonify(error="Origen no permitido"), 403
            if request.headers.get("X-Agenda") != "1" or not request.is_json:
                return jsonify(error="Petición no válida"), 400
        return None

    @app.after_request
    def _registro(resp):
        # One line per request in the journal, to see who reaches the panel and what they got.
        # Never the query string (the pairing key travels there) nor cookies.
        if request.path != "/api/version" or resp.status_code >= 400:
            emparejado = "sí" if request.cookies.get(COOKIE) else "no"
            registro.info("%s %s %s · host=%s · desde=%s · cookie=%s%s", request.method, request.path, resp.status_code,
                          request.host, request.headers.get("Tailscale-User-Login") or request.headers.get("X-Forwarded-For") or request.remote_addr, emparejado,
                          " · trae clave" if "clave" in request.args else "")
        return resp

    @app.after_request
    def _cabeceras(resp):
        resp.headers["Content-Security-Policy"] = CSP.replace("frame-ancestors 'none'", "frame-ancestors *") if demo else CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if not demo:
            resp.headers["X-Frame-Options"] = "DENY"
        resp.headers.setdefault("Cache-Control", "no-store")
        return resp


_NO_EMPAREJADO = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SkylerDeck</title>
<body style="background:#0e110c;color:#e8ecdf;font:16px system-ui,sans-serif;padding:32px">
<p>Este dispositivo no está emparejado.</p>
<p style="color:#a9b19a">Ábrelo con el enlace de <code>sudo scripts/instalar.sh enlace</code>.</p></body></html>"""
