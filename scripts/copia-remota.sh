#!/bin/bash
# Connects datos/ to a private git repository for the off-server copy (run as the user that owns datos/).
#
#   scripts/copia-remota.sh <carpeta de datos> <carpeta de ajustes> git@github.com:usuario/repo-privado.git
#
# It creates an SSH key used only for this (<ajustes>/copia/id_ed25519), prints its public half to add
# as a deploy key WITH write access on that repository, and then pushes. GitHub's host key is pinned,
# so the copy never trusts whatever answers on the network. Nothing secret goes in the copy: the
# bot token and the device key stay in <ajustes>.
set -euo pipefail
DATOS="${1:?Uso: copia-remota.sh <datos> <ajustes> <url ssh del repositorio>}"
CONFIG="${2:?Uso: copia-remota.sh <datos> <ajustes> <url ssh del repositorio>}"
REPO="${3:?Uso: copia-remota.sh <datos> <ajustes> <url ssh del repositorio>}"
DIR="$CONFIG/copia"
LLAVE="$DIR/id_ed25519"
# github.com, SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU (published by GitHub)
GITHUB_ED25519="github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"

[[ "$REPO" =~ ^git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git$ ]] \
  || { echo "Usa la dirección SSH del repositorio, así: git@github.com:usuario/mi-agenda-datos.git" >&2; exit 2; }
[[ -d "$DATOS/.git" ]] || { echo "$DATOS no es un repositorio git: instala la agenda primero" >&2; exit 1; }

mkdir -p "$DIR"
chmod 700 "$DIR"
[[ -f "$LLAVE" ]] || ssh-keygen -q -t ed25519 -N "" -C "copia-agenda@$(hostname)" -f "$LLAVE"
echo "$GITHUB_ED25519" > "$DIR/known_hosts"

git -C "$DATOS" remote remove origin 2>/dev/null || true
git -C "$DATOS" remote add origin "$REPO"
git -C "$DATOS" config core.sshCommand \
  "ssh -i $LLAVE -o IdentitiesOnly=yes -o UserKnownHostsFile=$DIR/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes"

if git -C "$DATOS" push -q -u origin HEAD 2>/dev/null; then
  echo "Copia conectada: tus datos ya están en $REPO"
  exit 0
fi
echo
echo "Falta un paso en GitHub. En el repositorio (privado) → Settings → Deploy keys → Add deploy key:"
echo "  · Title: copia de la agenda"
echo "  · Key: pega esta línea"
echo
cat "$LLAVE.pub"
echo
echo "  · Marca «Allow write access» y guarda. Después vuelve a ejecutar esto."
exit 3
