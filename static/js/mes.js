// Inicio as a month: a Monday-to-Sunday grid with up to three tasks per day, and the chosen day's
// tasks in full beside it (below it on the phone). Same rules as the week (agenda/semana.py).
import { destino } from './arrastrar.js';
import { h, icono, plural, sumarDias } from './dom.js';
import { item, saludo, siguiente } from './inicio.js';

const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const DIAS_LARGOS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const POR_CELDA = 3;

const indice = (fecha) => (new Date(`${fecha}T12:00:00`).getDay() + 6) % 7;

function nombreMes(mes) {
  const [y, m] = mes.split('-').map(Number);
  const nombre = MESES[m - 1];
  return `${nombre[0].toUpperCase()}${nombre.slice(1)} de ${y}`;
}

function celda(dia, s, ctx, seleccionado) {
  const enMes = dia.fecha.startsWith(s.mes);
  const lineas = dia.items.slice(0, POR_CELDA).map((it) => {
    const t = s.tareas[it.id];
    return h(`span.mes-linea.mes-linea--${it.tipo}`,
      h(`i.punto.punto--${t.ambito}`),
      t.hora && it.tipo !== 'revisar' ? h('b', t.hora) : null,
      h('span', t.titulo));
  });
  const resto = dia.items.length - POR_CELDA;
  const clases = [
    enMes ? '' : '.mes-dia--fuera',
    dia.fecha === s.hoy ? '.mes-dia--hoy' : '',
    dia.fecha === seleccionado ? '.mes-dia--sel' : '',
    dia.fecha < s.hoy ? '.mes-dia--pasado' : '',
  ].join('');
  const numero = Number(dia.fecha.slice(8));
  const pendientes = dia.items.filter((it) => it.tipo !== 'hecha').length;
  return destino(h(`button.mes-dia${clases}`, {
    'aria-label': `${DIAS_LARGOS[indice(dia.fecha)]} ${numero}: ${plural(pendientes, 'tarea', 'tareas')}`,
    'aria-pressed': String(dia.fecha === seleccionado),
    onclick: () => ctx.elegirDia(dia.fecha),
  },
  h('span.mes-dia__num', numero, (s.notas_dia || []).includes(dia.fecha) ? h('span.mes-dia__nota', icono('nota', 'ico--s')) : null),
  h('span.mes-dia__lineas', lineas, resto > 0 ? h('span.mes-dia__mas', `+${resto} más`) : null),
  // On the phone the grid only shows dots, one per task (up to four).
  h('span.mes-dia__puntos', dia.items.slice(0, 4).map((it) => h(`i.punto.punto--${s.tareas[it.id].ambito}${it.tipo === 'hecha' ? '.punto--hecha' : ''}`)))),
  dia.fecha, ctx.moverA);
}

function detalle(fecha, s, ctx) {
  const dia = s.dias.find((x) => x.fecha === fecha);
  const [, m, d] = fecha.split('-').map(Number);
  const titulo = `${DIAS_LARGOS[indice(fecha)]}, ${d} de ${MESES[m - 1]}`;
  const vencidas = fecha === s.hoy && s.vencidas.length
    ? [h('p.sem-dia__sub.t-vencida', 'De días anteriores'), ...s.vencidas.map((id) => item({ id, tipo: 'vencida' }, s.tareas[id], s, ctx)),
      h('p.sem-dia__sub', 'Hoy')]
    : [];
  const items = (dia?.items || []).map((it) => item(it, s.tareas[it.id], s, ctx));
  return h('aside.tarjeta.mes-detalle', { 'aria-label': `Tareas del ${titulo}` },
    h('header.mes-detalle__cab',
      h('h2', fecha === s.hoy ? `Hoy · ${titulo.split(', ')[1]}` : titulo),
      h('button.icono-btn', { 'aria-label': `Añadir tarea el ${titulo}`, onclick: () => ctx.anadirEn(fecha) }, icono('mas', 'ico--s'))),
    h('div.mes-detalle__lista', vencidas, items.length ? items : (vencidas.length ? null : h('p.sem-dia__libre', 'Nada este día.'))),
    h('footer.mes-detalle__pie',
      h('button.anadir', { onclick: () => ctx.verSemana(fecha) }, icono('calendario', 'ico--s'), 'Ver la semana'),
      h('a.anadir', { href: `#/n/${fecha}` }, icono('nota', 'ico--s'), (s.notas_dia || []).includes(fecha) ? 'Nota del día' : 'Escribir nota del día')));
}

export function mes(d, s, ctx) {
  const actual = s.mes === s.hoy.slice(0, 7);
  const seleccionado = ctx.diaSeleccionado() && s.dias.some((x) => x.fecha === ctx.diaSeleccionado())
    ? ctx.diaSeleccionado()
    : (actual ? s.hoy : `${s.mes}-01`);
  const delMes = s.dias.filter((x) => x.fecha.startsWith(s.mes));
  const pendientes = new Set([...delMes.flatMap((x) => x.items.filter((i) => i.tipo !== 'hecha').map((i) => i.id)), ...s.vencidas]).size;

  const cabecera = h('header.cabecera',
    h('div',
      h('h1', d.nombre ? `${saludo(d.ahora)}, ${d.nombre}` : saludo(d.ahora)),
      h('p', `${nombreMes(s.mes)} · ${plural(pendientes, 'tarea pendiente', 'tareas pendientes')}`)),
    ctx.filtro());

  const barra = h('div.sem-barra',
    h('div.sem-barra__izq',
      actual ? siguiente(d, ctx) : null,
      h('a.sem-nota-dia', { href: '#/notas/hoy' }, icono('nota', 'ico--s'),
        (s.notas_dia || []).includes(s.hoy) ? 'Nota del día' : 'Escribir la nota del día')),
    h('nav.sem-nav', { 'aria-label': 'Mes' },
      ctx.conmutadorVista(),
      h('button.icono-btn', { 'aria-label': 'Mes anterior', onclick: () => ctx.irMes(-1) }, icono('izquierda')),
      h('button.boton.boton--fantasma', { disabled: actual, onclick: () => ctx.irMes(0) }, 'Este mes'),
      h('button.icono-btn', { 'aria-label': 'Mes siguiente', onclick: () => ctx.irMes(1) }, icono('derecha'))));

  const rejilla = h('section.tarjeta.mes-rejilla', { 'aria-label': nombreMes(s.mes) },
    DIAS.map((n) => h('span.mes-cab', n)),
    s.dias.map((x) => celda(x, s, ctx, seleccionado)));
  rejilla.style.gridTemplateRows = `auto repeat(${s.dias.length / 7}, minmax(0, 1fr))`;

  return h('div.inicio.inicio--mes', cabecera, ctx.quickAdd(), barra,
    h('div.mes', rejilla, detalle(seleccionado, s, ctx)));
}

/** Monday of the week that holds `fecha` (for «Ver la semana»). */
export function lunesDe(fecha) {
  return sumarDias(fecha, -indice(fecha));
}
