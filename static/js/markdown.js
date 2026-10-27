// Small Markdown renderer for notes and task context. Builds DOM from text nodes (never innerHTML),
// so nothing in a note can inject markup or scripts. Supports headings, paragraphs, lists and
// checklists, quotes, code, rules, **bold**, *italic*, `code`, [text](https://…), [[links]] and @tags.
import { h } from './dom.js';

const ENLACE_RE = /\[\[([^\[\]|\n]{1,120})(?:\|([^\[\]\n]{1,120}))?\]\]/g;
const INLINE_RE = /(`[^`\n]+`)|(\[\[[^\[\]\n]{1,240}\]\])|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*|_[^_\n]+_)|(\[[^\]\n]+\]\(https?:\/\/[^)\s]+\))|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?])|((?<![\w@/.])@[^\W_][\w-]{0,39})/gu;

/** All `[[target]]` texts in a Markdown string (to resolve them in one request). */
export function destinos(md) {
  return [...String(md || '').matchAll(ENLACE_RE)].map((m) => m[1].trim());
}

function inline(texto, op) {
  const out = [];
  let pos = 0;
  for (const m of texto.matchAll(INLINE_RE)) {
    if (m.index > pos) out.push(texto.slice(pos, m.index));
    const [todo, codigo, wiki, negrita, cursiva, link, url, etiqueta] = m;
    if (codigo) out.push(h('code', codigo.slice(1, -1)));
    else if (wiki) {
      const [, destino, alias] = /^\[\[([^\]|]+)(?:\|([^\]]+))?\]\]$/.exec(wiki) || [null, wiki.slice(2, -2), null];
      const resuelto = op.enlaces?.[destino.trim()];
      out.push(h(`a.md-enlace${resuelto === null ? '.md-enlace--roto' : ''}`, {
        href: '#', title: resuelto === null ? `«${destino.trim()}» no existe todavía: tócalo para crear la nota` : (resuelto?.titulo || destino),
        onclick: (e) => { e.preventDefault(); op.alEnlace?.(destino.trim(), resuelto); },
      }, (alias || destino).trim()));
    } else if (negrita) out.push(h('strong', inline(negrita.slice(2, -2), op)));
    else if (cursiva) out.push(h('em', inline(cursiva.slice(1, -1), op)));
    else if (link) {
      const [, t, href] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(link);
      out.push(h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, t));
    } else if (url) out.push(h('a', { href: url, target: '_blank', rel: 'noopener noreferrer' }, url));
    else if (etiqueta) {
      out.push(h('a.md-etiqueta', { href: `#/e/${encodeURIComponent(etiqueta.slice(1).toLowerCase())}` }, etiqueta));
    } else out.push(todo);
    pos = m.index + todo.length;
  }
  if (pos < texto.length) out.push(texto.slice(pos));
  return out;
}

/**
 * op.enlaces: {target: {tipo, ref, titulo} | null} from /api/resolver (null = goes nowhere yet)
 * op.alEnlace(target, resolved): what a click on a [[link]] does
 * op.alMarcar(lineIndex, checked): makes checklist boxes clickable (optional)
 */
export function render(md, op = {}) {
  const lineas = String(md || '').replace(/\r\n/g, '\n').split('\n');
  const raiz = h('div.md');
  let i = 0;
  let parrafo = [];
  const cerrarParrafo = () => {
    if (parrafo.length) raiz.append(h('p', inline(parrafo.join(' '), op)));
    parrafo = [];
  };
  while (i < lineas.length) {
    const linea = lineas[i];
    if (/^```/.test(linea)) {
      cerrarParrafo();
      const codigo = [];
      i += 1;
      while (i < lineas.length && !/^```/.test(lineas[i])) codigo.push(lineas[i++]);
      raiz.append(h('pre', h('code', codigo.join('\n'))));
      i += 1;
      continue;
    }
    const titulo = /^(#{1,6})\s+(.*)$/.exec(linea);
    if (titulo) {
      cerrarParrafo();
      raiz.append(h(`h${Math.min(6, titulo[1].length + 1)}`, inline(titulo[2], op)));
      i += 1;
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(linea)) {
      cerrarParrafo();
      raiz.append(h('hr'));
      i += 1;
      continue;
    }
    if (/^>\s?/.test(linea)) {
      cerrarParrafo();
      const cita = [];
      while (i < lineas.length && /^>\s?/.test(lineas[i])) cita.push(lineas[i++].replace(/^>\s?/, ''));
      raiz.append(h('blockquote', [...render(cita.join('\n'), op).childNodes]));
      continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(linea)) {
      cerrarParrafo();
      const ordenada = /^\s*\d+[.)]/.test(linea);
      const lista = h(ordenada ? 'ol' : 'ul');
      while (i < lineas.length && /^\s*([-*+]|\d+[.)])\s+/.test(lineas[i])) {
        const texto = lineas[i].replace(/^\s*([-*+]|\d+[.)])\s+/, '');
        const casilla = /^\[([ xX])\]\s+(.*)$/.exec(texto);
        if (casilla) {
          const n = i;
          const marcada = casilla[1] !== ' ';
          lista.append(h(`li.md-check${marcada ? '.md-check--hecha' : ''}`,
            h('input', { type: 'checkbox', checked: marcada, disabled: !op.alMarcar, onchange: (e) => op.alMarcar?.(n, e.target.checked),
              'aria-label': casilla[2] }),
            h('span', inline(casilla[2], op))));
        } else {
          lista.append(h('li', inline(texto, op)));
        }
        i += 1;
      }
      raiz.append(lista);
      continue;
    }
    if (!linea.trim()) {
      cerrarParrafo();
      i += 1;
      continue;
    }
    parrafo.push(linea.trim());
    i += 1;
  }
  cerrarParrafo();
  return raiz;
}

/** Toggles the checklist box on line `n` of a Markdown text. */
export function marcarLinea(md, n, marcada) {
  const lineas = String(md).split('\n');
  lineas[n] = lineas[n].replace(/\[([ xX])\]/, marcada ? '[x]' : '[ ]');
  return lineas.join('\n');
}
