// Markdown editor shared by notes and task context: Editar / Vista previa, and `[[` autocomplete
// of tasks, notes and projects. Links in the preview open their target (or create the note).
import { api } from './api.js';
import { h, icono, vaciar } from './dom.js';
import { destinos, marcarLinea, render } from './markdown.js';

const ICONO_TIPO = { tarea: 'lista', nota: 'nota', proyecto: 'carpetas' };
const PAUSA_MS = 120;

/** Pixel position of the caret inside a textarea, measured with a hidden mirror. */
function posicionCursor(area) {
  const estilo = getComputedStyle(area);
  const espejo = h('div');
  for (const p of ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 'letterSpacing', 'paddingTop', 'paddingLeft',
    'paddingRight', 'borderTopWidth', 'borderLeftWidth', 'boxSizing', 'width']) espejo.style[p] = estilo[p];
  espejo.style.position = 'absolute';
  espejo.style.visibility = 'hidden';
  espejo.style.whiteSpace = 'pre-wrap';
  espejo.style.overflowWrap = 'break-word';
  espejo.textContent = area.value.slice(0, area.selectionStart);
  const marca = h('span', '​');
  espejo.append(marca);
  document.body.append(espejo);
  const pos = { top: marca.offsetTop - area.scrollTop, left: marca.offsetLeft, alto: parseFloat(estilo.lineHeight) || 22 };
  espejo.remove();
  return pos;
}

function autocompletar(area, contenedor) {
  const lista = h('ul.sugerencias', { role: 'listbox', hidden: true });
  contenedor.append(lista);
  let items = [];
  let activo = 0;
  let inicio = -1;
  let temporizador = null;
  let peticion = 0;

  const cerrar = () => { lista.hidden = true; items = []; inicio = -1; };

  function elegir(i) {
    const it = items[i];
    if (!it) return;
    const antes = area.value.slice(0, inicio);
    const despues = area.value.slice(area.selectionStart).replace(/^[^\]\n]*\]\]/, '');
    const insertado = `[[${it.enlace}]]`;
    area.value = antes + insertado + despues;
    const cursor = antes.length + insertado.length;
    area.setSelectionRange(cursor, cursor);
    cerrar();
    area.dispatchEvent(new Event('input'));
    area.focus();
  }

  function pintar() {
    vaciar(lista, items.map((it, i) => h(`li.sugerencia${i === activo ? '.sugerencia--activa' : ''}`, {
      role: 'option', 'aria-selected': String(i === activo),
      onpointerdown: (e) => { e.preventDefault(); elegir(i); },
    }, icono(ICONO_TIPO[it.tipo] || 'nota', 'ico--s'), h('span.sugerencia__titulo', it.titulo), h('span.sugerencia__detalle', it.detalle))));
    lista.hidden = !items.length;
    if (items.length) {
      const pos = posicionCursor(area);
      lista.style.top = `${Math.min(area.offsetTop + pos.top + pos.alto + 4, area.offsetTop + area.offsetHeight)}px`;
      lista.style.left = `${Math.min(area.offsetLeft + pos.left, Math.max(0, contenedor.clientWidth - 280))}px`;
    }
  }

  async function buscar() {
    const m = /\[\[([^\[\]\n|]{0,60})$/.exec(area.value.slice(0, area.selectionStart));
    if (!m) { cerrar(); return; }
    inicio = area.selectionStart - m[0].length;
    const n = ++peticion;
    try {
      const r = await api.sugerir(m[1]);
      if (n !== peticion) return;
      items = r;
      activo = 0;
      pintar();
    } catch {
      cerrar();
    }
  }

  area.addEventListener('input', () => { clearTimeout(temporizador); temporizador = setTimeout(buscar, PAUSA_MS); });
  area.addEventListener('blur', () => setTimeout(cerrar, 150));
  area.addEventListener('keydown', (e) => {
    if (lista.hidden) return;
    if (e.key === 'ArrowDown') { activo = (activo + 1) % items.length; pintar(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { activo = (activo - 1 + items.length) % items.length; pintar(); e.preventDefault(); }
    else if (e.key === 'Enter' || e.key === 'Tab') { elegir(activo); e.preventDefault(); }
    else if (e.key === 'Escape') { cerrar(); e.preventDefault(); e.stopPropagation(); }
  });
}

/**
 * opciones: valor, alCambiar(texto), placeholder, filas, modo ('editar' | 'ver'), alEnlace(destino, resuelto), id
 * Returns {el, valor(), poner(texto)}.
 */
export function editorMarkdown({ valor = '', alCambiar, placeholder = '', filas = 8, modo = 'editar', alEnlace, id }) {
  let texto = valor;
  let actual = modo;
  const area = h('textarea.campo.md-editor__area', { rows: filas, placeholder, id, spellcheck: true });
  area.value = texto;
  const vista = h('div.md-editor__vista');
  const cuerpo = h('div.md-editor__cuerpo', area, vista);
  const pestanas = h('div.pildoras.pildoras--sobrio.md-editor__pestanas', { role: 'group', 'aria-label': 'Modo' });

  async function pintarVista() {
    const lista = destinos(texto);
    let enlaces = {};
    if (lista.length) {
      try { enlaces = await api.resolver(lista); } catch { /* links show as plain until resolved */ }
    }
    vaciar(vista, texto.trim() ? render(texto, {
      enlaces,
      alEnlace,
      alMarcar: (n, marcada) => { texto = marcarLinea(texto, n, marcada); area.value = texto; alCambiar?.(texto); pintarVista(); },
    }) : h('p.meta', 'Vacía. Toca «Editar» para escribir.'));
  }

  function poner(m) {
    actual = m;
    area.hidden = m !== 'editar';
    vista.hidden = m !== 'ver';
    vaciar(pestanas, [['editar', 'Editar'], ['ver', 'Vista previa']].map(([v, t]) =>
      h('button.pildora', { type: 'button', 'aria-pressed': String(v === actual), onclick: () => { poner(v); if (v === 'editar') area.focus(); } }, t)));
    if (m === 'ver') pintarVista();
  }

  area.addEventListener('input', () => { texto = area.value; alCambiar?.(texto); });
  autocompletar(area, cuerpo);
  poner(modo);
  return {
    el: h('div.md-editor', pestanas, cuerpo),
    valor: () => texto,
    poner: (nuevo) => { texto = nuevo; area.value = nuevo; if (actual === 'ver') pintarVista(); },
    modo: () => actual,
  };
}
