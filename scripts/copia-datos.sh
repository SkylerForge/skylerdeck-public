#!/bin/bash
# Daily backup of datos/: one git commit with whatever changed (nothing if nothing changed), then a
# push to its private remote when it has one (scripts/copia-remota.sh sets it up). The reminder
# settings (avisos.json, nothing secret) travel with the data in ajustes/. The result goes to
# <config>/copia-estado.json: Ajustes shows it and the reminders process warns by Telegram if it failed.
set -euo pipefail
DATOS="${1:?Uso: copia-datos.sh <carpeta de datos> [carpeta de ajustes]}"
CONFIG="${2:-}"  # without it (older units), the copy still happens, unreported
cd "$DATOS"

if [[ -n "$CONFIG" && -f "$CONFIG/avisos.json" ]]; then
  mkdir -p ajustes
  cp "$CONFIG/avisos.json" ajustes/avisos.json
fi
git add -A
if ! git diff --cached --quiet; then
  git commit -q -m "Copia del $(date '+%Y-%m-%d %H:%M')"
  echo "Copia guardada"
else
  echo "Sin cambios desde la última copia"
fi

anotar() {  # anotar ok|error [texto]
  [[ -n "$CONFIG" ]] || return 0
  python3 -I -c 'import json, sys, datetime
estado = {"cuando": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "ok": sys.argv[1] == "ok", "texto": sys.argv[2][:300]}
print(json.dumps(estado, ensure_ascii=False))' "$1" "${2:-}" > "$CONFIG/copia-estado.json.tmp"
  mv "$CONFIG/copia-estado.json.tmp" "$CONFIG/copia-estado.json"
}

# A brand-new agenda with nothing written yet has no commit to send.
if git remote get-url origin >/dev/null 2>&1 && git rev-parse -q --verify HEAD >/dev/null; then
  if salida=$(git push -q origin HEAD 2>&1); then
    anotar ok
    echo "Copia subida"
  else
    anotar error "$salida"
    echo "No se ha podido subir la copia: $salida" >&2
    exit 1
  fi
fi
