// Ajustes: reminders by Telegram (the agenda's bot). The panel only saves the settings and asks for
// a test; a separate process (agenda.avisos, every minute) sends the messages.
import { api } from './api.js';
import { avisar, h, vaciar } from './dom.js';

function hora(texto) {
  return texto ? texto.slice(11, 16) : '';
}

function interruptor(etiqueta, ayuda, activo, alCambiar) {
  const input = h('input', { type: 'checkbox', checked: activo, role: 'switch', onchange: (e) => alCambiar(e.target.checked) });
  return h('label.ajuste', h('span.ajuste__texto', h('strong', etiqueta), h('small', ayuda)), h('span.interruptor', input, h('i')));
}

function pintar(caja, a) {
  const guardar = async (cambios) => {
    try {
      pintar(caja, await api.ajustesAvisos(cambios));
      avisar('Guardado');
    } catch (err) {
      avisar(err.message, { error: true });
      cargar(caja);
    }
  };

  const antelacion = h('select.campo', { 'aria-label': 'Minutos de antelación', onchange: (e) => guardar({ antelacion: Number(e.target.value) }) },
    a.antelaciones.map((m) => h('option', { value: m, selected: m === a.ajustes.antelacion }, `${m} minutos antes`)));
  const reloj = (clave, etiqueta) => {
    const input = h('input.campo', { type: 'time', step: 300, 'aria-label': etiqueta });
    input.value = a.ajustes[clave] || '';
    input.addEventListener('change', () => input.value && guardar({ [clave]: input.value }));
    return h('label.ajuste.ajuste--campo', h('span.ajuste__texto', h('strong', etiqueta)), input);
  };

  let estado;
  if (!a.configurado) {
    estado = h('p.ajustes__estado.t-vencida', 'Falta el bot de Telegram. Configúralo en el servidor con sudo scripts/instalar.sh telegram (docs/bot-telegram.md); hasta entonces no saldrá ningún aviso.');
  } else if (a.ultimo_error) {
    estado = h('p.ajustes__estado.t-vencida', `Último intento fallido (${hora(a.ultimo_error.cuando)}): ${a.ultimo_error.texto}`);
  } else if (!a.ultima_revision) {
    estado = h('p.ajustes__estado.t-hoy-hora', 'El envío de avisos aún no se ha puesto en marcha en el servidor.');
  } else {
    estado = h('p.ajustes__estado', `Funcionando. Última revisión a las ${hora(a.ultima_revision)}`
      + (a.ultimo_envio ? ` · último aviso enviado el ${a.ultimo_envio.slice(8, 10)}/${a.ultimo_envio.slice(5, 7)} a las ${hora(a.ultimo_envio)}` : ''));
  }

  vaciar(caja,
    h('header.principal__cab', h('div', h('h1', 'Ajustes'), h('p', 'La apariencia es de este dispositivo; los avisos, de toda la agenda.'))),
    apariencia(),
    h('section.ajustes.ajustes--apariencia',
      h('h2', 'Modo kiosco'),
      h('p.meta', 'Para una tablet fija en la pared: el Inicio a pantalla completa, con un reloj grande y la pantalla siempre encendida.'),
      h('a.boton.ajustes__kiosco', { href: '#/kiosco' }, 'Abrir el modo kiosco')),
    h('section.ajustes',
      h('h2', 'Avisos'),
      h('p.meta', 'Te llegan por Telegram, en tu chat con el bot de la agenda. También puedes escribirle para apuntar tareas.'),
      estado,
      interruptor('Tareas con hora', 'Un aviso antes de cada tarea o bloque con hora de hoy.', a.ajustes.tareas_hora,
        (v) => guardar({ tareas_hora: v })),
      h('label.ajuste.ajuste--campo', h('span.ajuste__texto', h('strong', 'Antelación')), antelacion),
      interruptor('Resumen de la mañana', 'Lo que tienes hoy, por orden de hora, y lo que se ha quedado vencido.', a.ajustes.resumen,
        (v) => guardar({ resumen: v })),
      reloj('hora_resumen', 'Hora del resumen'),
      // Older servers do not know these two yet: they only show up once the server sends them.
      'noche' in a.ajustes && interruptor('Resumen de la noche', 'Lo que tienes mañana, la noche antes.', a.ajustes.noche,
        (v) => guardar({ noche: v })),
      'noche' in a.ajustes && a.ajustes.noche && reloj('hora_noche', 'Hora del resumen de la noche'),
      'repaso' in a.ajustes && interruptor('Repaso del domingo', 'La semana que viene, lo vencido y lo que esperas de otros.',
        a.ajustes.repaso, (v) => guardar({ repaso: v })),
      'repaso' in a.ajustes && a.ajustes.repaso && reloj('hora_repaso', 'Hora del repaso'),
      h('div.ajustes__prueba',
        h('button.boton', {
          disabled: a.prueba_pendiente || !a.configurado,
          onclick: async () => {
            try {
              pintar(caja, await api.pruebaAviso());
              avisar('Te llegará un mensaje de prueba en menos de un minuto');
            } catch (err) {
              avisar(err.message, { error: true });
            }
          },
        }, a.prueba_pendiente ? 'Prueba en camino…' : 'Enviar un mensaje de prueba'))),
    copiaSeccion(a.copia),
    a.version && h('section.ajustes',
      h('h2', 'Versión'),
      h('p.meta', `SkylerDeck ${a.version}. Para pasar a la última, en el servidor: sudo scripts/instalar.sh actualizar`)));
}

/** The off-server copy of the data (scripts/copia-datos.sh, every night). Old servers send no `copia`. */
function copiaSeccion(c) {
  if (!c) return h('section.ajustes', h('h2', 'Copia de seguridad'), h('p.meta', 'Cada noche a las 03:30 se guarda una copia de lo que haya cambiado, en este mismo servidor. Si además quieres una copia fuera, en un repositorio privado tuyo: sudo scripts/instalar.sh copia-remota (opcional).'));
  const fecha = `${c.cuando.slice(8, 10)}/${c.cuando.slice(5, 7)}`;
  return h('section.ajustes',
    h('h2', 'Copia de seguridad'),
    h('p.meta', 'Cada noche a las 03:30 se guarda lo que haya cambiado y se sube a tu repositorio privado.'),
    c.ok
      ? h('p.ajustes__estado', `Funcionando. Última subida el ${fecha} a las ${hora(c.cuando)}`)
      : h('p.ajustes__estado.t-vencida', `La última subida falló (${fecha} ${hora(c.cuando)}): ${c.texto}`));
}

/** Light or dark for this device only (js/tema.js keeps it before the first paint). */
function apariencia() {
  const tema = window.agendaTema;
  const seccion = h('section.ajustes.ajustes--apariencia');
  const pintarSeccion = () => {
    const actual = tema ? tema.preferencia() : 'oscuro';
    vaciar(seccion,
      h('h2', 'Apariencia'),
      h('div.pildoras.pildoras--sobrio', { role: 'group', 'aria-label': 'Tema' },
        [['oscuro', 'Oscuro'], ['claro', 'Claro'], ['sistema', 'Como el sistema']].map(([v, t]) =>
          h('button.pildora', { 'aria-pressed': String(v === actual), onclick: () => { tema?.poner(v); pintarSeccion(); } }, t))));
  };
  pintarSeccion();
  return seccion;
}

function cargar(caja) {
  api.avisos().then((a) => pintar(caja, a)).catch((err) => vaciar(caja, h('p.error-campo', err.message)));
}

export function ajustes() {
  const caja = h('section.tarjeta.principal.pagina-ajustes', h('p.meta', 'Cargando…'));
  cargar(caja);
  return h('div.ajustes-pagina', caja);
}
