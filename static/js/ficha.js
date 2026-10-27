// Task sheet: edit every field, subtasks, context and log. Saves with the card's version, so a
// change made elsewhere meanwhile (CLI, agent, another device) is never overwritten silently.
import { api } from './api.js';
import { avisar, h, icono, sumarDias, vaciar } from './dom.js';
import { editorMarkdown } from './editor.js';
import { menciones } from './notas.js';

const ESTADOS = [['pendiente', 'Pendiente'], ['en-curso', 'En curso'], ['esperando', 'Esperando'], ['mas-adelante', 'Más adelante']];
const CAMPOS = ['titulo', 'estado', 'prioridad', 'proyecto', 'ambito', 'fecha', 'hora', 'duracion', 'repetir', 'hasta',
  'etiquetas', 'esperando_a', 'revisar', 'caso', 'contexto'];

let ctx = null;
let actual = null; // the card as the server last sent it
let form = {}; // what the sheet shows, edited in place
let avisoCambio = null; // text of the banner shown above the body
let errorGuardado = '';

const hoja = () => document.getElementById('hoja');
const velo = () => document.getElementById('velo');

function desdeServidor(t) {
  const f = {};
  for (const k of CAMPOS) f[k] = k === 'etiquetas' ? t.etiquetas.map((e) => `@${e}`).join(' ') : String(t[k] ?? '');
  return f;
}

function cambiados() {
  const base = desdeServidor(actual);
  return CAMPOS.filter((k) => form[k].trim() !== base[k].trim());
}

export function sucio() {
  return !!actual && cambiados().length > 0;
}

export function iniciarFicha(contexto) {
  ctx = contexto;
  velo().addEventListener('click', () => cerrar());
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && actual) cerrar(); });
}

export async function abrir(id) {
  try {
    actual = await api.ficha(id);
  } catch (err) {
    avisar(err.message, { error: true });
    return;
  }
  form = desdeServidor(actual);
  avisoCambio = null;
  errorGuardado = '';
  pintar();
  hoja().hidden = false;
  velo().hidden = false;
  hoja().querySelector('.hoja__titulo')?.focus();
}

export function cerrar(forzar = false) {
  if (!actual) return;
  if (!forzar && sucio()) {
    avisoCambio = { texto: 'Tienes cambios sin guardar.', accion: 'Descartarlos y cerrar', alPulsar: () => cerrar(true) };
    pintar();
    return;
  }
  actual = null;
  hoja().hidden = true;
  velo().hidden = true;
  vaciar(hoja());
}

/** Called when data changed somewhere: refresh the open card without stepping on unsaved edits. */
export async function alCambiarDatos() {
  if (!actual) return;
  let nueva;
  try {
    nueva = await api.ficha(actual.id);
  } catch (err) {
    if (err.status === 404) cerrar(true);
    return;
  }
  if (nueva.version === actual.version) return;
  if (!sucio()) {
    actual = nueva;
    form = desdeServidor(nueva);
    pintar();
    return;
  }
  avisoCambio = {
    texto: 'Esta tarea ha cambiado fuera del panel.',
    accion: 'Ver la versión nueva (pierdes tus cambios)',
    alPulsar: () => { actual = nueva; form = desdeServidor(nueva); avisoCambio = null; pintar(); },
  };
  pintar();
}

function etiquetasLista(texto) {
  return texto.split(/[\s,]+/).map((e) => e.replace(/^@/, '').trim()).filter(Boolean);
}

async function guardar() {
  const lista = cambiados();
  if (!lista.length) return;
  errorGuardado = '';
  let t = actual;
  try {
    if (lista.includes('estado') || (form.estado === 'esperando' && (lista.includes('esperando_a') || lista.includes('revisar')))) {
      t = await api.estado(t.id, form.estado, t.version, { esperando_a: form.esperando_a, revisar: form.revisar });
    }
    const editables = lista.filter((k) => !['estado', 'contexto'].includes(k)
      && !(['esperando_a', 'revisar'].includes(k) && form.estado === 'esperando'));
    if (editables.length) {
      const cambios = Object.fromEntries(editables.map((k) => [k, k === 'etiquetas' ? etiquetasLista(form[k]) : form[k]]));
      t = await api.editar(t.id, cambios, t.version);
    }
    if (lista.includes('contexto')) t = await api.contexto(t.id, form.contexto, t.version);
    actual = t;
    form = desdeServidor(t);
    avisoCambio = null;
    avisar('Guardado');
    ctx.recargar();
  } catch (err) {
    actual = t; // keep whatever part was saved
    if (err.status === 409) {
      avisoCambio = {
        texto: 'No se ha guardado: la tarea cambió fuera del panel mientras la editabas.',
        accion: 'Ver la versión nueva (pierdes tus cambios)',
        alPulsar: () => abrir(t.id),
      };
    } else {
      errorGuardado = err.message;
    }
  }
  pintar();
}

async function accionInmediata(promesa) {
  try {
    const t = await promesa;
    const pendientes = Object.fromEntries(cambiados().map((k) => [k, form[k]]));
    actual = t;
    form = { ...desdeServidor(t), ...pendientes };
    ctx.recargar();
  } catch (err) {
    if (err.status === 409) await alCambiarDatos();
    else avisar(err.message, { error: true });
  }
  pintar();
}

/** Hoy, Mañana, El lunes, Sin fecha: one tap sets the date; «Guardar cambios» keeps it. */
function fechasRapidas() {
  const hoy = ctx.hoy?.();
  if (!hoy) return null;
  const dia = (new Date(`${hoy}T12:00:00`).getDay() + 6) % 7;
  const opciones = [['Hoy', hoy], ['Mañana', sumarDias(hoy, 1)], ['El lunes', sumarDias(hoy, 7 - dia)], ['Sin fecha', '']];
  return h('div.pildoras.pildoras--sobrio.ancho.fechas-rapidas', { role: 'group', 'aria-label': 'Fecha rápida' },
    opciones.map(([texto, fecha]) => h('button.pildora', {
      type: 'button',
      'aria-pressed': String(form.fecha === fecha),
      onclick: () => {
        form.fecha = fecha;
        if (!fecha) form.hora = form.duracion = '';
        pintar();
      },
    }, texto)));
}

function campo(etiqueta, clave, attrs = {}, clase = '') {
  const tag = attrs.tag || 'input';
  delete attrs.tag;
  const el = h(`${tag}.campo`, { ...attrs, value: form[clave] });
  el.value = form[clave];
  el.addEventListener('input', () => { form[clave] = el.value; actualizarPie(); });
  return h(`label${clase ? `.${clase}` : ''}`, etiqueta, el);
}

function selector(etiqueta, clave, opciones, alCambiar) {
  const el = h('select.campo', opciones.map(([v, t]) => h('option', { value: v, selected: v === form[clave] }, t)));
  el.addEventListener('change', () => { form[clave] = el.value; alCambiar ? alCambiar() : actualizarPie(); });
  return h('label', etiqueta, el);
}

function actualizarPie() {
  const boton = hoja().querySelector('[data-guardar]');
  if (boton) boton.disabled = !sucio();
}

function subtareas() {
  const nueva = h('input.campo', { placeholder: 'Añadir subtarea', maxLength: 200, 'aria-label': 'Nueva subtarea' });
  nueva.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && nueva.value.trim()) accionInmediata(api.subtarea(actual.id, 'anadir', nueva.value, actual.version));
  });
  return [
    h('h3', 'Subtareas'),
    actual.subtareas.map((s, i) => h(`div.sub${s.hecha ? '.sub--hecha' : ''}`,
      h('label',
        h('input', { type: 'checkbox', checked: s.hecha, onchange: () => accionInmediata(
          api.subtarea(actual.id, s.hecha ? 'desmarcar' : 'marcar', String(i + 1), actual.version)) }),
        h('span', s.texto)),
      h('button.icono-btn', { 'aria-label': `Quitar «${s.texto}»`,
        onclick: () => accionInmediata(api.subtarea(actual.id, 'quitar', String(i + 1), actual.version)) }, icono('cerrar', 'ico--s')))),
    nueva,
  ];
}

let editorContexto = null;
let editorDe = null; // id+version the editor was built for, so a repaint keeps the cursor and what is typed

function contexto() {
  const clave = `${actual.id}`;
  if (!editorContexto || editorDe !== clave) {
    editorContexto = editorMarkdown({
      valor: form.contexto, filas: 5, id: 'ficha-contexto',
      modo: form.contexto.trim() ? 'ver' : 'editar',
      placeholder: 'Lo que hace falta para retomarla. [[ enlaza una nota, tarea o proyecto.',
      alCambiar: (texto) => { form.contexto = texto; actualizarPie(); },
      alEnlace: (destino, resuelto) => { if (!sucio()) cerrar(true); ctx.abrirEnlace(destino, resuelto, form.proyecto); },
    });
    editorDe = clave;
  } else if (editorContexto.valor() !== form.contexto) {
    editorContexto.poner(form.contexto);
  }
  return editorContexto.el;
}

function bitacora() {
  const nota = h('input.campo', { placeholder: 'Apuntar algo en la bitácora', maxLength: 4000, 'aria-label': 'Nota' });
  nota.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && nota.value.trim()) accionInmediata(api.anotar(actual.id, nota.value));
  });
  return [h('h3', 'Bitácora'), nota, h('ul.bitacora', [...actual.bitacora].reverse().map((l) => h('li', l)))];
}

function pintar() {
  if (!actual) return;
  const conProyecto = !!form.proyecto;
  const titulo = h('textarea.hoja__titulo', { rows: 2, maxLength: 200, 'aria-label': 'Título' });
  titulo.value = form.titulo;
  titulo.addEventListener('input', () => { form.titulo = titulo.value.replace(/\n/g, ' '); actualizarPie(); });

  const prios = h('div.prios', ['p1', 'p2', 'p3', 'p4'].map((p) => h(`button.prio-${p}`, {
    'aria-pressed': String(form.prioridad === p),
    onclick: () => { form.prioridad = p; pintar(); },
  }, p)));

  const cuerpo = h('div.hoja__cuerpo',
    h('div.rejilla',
      selector('Estado', 'estado', ESTADOS, () => pintar()),
      h('label', 'Prioridad', prios),
      selector('Proyecto', 'proyecto', [['', 'Sin proyecto'], ...ctx.proyectos().map((p) => [p.slug, p.nombre])], () => pintar()),
      conProyecto
        ? h('label', 'Ámbito', h('div.campo', form.ambito === 'laboral' ? 'Laboral (del proyecto)' : 'Personal (del proyecto)'))
        : selector('Ámbito', 'ambito', [['personal', 'Personal'], ['laboral', 'Laboral']]),
      campo('Fecha', 'fecha', { type: 'date' }),
      campo('Hora', 'hora', { type: 'time', step: 300 }),
      fechasRapidas(),
      campo('Duración (min)', 'duracion', { type: 'number', min: 5, max: 720, step: 5, inputMode: 'numeric' }),
      campo('Repetir', 'repetir', { placeholder: 'cada lunes, cada 3 días…' }),
      form.repetir && campo('Hasta (vacío: sin final)', 'hasta', { type: 'date' }),
      form.estado === 'esperando' && campo('¿A quién esperas?', 'esperando_a', { maxLength: 80 }),
      ['esperando', 'mas-adelante'].includes(form.estado) && campo('¿Cuándo la vuelves a mirar?', 'revisar', { type: 'date' }),
      campo('Etiquetas', 'etiquetas', { placeholder: '@teléfono @casa' }, 'ancho'),
      campo('Referencia (expediente, pedido…)', 'caso', { maxLength: 30 }, 'ancho')),
    subtareas(),
    h('h3', 'Contexto'),
    contexto(),
    menciones(actual.menciones || [], ctx, 'Ninguna nota ni tarea enlaza a esta tarea.'),
    bitacora());

  vaciar(hoja(),
    h('div.hoja__cab',
      h(`button.fila__check.prio-${form.prioridad}`, { 'aria-label': 'Marcar como hecha', onclick: () => { const t = actual; cerrar(true); ctx.completar(t); } },
        h('span', icono('check'))),
      titulo,
      h('button.icono-btn', { 'aria-label': 'Cerrar', onclick: () => cerrar() }, icono('cerrar'))),
    avisoCambio && h('div.hoja__aviso', avisoCambio.texto, h('button', { onclick: avisoCambio.alPulsar }, avisoCambio.accion)),
    cuerpo,
    errorGuardado && h('div.hoja__aviso', errorGuardado),
    h('footer.hoja__pie',
      h('button.boton.boton--fantasma', { onclick: () => accionInmediata(api.estado(actual.id, 'soltada', actual.version)).then(() => cerrar(true)) },
        actual.repetir ? 'Soltar todas' : 'Soltar tarea'),
      actual.repetir && actual.estado !== 'hecha' && h('button.boton.boton--fantasma', {
        onclick: async () => {
          const antes = actual.fecha;
          await accionInmediata(api.saltar(actual.id, actual.version));
          if (actual.fecha !== antes) avisar(actual.estado === 'soltada' ? 'Saltada; era la última' : `Saltada; la siguiente, ${actual.cuando.toLowerCase()}`);
        },
      }, 'Saltar esta vez'),

      h('button.boton.boton--principal', { 'data-guardar': '', disabled: !sucio(), onclick: guardar }, 'Guardar cambios')));
}
