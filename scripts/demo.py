"""Fills a folder with made-up tasks and projects around today, for screenshots and UI tests.

    .venv/bin/python scripts/demo.py /ruta/a/datos-demo

Refuses to write into a folder that already has data, so it can never touch the real `datos/`.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agenda import fechas  # noqa: E402
from agenda.fichas import Fichas  # noqa: E402
from agenda.notas import Notas  # noqa: E402

PROYECTOS = [("Clientes", "laboral"), ("Web", "laboral"), ("Equipo", "laboral"), ("Formación", "laboral"),
             ("Casa", "personal"), ("Taller", "personal"), ("Compras", "personal")]


def main(destino: str) -> None:
    datos = Path(destino).expanduser().resolve()
    if datos.exists() and any(datos.iterdir()):
        sys.exit(f"{datos} ya tiene datos: usa una carpeta vacía")
    f = Fichas(datos)
    for nombre, ambito in PROYECTOS:
        f.proyectos.crear(nombre, ambito)
    hoy = fechas.hoy()
    d = lambda n: (hoy + dt.timedelta(days=n)).isoformat()  # noqa: E731
    gimnasio = next(n for n in range(7) if (hoy + dt.timedelta(days=n)).weekday() in (0, 3))  # its first Monday or Thursday
    tareas = [
        {"titulo": "Reunión de equipo", "proyecto": "equipo", "fecha": d(0), "hora": "10:30", "duracion": "60", "prioridad": "p3"},
        {"titulo": "Responder a Marta sobre el presupuesto", "proyecto": "clientes", "fecha": d(-1), "prioridad": "p1"},
        {"titulo": "Entregar la propuesta a Estudio Norte", "proyecto": "clientes", "fecha": d(0), "hora": "14:00", "prioridad": "p1",
         "caso": "PRES-2026-031", "etiquetas": ["entrega"], "subtareas": ["Textos", "Maqueta", "Presupuesto", "Revisión", "Enviar"]},
        {"titulo": "Revisar las maquetas de la home", "proyecto": "web", "fecha": d(0), "hora": "12:00", "duracion": "60",
         "prioridad": "p2", "etiquetas": ["diseño"]},
        {"titulo": "Pedir cita para la ITV", "proyecto": "casa", "fecha": d(0), "prioridad": "p2"},
        {"titulo": "Preparar el orden del día del lunes", "proyecto": "equipo", "fecha": d(0), "prioridad": "p3"},
        {"titulo": "Comprar tornillería para la estantería", "proyecto": "taller", "fecha": d(0), "prioridad": "p3"},
        {"titulo": "Regar las plantas", "proyecto": "casa", "fecha": d(0), "repetir": "cada 3 días"},
        {"titulo": "Recoger paquete", "proyecto": "compras", "fecha": d(0), "hora": "17:30"},
        {"titulo": "Gimnasio", "fecha": d(gimnasio), "hora": "19:00", "repetir": "cada lunes y jueves", "etiquetas": ["salud"]},
        {"titulo": "Llamada con Estudio Norte", "proyecto": "clientes", "fecha": d(1), "hora": "09:00", "prioridad": "p1"},
        {"titulo": "Tutoría del cole", "fecha": d(1), "hora": "18:00"},
        {"titulo": "Facturar los proyectos del mes", "proyecto": "clientes", "fecha": d(4), "etiquetas": ["administración"]},
        {"titulo": "Publicar la nueva página de servicios", "proyecto": "web", "fecha": d(3), "prioridad": "p2"},
        {"titulo": "Curso de accesibilidad web", "proyecto": "formacion", "fecha": d(9)},
        {"titulo": "Pensar en el viaje de diciembre"},
        {"titulo": "Mirar presupuestos de la caldera", "ambito": "personal"},
        {"titulo": "Comprar barniz para la mesa", "proyecto": "taller", "etiquetas": ["tienda"]},
    ]
    ids = [f.crear(t, quien="demo").id for t in tareas]
    f.mover(ids[2], "en-curso", quien="demo")
    f.subtarea(ids[2], "marcar", "1", quien="demo")
    f.subtarea(ids[2], "marcar", "2", quien="demo")
    f.subtarea(ids[2], "marcar", "3", quien="demo")
    f.mover(ids[3], "en-curso", quien="demo")
    f.mover(ids[1], "esperando", quien="demo", esperando_a="Marta")
    espera = f.crear({"titulo": "Recibir los textos definitivos", "proyecto": "clientes"}, quien="demo")
    f.mover(espera.id, "esperando", quien="demo", esperando_a="Estudio Norte", revisar=d(2))
    for titulo in ("Ordenar el archivo del año pasado", "Plantilla nueva de propuesta"):
        t = f.crear({"titulo": titulo, "proyecto": "clientes"}, quien="demo")
        f.mover(t.id, "mas-adelante", quien="demo", revisar=d(30))
    for titulo in ("Montar el banco de trabajo", "Afilar los formones"):
        t = f.crear({"titulo": titulo, "proyecto": "taller"}, quien="demo")
        f.completar(t.id, quien="demo")
    notas = Notas(datos)
    plantilla = notas.crear("Plantilla de propuesta", (
        "## Estructura\n\n- [x] Objetivo del cliente\n- [x] Alcance y entregables\n- [ ] Calendario\n- [ ] Presupuesto\n\n"
        f"Se usa en [[{ids[2]}|Entregar la propuesta]] y en todo [[Clientes]]. @entrega"), proyecto="clientes")
    notas.crear("Ideas para la web", "- Casos de éxito con fotos\n- Formulario más corto\n\nVer [[Publicar la nueva página de servicios]] @ideas",
                proyecto="web")
    notas.crear("Lista de la compra", "- [ ] Pilas AA\n- [ ] Barniz\n\n@tienda")
    notas.guardar(hoy.isoformat(), cuerpo=(
        f"Hoy toca cerrar la [[{ids[2]}|propuesta de Estudio Norte]] con la [[{plantilla.titulo}]].\n\n"
        f"Mañana, [[{ids[10]}|llamada con ellos]] a primera hora. @entrega"))
    f.contexto(ids[2], f"Seguir la [[{plantilla.titulo}]]. Los textos están en la carpeta compartida.", quien="demo")
    print(f"Datos de demo en {datos}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
