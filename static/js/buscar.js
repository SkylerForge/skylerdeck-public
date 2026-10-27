// Ctrl+K (or the search button in the rail): jump to any task, note, project or tag.
import { api } from './api.js';
import { avisar, h, icono, vaciar } from './dom.js';

const ICONO = { tarea: 'lista', nota: 'nota', proyecto: 'carpetas', etiqueta: 'arroba', accion: 'flecha' };
const TIPO = { tarea: 'Tarea', nota: 'Nota', proyecto: 'Proyecto', etiqueta: 'Etiqueta', accion: '' };
const PAUSA_MS = 120;

let ctx = null;
let resultados = [];
let activo = 0;
let peticion = 0;
let temporizador = null;
let input = null;
let lista = null;

function acciones(q) {
  const base = [
    { tipo: 'accion', titulo: 'Nota del día', detalle: 'Notas', ir: '#/notas/hoy' },
    { tipo: 'accion', titulo: 'Semana', detalle: 'Inicio', ir: '#/inicio' },
    { tipo: 'accion', titulo: 'Hoy', detalle: 'Tareas', ir: '#/hoy' },
    { tipo: 'accion', titulo: 'Bandeja', detalle: 'Tareas', ir: '#/bandeja' },
  ];
  if (!q) return base;
  return [{ tipo: 'accion', titulo: `Crear la nota «${q}»`, detalle: 'Nota nueva', crear: q }];
}

function cerrar() {
  document.getElementById('paleta').hidden = true;
  document.getElementById('velo').hidden = !!document.getElementById('hoja').hidden;
}

async function elegir(r) {
  if (!r) return;
  cerrar();
  if (r.ir) ctx.ir(r.ir);
  else if (r.crear) {
    try {
      const n = await api.nuevaNota(r.crear);
      ctx.ir(`#/n/${n.slug}`);
    } catch (err) {
      avisar(err.message, { error: true });
    }
  } else if (r.tipo === 'tarea') ctx.abrir(r.ref);
  else if (r.tipo === 'nota') ctx.ir(`#/n/${r.ref}`);
  else if (r.tipo === 'proyecto') ctx.ir(`#/p/${r.ref}`);
  else if (r.tipo === 'etiqueta') ctx.ir(`#/e/${encodeURIComponent(r.ref)}`);
}

function pintar() {
  vaciar(lista, resultados.length ? resultados.map((r, i) => h(`li.paleta__item${i === activo ? '.paleta__item--activo' : ''}`, {
    role: 'option', 'aria-selected': String(i === activo), id: `paleta-${i}`,
    onclick: () => elegir(r), onpointermove: () => { if (activo !== i) { activo = i; pintar(); } },
  },
  icono(ICONO[r.tipo], 'ico--s'),
  h('span.paleta__titulo', r.ambito ? h(`i.punto.punto--${r.ambito}`) : null, r.titulo),
  h('span.paleta__detalle', [TIPO[r.tipo], r.detalle].filter(Boolean).join(' · ')))) : h('li.paleta__vacio', 'Sin resultados'));
  input.setAttribute('aria-activedescendant', resultados.length ? `paleta-${activo}` : '');
  lista.querySelector('.paleta__item--activo')?.scrollIntoView({ block: 'nearest' });
}

async function buscar() {
  const q = input.value.trim();
  const n = ++peticion;
  if (!q) { resultados = acciones(''); activo = 0; pintar(); return; }
  try {
    const r = await api.buscar(q);
    if (n !== peticion) return;
    resultados = [...r, ...acciones(q)];
    activo = 0;
    pintar();
  } catch (err) {
    avisar(err.message, { error: true });
  }
}

export function abrirBuscador() {
  const paleta = document.getElementById('paleta');
  paleta.hidden = false;
  document.getElementById('velo').hidden = false;
  input.value = '';
  buscar();
  input.focus();
}

export function iniciarBuscador(contexto) {
  ctx = contexto;
  input = h('input.paleta__input', {
    type: 'search', placeholder: 'Buscar tareas, notas, proyectos y @etiquetas', autocomplete: 'off',
    role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'paleta-lista', 'aria-label': 'Buscar',
  });
  lista = h('ul.paleta__lista', { id: 'paleta-lista', role: 'listbox' });
  vaciar(document.getElementById('paleta'),
    h('div.paleta__caja', icono('buscar'), input, h('kbd.paleta__tecla', 'Esc')), lista);
  input.addEventListener('input', () => { clearTimeout(temporizador); temporizador = setTimeout(buscar, PAUSA_MS); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { activo = Math.min(activo + 1, resultados.length - 1); pintar(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { activo = Math.max(activo - 1, 0); pintar(); e.preventDefault(); }
    else if (e.key === 'Enter') { elegir(resultados[activo]); e.preventDefault(); }
    else if (e.key === 'Escape') { cerrar(); e.preventDefault(); e.stopPropagation(); }
  });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); abrirBuscador(); }
  });
  document.getElementById('velo').addEventListener('click', () => { if (!document.getElementById('paleta').hidden) cerrar(); });
}
