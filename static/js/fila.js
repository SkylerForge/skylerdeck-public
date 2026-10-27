// One task row, shared by Inicio and the task lists, and the board card.
import { deslizable } from './deslizar.js';
import { diaCorto, h, icono } from './dom.js';

const ESTADOS = { 'en-curso': 'En curso', esperando: 'Esperando', 'mas-adelante': 'Más adelante' };
const AMBITOS = { laboral: 'Laboral', personal: 'Personal' };

function claseCuando(t, hoy) {
  if (t.vencida) return 't-vencida';
  if (t.fecha === hoy && t.hora) return 't-hoy-hora';
  return '';
}

export function metaDe(t, { hoy, ambito = true, proyecto = true, estado = true } = {}) {
  const bits = [];
  if (ambito) bits.push(h(`span.chip.chip--${t.ambito}`, AMBITOS[t.ambito]));
  if (proyecto && t.proyecto) bits.push(h('span', t.proyecto_nombre));
  if (t.cuando) bits.push(h(`span.${claseCuando(t, hoy) || 'x'}`, t.duracion ? `Bloque ${t.cuando.replace(/^Hoy, /, '')}` : t.cuando));
  if (t.repetir) {
    const regla = t.repetir[0].toUpperCase() + t.repetir.slice(1);
    bits.push(h('span', icono('repetir'), t.hasta ? `${regla} hasta el ${diaCorto(t.hasta)}` : regla));
  }
  if (estado && ESTADOS[t.estado]) {
    bits.push(h('span', t.estado === 'esperando' && t.esperando_a ? `Esperando a ${t.esperando_a}` : ESTADOS[t.estado]));
  }
  if (t.revisar) bits.push(h('span.t-revisar', t.toca_revisar ? 'Toca revisar' : `Revisar el ${diaCorto(t.revisar)}`));
  if (t.subtareas.length) {
    const hechas = t.subtareas.filter((s) => s.hecha).length;
    const barra = h('b');
    barra.style.width = `${Math.round((hechas / t.subtareas.length) * 100)}%`;
    bits.push(h('span.progreso', h('i', barra), `${hechas}/${t.subtareas.length}`));
  }
  for (const e of t.etiquetas) bits.push(h('span', `@${e}`));
  if (t.caso) bits.push(h('span', `Ref. ${t.caso}`));
  return h('div.fila__meta', bits);
}

/** With `alManana`, the row can be swiped: right to tick it, left to move it to tomorrow. */
export function fila(t, { hoy, alAbrir, alCompletar, alManana = null, ambito = true, proyecto = true, hecha = false }) {
  const el = h(`div.fila.prio-${t.prioridad}${hecha ? '.fila--hecha' : ''}`, { dataset: { id: t.id } },
    h('button.fila__check', {
      'aria-label': `Marcar como hecha: ${t.titulo}`,
      onclick: () => alCompletar(t),
    }, h('span', icono('check'))),
    h('button.fila__cuerpo', { onclick: () => alAbrir(t.id) },
      h('div.fila__titulo', t.titulo),
      metaDe(t, { hoy, ambito, proyecto })));
  if (!alManana || hecha) return el;
  return deslizable(el, {
    derecha: { texto: 'Hecha', icono: 'check', accion: () => alCompletar(t) },
    izquierda: { texto: 'Mañana', icono: 'derecha', accion: () => alManana(t) },
  }, '.desliza--fila');
}


export function carta(t, { hoy, alAbrir }) {
  return h(`button.carta.prio-${t.prioridad}`, { onclick: () => alAbrir(t.id) },
    h('div.carta__titulo', h('i'), h('span', t.titulo)),
    metaDe(t, { hoy, ambito: false, proyecto: false, estado: t.estado === 'esperando' && !!t.esperando_a }));
}
