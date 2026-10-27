# Novedades

Lo que trae cada versión de SkylerDeck. Para pasar a la última: `sudo scripts/instalar.sh actualizar` ([cómo funciona](docs/instalacion.md#actualizar)).

## 1.0.2 · 27 de octubre de 2026

**Diario**
- Escríbele al bot «nota: …», «anota: …» o «diario: …» (o «apunta en la nota de hoy que…») y se añade a la nota del día, sin crear una tarea. La respuesta trae el botón **Abrir la nota**.
- Al señalar un día en el calendario, debajo de sus tareas se ve su nota del día.

## 1.0.1 · 27 de octubre de 2026

**Bot de Telegram**
- Cuando un mensaje apunta varias tareas («la clase de crossfit hoy y mañana»), cada una llega con sus botones, como si la hubieras escrito sola. Si son más de cuatro, llega la lista con un botón por tarea y otro para quitarlas todas.
- «Elimina las dos clases de crossfit» las encuentra (los números y «todas» o «ambas» ya no se buscan en el título) y ofrece **🗑 Todas**.
- Para quitar varias de una vez: «elimina» en la primera línea y debajo una por línea, o las líneas pegadas de una respuesta del bot.
- Una orden como «borra…» o «elimina…» que no encuentra nada ya no se apunta como tarea: lo dice y ofrece apuntarla.
- «Añádeme», «Agrégame», «Ponme» o «Méteme» al principio ya no pasan al título.

## 1.0.0 · 27 de octubre de 2026

La primera versión.

**Panel**
- Inicio con el mes o la semana, «A continuación» y la lista del día. Vistas Hoy, Próximo, Bandeja y proyectos en lista o en tablero.
- Tareas con prioridad, etiquetas, subtareas, duración, repeticiones con o sin fecha de fin y bitácora de cambios.
- Notas Markdown con `[[enlaces]]`, menciones y la nota del día.
- Búsqueda rápida con `Ctrl+K`, tema claro y oscuro.
- En el móvil, desliza una tarea para marcarla como hecha o pasarla a mañana. En el ordenador, arrástrala a otro día.
- En la ficha de una tarea, fechas rápidas (Hoy, Mañana, El lunes…) y «Saltar esta vez» en las que se repiten.
- Modo kiosco para una tablet en la pared: reloj grande y la pantalla siempre encendida.

**Escribir como hablas**
- Fechas, horas dichas con palabras («a las cinco y media»), partes del día, bloques («de 9 a 11») y duraciones.
- Repeticiones solo cuando las dices («todos los días», «cada dos semanas los lunes»), con principio y fin («desde el lunes», «hasta diciembre»).
- Varias citas sueltas en una frase («el lunes y el miércoles»): una tarea por día.

**Bot de Telegram**
- Avisos antes de cada cita, con botones para marcarla como hecha, posponerla 10 minutos o 1 hora, o pasarla a mañana.
- Resumen de la mañana. Opcionales: el de la noche y el repaso del domingo.
- Entiende frases sobre tareas que ya tienes: «ya he ido al dentista», «pasa la reunión al jueves», «hoy no hay gimnasio», «añade a la compra: leche, pan».
- Quitar tareas por su nombre, no solo por su número. En las que se repiten, pregunta si solo esa vez o todas.
- Solo habla con la cuenta que lo vincula primero.

**Servidor**
- Instalador para Linux con systemd: panel, avisos, bot y copia diaria, con el sistema en solo lectura.
- Acceso por Tailscale (`tailscale serve`) o por tu propio dominio con proxy.
- Copia diaria de los datos en git y, si quieres, en un repositorio privado tuyo (`copia-remota`). Ajustes enseña si funciona y el bot avisa si falla.
- `sudo scripts/instalar.sh actualizar` para pasar a la versión nueva.
