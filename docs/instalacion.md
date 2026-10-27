# Instalación

Esta guía explica cómo instalar SkylerDeck en un servidor Linux tuyo (un VPS, un mini PC, una Raspberry Pi…). Si ya tienes Tailscale funcionando, la versión corta del [README](../README.md#instalación-en-5-minutos) basta.

## Qué necesitas

| | |
|---|---|
| **Sistema** | Linux con systemd: Ubuntu 22.04 o posterior, Debian 12 o posterior y la mayoría de distribuciones actuales. |
| **Python** | 3.10 o posterior, con `venv` (en Debian y Ubuntu: `sudo apt install python3 python3-venv git`). |
| **Máquina** | Cualquier cosa vale: con 1 CPU y 512 MB de RAM sobra. Ocupa menos de 100 MB con su entorno de Python. |
| **Acceso** | [Tailscale](https://tailscale.com) (recomendado y gratis para uso personal) o un dominio con HTTPS delante. |
| **Telegram** | Opcional, para los avisos y el bot. Ver [bot-telegram.md](bot-telegram.md). |

## 1. Prepara Tailscale

Tailscale crea una red privada entre tus dispositivos. La agenda solo se ve dentro de esa red: no abre ningún puerto a internet y nadie de fuera puede llegar a ella.

En el **servidor**:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`tailscale up` te da un enlace para iniciar sesión. Ábrelo y entra con tu cuenta (Google, Microsoft, GitHub…).

En la **consola de Tailscale** ([login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns)):

1. Comprueba que **MagicDNS** está activado (viene activado en las cuentas nuevas).
2. En **HTTPS Certificates**, pulsa **Enable HTTPS**. Así la agenda tiene una dirección `https://…ts.net` con certificado válido.

En el **móvil, la tablet y el ordenador** donde vayas a usar la agenda: instala la app de Tailscale (App Store, Google Play, Windows, macOS) y entra con la misma cuenta.

> ¿Usas otra VPN en el móvil o el PC (NordVPN, ProtonVPN…)? Muchas bloquean el tráfico de Tailscale mientras están conectadas. Si el dispositivo tiene internet pero no llega a la agenda, desconecta la otra VPN o activa su «split tunneling».

## 2. Descarga e instala

Con tu usuario normal (no hace falta ser root para clonar):

```bash
git clone https://github.com/SkylerForge/skylerdeck-public.git skylerdeck
cd skylerdeck
sudo scripts/instalar.sh
```

El instalador:

1. Comprueba Python y git, crea el entorno `.venv` e instala las dependencias.
2. Te pregunta tu **nombre** (para el saludo) y la **zona horaria** (por defecto `Europe/Madrid`; por ejemplo `America/Mexico_City`, `America/Bogota`, `America/Argentina/Buenos_Aires`).
3. Detecta Tailscale y publica la agenda en `https://<tu-servidor>.<tu-red>.ts.net:8443`.
4. Instala cuatro servicios de systemd, que arrancan solos al encender el servidor:

| Servicio | Qué hace |
|---|---|
| `skylerdeck` | El panel web. Escucha solo en `127.0.0.1:4850`. |
| `skylerdeck-avisos.timer` | Revisa cada minuto si toca algún aviso de Telegram. |
| `skylerdeck-bot` | El bot de Telegram. Solo arranca cuando lo has configurado. |
| `skylerdeck-copia.timer` | Copia diaria de tus datos a las 03:30. |

Los servicios corren con **tu usuario**, no como root, y con el sistema en solo lectura: solo pueden escribir en `datos/` y en `~/.config/skylerdeck/`.

Las respuestas se guardan en `/etc/skylerdeck.env`: al actualizar o volver a ejecutar el instalador no te pregunta nada.

Si prefieres no contestar preguntas (por ejemplo, desde un script):

```bash
sudo AGENDA_NOMBRE="Lucía" AGENDA_TZ="Europe/Madrid" scripts/instalar.sh
```

## 3. Empareja tus dispositivos

Además de estar en tu red de Tailscale, cada navegador necesita una **clave de dispositivo**. Es una segunda capa de seguridad: si alguien entra en tu red, sigue sin poder abrir la agenda.

```bash
sudo scripts/instalar.sh enlace
```

Te da un enlace y un código QR. Escanéalo con el móvil o abre el enlace en el ordenador: la clave se guarda en ese navegador y desaparece de la barra de direcciones. Repite con cada dispositivo.

> El enlace contiene la clave. No lo mandes por chat ni lo pegues en sitios públicos. Si se filtra, borra `~/.config/skylerdeck/clave` y ejecuta `sudo systemctl restart skylerdeck`: se crea una clave nueva y tendrás que emparejar otra vez tus dispositivos.

**Acceso directo**: en el móvil, abre la agenda y elige «Añadir a pantalla de inicio» (Safari: botón Compartir; Chrome: menú ⋮).

## 4. Telegram (opcional)

```bash
sudo scripts/instalar.sh telegram
```

El paso a paso, con BotFather incluido, está en [bot-telegram.md](bot-telegram.md).

---

## Sin Tailscale: tu propio dominio

Si prefieres entrar con `https://agenda.tudominio.com`, pon delante un proxy con HTTPS. La agenda queda accesible desde internet. La protegen la clave de dispositivo (aleatoria, de 256 bits) y las comprobaciones de origen, pero queda más expuesta que dentro de Tailscale.

```bash
sudo AGENDA_ACCESO=dominio AGENDA_DOMINIO=agenda.tudominio.com scripts/instalar.sh
```

Después, configura tu proxy para que mande ese dominio a `http://127.0.0.1:4850`. El proxy tiene que estar en la misma máquina: la agenda no escucha fuera de `127.0.0.1`.

**Caddy** (consigue el certificado HTTPS solo):

```
agenda.tudominio.com {
    reverse_proxy 127.0.0.1:4850
}
```

**nginx** (con el certificado de certbot):

```nginx
server {
    listen 443 ssl http2;
    server_name agenda.tudominio.com;
    ssl_certificate     /etc/letsencrypt/live/agenda.tudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agenda.tudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:4850;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

El proxy tiene que mantener la cabecera `Host` original: la agenda rechaza cualquier nombre que no sea el tuyo, para protegerse del *DNS rebinding*.

Si el proxy corre en Docker (Traefik, Easypanel, Coolify…), `127.0.0.1` dentro del contenedor no es el servidor. En ese caso es más sencillo usar Tailscale.

---

## Día a día

| Para | Ejecuta |
|---|---|
| Ver si todo está en marcha (y qué versión tienes) | `sudo scripts/instalar.sh estado` |
| Pasar a la última versión | `sudo scripts/instalar.sh actualizar` |
| Emparejar otro dispositivo | `sudo scripts/instalar.sh enlace` |
| Pasar el bot a otra cuenta de Telegram | `sudo scripts/instalar.sh cambiar-cuenta` |
| Copia de los datos en tu GitHub privado | `sudo scripts/instalar.sh copia-remota git@github.com:…` |
| Ver qué pasa en el panel | `journalctl -u skylerdeck -f` |
| Ver qué hace el bot | `journalctl -u skylerdeck-bot -f` |

### Actualizar

```bash
cd skylerdeck
sudo scripts/instalar.sh actualizar
```

Descarga la última versión de GitHub, te enseña qué ha cambiado y vuelve a instalar con tus respuestas de la primera vez. El panel, el bot y los avisos se reinician solos, en unos segundos. Si ya la tenías, te lo dice y no toca nada.

- **Tus datos no se tocan:** `datos/` no está en el repositorio. Tampoco el bot ni las claves de tus dispositivos.
- **La versión que tienes** sale en **Ajustes**, al final, y en `sudo scripts/instalar.sh estado`. Lo que trae cada versión está en [CHANGELOG.md](../CHANGELOG.md) y en las [Releases](https://github.com/SkylerForge/skylerdeck-public/releases) de GitHub.
- **Si se niega porque «hay archivos del programa cambiados»**, es que algo dentro de la carpeta se editó a mano. `git -C skylerdeck status` dice qué, y `git -C skylerdeck checkout -- .` lo devuelve a como venía.
- **Si lo descargaste en .zip** en vez de con `git clone`, no se puede actualizar solo. Clona el repositorio en otra carpeta, mueve a ella tu carpeta `datos/` y ejecuta `sudo scripts/instalar.sh` desde la nueva.

### Copias de seguridad

`datos/` es un repositorio git propio. Cada noche se hace un commit con lo que haya cambiado, así que puedes volver a cualquier día anterior:

```bash
cd datos
git log --oneline                      # una línea por día con cambios
git show HEAD~3:tareas/T-012.md        # cómo estaba esa tarea hace tres copias
```

Eso te protege de borrados y errores, pero no de perder el servidor. Para tener además una copia **fuera**, en un repositorio privado de GitHub que se actualiza solo cada noche:

1. En GitHub, crea un repositorio nuevo, **privado** y vacío (sin README). Por ejemplo, `mi-agenda-datos`.
2. En el servidor:

   ```bash
   sudo scripts/instalar.sh copia-remota git@github.com:tu-usuario/mi-agenda-datos.git
   ```

3. El script crea una llave SSH solo para esto y te la enseña. En el repositorio, entra en **Settings → Deploy keys → Add deploy key**, pégala, marca **Allow write access** y guarda.
4. Vuelve a ejecutar el mismo comando: sube tus datos y te dice «Copia conectada».

A partir de ahí, la copia de las 03:30 sube lo que haya cambiado. La llave solo sirve para ese repositorio, no para tu cuenta. En **Ajustes** del panel ves cuándo se subió la última vez, y si alguna noche falla, el bot te avisa por Telegram.

A la copia van tus tareas, notas y proyectos, y los ajustes de los avisos. **Nunca** van el token del bot ni la clave de tus dispositivos.

**Restaurar en un servidor nuevo:** instala SkylerDeck, clona tu repositorio de datos en la carpeta `datos/` (`git clone git@github.com:tu-usuario/mi-agenda-datos.git datos`) y vuelve a ejecutar `sudo scripts/instalar.sh`. Empareja los dispositivos y configura el bot otra vez.

### La línea de comandos

`bin/agenda` maneja la agenda desde la terminal. También sirve para scripts y para agentes de IA que trabajen en tu servidor:

```bash
bin/agenda anadir "Llamar al dentista mañana 10:00 #Salud p1"
bin/agenda lista --vista hoy
bin/agenda hecha T-012
bin/agenda notas diario --texto "Idea: …"
bin/agenda --help
```

Escribe en la misma carpeta `datos/` que el panel, que se actualiza solo.

### Desinstalar

```bash
sudo scripts/instalar.sh desinstalar
```

Quita los servicios y deja tus datos (`datos/`) y la configuración del bot (`~/.config/skylerdeck/`). Si usabas Tailscale, deja de publicar la agenda en él.

---

## Variables

Las pone el instalador en los servicios. Solo las necesitas si lo montas a mano.

| Variable | Para qué | Por defecto |
|---|---|---|
| `AGENDA_DATOS` | Carpeta de datos | `datos/` junto al código |
| `AGENDA_CONFIG` | Ajustes, clave y bot | `~/.config/skylerdeck` |
| `AGENDA_NOMBRE` | Nombre del saludo | vacío (solo «Buenos días») |
| `AGENDA_TZ` | Zona horaria | `Europe/Madrid` |
| `AGENDA_URL` | Dirección pública (para los botones de Telegram) | la del instalador |
| `AGENDA_HOST`, `AGENDA_PUERTO` | Dónde escucha el panel | IP de Tailscale, `4850` |
| `AGENDA_HOSTS` | Nombres extra que el panel acepta (tu dominio) | vacío |
