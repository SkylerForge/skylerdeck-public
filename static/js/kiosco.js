// Kiosk mode (#/kiosco) for a tablet on the wall: Inicio without the rail, a big clock, the screen kept
// on (Wake Lock) and full screen after the first touch (browsers only allow it after a gesture).
// It is still the web page: leaving is a button, not an app to close.
import { h, icono } from './dom.js';

let bloqueo = null;
let activo = false;

async function mantenerEncendida() {
  if (!activo || bloqueo || document.hidden || !navigator.wakeLock) return;
  try {
    bloqueo = await navigator.wakeLock.request('screen');
    bloqueo.addEventListener('release', () => { bloqueo = null; });
  } catch { /* battery saver or no HTTPS: the screen may dim, the rest works */ }
}

function pantallaCompleta() {
  if (activo && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
}

document.addEventListener('visibilitychange', mantenerEncendida); // the lock is dropped when the tab hides
document.addEventListener('pointerdown', pantallaCompleta);

/** Called on every route change: turns kiosk mode on for #/kiosco and off anywhere else. */
export function modoKiosco(encendido) {
  if (encendido === activo) return;
  activo = encendido;
  document.documentElement.classList.toggle('kiosco', encendido);
  if (encendido) {
    mantenerEncendida();
  } else {
    bloqueo?.release().catch(() => {});
    bloqueo = null;
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  }
}

/** The kiosk frame around Inicio: a big clock and a way out. */
export function marcoKiosco(contenido) {
  return h('div.kiosco-vista',
    h('div.kiosco-barra',
      h('span.kiosco-reloj', { id: 'reloj-kiosco' }),
      h('a.boton.boton--fantasma', { href: '#/inicio' }, icono('cerrar', 'ico--s'), 'Salir del modo kiosco')),
    contenido);
}
