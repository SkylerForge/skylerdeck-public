// The Notas module: daily note, recent notes, diary, tags, and the note editor (autosave with
// the note's version: an outside change never gets overwritten). Also the «Mencionado en» list
// and the notes tab of a project, which other modules reuse.
import { api } from './api.js';
import { avisar, diaCorto, h, icono, plural, vaciar } from './dom.js';
import { editorMarkdown } from './editor.js';
import { fila } from './fila.js';

const AUTOGUARDADO_MS = 1200;
const LISTAS = [
  ['#/notas/hoy', 'calendario', 'Nota del día'],
  ['#/notas/recientes', 'reloj', 'Recientes'],
  ['#/notas/diario', 'nota', 'Diario'],
  ['#/notas/etiquetas', 'arroba', 'Etiquetas'],
];

// The open note. Kept here so repaints of the rest of the page never touch what is being typed.
const est = { slug: null, nota: null, editor: null, pendiente: null, guardando: false, conflicto: null, estado: '', raiz: null, confirmarBorrado: false };

export function rutaNotas(r) {
  return /^#\/(notas(\/(hoy|recientes|diario|etiquetas))?|n\/.+|e\/.+)$/.test(r);
}

const hoySlug = (d) => d.hoy;

// ---------- pieces reused by other modules ----------

export function menciones(lista, ctx, vacio = 'Nada enlaza aquí todavía.') {
  return h('section.menciones',
    h('h3', 'Mencionado en', lista.length > 0 && h('small', lista.length)),
    lista.length ? lista.map((m) => h('button.mencion', {
      onclick: () => (m.tipo === 'tarea' ? ctx.abrir(m.ref) : ctx.ir(`#/n/${m.ref}`)),
    }, icono(m.tipo === 'tarea' ? 'lista' : 'nota', 'ico--s'), h('span.mencion__titulo', m.titulo), h('span.mencion__fragmento', m.fragmento)))
      : h('p.meta', vacio));
}

function tarjetaNota(n, ctx) {
  return h('button.nota-fila', { onclick: () => ctx.ir(`#/n/${n.slug}`) },
    h('span.nota-fila__titulo', icono(n.tipo === 'diario' ? 'calendario' : 'nota', 'ico--s'), n.titulo),
    n.resumen && h('span.nota-fila__resumen', n.resumen),
    h('span.nota-fila__meta', [n.actualizada && `Editada ${diaCorto(n.actualizada.slice(0, 10))}`, ...n.etiquetas.map((e) => `@${e}`)].filter(Boolean).join(' · ')));
}

function nuevaNota(ctx, proyecto = '') {
  const cont = h('div.nueva-nota');
  const boton = h('button.anadir', { onclick: abrir }, icono('mas', 'ico--s'), 'Nueva nota');
  cont.append(boton);
  function abrir() {
    const titulo = h('input.campo', { placeholder: 'Título de la nota', maxLength: 120, 'aria-label': 'Título de la nota' });
    const crear = async () => {
      try {
        const n = await api.nuevaNota(titulo.value, '', proyecto);
        ctx.ir(`#/n/${n.slug}`);
      } catch (err) {
        avisar(err.message, { error: true });
      }
    };
    titulo.addEventListener('keydown', (e) => { if (e.key === 'Enter') crear(); if (e.key === 'Escape') vaciar(cont, boton); });
    vaciar(cont, h('div.renombrar', titulo, h('button.boton.boton--principal', { onclick: crear }, 'Crear'),
      h('button.boton.boton--fantasma', { onclick: () => vaciar(cont, boton) }, 'Cancelar')));
    titulo.focus();
  }
  return cont;
}

/** The «Notas» tab of a project: its notes and the notes and tasks that mention it. */
export function notasDeProyecto(slug, ctx) {
  const caja = h('div', h('p.meta', 'Cargando notas…'));
  api.notas({ proyecto: slug }).then((r) => {
    vaciar(caja,
      nuevaNota(ctx, slug),
      r.notas.length ? r.notas.map((n) => tarjetaNota(n, ctx)) : h('p.vacio', 'Este proyecto aún no tiene notas.'),
      menciones(r.menciones, ctx, 'Ninguna nota ni tarea enlaza a este proyecto.'));
  }).catch((err) => vaciar(caja, h('p.error-campo', err.message)));
  return caja;
}

// ---------- navigation ----------

function lateral(ruta, d) {
  const enlace = (hash, ico, texto) => h('a.lat', { href: hash, 'aria-current': ruta === hash ? 'page' : null }, icono(ico), h('span', texto));
  return h('nav.tarjeta.lateral', { 'aria-label': 'Notas' }, LISTAS.map(([hash, ico, texto]) => enlace(hash, ico, texto)));
}

function tira(ruta) {
  return h('div.tira', h('nav.tira__chips', { 'aria-label': 'Notas' }, LISTAS.map(([hash, , texto]) =>
    h('a.tira__chip', { href: hash, 'aria-current': ruta === hash ? 'page' : null }, texto))));
}

// ---------- list views ----------

function cargar(contenedor, promesa, pintar) {
  promesa.then((r) => vaciar(contenedor, pintar(r))).catch((err) => vaciar(contenedor, h('p.error-campo', err.message)));
  return contenedor;
}

function vistaRecientes(ctx, tipo) {
  const titulo = tipo === 'diario' ? 'Diario' : 'Recientes';
  const sub = tipo === 'diario' ? 'Las notas de cada día' : 'Todas las notas, la última editada primero';
  return [
    h('header.principal__cab', h('div', h('h1', titulo), h('p', sub))),
    tipo !== 'diario' && nuevaNota(ctx),
    cargar(h('div', h('p.meta', 'Cargando…')), api.notas(tipo === 'diario' ? { tipo } : {}),
      (r) => (r.notas.length ? r.notas.map((n) => tarjetaNota(n, ctx)) : h('p.vacio', 'Todavía no hay notas.'))),
  ];
}

function vistaEtiquetas() {
  return [
    h('header.principal__cab', h('div', h('h1', 'Etiquetas'), h('p', 'Las mismas @etiquetas en tareas y notas'))),
    cargar(h('div', h('p.meta', 'Cargando…')), api.etiquetas(), (lista) => (lista.length
      ? h('div.etiquetas', lista.map((e) => h('a.etiqueta', { href: `#/e/${encodeURIComponent(e.etiqueta)}` },
        h('span', `@${e.etiqueta}`), h('small', [e.tareas && plural(e.tareas, 'tarea', 'tareas'), e.notas && plural(e.notas, 'nota', 'notas')].filter(Boolean).join(' · ')))))
      : h('p.vacio', 'Aún no hay etiquetas. Escribe @algo en una nota o ponla en una tarea.'))),
  ];
}

function vistaEtiqueta(etiqueta, d, ctx) {
  return [
    h('header.principal__cab', h('div', h('h1', `@${etiqueta}`), h('p', 'Tareas abiertas y notas con esta etiqueta'))),
    cargar(h('div', h('p.meta', 'Cargando…')), api.etiqueta(etiqueta), (r) => [
      h('section.grupo', h('h2', 'Tareas', h('small', r.tareas.length)),
        r.tareas.length ? r.tareas.map((t) => fila(t, { hoy: d.hoy, alAbrir: ctx.abrir, alCompletar: ctx.completar, hecha: ctx.hecha(t.id) }))
          : h('p.meta', 'Ninguna tarea abierta.')),
      h('section.grupo', h('h2', 'Notas', h('small', r.notas.length)),
        r.notas.length ? r.notas.map((n) => tarjetaNota(n, ctx)) : h('p.meta', 'Ninguna nota.')),
    ]),
  ];
}

// ---------- the note editor ----------

function pintarEstado() {
  const el = est.raiz?.querySelector('.nota__estado');
  if (el) el.textContent = est.estado;
}

async function guardar(extra = {}) {
  if (!est.nota || est.conflicto) return;
  clearTimeout(est.pendiente);
  est.pendiente = null;
  if (est.guardando) { est.pendiente = setTimeout(() => guardar(), 300); return; }
  est.guardando = true;
  const texto = est.editor.valor();
  est.estado = 'Guardando…';
  pintarEstado();
  try {
    const n = await api.guardarNota(est.slug, { cuerpo: texto, version: est.nota.existe ? est.nota.version : '', ...extra });
    const titulo = est.nota.titulo;
    est.nota = n;
    est.estado = `Guardada a las ${new Date().toTimeString().slice(0, 5)}`;
    if (extra.titulo && n.titulo !== titulo) avisar('Título cambiado; los enlaces a esta nota se han actualizado');
    if (est.editor.valor() !== texto) programar();
  } catch (err) {
    if (err.status === 409) {
      est.conflicto = 'No se ha guardado: la nota cambió fuera del panel mientras la editabas.';
      pintarNota();
    } else {
      est.estado = `Sin guardar: ${err.message}`;
    }
  } finally {
    est.guardando = false;
    pintarEstado();
  }
}

function programar() {
  est.estado = 'Cambios sin guardar';
  pintarEstado();
  clearTimeout(est.pendiente);
  est.pendiente = setTimeout(() => guardar(), AUTOGUARDADO_MS);
}

/** Saves right away whatever is pending (when leaving the note or hiding the page). */
export function guardarPendiente() {
  if (est.pendiente) guardar();
}

async function abrirNota(slug) {
  est.slug = slug;
  est.conflicto = null;
  est.confirmarBorrado = false;
  est.nota = null;
  est.estado = '';
  try {
    est.nota = await api.nota(slug);
  } catch (err) {
    if (est.raiz) vaciar(est.raiz, h('p.error-campo', err.message));
    return;
  }
  pintarNota();
}

/** Paints the open note. `desdeServidor`: take the text from the server instead of what is in the editor. */
function pintarNota({ desdeServidor = false } = {}) {
  const n = est.nota;
  const ctx = est.ctx;
  if (!n || !est.raiz) return;
  const mismo = est.editor && est.slug === est.editorSlug;
  const textoActual = mismo && !desdeServidor ? est.editor.valor() : n.cuerpo;
  // A refresh keeps the mode, the focus and the cursor, so typing carries on where it was.
  const area = mismo ? est.raiz.querySelector('#nota-cuerpo') : null;
  const foco = area && document.activeElement === area ? [area.selectionStart, area.selectionEnd] : null;
  est.editor = editorMarkdown({
    valor: textoActual, id: 'nota-cuerpo', filas: 16,
    modo: mismo ? est.editor.modo() : (n.cuerpo.trim() ? 'ver' : 'editar'),
    placeholder: 'Escribe en Markdown. [[ para enlazar una tarea, nota o proyecto; @ para etiquetar.',
    alCambiar: () => programar(),
    alEnlace: (destino, resuelto) => { guardarPendiente(); ctx.abrirEnlace(destino, resuelto, n.proyecto); },
  });
  est.editorSlug = est.slug;

  let titulo;
  if (n.tipo === 'diario') {
    titulo = h('h1', n.titulo);
  } else {
    titulo = h('input.nota__titulo', { value: n.titulo, maxLength: 120, 'aria-label': 'Título de la nota' });
    titulo.value = n.titulo;
    const renombrar = () => { if (titulo.value.trim() && titulo.value.trim() !== n.titulo) guardar({ titulo: titulo.value.trim() }); };
    titulo.addEventListener('change', renombrar);
    titulo.addEventListener('keydown', (e) => { if (e.key === 'Enter') titulo.blur(); });
  }
  const proyecto = n.tipo === 'diario' ? h('span.chip.chip--personal', 'Nota del día') : (() => {
    const sel = h('select.campo.nota__proyecto', { 'aria-label': 'Proyecto' },
      [['', 'Sin proyecto'], ...ctx.proyectos().map((p) => [p.slug, p.nombre])].map(([v, t]) => h('option', { value: v, selected: v === n.proyecto }, t)));
    sel.addEventListener('change', () => guardar({ proyecto: sel.value }));
    return sel;
  })();

  const borrar = n.existe && h('button.boton.boton--fantasma.boton--peligro.nota__borrar', {
    onclick: () => { est.confirmarBorrado = true; pintarNota(); },
  }, icono('papelera', 'ico--s'), 'Borrar nota');
  const enlazan = n.menciones.length;
  const confirmar = est.confirmarBorrado && h('div.hoja__aviso.nota__confirmar',
    h('p', `¿Borrar «${n.titulo}»? Irá a la papelera y podrás deshacerlo un momento.`,
      enlazan ? (enlazan === 1 ? ' Una nota o tarea la enlaza; ese enlace quedará roto.' : ` ${enlazan} notas o tareas la enlazan; esos enlaces quedarán rotos.`) : ''),
    h('div.nota__confirmar-botones',
      h('button.boton.boton--peligro-lleno', { onclick: borrarNota }, 'Borrar'),
      h('button.boton.boton--fantasma', { onclick: () => { est.confirmarBorrado = false; pintarNota(); } }, 'Cancelar')));

  vaciar(est.raiz,
    h('header.nota__cab', titulo, h('div.nota__meta', proyecto, h('span.nota__estado.meta', est.estado || (n.existe ? '' : 'Se guardará en cuanto escribas')), borrar)),
    confirmar,
    est.conflicto && h('div.hoja__aviso', est.conflicto,
      h('button', { onclick: verVersionNueva }, 'Ver la versión nueva (pierdes tus cambios)'),
      h('button', { onclick: guardarComoCopia }, 'Guardar mi texto como nota nueva')),
    est.editor.el,
    menciones(n.menciones, ctx));
  if (foco) {
    const nueva = est.raiz.querySelector('#nota-cuerpo');
    nueva.focus();
    nueva.setSelectionRange(Math.min(foco[0], nueva.value.length), Math.min(foco[1], nueva.value.length));
  }
}

async function borrarNota() {
  clearTimeout(est.pendiente);
  est.pendiente = null;
  const { slug, nota } = est;
  try {
    const { papelera } = await api.borrarNota(slug, nota.version);
    est.slug = null;
    est.nota = null;
    est.editorSlug = null;
    est.ctx.ir(nota.tipo === 'diario' ? '#/notas/diario' : '#/notas/recientes');
    avisar(`Nota «${nota.titulo}» borrada`, {
      ms: 8000,
      accion: {
        texto: 'Deshacer',
        alPulsar: async () => {
          try {
            const n = await api.restaurarNota(papelera);
            est.ctx.ir(`#/n/${n.slug}`);
          } catch (err) {
            avisar(err.message, { error: true });
          }
        },
      },
    });
  } catch (err) {
    est.confirmarBorrado = false;
    if (err.status === 409) est.conflicto = 'No se ha borrado: la nota cambió fuera del panel. Mira la versión nueva antes de borrarla.';
    else avisar(err.message, { error: true });
    pintarNota();
  }
}

async function verVersionNueva() {
  clearTimeout(est.pendiente);
  est.pendiente = null;
  try {
    est.nota = await api.nota(est.slug);
  } catch (err) {
    avisar(err.message, { error: true });
    return;
  }
  est.conflicto = null;
  est.estado = '';
  pintarNota({ desdeServidor: true });
}

async function guardarComoCopia() {
  try {
    const copia = await api.nuevaNota(`${est.nota.titulo} (mi versión ${new Date().toTimeString().slice(0, 5)})`, est.editor.valor(), est.nota.proyecto);
    clearTimeout(est.pendiente);
    est.pendiente = null;
    est.editorSlug = null;
    est.ctx.ir(`#/n/${copia.slug}`);
  } catch (err) {
    avisar(err.message, { error: true });
  }
}

/** Data changed somewhere: refresh the open note unless there are unsaved edits. */
export async function alCambiarDatos() {
  if (!est.slug || !est.nota || !est.raiz?.isConnected) return;
  let nueva;
  try { nueva = await api.nota(est.slug); } catch { return; }
  if (nueva.version === est.nota.version || est.conflicto) return; // a conflict is solved by hand, never by a refresh
  if (est.pendiente || est.guardando || (est.editor && est.editor.valor().trim() !== est.nota.cuerpo.trim())) {
    if (!est.guardando) est.conflicto = 'Esta nota ha cambiado fuera del panel y tienes cambios sin guardar.';
    pintarNota();
    return;
  }
  est.nota = nueva;
  pintarNota({ desdeServidor: true });
}

// ---------- entry point ----------

export function notas(d, ruta, ctx) {
  est.ctx = ctx;
  let contenido;
  let actual = ruta;
  if (ruta === '#/notas/hoy' || ruta.startsWith('#/n/')) {
    const slug = ruta === '#/notas/hoy' ? hoySlug(d) : decodeURIComponent(ruta.slice(4));
    if (slug === hoySlug(d)) actual = '#/notas/hoy';
    est.raiz = h('div.nota', h('p.meta', 'Cargando…'));
    if (est.slug !== slug) est.editorSlug = null;
    abrirNota(slug);
    contenido = est.raiz;
  } else {
    est.slug = null;
    if (ruta === '#/notas/diario') contenido = vistaRecientes(ctx, 'diario');
    else if (ruta === '#/notas/etiquetas') contenido = vistaEtiquetas();
    else if (ruta.startsWith('#/e/')) { contenido = vistaEtiqueta(decodeURIComponent(ruta.slice(4)), d, ctx); actual = '#/notas/etiquetas'; }
    else contenido = vistaRecientes(ctx, 'nota');
  }
  return h('div.tareas', lateral(actual, d), h('div.tareas__main', tira(actual), h('section.tarjeta.principal', contenido)));
}
