// Quick-add box: highlights what the parser understood while typing, Enter creates the task.
// The parsing itself happens on the server (agenda/quickadd.py), so the CLI, the bot and the page agree.
import { api } from './api.js';
import { avisar, diaCorto, h, icono, vaciar } from './dom.js';

const PAUSA_MS = 140;

function lectura(r, hoy) {
  const bits = [];
  if (r.fecha) {
    const dia = r.fecha === hoy ? 'Hoy' : diaCorto(r.fecha);
    const hora = r.hora ? (r.duracion ? ` ${r.hora} · ${r.duracion} min` : ` ${r.hora}`) : '';
    bits.push(h('span', icono('calendario', 'ico--s'), dia + hora));
  }
  if (r.repetir) bits.push(h('span', icono('repetir', 'ico--s'), r.hasta ? `${r.repetir} hasta el ${diaCorto(r.hasta)}` : r.repetir));
  if (r.otras_fechas?.length) bits.push(h('span', `y ${r.otras_fechas.map(diaCorto).join(', ')} (una tarea por día)`));
  if (r.proyecto) {
    bits.push(r.proyecto_nombre
      ? h('span', `#${r.proyecto_nombre}`)
      : h('span.qa--mal', `#${r.proyecto} no existe`));
  }
  if (r.prioridad) bits.push(h('span', r.prioridad));
  for (const e of r.etiquetas) bits.push(h('span', `@${e}`));
  for (const a of r.avisos) bits.push(h('span', a));
  return bits;
}

/**
 * opciones.contexto() → {ambito, proyecto} used when the text has no #proyecto.
 * opciones.alCrear(tarea) runs after the task is created.
 */
export function quickAdd({ placeholder, compacto = false, contexto = () => ({}), alCrear, hoy }) {
  const input = h('input.qa__input', {
    type: 'text', placeholder, autocomplete: 'off', spellcheck: false, enterKeyHint: 'done',
    'aria-label': 'Añadir tarea',
  });
  const espejo = h('div.qa__espejo', { 'aria-hidden': 'true' });
  const info = h('div.qa__lectura', { 'aria-live': 'polite' });
  let temporizador = null;
  let peticion = 0;
  let ocupado = false;

  function pintarEspejo(texto, partes, proyectoMal) {
    const trozos = [];
    let pos = 0;
    for (const p of partes) {
      trozos.push(texto.slice(pos, p.inicio));
      const mal = p.tipo === 'proyecto' && proyectoMal;
      trozos.push(h(`mark${mal ? '.qa--mal' : ''}`, texto.slice(p.inicio, p.fin)));
      pos = p.fin;
    }
    trozos.push(texto.slice(pos));
    vaciar(espejo, trozos);
    espejo.scrollLeft = input.scrollLeft;
  }

  async function leer() {
    const texto = input.value;
    const n = ++peticion;
    if (!texto.trim()) {
      vaciar(espejo);
      vaciar(info);
      return;
    }
    try {
      const r = await api.parsear(texto);
      if (n !== peticion || input.value !== texto) return;
      pintarEspejo(texto, r.partes, r.proyecto && !r.proyecto_nombre);
      vaciar(info, lectura(r, hoy()));
    } catch {
      /* the preview is optional; creating still reports errors */
    }
  }

  async function crear() {
    const texto = input.value.trim();
    if (!texto || ocupado) return;
    ocupado = true;
    try {
      const { tarea, avisos, otras = 0 } = await api.crear(texto, contexto());
      input.value = '';
      vaciar(espejo);
      vaciar(info);
      const donde = tarea.proyecto_nombre ? ` en ${tarea.proyecto_nombre}` : '';
      const que = otras ? `Añadidas ${otras + 1} tareas` : 'Añadida';
      avisar(`${que}${donde}${tarea.cuando ? ` · ${tarea.cuando.toLowerCase()}` : ''}${avisos.length ? ` · ${avisos[0]}` : ''}`);
      alCrear?.(tarea);
    } catch (err) {
      avisar(err.message, { error: true });
    } finally {
      ocupado = false;
    }
  }

  input.addEventListener('input', () => {
    espejo.textContent = input.value;
    if (!input.value.trim()) vaciar(info);
    clearTimeout(temporizador);
    temporizador = setTimeout(leer, PAUSA_MS);
  });
  input.addEventListener('scroll', () => { espejo.scrollLeft = input.scrollLeft; });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); crear(); }
    if (e.key === 'Escape') { input.value = ''; vaciar(espejo); vaciar(info); input.blur(); }
  });

  const caja = h(`div.qa${compacto ? '.qa--linea' : ''}`,
    icono('mas'),
    h('div.qa__caja', espejo, input),
    !compacto && h('span.qa__tecla', 'Intro ↵'));
  return { el: h('div', caja, info), input };
}
