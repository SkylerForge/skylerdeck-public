# AGENTS.md

SkylerDeck: personal tasks and notes, Todoist-style, with Obsidian-style linked notes. The Markdown files in `datos/` are the source of truth; the panel, the CLI and the Telegram bot sit on top of them. User docs: `README.md`, `docs/instalacion.md`, `docs/bot-telegram.md`.

## Commands

- `.venv/bin/python -m unittest discover -s tests -t .`: tests. Run them after any change.
- `bin/agenda --help`: the CLI. Agents sign their changes with `--quien <nombre>` and can ask for `--json`.
- `bin/agenda anadir --probar "texto"`: shows what the quick-add understands without creating anything.
- `bin/agenda notas lista|ver|nueva|anadir|diario|menciones`: notes for agents (`agenda notas diario --texto "…"` appends to today's note).
- `bin/agenda-panel`: serves the panel on the Tailscale IP (`AGENDA_HOST`, default `tailscale ip -4`; `AGENDA_PUERTO`, default 4850). It re-runs itself with `.venv`.
- `bin/agenda-bot configurar|vincular|cambiar|probar`: the Telegram bot's setup. The bot talks only to its owner, the first account linked; `cambiar` hands it to another account, nothing adds a second one (`sudo scripts/instalar.sh telegram` wraps it with the right user and paths).
- `bin/agenda-panel enlace`: prints the pairing link for a new device. It contains the device key: never print it into logs or chats.

## Running on a server

- `sudo scripts/instalar.sh` creates `.venv`, asks for the name and time zone (answers in `/etc/skylerdeck.env`, reused on updates) and installs the systemd units, all running as the user who ran sudo: `skylerdeck` (the panel), `skylerdeck-avisos.timer` (reminders, every minute), `skylerdeck-bot` (enabled once the bot is linked) and `skylerdeck-copia.timer` (a git commit of `datos/` at 03:30, `scripts/copia-datos.sh`). Subcommands: `actualizar` (git pull as that user, refuses with local edits or without `.git`, then re-runs the new installer), `telegram`, `cambiar-cuenta`, `enlace`, `copia-remota`, `estado`, `desinstalar`. The install user is saved in `/etc/skylerdeck.env` too, so later runs keep it.
- Version: `agenda.__version__`, shown at the end of Ajustes (`/api/avisos` → `version`) and by `estado`. Bump it with a new entry in `CHANGELOG.md`, then tag `vX.Y.Z` and make a GitHub release.
- Access: `tailscale serve --https=8443` inside the tailnet (never `funnel`), or `AGENDA_ACCESO=dominio AGENDA_DOMINIO=…` behind the user's own HTTPS proxy (the domain goes into `AGENDA_HOSTS`). The panel always listens on 127.0.0.1:4850 only.
- The units are hardened: read-only system, writes only to `datos/` and `~/.config/skylerdeck`. The panel has no outgoing network (`IPAddressDeny=any`); only the reminders and the bot reach Telegram.
- After changing `agenda/` or `bin/`, restart: `systemctl restart skylerdeck skylerdeck-bot`. Changes in `static/` reach open pages by themselves.
- Access log: `journalctl -u skylerdeck` shows one line per request (path, status, Tailscale login, whether the device cookie came). It never logs the query string or cookies, because the pairing key travels there.
- Pairing a device: `sudo scripts/instalar.sh enlace` prints the link and a QR code. The device cookie is `SameSite=Lax`: with Strict, opening the panel from a link in another app looked unpaired.
- If a device reaches the internet but nothing in the tailnet, look for another VPN with a kill switch on that device (NordVPN and similar block Tailscale while connected).
- Deleted notes go to `datos/papelera/notas/` (the page offers «Deshacer»; older ones are restored by hand).

## Never touch the real data while testing

Point `AGENDA_DATOS` at a scratch folder for any CLI write you make for testing: `AGENDA_DATOS="$SCRATCH/datos" bin/agenda …`. Without it, the CLI writes to the real `datos/`.

For the UI, run a second panel on made-up data with its own key, so nothing real is on screen and no real device key is involved:

```bash
.venv/bin/python scripts/demo.py "$SCRATCH/demo/datos"
AGENDA_DATOS="$SCRATCH/demo/datos" AGENDA_CLAVE_FILE="$SCRATCH/demo/clave" AGENDA_PUERTO=4851 bin/agenda-panel
```

## Layout

- `agenda/fichas.py`: card format, states, validation, subtasks and recurring tasks, and every file operation on tasks. The CLI, server and bot go through it; never write cards any other way.
- `agenda/proyectos.py`: projects (`datos/proyectos/<slug>.md`). The slug never changes; renaming only changes `nombre`.
- `agenda/frontmatter.py`: the flat YAML header, `## sections` of the body, and the version hash used for 409 conflicts.
- `agenda/quickadd.py`: the quick-add parser (rules only, no LLM: the owner chose rules over an LLM for privacy and cost). It reads spoken Spanish (`a las cinco y media`, `menos cuarto`, `esta tarde`, `dentro de 2 horas`, `el lunes 2`, `durará una hora`) and drops openings like «Recuérdame que» / «Tengo que» from the title. When it guesses (5 → 17:00, «por la tarde» → 17:00) it says so in `avisos`; the bot then offers «Era por la mañana». It returns spans so the UI can highlight what it understood.
- `agenda/horas.py`: the time rules quick-add uses (`a las cinco y media`, `esta tarde`, `de 9 a 11`, `dentro de 2 horas`, durations); quickadd.py decides the order they are tried in.
- `agenda/recurrencia.py`: `cada lunes`, `los martes`, `cada 3 días`, `cada quince días`, `cada 2 semanas los lunes`, `los fines de semana`, `semanalmente`… The card stores the canonical text, so one parser reads both. A rule only comes from those words: «el lunes y el miércoles» (singular) are one-off dates, one task each (`quickadd.Resultado.otras_fechas`; the bot, the panel and the CLI create them). Quick-add also reads the end (`hasta el 15/12`, `hasta diciembre`, `durante 2 meses`) and the start (`desde…`, `a partir del…`); a rule never starts on a time already gone today.
- `agenda/vistas.py`: what Hoy, Próximo and Bandeja show, and in which order.
- Inicio opens as a month (`/api/mes?mes=AAAA-MM`, `semana.construir_mes`: whole weeks around the month, same rules as the week) with the chosen day's tasks beside it; «Mes · Semana» switches per device (`static/js/mes.js`, `inicio.js`).
- `agenda/semana.py`: Inicio's weekly sheet (`/api/semana?desde=`): each day of one week with its tasks, the projected repeats of recurring tasks (not real cards: they cannot be ticked), the reviews of waiting tasks, and what was done that day; overdue tasks from earlier weeks go apart.
- `agenda/fechas.py`: dates in the agenda's time zone (`AGENDA_TZ`, Europe/Madrid by default) and their Spanish names. The page's clock and greeting name come from `/api/panel` (`zona`, `nombre` from `AGENDA_NOMBRE`).
- `agenda/cli.py` + `bin/agenda`: the CLI.
- `agenda/servidor.py`: Flask API (served by waitress). `agenda/panel.py` builds the one payload the page needs and the data fingerprint the page polls (`/api/version`, every 3 s; a change in `static/` reloads open pages).
- `agenda/seguridad.py`: Host allow-list (Tailscale IP range, `*.ts.net`, loopback, `AGENDA_HOSTS`) against DNS rebinding; device key in an HttpOnly cookie (`/?clave=` pairs, file `~/.config/skylerdeck/clave`, no loopback exemption because `tailscale serve` arrives over loopback); writes need JSON + `X-Agenda: 1` + same Origin; strict CSP.
- `static/`: the page, vanilla JS modules with no build step. `app.js` (routes, filter, polling, complete with undo, week shown on Inicio), `inicio.js` (weekly sheet: Monday–Friday a column each, Saturday and Sunday sharing the last one), `tareas.js` (the Tareas module: its sidebar, or a strip of chips on the phone, with Hoy, Próximo, Bandeja and the projects as list or board). The rail holds modules only (Inicio, Tareas, Notas) plus search; lists inside a module never go in the rail, `ficha.js` (task sheet: saves with the card version; an outside change shows a banner instead of overwriting unsaved edits), `quickadd.js` (highlights the server parser's spans), `fila.js`, `dom.js` (builds DOM from text nodes only, never `innerHTML`), `api.js`.
- `agenda/notas.py`: notes (`datos/notas/<slug>.md`: flat header with `titulo`, `tipo` nota|diario, `proyecto`, dates; Markdown body). The slug never changes. A daily note's slug is its date and its file only appears once something is written.
- `agenda/enlaces.py`: `[[links]]` (task id, note title or slug, date, project name or slug; `[[target|text]]`), backlinks («Mencionado en»), `@tags` shared by tasks (`etiquetas`) and notes (written in the text), `[[` suggestions, Ctrl+K search, and rewriting every link when a note or project is renamed. Computed from the files on each call.
- Touch and mouse editing: `static/js/deslizar.js` (swipe a row or an Inicio item with a finger: right = done, left = tomorrow; pointerType touch/pen only, `touch-action: pan-y`), `static/js/arrastrar.js` (drag an Inicio item onto a week day or a month cell with a fine pointer; `ctx.moverA`). Both end with «Deshacer». The task sheet has quick dates (Hoy, Mañana, El lunes, Sin fecha) and, for recurring tasks, «Saltar esta vez» (`POST /api/tareas/<id>/saltar`, `fichas.saltar`).
- `static/js/kiosco.js`: `#/kiosco`, Inicio for a wall tablet: no rail, bigger, a big clock, Wake Lock, full screen after the first touch. Still the web page, not an app (the owner does not want an installable app).
- `static/js/notas.js` (Notas module and its editor: autosave with the note's version; a refresh never replaces text being edited or in conflict), `editor.js` (Markdown editor with `[[` autocomplete, shared with the task context), `markdown.js` (renderer that builds DOM, never `innerHTML`), `buscar.js` (Ctrl+K).
- `agenda/avisos.py`: reminders by Telegram: a heads-up before each task with a time today and a morning summary. Run every minute by `skylerdeck-avisos.timer`. Settings in `~/.config/skylerdeck/avisos.json` (edited from Ajustes in the panel); each reminder is sent once (`avisos-estado.json`); late ones are skipped. A Telegram button opens `#/t/T-012`, which the page turns into that task's sheet. Also, off by default: an evening summary of tomorrow (`noche`, `hora_noche`) and a Sunday review (`repaso`, `hora_repaso`). Reminder buttons: «✓ Hecha», «+10 min», «+1 h» (`avisos.posponer` → `avisos-pospuestos.json`, sent once by the next run), «→ Mañana».
- `agenda/telegram.py`: the bot's credentials and Bot API calls. The bot is in `~/.config/skylerdeck/telegram.env` (`AGENDA_TELEGRAM_TOKEN`, `AGENDA_TELEGRAM_CHAT`: comma-separated, reminders go to the first; 0600, never logged).
- `agenda/bot.py`: the bot. Each line of a message becomes a task through the quick-add parser; `/hoy`, `/manana`, `/semana`, `/bandeja`, `/hecha`, `/posponer`, `/ver`, `/nota` (today's note), `/buscar`, `/probar`, `/proyectos`; buttons «✓ Hecha» and «→ Mañana». Only the linked chats; others are ignored silently. `agenda/bot_servicio.py` + `bin/agenda-bot`: the long-polling loop (`skylerdeck-bot.service`) and `configurar` / `vincular` / `probar`.
- `agenda/bot_textos.py`: what the bot says (lists, a task, search, `/probar`, projects, help, choice buttons) as the `Textos` mixin of `Bot`; everything that changes a task stays in bot.py.
- `agenda/bot_frases.py` (`Frases` mixin): plain messages about existing tasks: «ya he ido al dentista» (done, with «Deshacer»), «hoy no hay gimnasio» / «sáltate…» / «no voy al…» (skip the NEXT repeat only, `fichas.saltar`), «pasa/cambia/mueve X al jueves / a las 8» (asks first, `pos:` button, «Deshacer»), «ponle prioridad 1 al…», «añade a la compra: leche, pan» (subtasks; the «:» form creates the list). Each acts only when `encontrar` finds a task; otherwise the message is a new task. Taking off a recurring task asks «solo esta vez o todas».
- `agenda/encontrar.py`: names tasks by a few of their words (every word must start a title word; a date in the words narrows the search; «cita»/«evento» only count alone) or by number. The bot uses it for `/hecha`, `/posponer`, `/ver` and `/borrar` (aliases `/eliminar`, `/quitar`, `/cancelar`): one match acts, several give a button each. «Borra la cita del dentista» as a plain message always asks first and also offers «apúntalo como tarea nueva»; with no match an order («borra…») says so and adds nothing (a button adds it), while the infinitive («Cancelar el seguro») is a new task. Several matches also get «🗑 Todas» (`varias:<token>`, undone by `volver:<token>`); «las dos», «todas», «ambas» are not title words. Several lines under a bare «elimina», or lines with task numbers pasted from the bot's answers, take those tasks off (`Frases._frase_lineas`); other multi-line messages are new tasks, each sent with its own buttons up to `MAX_SUELTAS` (4), a list with «ver» buttons and «🗑 Quitar estas N» above that. Taking a task off = estado `soltada` (the panel's «Soltar tarea»), with «↩ Deshacer».
- One reader per Telegram bot: a token another program already polls gives 409 Conflict, so the agenda needs its own bot. Linking cannot run while the service runs (`scripts/instalar.sh telegram|cambiar-cuenta` stop it first).
- `static/js/ajustes.js`: the Ajustes page (rail gear): reminders on/off, minutes ahead, summary time, test message.
- Renaming a project moves it to the slug of its new name (`enlaces.renombrar_proyecto`): cards, notes and links follow, and the old name is free again.
- `scripts/demo.py`: made-up data for screenshots and UI tests.

## The card

```markdown
---
id: T-007
titulo: "Entregar la propuesta"
estado: pendiente
ambito: laboral
proyecto: clientes
prioridad: p1
etiquetas: ["entrega"]
fecha: 2026-10-26
hora: "14:00"
caso: "PRES-2026-031"
creada: 2026-10-26
actualizada: "2026-10-26 08:01"
---

## Contexto

## Subtareas

- [x] Textos
- [ ] Revisión

## Bitácora

- 2026-10-26 08:01 · Yo: Creada en Pendiente
```

- `estado`: `pendiente`, `en-curso`, `esperando` (with `esperando_a` and `revisar`), `mas-adelante` (with `revisar`), `hecha`, `soltada`.
- `fecha`, `hora` (needs `fecha`) and `duracion` in minutes (needs `hora`; a timed task with a duration is a work block).
- `repetir`: when a recurring task is done, it moves on to its next date after today instead of closing, and its subtasks start over. `fichas.saltar` skips the next date without doing it (bot: «Saltar», «hoy no hay…»).
- `hasta` (optional, needs `repetir`): the last day it may fall on. Done on its last date, the task closes for good; repeats are not projected after it. Without `hasta` a rule never ends. Clearing `repetir` clears `hasta`.
- Bandeja = open tasks with no project.

## Rules

- The header is a contract with other readers: flat `key: value` lines, one line per value, valid YAML (free text and lists as JSON). Agents may read it with a regex.
- `caso` is a short reference shown as «Ref.» (validated: letters, numbers, `/ . - _`, up to 30), never details.
- No runtime dependencies beyond the standard library in `agenda/` (Flask comes with the server). Python 3.10+.
- User-facing text is Spanish; code and comments are English.
- Keep files under ~500 lines.
- The server listens only on 127.0.0.1 or the Tailscale IP, never on 0.0.0.0, with debug off.
- Design: «Ops nocturna», soft version (tokens in `static/css/base.css`). Inter for text, Aldrich only for the greeting, big times and the clock. Green only for the main action, the active filter and «A continuación». No all-caps labels. Touch targets of 44 px. Fonts are served locally (`static/fonts/`): the CSP allows nothing from outside.
- Light and dark: dark is the default; `:root[data-theme="claro"]` in `base.css` redefines the tokens, and `static/js/tema.js` (a classic script in `<head>`) sets `data-theme` before the first paint from the device's choice in Ajustes (Oscuro, Claro, Como el sistema). Colors only through tokens, so both themes follow.
- No inline `style` attributes or inline scripts (the CSP blocks them); set sizes through `el.style.x = …` or classes.


## Off-server copy

- `scripts/copia-datos.sh <datos> <config>` (nightly unit): commit, then `git push` when `datos/` has a remote; the result goes to `<config>/copia-estado.json`, shown in Ajustes, and a failure is sent once by Telegram (`avisos.leer_copia`). `avisos.json` travels in `datos/ajustes/`; the bot token and the device key never do.
- `sudo scripts/instalar.sh copia-remota git@github.com:usuario/repo.git` sets the remote with an SSH deploy key only for that repository (`<config>/copia/`) and GitHub's pinned host key.
