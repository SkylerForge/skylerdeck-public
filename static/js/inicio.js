// Inicio: the weekly sheet. Monday to Friday get a column each; Saturday and Sunday share the last one.
import { arrastrable, destino } from './arrastrar.js';
import { deslizable } from './deslizar.js';
import { diaCorto, h, icono, plural, sumarDias } from './dom.js';

const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

export function saludo(ahora) {
  const hora = Number(ahora.slice(11, 13));
  if (hora >= 6 && hora < 14) return 'Buenos días';
  if (hora >= 14 && hora < 21) return 'Buenas tardes';
  return 'Buenas noches';
}

function rango(lunes) {
  const domingo = sumarDias(lunes, 6);
  const [, m1, d1] = lunes.split('-').map(Number);
  const [, m2, d2] = domingo.split('-').map(Number);
  return m1 === m2 ? `${d1} al ${d2} de ${MESES[m2 - 1]}` : `${d1} de ${MESES[m1 - 1]} al ${d2} de ${MESES[m2 - 1]}`;
}

function horario(t) {
  if (!t.hora) return null;
  return t.duracion && t.fin ? `${t.hora}–${t.fin}` : t.hora;
}

export function item(it, t, s, ctx) {
  const tipo = it.tipo;
  const meta = [];
  if (tipo === 'vencida') meta.push(h('span.t-vencida', `Vencida el ${diaCorto(t.fecha).slice(4)}`));
  else if (tipo !== 'revisar' && horario(t)) meta.push(h('span.sem-item__hora', horario(t)));
  if (tipo === 'revisar') meta.push(h('span.t-revisar', t.esperando_a ? `Revisar · espera a ${t.esperando_a}` : 'Revisar'));
  if (tipo === 'repeticion') meta.push(h('span', icono('repetir', 'ico--s'), 'Se repite'));
  if (t.proyecto_nombre) meta.push(h('span', t.proyecto_nombre));

  let marca;
  if (tipo === 'tarea' || tipo === 'vencida') {
    marca = h('button.sem-item__check', { 'aria-label': `Marcar como hecha: ${t.titulo}`, onclick: () => ctx.completar(t) },
      h('span', icono('check')));
  } else if (tipo === 'hecha') {
    marca = h('span.sem-item__check.sem-item__check--hecha', { 'aria-hidden': 'true' }, h('span', icono('check')));
  } else {
    marca = h('span.sem-item__check.sem-item__check--muda', { 'aria-hidden': 'true' }, icono(tipo === 'revisar' ? 'esperar' : 'repetir', 'ico--s'));
  }
  const hecha = tipo === 'hecha' || ctx.hecha(t.id);
  const el = h(`div.sem-item.prio-${t.prioridad}.sem-item--${tipo}${hecha ? '.sem-item--hecha' : ''}`,
    marca,
    h('button.sem-item__cuerpo', { onclick: () => ctx.abrir(t.id) },
      h('span.sem-item__titulo', h(`i.punto.punto--${t.ambito}`), t.titulo),
      meta.length > 0 && h('span.sem-item__meta', meta)));
  if (hecha || !['tarea', 'vencida'].includes(tipo)) return el;
  arrastrable(el, t.id);
  return deslizable(el, {
    derecha: { texto: 'Hecha', icono: 'check', accion: () => ctx.completar(t) },
    izquierda: { texto: 'Mañana', icono: 'derecha', accion: () => ctx.manana(t) },
  });
}


function dia(fecha, items, s, ctx, extra = []) {
  const idx = (new Date(`${fecha}T12:00:00`).getDay() + 6) % 7;
  const esHoy = fecha === s.hoy;
  const pasado = fecha < s.hoy;
  const numero = Number(fecha.slice(8));
  const lista = [...extra, ...items.map((it) => item(it, s.tareas[it.id], s, ctx))];
  return destino(h(`section.sem-dia${esHoy ? '.sem-dia--hoy' : ''}${pasado ? '.sem-dia--pasado' : ''}`, { 'aria-label': `${DIAS[idx]} ${numero}` },
    h('header.sem-dia__cab',
      h('a.sem-dia__titulo', { href: `#/n/${fecha}`, title: `Nota del ${DIAS[idx].toLowerCase()} ${numero}` },
        h('span.sem-dia__nombre', DIAS[idx]),
        h('span.sem-dia__num', numero),
        (s.notas_dia || []).includes(fecha) && h('span.sem-dia__nota', { 'aria-label': 'tiene nota del día' }, icono('nota', 'ico--s'))),
      esHoy && h('span.sem-dia__hoy', 'Hoy'),
      h('button.icono-btn.sem-dia__mas', { 'aria-label': `Añadir tarea el ${DIAS[idx].toLowerCase()} ${numero}`, onclick: () => ctx.anadirEn(fecha) },
        icono('mas', 'ico--s'))),
    h('div.sem-dia__lista', lista.length ? lista : h('p.sem-dia__libre', 'Libre'))), fecha, ctx.moverA);
}

export function siguiente(d, ctx) {
  if (!d.siguiente) return h('div.sem-siguiente.sem-siguiente--nada', h('span', 'Nada más con hora hoy'));
  const t = d.tareas.find((x) => x.id === d.siguiente.id);
  if (!t) return null;
  return h('button.sem-siguiente', { onclick: () => ctx.abrir(t.id) },
    h('span.sem-siguiente__rotulo', d.siguiente.ahora ? 'Ahora' : 'A continuación'),
    h('span.sem-siguiente__hora', t.hora),
    h('span.sem-siguiente__titulo', t.titulo),
    d.siguiente.hasta && h('span.meta', `hasta las ${d.siguiente.hasta}`));
}

export function inicio(d, s, ctx) {
  const actual = s.lunes === ctx.lunesActual();
  const dias = s.dias;
  const vencidas = s.vencidas.map((id) => item({ id, tipo: 'vencida' }, s.tareas[id], s, ctx));
  const conVencidas = (f) => (f === s.hoy && vencidas.length ? [h('p.sem-dia__sub.t-vencida', 'De días anteriores'), ...vencidas, h('p.sem-dia__sub', 'Hoy')] : []);

  const cabecera = h('header.cabecera',
    h('div',
      h('h1', d.nombre ? `${saludo(d.ahora)}, ${d.nombre}` : saludo(d.ahora)),
      h('p', `Semana del ${rango(s.lunes)} · ${plural(s.pendientes, 'tarea pendiente', 'tareas pendientes')}`)),
    ctx.filtro());

  const barra = h('div.sem-barra',
    h('div.sem-barra__izq',
      actual ? siguiente(d, ctx) : null,
      h('a.sem-nota-dia', { href: '#/notas/hoy' }, icono('nota', 'ico--s'),
        (s.notas_dia || []).includes(s.hoy) ? 'Nota del día' : 'Escribir la nota del día')),
    h('nav.sem-nav', { 'aria-label': 'Semana' },
      ctx.conmutadorVista(),
      h('button.icono-btn', { 'aria-label': 'Semana anterior', onclick: () => ctx.irSemana(-7) }, icono('izquierda')),
      h('button.boton.boton--fantasma', { disabled: actual, onclick: () => ctx.irSemana(0) }, 'Esta semana'),
      h('button.icono-btn', { 'aria-label': 'Semana siguiente', onclick: () => ctx.irSemana(7) }, icono('derecha'))));

  const laborables = dias.slice(0, 5).map((x) => dia(x.fecha, x.items, s, ctx, conVencidas(x.fecha)));
  const finde = h('div.sem-finde', dias.slice(5).map((x) => dia(x.fecha, x.items, s, ctx, conVencidas(x.fecha))));
  return h('div.inicio.inicio--semana', cabecera, ctx.quickAdd(), barra, h('div.sem-rejilla', laborables, finde));
}
