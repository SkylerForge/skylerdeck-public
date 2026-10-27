"""Telegram: the bot's credentials and the few Bot API calls the agenda makes.

The bot lives in `<config>/telegram.env` (`AGENDA_TELEGRAM_TOKEN`, `AGENDA_TELEGRAM_CHAT`: its
owner, the one person it talks to), written by
`bin/agenda-bot configurar`. Telegram allows one reader per bot (a second one gets 409 Conflict),
so the agenda needs a bot of its own, not one another program already uses.
The token is never logged or printed.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API = "https://api.telegram.org"


@dataclass(frozen=True)
class Credenciales:
    token: str
    chats: tuple[str, ...]  # only the owner's: the bot talks to nobody else

    @property
    def chat(self) -> str:
        return self.chats[0]


class ErrorTelegram(RuntimeError):
    def __init__(self, texto: str, codigo: int = 0):
        super().__init__(texto)
        self.codigo = codigo


def env_path(config: Path) -> Path:
    return config / "telegram.env"


def leer_env(path: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    try:
        for linea in path.read_text("utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return valores


def _chats(texto: str) -> tuple[str, ...]:
    return tuple(c.strip() for c in texto.split(",") if c.strip())


def credenciales(config: Path) -> Credenciales | None:
    """The bot's token and linked chats, or None until both exist. Never printed."""
    valores = leer_env(env_path(config))
    token = valores.get("AGENDA_TELEGRAM_TOKEN", "")
    chats = _chats(os.environ.get("AGENDA_TELEGRAM_CHAT") or valores.get("AGENDA_TELEGRAM_CHAT", ""))
    return Credenciales(token, chats[:1]) if token and chats else None


def guardar(config: Path, token: str | None = None, chats: list[str] | None = None) -> None:
    """Writes telegram.env (0600), keeping whatever is not given."""
    valores = leer_env(env_path(config))
    if token is not None:
        valores["AGENDA_TELEGRAM_TOKEN"] = token.strip()
    if chats is not None:
        valores["AGENDA_TELEGRAM_CHAT"] = ",".join(dict.fromkeys(c.strip() for c in chats if c.strip()))
    config.mkdir(parents=True, exist_ok=True, mode=0o700)
    lineas = ["# Bot de Telegram de la agenda (bin/agenda-bot configurar). No lo compartas."]
    lineas += [f"{k}={v}" for k, v in valores.items()]
    path = env_path(config)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(lineas) + "\n")
    os.replace(tmp, path)


def sin_token(texto: str, token: str) -> str:
    return texto.replace(token, "***") if token else texto


def llamar(token: str, metodo: str, datos: dict | None = None, timeout: float = 20):
    """One Bot API call; returns its `result`. Errors come as ErrorTelegram, without the token."""
    req = urllib.request.Request(f"{API}/bot{token}/{metodo}", data=json.dumps(datos or {}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed host)
            respuesta = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        try:
            respuesta = json.loads(err.read().decode())
        except ValueError:
            raise ErrorTelegram(sin_token(f"Telegram respondió {err.code}", token), err.code) from None
    except Exception as err:  # noqa: BLE001 - network: never let the URL (with the token) out
        raise ErrorTelegram(sin_token(str(err), token)) from None
    if not respuesta.get("ok"):
        raise ErrorTelegram(sin_token(str(respuesta.get("description", "Telegram no aceptó la petición")), token),
                            int(respuesta.get("error_code") or 0))
    return respuesta.get("result")


def enviar(token: str, chat: str, texto: str, botones: list[list[dict]] | None = None) -> dict:
    datos = {"chat_id": chat, "text": texto[:4000], "disable_web_page_preview": True}
    if botones:
        datos["reply_markup"] = {"inline_keyboard": botones}
    return llamar(token, "sendMessage", datos)
