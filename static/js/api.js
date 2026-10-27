// JSON API client. Writes carry X-Agenda (the server refuses writes without it).

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function pedir(metodo, ruta, cuerpo) {
  const opciones = { method: metodo, headers: {}, credentials: 'same-origin' };
  if (cuerpo !== undefined) {
    opciones.headers['Content-Type'] = 'application/json';
    opciones.headers['X-Agenda'] = '1';
    opciones.body = JSON.stringify(cuerpo);
  }
  let resp;
  try {
    resp = await fetch(ruta, opciones);
  } catch {
    throw new ApiError('Sin conexión con el panel', 0);
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(data.error || `Error ${resp.status}`, resp.status);
  return data;
}

export const api = {
  version: () => pedir('GET', '/api/version'),
  panel: (ambito) => pedir('GET', `/api/panel?ambito=${encodeURIComponent(ambito)}`),
  semana: (ambito, desde) => pedir('GET', `/api/semana?ambito=${encodeURIComponent(ambito)}${desde ? `&desde=${desde}` : ''}`),
  mes: (ambito, mes) => pedir('GET', `/api/mes?ambito=${encodeURIComponent(ambito)}${mes ? `&mes=${mes}` : ''}`),
  parsear: (texto) => pedir('POST', '/api/parsear', { texto }),
  crear: (texto, extra = {}) => pedir('POST', '/api/tareas', { texto, ...extra }),
  ficha: (id) => pedir('GET', `/api/tareas/${id}`),
  editar: (id, cambios, version) => pedir('PATCH', `/api/tareas/${id}`, { cambios, version }),
  estado: (id, estado, version, extra = {}) => pedir('POST', `/api/tareas/${id}/estado`, { estado, version, ...extra }),
  saltar: (id, version) => pedir('POST', `/api/tareas/${id}/saltar`, { version }),
  contexto: (id, texto, version) => pedir('POST', `/api/tareas/${id}/contexto`, { texto, version }),
  subtarea: (id, accion, valor, version) => pedir('POST', `/api/tareas/${id}/subtareas`, { accion, valor, version }),
  anotar: (id, texto) => pedir('POST', `/api/tareas/${id}/nota`, { texto }),
  notas: (filtro = {}) => pedir('GET', `/api/notas?${new URLSearchParams(filtro)}`),
  nota: (slug) => pedir('GET', `/api/notas/${encodeURIComponent(slug)}`),
  nuevaNota: (titulo, cuerpo = '', proyecto = '') => pedir('POST', '/api/notas', { titulo, cuerpo, proyecto }),
  guardarNota: (slug, datos) => pedir('PUT', `/api/notas/${encodeURIComponent(slug)}`, datos),
  borrarNota: (slug, version) => pedir('DELETE', `/api/notas/${encodeURIComponent(slug)}`, { version }),
  restaurarNota: (papelera) => pedir('POST', '/api/notas/restaurar', { papelera }),
  sugerir: (q) => pedir('GET', `/api/sugerir?q=${encodeURIComponent(q)}`),
  resolver: (destinos) => pedir('POST', '/api/resolver', { destinos }),
  enlace: (destino, proyecto = '') => pedir('POST', '/api/enlace', { destino, proyecto }),
  buscar: (q) => pedir('GET', `/api/buscar?q=${encodeURIComponent(q)}`),
  etiquetas: () => pedir('GET', '/api/etiquetas'),
  etiqueta: (e) => pedir('GET', `/api/etiquetas/${encodeURIComponent(e)}`),
  avisos: () => pedir('GET', '/api/avisos'),
  ajustesAvisos: (ajustes) => pedir('PUT', '/api/avisos', { ajustes }),
  pruebaAviso: () => pedir('POST', '/api/avisos/prueba', {}),
  nuevoProyecto: (nombre, ambito) => pedir('POST', '/api/proyectos', { nombre, ambito }),
  renombrarProyecto: (slug, nombre) => pedir('PATCH', `/api/proyectos/${slug}`, { nombre }),
};
