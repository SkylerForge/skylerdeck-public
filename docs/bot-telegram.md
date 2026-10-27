# Bot de Telegram

El bot de Telegram hace dos cosas:

- **Te avisa**: unos minutos antes de cada tarea con hora (con botones para recordártelo más tarde), con el resumen de la mañana y, si quieres, con el de la noche y el repaso del domingo.
- **Apunta lo que le escribes**: le mandas «Llamar al dentista mañana a las 10 #Salud p1» y la tarea aparece en la agenda. También te dice qué tienes hoy, marca tareas como hechas, las pasa a otro día o las quita de la agenda, nombrándolas con sus palabras («borra la cita del dentista»).

<div align="center">
<img src="bot.webp" width="340" alt="Conversación con el bot: apunta tareas, avisa antes de una cita y enseña la lista de hoy">
</div>

Montarlo lleva unos cinco minutos y tiene tres pasos:

1. Crear el bot en Telegram con **@BotFather** (es gratis).
2. Darle el token al servidor.
3. Vincular tu chat para que el bot solo te haga caso a ti.

> **Un bot nuevo, solo para la agenda.** Telegram solo deja que un programa lea los mensajes de cada bot. Si usas un bot que ya tienes para otra cosa, los dos programas se pisan y uno deja de recibir mensajes (error 409). Crea uno nuevo; no cuesta nada.

---

## 1. Crea el bot con @BotFather

@BotFather es el bot oficial de Telegram para crear bots.

1. En Telegram, busca **@BotFather** (lleva la marca azul de verificado) y abre el chat.
2. Pulsa **Iniciar** o escribe `/start`.
3. Escribe `/newbot`.
4. Te pide un **nombre**: es el que verás en el chat. Por ejemplo: `Mi agenda`.
5. Te pide un **nombre de usuario**: tiene que ser único y acabar en `bot`. Por ejemplo: `agenda_de_lucia_bot`. Si ya está cogido, prueba otro.
6. BotFather te contesta con un mensaje que incluye el **token**, una línea parecida a esta:

   ```
   7123456789:AAHk3-EjEmPlO_dE_ToKeN_nO_lO_cOmPaRtAs
   ```

   Cópialo. **Es la contraseña del bot**: quien lo tenga puede hacerse pasar por él. No lo pegues en chats, capturas ni repositorios.

### Opcional: dale buena cara

En el mismo chat con @BotFather:

| Comando | Para qué |
|---|---|
| `/setuserpic` | Foto del bot. Sirve `static/iconos/icono-512.png` de este repositorio. |
| `/setdescription` | Texto que se ve antes de pulsar Iniciar, p. ej. «Mi agenda personal: te aviso y apunto tus tareas». |
| `/setabouttext` | La línea corta del perfil del bot. |

No hace falta configurar los comandos (`/setcommands`): la agenda los registra sola al arrancar.

---

## 2. Dale el token al servidor

En el servidor, dentro de la carpeta de la agenda:

```bash
sudo scripts/instalar.sh telegram
```

Te pide el token. Pégalo y pulsa Intro (no se ve mientras escribes; es normal). El script comprueba con Telegram que el token es bueno y te dice el nombre del bot:

```
Bot @agenda_de_lucia_bot (Mi agenda) guardado en /home/lucia/.config/skylerdeck/telegram.env
```

El token se guarda en ese archivo, que solo puede leer tu usuario. Nunca sale en los registros.

---

## 3. Vincula tu chat

Nada más guardar el token, el script te enseña un enlace y un código QR:

```
Abre este enlace en el móvil y pulsa «Iniciar»:

  https://t.me/agenda_de_lucia_bot?start=482913

o escanea este código con la cámara:
  ▄▄▄▄▄▄▄ ▄ ▄▄ ▄▄▄▄▄▄▄
  …
También vale escribirle a @agenda_de_lucia_bot este código: 482913
Espero 10 minutos…
```

Escanea el QR con la cámara del móvil (o abre el enlace) y pulsa **Iniciar** en Telegram. En un par de segundos el bot te saluda:

> ¡Hola, Lucía! Ya estás vinculado: te avisaré aquí de tus tareas y lo que me escribas lo apunto en la agenda. Escribe /ayuda para ver cómo.

Y el script termina con:

```
Vinculado el chat de Lucía.
→ Bot en marcha. Escríbele /ayuda desde Telegram.
```

Ya está. A partir de aquí el bot es tuyo y solo responde a tu cuenta: si cualquier otra persona le escribe, no contesta ni toca nada. Nadie puede vincularse después.

Para comprobar los avisos, entra en la agenda, abre **Ajustes** (la rueda) y pulsa **Enviar un mensaje de prueba**. Te llega en menos de un minuto.

---

## Cómo se usa

### Apuntar tareas

Escríbele como se lo dirías a alguien:

| Escribes | Se apunta |
|---|---|
| `Tengo cita con el dentista el martes a las cinco y media` | «Cita con el dentista», martes, 17:30 |
| `Recuérdame llamar a Ana pasado mañana por la tarde` | «Llamar a Ana», pasado mañana, 17:00 |
| `Reunión con Marta el lunes 2 de 10 a 12` | El lunes 2, de 10:00 a 12:00 |
| `Cita en hacienda el 5/11 a las 12:30, durará una hora` | 5 de noviembre, 12:30, una hora |
| `Dentro de 2 horas llamar al taller` | Hoy, dentro de dos horas |
| `Esta noche cena con amigos` | Hoy, 21:00 |
| `Tengo que renovar el DNI la semana que viene` | «Renovar el DNI», el lunes que viene |
| `Apúntame todos los días a las 9 el gimnasio` | «Gimnasio», cada día a las 9:00, sin fecha de fin |
| `Clase de inglés los jueves a las 7 de la tarde hasta diciembre #Formación` | Cada jueves a las 19:00 hasta el 31 de diciembre, en el proyecto Formación |
| `Fisio el lunes y el miércoles a las 10` | Dos tareas sueltas: lunes y miércoles a las 10:00 |
| `Comprar pilas` | Tarea sin fecha (va a la Bandeja) |

Las coletillas del principio, como «Recuérdame que», «Apunta», «Tengo que» o «Por favor», no pasan al título.

### Tareas que se repiten

Una tarea solo se repite si lo dices: «todos los días», «cada día», «los martes», «cada lunes y jueves», «de lunes a viernes», «los fines de semana», «cada 15 días», «cada dos semanas los lunes», «todos los meses». Sin esas palabras es una tarea de un día. Y si nombras varios días sueltos («el lunes y el miércoles»), apunta una tarea por día, sin repetición.

- **Sin final, salvo que lo digas.** Para ponerle uno: «hasta el 15 de diciembre», «hasta el 30/11», «hasta diciembre» (hasta el último día del mes), «hasta fin de año» o «durante 2 meses».
- **Empieza en la próxima vez que toque.** Si dices «todos los días a las 9» a las 10 de la mañana, empieza mañana y te lo dice. Para que empiece más tarde: «desde el 3 de noviembre» o «a partir del lunes».
- Cuando marcas una repetición como hecha, pasa a la siguiente fecha. La última antes del final se cierra del todo.
- El final se puede cambiar o quitar en el panel, en el campo «Hasta» de la tarea.

Cuando algo admite dos lecturas, el bot lo apunta de la forma más habitual y te lo dice en la respuesta:

- «a las 5» la entiende como 17:00 y te avisa. Si era de madrugada, pulsa **Era por la mañana**.
- «por la tarde» sin hora concreta pasa a las 17:00. Las demás partes del día: mañana a las 09:00, mediodía a las 14:00 y noche a las 21:00.
- Si pones un día de la semana que no cuadra con la fecha («el lunes 3 de noviembre», que es martes), se queda con la fecha y te avisa.

Si algo ha quedado mal, cámbialo en el panel o con `/posponer T-12 el jueves a las 10`.

Con **varias líneas en un mismo mensaje** se apuntan varias tareas (hasta 20). Sirve para vaciar la cabeza de golpe o pegar una lista.

Si una línea lleva un `#proyecto` que no existe, el bot te lo dice y no apunta esa línea. Los proyectos se crean en el panel; `/proyectos` te recuerda cómo se llaman.

Para ver qué entendería sin apuntar nada: `/probar Llamar a Ana el lunes a las 5 de la tarde`.

El bot no usa inteligencia artificial: entiende las frases con reglas escritas para el español, que funcionan en tu servidor sin enviar nada a nadie. Una frase muy enrevesada puede no entenderla del todo; la respuesta siempre te dice lo que ha apuntado.

### Comandos

| Comando | Qué hace |
|---|---|
| `/hoy` | Lo de hoy y lo que se ha quedado vencido, con un botón «✓» por tarea |
| `/manana` | Lo de mañana |
| `/semana` | Los próximos 7 días, agrupados por día |
| `/bandeja` | Las tareas sin proyecto |
| `/hecha dentista` | Marca la tarea como hecha (con números vale `/hecha 12 15 18` para varias) |
| `/posponer dentista el lunes` | Le cambia la fecha (y la hora, si la pones: `/posponer dentista mañana a las 9`) |
| `/borrar dentista` | La quita de la agenda, después de preguntarte (también `/eliminar`, `/quitar` o `/cancelar`) |
| `/saltar gimnasio` | Se salta la próxima vez de una tarea que se repite |
| `/ver dentista` | La tarea con sus subtareas |
| `/nota texto` | Lo añade a la nota del día |
| `/buscar texto` | Busca en tareas, notas, proyectos y etiquetas |
| `/probar texto` | Qué entiende de una frase, sin apuntar nada |
| `/proyectos` | Los nombres de proyecto para usar con `#` |
| `/ayuda` | Recordatorio de todo esto |

Para decirle de qué tarea hablas no hace falta saberse su número: basta con alguna de sus palabras (`dentista`, `reunión con Marta`), y puedes añadir el día para afinar (`gimnasio del miércoles`, `lo de mañana`). Si varias encajan, el bot te enseña un botón por cada una para que elijas. El número de cada tarea (`T-12`) sale en los mensajes del bot y en el panel, y también vale.

### Quitar algo de la agenda

Escríbelo como lo dirías:

```
Borra la cita del dentista
Cancela la reunión con Marta del lunes
Quítame el gimnasio de mañana
```

El bot busca la tarea y **pregunta antes de quitarla**: «¿Quito de la agenda «Dentista»?», con los botones **🗑 Sí, quítala** y **No**. Si hay varias que encajan, te deja elegir cuál.

Como «Cancelar el seguro del coche» también podría ser una tarea nueva, cuando la frase empieza por borra, cancela, quita, elimina o anula pasa esto:

- Si no hay ninguna tarea que encaje, la apunta como tarea nueva, como siempre.
- Si alguna encaja, te pregunta y te da también el botón **No: apúntalo como tarea nueva**.

Quitar una tarea es lo mismo que «Soltar tarea» en el panel: desaparece de la agenda y de los avisos, pero no se borra. Justo después tienes el botón **↩ Deshacer**, y más tarde puedes recuperarla desde el panel.

Si es una tarea que se repite, te pregunta: **⏭ Solo la del 26/10** (se salta esa vez y sigue con las demás) o **🗑 Todas**.

### Hablarle de tareas que ya tienes

Además de apuntar y quitar, entiende estas frases. Igual que al quitar, solo actúan si alguna tarea encaja con lo que dices; si no, el mensaje se apunta como tarea nueva.

| Escribes | Qué hace |
|---|---|
| `Ya he ido al dentista`, `Hecho el informe`, `He comprado las pilas` | La marca como hecha, con **↩ Deshacer** |
| `Hoy no hay gimnasio`, `Sáltate el gimnasio del jueves`, `No voy al gimnasio mañana` | Se salta esa vez de una tarea que se repite, con **↩ Deshacer** |
| `Pasa el dentista al jueves`, `Cambia el gimnasio a las 8`, `Mueve la reunión con Marta al lunes a las 10` | Te pregunta antes de cambiarla (con **No: apúntalo como tarea nueva**) y luego te da **↩ Deshacer** |
| `Ponle prioridad 1 al informe`, `Marca el informe como urgente` | Le cambia la prioridad |
| `Añade a la compra: leche, pan y huevos` | Lo añade a la lista «Compra» como subtareas; si no existe, la crea |
| `Añade pilas a la compra` | Lo mismo, si ya tienes una lista que se llame así |

Saltar solo vale para la **próxima** vez que toca una tarea que se repite. Si nombras una fecha más lejana, el bot te lo dice y te ofrece saltar la próxima.

### Botones

- **✓ Hecha**: la cierra. Si es una tarea que se repite, pasa a la siguiente fecha.
- **→ Mañana**: la pasa a mañana, con la misma hora.
- **+10 min** / **+1 h**: en los avisos, te lo vuelve a recordar más tarde sin cambiar la tarea.
- **Era por la mañana**: sale cuando ha entendido «a las 5» como las 17:00; la pasa a las 05:00.
- **Abrir** / **Abrir en la agenda**: abre esa tarea en el panel. Desde el móvil hace falta estar emparejado y, si usas Tailscale, tenerlo encendido.

### Avisos

Se ajustan en el panel, en **Ajustes**:

- **Tareas con hora**: un aviso 5, 10, 15, 30 o 60 minutos antes.
- **Resumen de la mañana**: a la hora que elijas, lo que tienes hoy por orden de hora y lo que se ha quedado vencido.
- **Resumen de la noche** (desactivado al principio): a la hora que elijas, lo que tienes mañana.
- **Repaso del domingo** (desactivado al principio): la semana que viene día a día, lo vencido y lo que esperas de otros.

Cada aviso se envía una sola vez. Si el servidor ha estado apagado, no te llegan de golpe los avisos atrasados.

---

## Solo habla contigo

El bot es de la primera cuenta de Telegram que se vincula, la tuya, y solo habla con ella. Si otra persona encuentra el bot y le escribe, no contesta ni toca nada. No hay forma de añadir una segunda cuenta.

Si cambias de cuenta de Telegram (o quieres pasarle el bot a otra persona):

```bash
sudo scripts/instalar.sh cambiar-cuenta
```

Te enseña un QR nuevo. La cuenta que lo escanee y pulse Iniciar pasa a ser la dueña, y la anterior queda olvidada. El script para el bot un momento mientras espera y lo vuelve a poner en marcha al terminar.

---

## Cambiar de bot o de token

Si el token se ha filtrado, revócalo: en @BotFather, `/mybots` → tu bot → **API Token** → **Revoke current token**. Te da uno nuevo. Luego:

```bash
sudo scripts/instalar.sh telegram
```

y pega el token nuevo. El bot sigue siendo de tu cuenta: no hace falta volver a vincularla.

---

## Si algo no va

Mira el registro del bot:

```bash
journalctl -u skylerdeck-bot -n 30
```

Muestra una línea por mensaje («1 tarea(s) apuntada(s)», «/hoy»…), nunca el texto que escribiste ni el token.

| Lo que pasa | Qué hacer |
|---|---|
| El bot no contesta | `sudo systemctl status skylerdeck-bot`. Si no está en marcha, `sudo scripts/instalar.sh telegram`. |
| En el registro: «Otro programa está leyendo los mensajes de este bot» | Ese token lo usa otro programa (otro bot, n8n, una copia antigua de la agenda…). Crea un bot nuevo solo para la agenda. |
| En el registro: «Telegram no acepta el token» | El token se revocó o se copió mal. Vuelve a `sudo scripts/instalar.sh telegram`. |
| En el registro: «Mensaje ignorado: viene de un chat no autorizado» | Alguien que no está vinculado escribió al bot. No ha tocado nada. Si eras tú desde otra cuenta, usa `sudo scripts/instalar.sh cambiar-cuenta`. |
| «El bot ya está en marcha y Telegram solo deja un lector» al vincular | Usa `sudo scripts/instalar.sh cambiar-cuenta`, que para el bot por ti, en vez de llamar a `bin/agenda-bot` directamente. |
| No llegan los avisos | En **Ajustes** del panel sale el último error. `journalctl -u skylerdeck-avisos -n 20` da más detalle. |
| «No ha llegado el código» | Han pasado 10 minutos o el mensaje no llegó. Repite `sudo scripts/instalar.sh telegram`. |

---

## Privacidad

- El servidor habla directamente con `api.telegram.org`. No pasa por ningún servicio intermedio.
- El bot no usa inteligencia artificial: interpreta las frases con reglas fijas, en tu servidor.
- Telegram ve los mensajes que intercambias con el bot, como cualquier chat normal (no son chats secretos). Si una tarea es delicada, apúntala desde el panel.
- Solo atiende a su dueño, la primera cuenta que se vinculó, y no responde a nadie más, así que un desconocido no puede saber siquiera si el bot funciona.
- Los servicios del bot y de los avisos son los únicos que salen a internet. El panel tiene la salida a internet bloqueada.
