// Task views: sidebar, Hoy, Próximo, Bandeja, a project (list or board) and, on the phone, the project list.
import { api } from './api.js';
import { avisar, diaCorto, fechaLarga, h, icono, plural, sumarDias, vaciar } from './dom.js';
import { carta, fila } from './fila.js';
import { notasDeProyecto } from './notas.js';

const GRUPOS = [
  ['en-curso', 'En curso'],
  ['pendiente', 'Pendiente'],
  ['esperando', 'Esperando'],
];
const AMBITOS = { laboral: 'Laboral', personal: 'Personal' };
let masAdelanteAbierto = false;

function filas(lista, d, ctx, opciones = {}) {
  return lista.map((t) => fila(t, { hoy: d.hoy, alAbrir: ctx.abrir, alCompletar: ctx.completar, alManana: ctx.manana, hecha: ctx.hecha(t.id), ...opciones }));
}

function nuevoProyecto(ctx, d) {
  const cont = h('div');
  const boton = h('button.lat.lat--nuevo', { onclick: abrirFormulario }, icono('mas'), h('span', 'Nuevo proyecto'));
  cont.append(boton);

  function abrirFormulario() {
    let ambito = d.ambito === 'personal' ? 'personal' : 'laboral';
    const nombre = h('input.campo', { placeholder: 'Nombre del proyecto', maxLength: 60, 'aria-label': 'Nombre del proyecto' });
    const pildoras = h('div.pildoras.pildoras--sobrio', ['laboral', 'personal'].map((amb) =>
      h('button.pildora', { 'aria-pressed': String(amb === ambito), onclick: (e) => {
        ambito = amb;
        for (const b of pildoras.children) b.setAttribute('aria-pressed', String(b === e.currentTarget));
      } }, AMBITOS[amb])));
    const crear = async () => {
      try {
        const p = await api.nuevoProyecto(nombre.value, ambito);
        avisar(`Proyecto «${p.nombre}» creado`);
        ctx.ir(`#/p/${p.slug}`);
        ctx.recargar();
      } catch (err) {
        avisar(err.message, { error: true });
      }
    };
    nombre.addEventListener('keydown', (e) => { if (e.key === 'Enter') crear(); if (e.key === 'Escape') vaciar(cont, boton); });
    vaciar(cont, h('div.lat--nuevo-form', nombre, h('div', pildoras),
      h('div', h('button.boton.boton--principal', { onclick: crear }, 'Crear proyecto'),
        h('button.boton.boton--fantasma', { onclick: () => vaciar(cont, boton) }, 'Cancelar'))));
    nombre.focus();
  }
  return cont;
}

export function lateral(d, ruta, ctx) {
  const enlace = (hash, ico, texto, n) => h('a.lat', { href: hash, 'aria-current': ruta === hash ? 'page' : null },
    ico, h('span', texto), h('span.lat__n', n));
  const grupos = ['laboral', 'personal'].map((amb) => {
    const lista = d.proyectos.filter((p) => p.ambito === amb);
    if (!lista.length) return null;
    return [h('h3', AMBITOS[amb]), lista.map((p) => enlace(`#/p/${p.slug}`, h(`span.punto.punto--${amb}`), p.nombre, p.abiertas))];
  });
  return h('nav.tarjeta.lateral', { 'aria-label': 'Listas y proyectos' },
    enlace('#/hoy', icono('lista'), 'Hoy', d.conteos.hoy),
    enlace('#/proximo', icono('flecha'), 'Próximo', d.conteos.proximo),
    enlace('#/bandeja', icono('bandeja'), 'Bandeja', d.conteos.bandeja),
    grupos,
    nuevoProyecto(ctx, d));
}

function cabecera(titulo, sub, ...extra) {
  return h('header.principal__cab', h('div', h('h1', titulo), sub && h('p', sub)), ...extra);
}

function vistaLista(d, ctx, clave) {
  const porId = Object.fromEntries(d.tareas.map((t) => [t.id, t]));
  const ids = d.vistas[clave];
  const qa = ctx.quickAdd({ compacto: true });
  if (clave === 'hoy') {
    return [cabecera('Hoy', `${fechaLarga(d.hoy)} · ${plural(ids.length, 'tarea', 'tareas')}`, ctx.filtro()), qa,
      ids.length ? filas(ids.map((id) => porId[id]), d, ctx) : h('p.vacio', 'Nada para hoy.')];
  }
  if (clave === 'bandeja') {
    return [cabecera('Bandeja', 'Lo que no tiene proyecto todavía', ctx.filtro()), qa,
      ids.length ? filas(ids.map((id) => porId[id]), d, ctx) : h('p.vacio', 'La bandeja está vacía.')];
  }
  const porDia = new Map();
  for (const id of ids) {
    const t = porId[id];
    if (!porDia.has(t.fecha)) porDia.set(t.fecha, []);
    porDia.get(t.fecha).push(t);
  }
  const titulo = (dia) => (dia === d.hoy ? 'Hoy' : dia === sumarDias(d.hoy, 1) ? 'Mañana' : null);
  return [cabecera('Próximo', 'Las dos próximas semanas', ctx.filtro()), qa,
    porDia.size ? [...porDia].map(([dia, lista]) => h('section.grupo',
      h('h2.dia', titulo(dia) || diaCorto(dia), titulo(dia) && h('small', diaCorto(dia))),
      filas(lista, d, ctx))) : h('p.vacio', 'Nada con fecha en las dos próximas semanas.')];
}

function tituloProyecto(p, ctx) {
  const h1 = h('h1', p.nombre, h(`span.chip.chip--${p.ambito}`, AMBITOS[p.ambito]),
    h('button.icono-btn', { 'aria-label': 'Renombrar proyecto', onclick: editar }, icono('lapiz')));
  const cont = h('div', h1);
  function editar() {
    const input = h('input.campo', { value: p.nombre, maxLength: 60, 'aria-label': 'Nombre nuevo' });
    const guardar = async () => {
      try {
        const nuevo = await api.renombrarProyecto(p.slug, input.value);
        ctx.recargar();
        if (nuevo.slug !== p.slug) ctx.ir(`#/p/${nuevo.slug}`); // the address follows the new name
      } catch (err) {
        avisar(err.message, { error: true });
      }
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape') vaciar(cont, h1); });
    vaciar(cont, h('div.renombrar', input, h('button.boton.boton--principal', { onclick: guardar }, 'Guardar'),
      h('button.boton.boton--fantasma', { onclick: () => vaciar(cont, h1) }, 'Cancelar')));
    input.focus();
    input.select();
  }
  return cont;
}

function vistaProyecto(d, ctx, slug) {
  const p = d.proyectos.find((x) => x.slug === slug);
  if (!p) {
    return [cabecera('Proyecto', 'Este proyecto no está en el filtro actual o no existe.', ctx.filtro())];
  }
  const suyas = d.tareas.filter((t) => t.proyecto === slug);
  const modo = ctx.preferencia(`modo:${slug}`, 'lista');
  const conmutador = h('div.pildoras.pildoras--sobrio', [['lista', 'Lista'], ['tablero', 'Tablero'], ['notas', 'Notas']].map(([m, texto]) =>
    h('button.pildora', { 'aria-pressed': String(m === modo), onclick: () => { ctx.preferencia(`modo:${slug}`, m, true); ctx.pintar(); } }, texto)));
  const activas = suyas.filter((t) => t.estado !== 'mas-adelante');
  const cab = h('header.principal__cab',
    h('div', tituloProyecto(p, ctx), h('p', `${plural(activas.length, 'pendiente', 'pendientes')} · ${p.hechas} hechas esta semana`)),
    conmutador);
  if (modo === 'notas') return [cab, notasDeProyecto(slug, ctx)];
  const qa = ctx.quickAdd({ compacto: true, proyecto: slug, placeholder: `Añadir tarea a ${p.nombre}…` });

  if (modo === 'tablero') {
    const columnas = [...GRUPOS, ['mas-adelante', 'Más adelante']].map(([estado, nombre]) => {
      const lista = suyas.filter((t) => t.estado === estado);
      return h('section.columna', h('h2', nombre, h('small', lista.length)),
        lista.map((t) => carta(t, { hoy: d.hoy, alAbrir: ctx.abrir })));
    });
    return [cab, qa, h('div.tablero', columnas)];
  }

  const grupos = GRUPOS.map(([estado, nombre]) => {
    const lista = suyas.filter((t) => t.estado === estado);
    if (!lista.length) return null;
    return h('section.grupo', h('h2', nombre, h('small', lista.length)), filas(lista, d, ctx, { ambito: false, proyecto: false }));
  });
  const luego = suyas.filter((t) => t.estado === 'mas-adelante');
  const bloqueLuego = luego.length > 0 && h('div',
    h('button.mas-adelante-btn', {
      'aria-expanded': String(masAdelanteAbierto),
      onclick: () => { masAdelanteAbierto = !masAdelanteAbierto; ctx.pintar(); },
    }, icono('derecha', 'ico--s'), `Más adelante · ${luego.length}`),
    masAdelanteAbierto && h('div', filas(luego, d, ctx, { ambito: false, proyecto: false })));
  return [cab, qa, grupos, !activas.length && h('p.vacio', 'No hay nada pendiente en este proyecto.'), bloqueLuego];
}

/** Phone only: the sidebar's lists as a strip of chips that scrolls sideways. */
function tiraMovil(d, ruta, ctx) {
  const chip = (hash, texto, extra = null) => h('a.tira__chip', { href: hash, 'aria-current': ruta === hash ? 'page' : null }, extra, texto);
  const nuevo = h('div.tira__nuevo');
  const chips = h('nav.tira__chips', { 'aria-label': 'Listas y proyectos' },
      chip('#/hoy', `Hoy · ${d.conteos.hoy}`),
      chip('#/proximo', `Próximo · ${d.conteos.proximo}`),
      chip('#/bandeja', `Bandeja · ${d.conteos.bandeja}`),
      d.proyectos.map((p) => chip(`#/p/${p.slug}`, p.nombre, h(`span.punto.punto--${p.ambito}`))),
      h('button.tira__chip', { onclick: () => vaciar(nuevo, nuevoProyecto(ctx, d)).querySelector('button')?.click() },
        icono('mas', 'ico--s'), 'Proyecto'));
  // Bring the current list into view (a project far to the right would otherwise be hidden).
  requestAnimationFrame(() => {
    const activo = chips.querySelector('[aria-current="page"]');
    if (activo) chips.scrollLeft = activo.offsetLeft - chips.offsetLeft - 16;
  });
  return h('div.tira', chips, nuevo);
}

export function tareas(d, ruta, ctx) {
  const contenido = ruta.startsWith('#/p/')
    ? vistaProyecto(d, ctx, decodeURIComponent(ruta.slice(4)))
    : vistaLista(d, ctx, ruta.slice(2));
  return h('div.tareas', lateral(d, ruta, ctx), h('div.tareas__main', tiraMovil(d, ruta, ctx), h('section.tarjeta.principal', contenido)));
}
