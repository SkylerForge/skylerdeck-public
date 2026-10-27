"""Runs the agenda's Telegram bot and sets it up (`bin/agenda-bot`).

    bin/agenda-bot              serve: long polling, what the systemd unit runs
    bin/agenda-bot configurar   ask for the token BotFather gave you, check it, then link your chat
    bin/agenda-bot vincular     link its owner, when none is linked: open the link or send the code
    bin/agenda-bot cambiar      hand the bot to another Telegram account (the old one is forgotten)
    bin/agenda-bot probar       send a test message to the linked chat

The bot talks only to its owner, the first account linked; nobody can add a second one.
Telegram allows one reader per bot: while the service runs, linking cannot (409), so stop it
first (`systemctl stop skylerdeck-bot`); `scripts/instalar.sh telegram` does it for you. The token is read from telegram.env and never printed.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

from . import telegram
from .avisos import config_dir
from .bot import Bot
from .bot_textos import COMANDOS
from .escritura import write_atomic
from .fichas import Fichas
from .proyectos import datos_dir

TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
SONDEO_S = 50
VINCULAR_MIN = 10
SERVICIO = "skylerdeck-bot"
USO = """Uso:
  bin/agenda-bot              pone el bot en marcha (lo hace el servicio)
  bin/agenda-bot configurar   guarda el token de @BotFather y vincula tu chat
  bin/agenda-bot cambiar      el bot pasa a ser de otra cuenta de Telegram (con el servicio parado)
  bin/agenda-bot probar       envía un mensaje de prueba"""


def log(texto: str) -> None:
    print(texto, flush=True)


def _estado_path(config: Path) -> Path:
    return config / "bot-estado.json"


def leer_offset(config: Path) -> int | None:
    try:
        return int(json.loads(_estado_path(config).read_text("utf-8"))["offset"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def guardar_offset(config: Path, offset: int) -> None:
    write_atomic(_estado_path(config), json.dumps({"offset": offset}))


def _url(config: Path) -> str:
    try:
        return os.environ.get("AGENDA_URL") or (config / "url").read_text().strip()
    except OSError:
        return ""


# ---------- serve ----------

def servir(config: Path) -> int:
    cred = telegram.credenciales(config)
    if not cred:
        sys.exit("Falta el bot de la agenda o su dueño: sudo scripts/instalar.sh telegram")

    def api(metodo, datos):
        return telegram.llamar(cred.token, metodo, datos)

    bot = Bot(Fichas(datos_dir()), cred.chats, api, _url(config))
    try:
        yo = api("getMe", {})
        api("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in COMANDOS]})
        log(f"Bot @{yo.get('username')} en marcha: solo habla con su dueño")
    except telegram.ErrorTelegram as err:
        log(f"Aviso al arrancar: {err}")

    offset, pausa = leer_offset(config), 1
    while True:
        try:
            datos = {"timeout": SONDEO_S, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                datos["offset"] = offset
            updates = telegram.llamar(cred.token, "getUpdates", datos, timeout=SONDEO_S + 20)
        except telegram.ErrorTelegram as err:
            if err.codigo == 409:
                log("Otro programa está leyendo los mensajes de este bot (¿otra copia, u otro programa con el mismo token?). Reintento en 30 s")
                time.sleep(30)
            elif err.codigo == 401:
                log("Telegram no acepta el token. Vuelve a configurarlo: sudo scripts/instalar.sh telegram")
                time.sleep(300)
            else:
                log(f"Sin conexión con Telegram ({err}). Reintento en {pausa} s")
                time.sleep(pausa)
                pausa = min(pausa * 2, 60)
            continue
        pausa = 1
        for u in updates or []:
            offset = int(u["update_id"]) + 1
            try:
                hecho = bot.atender(u)
            except Exception as err:  # noqa: BLE001 - one bad update never stops the bot
                hecho = f"fallo inesperado: {type(err).__name__}"
                chat = ((u.get("message") or {}).get("chat") or {}).get("id")
                if str(chat) in bot.chats:
                    try:
                        api("sendMessage", {"chat_id": chat, "text": "Algo ha fallado al hacerlo. Míralo en el panel."})
                    except telegram.ErrorTelegram:
                        pass
            log(hecho if hecho is not None else "Mensaje ignorado: viene de un chat no autorizado")
            guardar_offset(config, offset)


# ---------- setup ----------

def configurar(config: Path) -> int:
    print("Pega el token que te dio @BotFather (no se ve mientras escribes) y pulsa Intro.")
    token = (os.environ.get("AGENDA_TELEGRAM_TOKEN") or getpass.getpass("Token: ")).strip()
    if not TOKEN_RE.match(token):
        sys.exit("Eso no parece un token de bot. Tiene esta forma: 123456789:AAH…, todo seguido.")
    try:
        yo = telegram.llamar(token, "getMe")
    except telegram.ErrorTelegram as err:
        sys.exit(f"Telegram no acepta ese token: {err}")
    telegram.guardar(config, token=token)
    print(f"Bot @{yo.get('username')} ({yo.get('first_name')}) guardado en {telegram.env_path(config)}")
    if telegram.credenciales(config):
        print("El bot ya tiene dueño y solo habla con esa cuenta. Para pasárselo a otra: sudo scripts/instalar.sh cambiar-cuenta")
        return 0
    return vincular(config)


def vincular(config: Path, cambiar: bool = False) -> int:
    valores = telegram.leer_env(telegram.env_path(config))
    token = valores.get("AGENDA_TELEGRAM_TOKEN")
    if not token:
        sys.exit("Primero el token: bin/agenda-bot configurar")
    if valores.get("AGENDA_TELEGRAM_CHAT", "").strip() and not cambiar:
        sys.exit("El bot ya tiene dueño y solo habla con esa cuenta. Para pasárselo a otra: sudo scripts/instalar.sh cambiar-cuenta")
    if cambiar:
        print("El bot dejará de hablar con su cuenta actual y pasará a ser de la que envíe el código.")
    try:
        yo = telegram.llamar(token, "getMe")
    except telegram.ErrorTelegram as err:
        sys.exit(f"Telegram no acepta el token: {err}")
    codigo = f"{secrets.randbelow(10**6):06d}"
    enlace = f"https://t.me/{yo['username']}?start={codigo}"
    print(f"\nAbre este enlace en el móvil y pulsa «Iniciar»:\n\n  {enlace}\n")
    try:
        import segno

        print("o escanea este código con la cámara:\n")
        segno.make(enlace, error="m").terminal(compact=True)
    except ImportError:
        pass
    print(f"\nTambién vale escribirle a @{yo['username']} este código: {codigo}")
    print(f"Espero {VINCULAR_MIN} minutos…", flush=True)

    fin = time.monotonic() + VINCULAR_MIN * 60
    offset = None
    while time.monotonic() < fin:
        datos = {"timeout": 25, "allowed_updates": ["message"]}
        if offset is not None:
            datos["offset"] = offset
        try:
            updates = telegram.llamar(token, "getUpdates", datos, timeout=45)
        except telegram.ErrorTelegram as err:
            if err.codigo == 409:
                sys.exit(f"El bot ya está en marcha y Telegram solo deja un lector. Páralo antes: systemctl stop {SERVICIO}")
            print(f"Sin conexión con Telegram ({err}); sigo intentándolo")
            time.sleep(5)
            continue
        for u in updates or []:
            offset = int(u["update_id"]) + 1
            msg = u.get("message") or {}
            palabras = (msg.get("text") or "").split()
            if (msg.get("chat") or {}).get("type") == "private" and codigo in palabras[:2]:
                chat = str(msg["chat"]["id"])
                telegram.guardar(config, chats=[chat])  # the owner: one account, never a list
                telegram.llamar(token, "getUpdates", {"offset": offset, "timeout": 0})  # the code is not a task
                guardar_offset(config, offset)
                quien = (msg.get("from") or {}).get("first_name") or "tú"
                telegram.enviar(token, chat, f"¡Hola, {quien}! Ya estás vinculado: te avisaré aquí de tus tareas "
                                             "y lo que me escribas lo apunto en la agenda. Escribe /ayuda para ver cómo.")
                print(f"Vinculado el chat de {quien}.")
                return 0
    print(f"No ha llegado el código. Vuelve a probar: bin/agenda-bot {'cambiar' if cambiar else 'vincular'}")
    return 1


def probar(config: Path) -> int:
    cred = telegram.credenciales(config)
    if not cred:
        sys.exit("Falta el bot de la agenda o su dueño: sudo scripts/instalar.sh telegram")
    try:
        telegram.enviar(cred.token, cred.chat, "Prueba del bot de la agenda: funciona.")
    except telegram.ErrorTelegram as err:
        sys.exit(f"No ha salido: {err}")
    print("Mensaje enviado.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    acciones = {"configurar": configurar, "vincular": vincular, "probar": probar,
                "cambiar": lambda config: vincular(config, cambiar=True)}
    if not argv:
        return servir(config_dir())
    if len(argv) == 1 and argv[0] in acciones:
        return acciones[argv[0]](config_dir())
    sys.exit(USO)


if __name__ == "__main__":
    sys.exit(main())
