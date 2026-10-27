// The page: routes, scope filter, polling for changes, completing with undo.
import { api } from './api.js';
import { avisar, diaCorto, h, icono, sumarDias, vaciar } from './dom.js';
import { ajustes } from './ajustes.js';
import { abrirBuscador, iniciarBuscador } from './buscar.js';
import { abrir, alCambiarDatos, iniciarFicha, sucio } from './ficha.js';
import { inicio } from './inicio.js';
import { marcoKiosco, modoKiosco } from './kiosco.js';
import { lunesDe, mes } from './mes.js';
import * as modNotas from './notas.js';
import { quickAdd } from './quickadd.js';
import { tareas } from './tareas.js';

const SONDEO_MS = 3000;
const DESHACER_MS = 4000;
// The rail holds modules only; lists inside a module (Hoy, Próximo, projects…) live in that module's own navigation.
const MODULOS = [
  ['#/inicio', 'inicio', 'Inicio'],
  ['#/tareas', 'lista', 'Tareas'],
  ['#/notas', 'nota', 'Notas'],
];
const LISTAS = /^#\/(hoy|proximo|bandeja|p\/.+)$/;

const estado = {
  datos: null,
  semana: null, // what Inicio shows: one week or a month (agenda/semana.py)
  lunes: null, // Monday of the week shown on Inicio; null = this week
  mes: null, // month shown on Inicio (AAAA-MM); null = this month
  diaSel: null, // day picked in the month view
  huella: '',
  rutaPintada: '',
  version: { datos: null, app: null },
  completando: new Map(), // id → timer; shown as done until the server confirms
};

function preferencia(clave, porDefecto, guardar = false) {
  try {
    if (guardar) { localStorage.setItem(`agenda:${clave}`, porDefecto); return porDefecto; }
    return localStorage.getItem(`agenda:${clave}`) || porDefecto;
  } catch {
    return porDefecto;
  }
}

function ruta() {
  const r = location.hash || '#/inicio';
  // #/t/T-012 (the link in a Telegram reminder): open that task over the week.
  const tarea = /^#\/t\/(T-\d+)$/.exec(r);
  if (tarea) {
    history.replaceState(null, '', '#/inicio');
    setTimeout(() => abrir(tarea[1]), 0);
    return '#/inicio';
  }
  if (r === '#/ajustes' || r === '#/kiosco') return r;
  if (LISTAS.test(r)) return r;
  if (r === '#/tareas' || r === '#/proyectos') return preferencia('ultima-lista', '#/hoy');
  if (r === '#/notas') return preferencia('ultima-nota', '#/notas/hoy');
  if (modNotas.rutaNotas(r)) return r;
  return '#/inicio';
}

function ir(hash) {
  if (location.hash === hash) pintar();
  else location.hash = hash;
}

function filtro() {
  const actual = preferencia('ambito', 'todo');
  return h('div.pildoras', { role: 'group', 'aria-label': 'Ámbito' }, [['todo', 'Todo'], ['personal', 'Personal'], ['laboral', 'Laboral']].map(([v, t]) =>
    h('button.pildora', { 'aria-pressed': String(v === actual), onclick: () => { preferencia('ambito', v, true); recargar(); } }, t)));
}

function completar(t) {
  if (estado.completando.has(t.id)) return;
  const temporizador = setTimeout(async () => {
    try {
      const hecha = await api.estado(t.id, 'hecha', t.version);
      if (hecha.repetir && hecha.estado !== 'hecha') avisar(`Hecha. Vuelve ${hecha.cuando.toLowerCase()}`);
    } catch (err) {
      avisar(err.status === 409 ? 'La tarea había cambiado; no la he marcado. Mírala otra vez.' : err.message, { error: true });
    }
    estado.completando.delete(t.id);
    recargar();
  }, DESHACER_MS);
  estado.completando.set(t.id, temporizador);
  pintar(true);
  avisar(`Hecha: ${t.titulo}`, {
    ms: DESHACER_MS,
    accion: { texto: 'Deshacer', alPulsar: () => { clearTimeout(estado.completando.get(t.id)); estado.completando.delete(t.id); pintar(true); } },
  });
}

/** Moves a task to tomorrow (swipe left), with «Deshacer» back to the day it had. */
async function manana(t) {
  try {
    const movida = await api.editar(t.id, { fecha: sumarDias(estado.datos.hoy, 1) }, t.version);
    recargar();
    avisar(`Pasada a mañana: ${t.titulo}`, {
      accion: {
        texto: 'Deshacer',
        alPulsar: () => api.editar(t.id, { fecha: t.fecha || '' }, movida.version)
          .catch((err) => avisar(err.message, { error: true })).then(() => recargar()),
      },
    });
  } catch (err) {
    avisar(err.status === 409 ? 'La tarea había cambiado; no la he movido. Mírala otra vez.' : err.message, { error: true });
  }
}

/** Drops a task on another day of the week or month, with «Deshacer». */
async function moverA(id, fecha) {
  const t = estado.semana?.tareas?.[id];
  if (!t || t.fecha === fecha) return;
  try {
    const movida = await api.editar(id, { fecha }, t.version);
    recargar();
    avisar(`${t.titulo}: ${diaCorto(fecha)}`, {
      accion: {
        texto: 'Deshacer',
        alPulsar: () => api.editar(id, { fecha: t.fecha || '' }, movida.version)
          .catch((err) => avisar(err.message, { error: true })).then(() => recargar()),
      },
    });
  } catch (err) {
    avisar(err.status === 409 ? 'La tarea había cambiado; no la he movido. Mírala otra vez.' : err.message, { error: true });
  }
}

function lunesActual() {
  const hoy = estado.datos.hoy;
  return sumarDias(hoy, -((new Date(`${hoy}T12:00:00`).getDay() + 6) % 7));
}

/** Puts the day into the Inicio quick-add (full date, so a past day of this week is not read as next year). */
function anadirEn(fecha) {
  const qa = document.querySelector('.inicio .qa__input');
  if (!qa) return;
  const [y, m, d] = fecha.split('-');
  const sufijo = ` ${d}/${m}/${y}`;
  qa.value = `${qa.value.replace(/\s+\d{1,2}\/\d{1,2}\/\d{4}$/, '').trim()}${sufijo}`;
  qa.focus();
  qa.setSelectionRange(qa.value.length - sufijo.length, qa.value.length - sufijo.length);
  qa.dispatchEvent(new Event('input'));
}

/** What a click on a [[link]] does: open the task, note or project, or create the note it names. */
async function abrirEnlace(destino, resuelto, proyecto = '') {
  try {
    const d = resuelto || await api.enlace(destino, proyecto);
    if (d.tipo === 'tarea') abrir(d.ref);
    else if (d.tipo === 'proyecto') ir(`#/p/${d.ref}`);
    else ir(`#/n/${d.ref}`);
    if (!resuelto && d.tipo === 'nota') avisar(`Nota «${d.titulo}» creada`);
  } catch (err) {
    avisar(err.message, { error: true });
  }
}

function vistaInicio() {
  return preferencia('vista-inicio', 'mes');
}

function cambiarVista(v) {
  preferencia('vista-inicio', v, true);
  recargar();
}

function sumarMeses(m, n) {
  const [y, mm] = m.split('-').map(Number);
  const d = new Date(Date.UTC(y, mm - 1 + n, 1));
  return d.toISOString().slice(0, 7);
}

const ctx = {
  ir,
  abrirEnlace,
  conmutadorVista: () => h('div.pildoras.pildoras--sobrio.vista-inicio', { role: 'group', 'aria-label': 'Vista' },
    [['mes', 'Mes'], ['semana', 'Semana']].map(([v, t]) =>
      h('button.pildora', { 'aria-pressed': String(vistaInicio() === v), onclick: () => cambiarVista(v) }, t))),
  irMes: (n) => {
    estado.mes = n === 0 ? null : sumarMeses(estado.semana.mes, n);
    estado.diaSel = null;
    recargar();
  },
  diaSeleccionado: () => estado.diaSel,
  elegirDia: (fecha) => { estado.diaSel = fecha; pintar(true); },
  verSemana: (fecha) => {
    estado.lunes = lunesDe(fecha) === lunesActual() ? null : lunesDe(fecha);
    cambiarVista('semana');
  },
  lunesActual,
  anadirEn,
  irSemana: (dias) => {
    estado.lunes = dias === 0 ? null : sumarDias(estado.semana.lunes, dias);
    recargar();
  },
  abrir: (id) => abrir(id),
  completar,
  manana,
  moverA,
  hoy: () => estado.datos?.hoy,
  hecha: (id) => estado.completando.has(id),
  filtro,
  preferencia,
  recargar: () => recargar(),
  pintar: () => pintar(true),
  proyectos: () => estado.datos?.todos_proyectos || [],
  quickAdd: ({ compacto = false, proyecto = null, placeholder } = {}) => quickAdd({
    compacto,
    placeholder: placeholder || 'Añadir tarea… «Llamar al dentista mañana 10:00 #Salud p1»',
    hoy: () => estado.datos.hoy,
    contexto: () => ({ proyecto, ambito: preferencia('ambito', 'todo') }),
    alCrear: () => recargar(),
  }).el,
};

function pintarRail(r) {
  const nav = document.getElementById('rail-nav');
  const actual = r === '#/inicio' || r === '#/ajustes' ? r : modNotas.rutaNotas(r) ? '#/notas' : '#/tareas';
  vaciar(nav, MODULOS.map(([hash, ico, texto]) => h('a.rail__btn', {
    href: hash, 'aria-current': hash === actual ? 'page' : null, 'aria-label': texto, title: texto,
  }, icono(ico), h('span.rail__etiqueta', texto))),
  h('button.rail__btn.rail__buscar', { 'aria-label': 'Buscar (Ctrl+K)', title: 'Buscar (Ctrl+K)', onclick: abrirBuscador },
    icono('buscar'), h('span.rail__etiqueta', 'Buscar')),
  h('a.rail__btn.rail__ajustes', { href: '#/ajustes', 'aria-current': actual === '#/ajustes' ? 'page' : null, 'aria-label': 'Ajustes', title: 'Ajustes' },
    icono('ajustes'), h('span.rail__etiqueta', 'Ajustes')));
}

/** Repaints unless nothing visible changed (the tablet paints slowly). */
function pintar(forzar = false) {
  const d = estado.datos;
  if (!d) return;
  const r = ruta();
  if (LISTAS.test(r)) preferencia('ultima-lista', r, true);
  if (modNotas.rutaNotas(r)) {
    preferencia('ultima-nota', r, true);
    // The note editor refreshes itself (modNotas.alCambiarDatos); a repaint would reset what is being typed.
    if (!forzar && estado.rutaPintada === r) return;
  }
  const conSemana = r === '#/inicio' || r === '#/kiosco';
  const huella = `${r}|${JSON.stringify(d)}|${conSemana ? `${JSON.stringify(estado.semana)}|${estado.diaSel}` : ''}|${[...estado.completando.keys()]}`;
  if (!forzar && huella === estado.huella) return;
  const vista = document.getElementById('vista');
  // Keep whatever is being typed in a quick-add box across repaints.
  const activo = document.activeElement;
  const enFormulario = vista.contains(activo) && /^(INPUT|TEXTAREA|SELECT)$/.test(activo.tagName) && !activo.classList.contains('qa__input');
  if (!forzar && enFormulario) return; // do not wipe a half-typed rename or new project
  const escribiendo = activo?.classList.contains('qa__input') && activo.value ? activo.value : null;
  estado.huella = huella;
  estado.rutaPintada = r;
  pintarRail(r);
  modoKiosco(r === '#/kiosco');
  let contenido;
  if (conSemana) {
    contenido = estado.semana.mes ? mes(d, estado.semana, ctx) : inicio(d, estado.semana, ctx);
    if (r === '#/kiosco') contenido = marcoKiosco(contenido);
  } else if (r === '#/ajustes') contenido = ajustes();
  else if (modNotas.rutaNotas(r)) contenido = modNotas.notas(d, r, ctx);
  else contenido = tareas(d, r, ctx);
  vaciar(vista, contenido);
  if (r === '#/kiosco') reloj(); // its big clock is new: fill it now, not at the next tick
  if (escribiendo) {
    const qa = vista.querySelector('.qa__input');
    if (qa) { qa.value = escribiendo; qa.focus(); qa.dispatchEvent(new Event('input')); }
  }
}

async function recargar() {
  try {
    const ambito = preferencia('ambito', 'todo');
    const calendario = vistaInicio() === 'mes' ? api.mes(ambito, estado.mes) : api.semana(ambito, estado.lunes);
    [estado.datos, estado.semana] = await Promise.all([api.panel(ambito), calendario]);
    pintar();
  } catch (err) {
    avisar(err.message, { error: true });
  }
}

async function sondear() {
  try {
    const v = await api.version();
    if (estado.version.app && v.app !== estado.version.app && !sucio()) {
      location.reload();
      return;
    }
    const cambio = estado.version.datos && v.datos !== estado.version.datos;
    estado.version = v;
    if (cambio) {
      await recargar();
      await alCambiarDatos();
      await modNotas.alCambiarDatos();
    }
  } catch {
    /* offline for a moment: try again on the next tick */
  }
}

function reloj() {
  const ahora = new Date();
  const texto = ahora.toLocaleTimeString('es-ES', { timeZone: estado.datos?.zona || 'Europe/Madrid', hour: '2-digit', minute: '2-digit' });
  document.getElementById('reloj').textContent = texto;
  const grande = document.getElementById('reloj-kiosco');
  if (grande) grande.textContent = texto;
}

async function arrancar() {
  iniciarFicha(ctx);
  iniciarBuscador(ctx);
  reloj();
  setInterval(reloj, 10_000);
  await recargar();
  estado.version = await api.version().catch(() => estado.version);
  setInterval(sondear, SONDEO_MS);
  setInterval(recargar, 60_000); // «Vencida», «A continuación» and the greeting move with the clock
  window.addEventListener('hashchange', () => { modNotas.guardarPendiente(); pintar(true); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) modNotas.guardarPendiente(); });
}

arrancar();
