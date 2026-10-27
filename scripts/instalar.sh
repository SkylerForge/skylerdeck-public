#!/bin/bash
# Installs SkylerDeck on this server as systemd services. Safe to run again.
#
#   sudo scripts/instalar.sh                install, or apply the settings again (asks a few questions the first time)
#   sudo scripts/instalar.sh actualizar     download the latest version from GitHub and install it
#   sudo scripts/instalar.sh telegram       set up the Telegram bot: token from @BotFather + link your chat
#   sudo scripts/instalar.sh cambiar-cuenta hand the bot to another Telegram account (it talks to one only)
#   sudo scripts/instalar.sh enlace         pairing link (and QR code) for a new device
#   sudo scripts/instalar.sh copia-remota git@github.com:usuario/repo.git
#                                           nightly copy of the data to your own private repository
#   sudo scripts/instalar.sh estado         what is running
#   sudo scripts/instalar.sh desinstalar    remove the services (keeps datos/ and the settings)
#
# The panel listens on 127.0.0.1 only. The way in is HTTPS through Tailscale (`tailscale serve`,
# inside your tailnet) or through your own reverse proxy with a domain, plus the device key.
# Answers can be given ahead as variables: AGENDA_NOMBRE, AGENDA_TZ, AGENDA_ACCESO (tailscale|dominio),
# AGENDA_DOMINIO, AGENDA_PUERTO, AGENDA_PUERTO_HTTPS, AGENDA_USUARIO.
set -euo pipefail

RAIZ="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
ACCION="${1:-instalar}"
# Root reads these answers back, so they live where only root can write.
AJUSTES=/etc/skylerdeck.env
# shellcheck disable=SC1090
[[ -f "$AJUSTES" ]] && source "$AJUSTES"
# The user chosen the first time sticks, even if a later sudo comes from another account.
USUARIO="${AGENDA_USUARIO:-${USUARIO:-${SUDO_USER:-root}}}"
UNIDADES=(skylerdeck.service skylerdeck-bot.service skylerdeck-avisos.timer skylerdeck-copia.timer)

fallo() { echo "✗ $*" >&2; exit 1; }
paso() { echo "→ $*"; }
como_usuario() { (cd "$RAIZ" && runuser -u "$USUARIO" -- env AGENDA_DATOS="$DATOS" AGENDA_CONFIG="$CONFIG" \
  AGENDA_CLAVE_FILE="$CONFIG/clave" AGENDA_URL="${URL:-}" AGENDA_TZ="${ZONA:-Europe/Madrid}" "$@"); }
version() { sed -n 's/^__version__ = "\(.*\)"/\1/p' "$RAIZ/agenda/__init__.py"; }
git_usuario() { runuser -u "$USUARIO" -- git -C "$RAIZ" "$@"; }
preguntar() {  # preguntar VARIABLE "Pregunta" "por defecto"
  local actual="${!1:-}"
  if [[ -n "$actual" ]]; then return; fi
  if [[ -t 0 ]]; then
    read -r -p "$2 [$3]: " actual
  fi
  printf -v "$1" '%s' "${actual:-$3}"
}

[[ $EUID -eq 0 ]] || fallo "Ejecútalo con sudo: sudo scripts/instalar.sh $*"
getent passwd "$USUARIO" >/dev/null || fallo "No existe el usuario $USUARIO"
CASA="$(getent passwd "$USUARIO" | cut -d: -f6)"
CONFIG="$CASA/.config/skylerdeck"
DATOS="$RAIZ/datos"
NOMBRE="${AGENDA_NOMBRE:-${NOMBRE:-}}"
ZONA="${AGENDA_TZ:-${ZONA:-}}"
ACCESO="${AGENDA_ACCESO:-${ACCESO:-}}"
DOMINIO="${AGENDA_DOMINIO:-${DOMINIO:-}}"
PUERTO="${AGENDA_PUERTO:-${PUERTO:-4850}}"
PUERTO_HTTPS="${AGENDA_PUERTO_HTTPS:-${PUERTO_HTTPS:-8443}}"
URL="${URL:-}"

case "$ACCION" in
  estado)
    echo "SkylerDeck $(version)"
    systemctl --no-pager status skylerdeck.service skylerdeck-bot.service 2>/dev/null | grep -E '●|Active:' || true
    systemctl --no-pager list-timers 'skylerdeck-*' | head -4
    [[ "$ACCESO" == "tailscale" ]] && tailscale serve status
    echo "Dirección: ${URL:-(sin instalar)}"
    exit 0 ;;
  enlace)
    [[ -n "$URL" ]] || fallo "Primero instala: sudo scripts/instalar.sh"
    echo "Este enlace empareja un dispositivo. Contiene la clave: no lo compartas ni lo pegues en chats."
    como_usuario "$RAIZ/.venv/bin/python" "$RAIZ/bin/agenda-panel" enlace
    exit 0 ;;
  telegram|cambiar-cuenta)
    [[ -n "$URL" ]] || fallo "Primero instala: sudo scripts/instalar.sh"
    # Telegram allows one reader per bot: the service must be stopped while we link a chat.
    systemctl stop skylerdeck-bot.service 2>/dev/null || true
    if [[ "$ACCION" == "telegram" ]]; then
      como_usuario "$RAIZ/.venv/bin/python" -m agenda.bot_servicio configurar || true
    else
      como_usuario "$RAIZ/.venv/bin/python" -m agenda.bot_servicio cambiar || true
    fi
    if grep -q '^AGENDA_TELEGRAM_CHAT=.' "$CONFIG/telegram.env" 2>/dev/null; then
      systemctl enable --now skylerdeck-bot.service >/dev/null
      systemctl restart skylerdeck-bot.service
      paso "Bot en marcha. Escríbele /ayuda desde Telegram."
    else
      echo "El bot no ha quedado vinculado. Vuelve a probar: sudo scripts/instalar.sh telegram"
    fi
    exit 0 ;;
  copia-remota)
    [[ -n "$URL" ]] || fallo "Primero instala: sudo scripts/instalar.sh"
    [[ -n "${2:-}" ]] || fallo "Falta el repositorio: sudo scripts/instalar.sh copia-remota git@github.com:usuario/mi-agenda-datos.git (crea antes un repositorio PRIVADO vacío)"
    como_usuario "$RAIZ/scripts/copia-remota.sh" "$DATOS" "$CONFIG" "$2"
    exit $? ;;
  actualizar)
    [[ -n "$URL" ]] || fallo "Primero instala: sudo scripts/instalar.sh"
    [[ -d "$RAIZ/.git" ]] || fallo "Esta carpeta no es un clon de git (¿la descargaste en .zip?). Mira «Actualizar» en docs/instalacion.md"
    command -v git >/dev/null || fallo "Falta git (apt install git)"
    [[ -z "$(git_usuario status --porcelain --untracked-files=no)" ]] \
      || fallo "Hay archivos del programa cambiados en $RAIZ (git status los enseña). Para volver al original: git -C $RAIZ checkout -- ."
    ANTES="$(version)"
    COMMIT="$(git_usuario rev-parse HEAD)"
    paso "Descargando la última versión"
    git_usuario pull -q --ff-only --tags || fallo "No se pudo descargar. Comprueba que el servidor llega a GitHub: git -C $RAIZ pull"
    if [[ "$(git_usuario rev-parse HEAD)" == "$COMMIT" ]]; then
      echo "Ya tienes la última versión (SkylerDeck $ANTES)."
      exit 0
    fi
    paso "SkylerDeck $ANTES → $(version). Novedades en CHANGELOG.md; cambios:"
    git_usuario log --no-merges --format='   · %s' "$COMMIT..HEAD" | head -15
    # The script itself may have changed: run the new one, which reuses the answers in $AJUSTES.
    exec "$RAIZ/scripts/instalar.sh" instalar ;;
  desinstalar)
    systemctl disable --now "${UNIDADES[@]}" 2>/dev/null || true
    for u in "${UNIDADES[@]}" skylerdeck-avisos.service skylerdeck-copia.service; do rm -f "/etc/systemd/system/$u"; done
    systemctl daemon-reload
    [[ "$ACCESO" == "tailscale" ]] && tailscale serve --https="$PUERTO_HTTPS" off 2>/dev/null || true
    rm -f "$AJUSTES"
    echo "Servicios quitados. Tus datos siguen en $DATOS y los ajustes del bot en $CONFIG."
    exit 0 ;;
  instalar) ;;
  *) sed -n '2,12p' "$0" | cut -c3-; exit 2 ;;
esac

# ---------- requirements ----------

command -v python3 >/dev/null || fallo "Falta Python 3.10 o superior (apt install python3 python3-venv)"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fallo "Hace falta Python 3.10 o superior (tienes $(python3 -V))"
command -v git >/dev/null || fallo "Falta git, que hace la copia diaria de tus datos (apt install git)"
runuser -u "$USUARIO" -- test -r "$RAIZ/agenda/servidor.py" || fallo "$USUARIO no puede leer $RAIZ: clona el repositorio en su carpeta"

if [[ ! -x "$RAIZ/.venv/bin/python" ]]; then
  paso "Creando el entorno de Python (.venv)"
  runuser -u "$USUARIO" -- python3 -m venv "$RAIZ/.venv" || fallo "No se pudo crear el entorno. En Debian/Ubuntu: apt install python3-venv"
fi
paso "Instalando dependencias"
runuser -u "$USUARIO" -- "$RAIZ/.venv/bin/pip" install -q --disable-pip-version-check -r "$RAIZ/requirements.txt"

# ---------- questions (only the first time) ----------

preguntar NOMBRE "¿Cómo te llamas? (para el saludo; vacío para no usar nombre)" "$USUARIO"
preguntar ZONA "Zona horaria" "Europe/Madrid"
"$RAIZ/.venv/bin/python" -c 'import sys, zoneinfo; zoneinfo.ZoneInfo(sys.argv[1])' "$ZONA" 2>/dev/null \
  || fallo "Zona horaria desconocida: $ZONA (ejemplos: Europe/Madrid, America/Mexico_City, America/Bogota)"
if [[ -z "$ACCESO" ]]; then
  if command -v tailscale >/dev/null && tailscale status >/dev/null 2>&1; then
    ACCESO=tailscale
  else
    echo
    echo "No veo Tailscale conectado en este servidor. Dos opciones:"
    echo "  1) Instalar Tailscale (recomendado: la agenda no queda abierta a internet). Ver docs/instalacion.md"
    echo "  2) Usar tu propio dominio con HTTPS detrás de un proxy (Caddy, nginx, Traefik…)"
    preguntar DOMINIO "Si vas a usar dominio propio, escríbelo (p. ej. agenda.midominio.com); vacío para salir" ""
    [[ -n "$DOMINIO" ]] || fallo "Instala Tailscale (curl -fsSL https://tailscale.com/install.sh | sh && tailscale up) y vuelve a ejecutar esto"
    ACCESO=dominio
  fi
fi

if [[ "$ACCESO" == "tailscale" ]]; then
  DNS="$(tailscale status --json | "$RAIZ/.venv/bin/python" -I -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
  [[ -n "$DNS" ]] || fallo "Tailscale no da nombre a este servidor: activa MagicDNS y HTTPS en el panel de Tailscale"
  tailscale status --json | "$RAIZ/.venv/bin/python" -I -c 'import json,sys; sys.exit(not json.load(sys.stdin).get("CertDomains"))' \
    || fallo "Falta activar HTTPS en Tailscale: entra en https://login.tailscale.com/admin/dns, pulsa «Enable HTTPS» y vuelve a ejecutar esto"
  URL="https://$DNS:$PUERTO_HTTPS"
  HOSTS=""
else
  [[ "$DOMINIO" =~ ^[A-Za-z0-9.-]+$ ]] || fallo "Dominio no válido: $DOMINIO"
  URL="https://$DOMINIO"
  HOSTS="$DOMINIO"
fi

mkdir -p "$DATOS" "$CONFIG"
chown "$USUARIO": "$DATOS" "$CONFIG" "$CASA/.config" 2>/dev/null || true
chmod 700 "$CONFIG"
cat > "$AJUSTES" <<EOF
# Respuestas de scripts/instalar.sh (se reutilizan al actualizar)
USUARIO=$USUARIO
NOMBRE=$(printf '%q' "$NOMBRE")
ZONA=$(printf '%q' "$ZONA")
ACCESO=$ACCESO
DOMINIO=$DOMINIO
PUERTO=$PUERTO
PUERTO_HTTPS=$PUERTO_HTTPS
URL=$URL
EOF
echo "$URL" > "$CONFIG/url"
chmod 644 "$AJUSTES"
chown "$USUARIO": "$CONFIG/url"
como_usuario "$RAIZ/.venv/bin/python" -I -c 'import sys; sys.path.insert(0, "."); from agenda import seguridad; seguridad.leer_o_crear_clave()'

# ---------- services ----------

paso "Instalando los servicios"
ENTORNO="Environment=\"AGENDA_DATOS=$DATOS\" \"AGENDA_CONFIG=$CONFIG\" \"AGENDA_URL=$URL\" \"AGENDA_TZ=$ZONA\" \"AGENDA_NOMBRE=$NOMBRE\""
ENDURECIDO="NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
CapabilityBoundingSet="

cat > /etc/systemd/system/skylerdeck.service <<EOF
[Unit]
Description=SkylerDeck (panel de tareas y notas)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USUARIO
WorkingDirectory=$RAIZ
$ENTORNO
Environment="AGENDA_HOST=127.0.0.1" "AGENDA_PUERTO=$PUERTO" "AGENDA_CLAVE_FILE=$CONFIG/clave" "AGENDA_HOSTS=$HOSTS"
ExecStart=$RAIZ/.venv/bin/python $RAIZ/bin/agenda-panel
Restart=on-failure
RestartSec=3
# Read-only system, writes only to the data and its key, no outgoing connections.
$ENDURECIDO
ReadWritePaths=$DATOS $CONFIG
IPAddressDeny=any
IPAddressAllow=localhost

[Install]
WantedBy=multi-user.target
EOF

# Reminders by Telegram, every minute. It reads the data and writes only its own state.
cat > /etc/systemd/system/skylerdeck-avisos.service <<EOF
[Unit]
Description=Avisos de SkylerDeck por Telegram
After=network-online.target

[Service]
Type=oneshot
User=$USUARIO
WorkingDirectory=$RAIZ
$ENTORNO
ExecStart=$RAIZ/.venv/bin/python -m agenda.avisos
$ENDURECIDO
ReadWritePaths=$CONFIG
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
EOF
cat > /etc/systemd/system/skylerdeck-avisos.timer <<EOF
[Unit]
Description=Revisa cada minuto si toca algún aviso de SkylerDeck

[Timer]
OnCalendar=*-*-* *:*:05
AccuracySec=1s

[Install]
WantedBy=timers.target
EOF

# The Telegram bot: reads what you write to it and turns it into tasks.
cat > /etc/systemd/system/skylerdeck-bot.service <<EOF
[Unit]
Description=Bot de Telegram de SkylerDeck
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USUARIO
WorkingDirectory=$RAIZ
$ENTORNO
ExecStart=$RAIZ/.venv/bin/python -m agenda.bot_servicio
Restart=always
RestartSec=10
$ENDURECIDO
ReadWritePaths=$DATOS $CONFIG
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
EOF

# Daily backup: datos/ is its own git repository with one commit per day (when something changed).
[[ -d "$DATOS/.git" ]] || runuser -u "$USUARIO" -- git -C "$DATOS" init -q
# Also for a datos/ restored from the remote copy, which comes without an author.
runuser -u "$USUARIO" -- git -C "$DATOS" config user.name >/dev/null || runuser -u "$USUARIO" -- git -C "$DATOS" config user.name "SkylerDeck"
runuser -u "$USUARIO" -- git -C "$DATOS" config user.email >/dev/null || runuser -u "$USUARIO" -- git -C "$DATOS" config user.email "agenda@localhost"
cat > /etc/systemd/system/skylerdeck-copia.service <<EOF
[Unit]
Description=Copia diaria de los datos de SkylerDeck (commit en git)

[Service]
Type=oneshot
User=$USUARIO
ExecStart=$RAIZ/scripts/copia-datos.sh $DATOS $CONFIG
EOF
cat > /etc/systemd/system/skylerdeck-copia.timer <<EOF
[Unit]
Description=Copia diaria de los datos de SkylerDeck

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now skylerdeck.service skylerdeck-copia.timer skylerdeck-avisos.timer >/dev/null
systemctl restart skylerdeck.service
BOT_LISTO=no
if grep -q '^AGENDA_TELEGRAM_CHAT=.' "$CONFIG/telegram.env" 2>/dev/null; then
  systemctl enable skylerdeck-bot.service >/dev/null
  systemctl restart skylerdeck-bot.service
  BOT_LISTO=sí
fi
runuser -u "$USUARIO" -- "$RAIZ/scripts/copia-datos.sh" "$DATOS" "$CONFIG" >/dev/null || true

if [[ "$ACCESO" == "tailscale" ]]; then
  # HTTPS inside the tailnet only (serve, never funnel).
  tailscale serve --bg --https="$PUERTO_HTTPS" "http://127.0.0.1:$PUERTO" >/dev/null \
    || fallo "tailscale serve no ha funcionado (hace falta Tailscale 1.52 o posterior: tailscale update). Los servicios ya están instalados: vuelve a ejecutar esto cuando lo arregles"
fi

echo
echo "✓ SkylerDeck instalado en $URL"
if [[ "$ACCESO" == "tailscale" ]]; then
  echo "  Solo se abre desde dispositivos de tu red de Tailscale."
else
  echo "  Falta que tu proxy envíe https://$DOMINIO a http://127.0.0.1:$PUERTO (ejemplos en docs/instalacion.md)."
fi
echo
echo "  Siguiente paso: emparejar tu móvil u ordenador con  sudo scripts/instalar.sh enlace"
if [[ "$BOT_LISTO" == "no" ]]; then
  echo "  Avisos y bot de Telegram:                       sudo scripts/instalar.sh telegram  (docs/bot-telegram.md)"
  if [[ -t 0 ]]; then
    read -r -p "¿Configuras ahora el bot de Telegram? [s/N]: " r
    [[ "$r" =~ ^[sS] ]] && exec "$0" telegram
  fi
fi
