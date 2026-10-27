// Drag a task to another day with the mouse: from the week or the month's day list to a day of the
// week or a cell of the month. Only with a fine pointer; fingers swipe instead (deslizar.js).
const TIPO = 'application/x-agenda-tarea';
const conRaton = () => window.matchMedia('(pointer: fine)').matches;

export function arrastrable(el, id) {
  if (!conRaton()) return el;
  el.draggable = true;
  el.addEventListener('dragstart', (e) => {
    e.dataTransfer.setData(TIPO, id);
    e.dataTransfer.effectAllowed = 'move';
    el.classList.add('arrastrando');
  });
  el.addEventListener('dragend', () => el.classList.remove('arrastrando'));
  return el;
}

/** `alSoltar(id, fecha)` when a task is dropped on `el`. */
export function destino(el, fecha, alSoltar) {
  const nuestra = (e) => [...(e.dataTransfer?.types || [])].includes(TIPO);
  el.addEventListener('dragover', (e) => {
    if (!nuestra(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    el.classList.add('destino--encima');
  });
  el.addEventListener('dragleave', (e) => {
    if (!el.contains(e.relatedTarget)) el.classList.remove('destino--encima');
  });
  el.addEventListener('drop', (e) => {
    if (!nuestra(e)) return;
    e.preventDefault();
    el.classList.remove('destino--encima');
    alSoltar(e.dataTransfer.getData(TIPO), fecha);
  });
  return el;
}
