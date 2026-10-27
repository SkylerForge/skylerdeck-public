// Swipe a task with a finger: to the right, «Hecha»; to the left, «Mañana». Touch and pen only, so the
// mouse keeps clicking and the page keeps scrolling up and down (CSS sets touch-action: pan-y).
import { h, icono } from './dom.js';

const ARRANQUE = 10; // px before a horizontal move counts as a swipe
const TRAGAR_MS = 400; // the click a swipe leaves behind is ignored for this long

/** Wraps `el`; `derecha` / `izquierda` are { texto, icono, accion }; `clase` like '.desliza--fila'. */
export function deslizable(el, { derecha, izquierda }, clase = '') {
  const caja = h(`div.desliza${clase}`,
    h('div.desliza__fondo', { 'aria-hidden': 'true' },
      h('span.desliza__accion.desliza__accion--derecha', icono(derecha.icono, 'ico--s'), derecha.texto),
      h('span.desliza__accion.desliza__accion--izquierda', izquierda.texto, icono(izquierda.icono, 'ico--s'))),
    el);
  el.classList.add('desliza__fila');
  let puntero = null;
  let x0 = 0;
  let y0 = 0;
  let dx = 0;
  let moviendo = false;
  let tragarHasta = 0;
  const umbral = () => Math.min(110, caja.clientWidth * 0.3);

  el.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse') return;
    puntero = e.pointerId;
    x0 = e.clientX;
    y0 = e.clientY;
    dx = 0;
    moviendo = false;
  });
  el.addEventListener('pointermove', (e) => {
    if (e.pointerId !== puntero) return;
    const x = e.clientX - x0;
    if (!moviendo) {
      if (Math.abs(x) < ARRANQUE) return;
      if (Math.abs(e.clientY - y0) > Math.abs(x)) { puntero = null; return; } // scrolling, not swiping
      moviendo = true;
      try { el.setPointerCapture(puntero); } catch { /* the pointer is already gone: the move still works */ }
      caja.classList.add('desliza--moviendo');
    }
    dx = x;
    el.style.transform = `translateX(${dx}px)`;
    caja.dataset.lado = dx > 0 ? 'derecha' : 'izquierda';
    caja.classList.toggle('desliza--listo', Math.abs(dx) > umbral());
  });
  const soltar = (e) => {
    if (e.pointerId !== puntero) return;
    puntero = null;
    if (!moviendo) return;
    moviendo = false;
    tragarHasta = Date.now() + TRAGAR_MS;
    const hecho = Math.abs(dx) > umbral();
    caja.classList.remove('desliza--moviendo', 'desliza--listo');
    el.style.transform = '';
    if (hecho) (dx > 0 ? derecha : izquierda).accion();
  };
  el.addEventListener('pointerup', soltar);
  el.addEventListener('pointercancel', soltar);
  // A swipe ends with a click on whatever is under the finger: it must not open the task.
  el.addEventListener('click', (e) => {
    if (Date.now() < tragarHasta) { e.stopPropagation(); e.preventDefault(); }
  }, true);
  return caja;
}
