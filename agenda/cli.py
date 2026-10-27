"""`agenda`: the command line, for you and for agents. Every write goes through fichas.py."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import enlaces, fechas, quickadd, vistas
from .errores import AgendaError
from .fichas import EDITABLES, ESTADOS, ETIQUETAS_ESTADO, Fichas, Tarea
from .notas import Notas, es_diario
from .proyectos import datos_dir

AYUDA = """\
SkylerDeck: tareas en fichas Markdown (datos/tareas/T-NNN.md).

Ejemplos:
  agenda anadir "Llamar al dentista mañana 10:00 #Salud p1 @teléfono"
  agenda anadir --probar "Regar las plantas cada 3 días #Casa"
  agenda lista --vista hoy --ambito laboral
  agenda mover T-012 esperando --a "Proveedor" --revisar 2026-10-28
  agenda hecha T-012 --quien claude
  agenda proyecto nuevo "Clientes" --ambito laboral

Los agentes firman con --quien (sale en la bitácora) y pueden pedir --json.
Datos en AGENDA_DATOS (por defecto, datos/ junto al código).
"""


def _quien(args) -> str:
    return args.quien or os.environ.get("AGENDA_QUIEN") or "yo"


def _linea(t: Tarea, fichas: Fichas) -> str:
    bits = [f"{t.id}", "●" if t.ambito == "laboral" else "○", t.prioridad, t.titulo]
    meta = []
    if t.proyecto:
        p = fichas.proyectos.buscar(t.proyecto)
        meta.append(f"#{p.nombre if p else t.proyecto}")
    if t.fecha:
        meta.append(vistas.cuando(t))
    if t.repetir:
        meta.append(f"↻ {t.repetir}" + (f" hasta {fechas.corta(fechas.desde_iso(t.hasta))}" if t.hasta else ""))
    if t.estado != "pendiente":
        estado = ETIQUETAS_ESTADO.get(t.estado, t.estado)
        meta.append(f"{estado} a {t.esperando_a}" if t.esperando_a else estado)
    if t.revisar and t.abierta:
        meta.append(f"revisar {fechas.humana(fechas.desde_iso(t.revisar))}")
    if t.subtareas:
        meta.append(f"{sum(s.hecha for s in t.subtareas)}/{len(t.subtareas)}")
    meta += [f"@{e}" for e in t.etiquetas]
    if t.caso:
        meta.append(f"ref. {t.caso}")
    return "  ".join(bits) + (f"   · {' · '.join(meta)}" if meta else "")


def _salida(args, data, texto: str) -> None:
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(texto)


def _ficha_texto(t: Tarea, fichas: Fichas) -> str:
    return "\n".join([_linea(t, fichas), f"version {t.version}", "", t.cuerpo.strip()])


def cmd_anadir(args, fichas: Fichas) -> None:
    r = quickadd.parsear(" ".join(args.texto))
    campos = r.campos()
    if args.ambito:
        campos["ambito"] = args.ambito
    if not r.titulo:
        raise AgendaError("No queda título después de leer fechas, proyecto y etiquetas")
    if r.proyecto:
        campos["proyecto"] = fichas.proyectos.obtener(r.proyecto).slug
    if args.probar:
        resumen = [f"título     {r.titulo}"]
        for key in ("fecha", "hora", "duracion", "repetir", "hasta", "proyecto", "prioridad", "etiquetas", "ambito"):
            if campos.get(key):
                resumen.append(f"{key:<10} {campos[key]}")
        resumen += [f"otra fecha {d}" for d in r.otras_fechas]
        resumen += [f"aviso      {a}" for a in r.avisos]
        _salida(args, {**r.to_dict(), "campos": campos}, "\n".join(resumen))
        return
    nota = f"Creada con «{' '.join(args.texto)}»"
    tareas = [fichas.crear({**campos, "fecha": dia} if dia else campos, _quien(args), nota=nota)
              for dia in [None, *r.otras_fechas]]  # «el lunes y el miércoles»: one task per day
    for aviso in r.avisos:
        print(f"Aviso: {aviso}", file=sys.stderr)
    _salida(args, [t.to_dict() for t in tareas] if len(tareas) > 1 else tareas[0].to_dict(),
            "\n".join(_linea(t, fichas) for t in tareas))


def cmd_nueva(args, fichas: Fichas) -> None:
    datos = {k: getattr(args, k) for k in EDITABLES if getattr(args, k, None)}
    datos["estado"] = args.estado
    datos["contexto"] = args.contexto
    datos["subtareas"] = args.subtarea
    t = fichas.crear(datos, _quien(args), nota=args.nota or "")
    _salida(args, t.to_dict(), _linea(t, fichas))


def cmd_lista(args, fichas: Fichas) -> None:
    proyecto = fichas.proyectos.obtener(args.proyecto).slug if args.proyecto else None
    tareas = vistas.filtrar(fichas.listar(), args.vista, ambito=args.ambito, proyecto=proyecto,
                            estado=args.estado, etiqueta=args.etiqueta)
    texto = "\n".join(_linea(t, fichas) for t in tareas) or "(nada)"
    _salida(args, [t.to_dict() for t in tareas], texto)


def cmd_ver(args, fichas: Fichas) -> None:
    t = fichas.obtener(args.id)
    _salida(args, t.to_dict(con_cuerpo=True), _ficha_texto(t, fichas))


def cmd_editar(args, fichas: Fichas) -> None:
    cambios = {k: getattr(args, k) for k in EDITABLES if getattr(args, k, None) is not None}
    t = fichas.editar(args.id, cambios, _quien(args), args.version)
    _salida(args, t.to_dict(), _linea(t, fichas))


def cmd_mover(args, fichas: Fichas) -> None:
    t = fichas.mover(args.id, args.estado, _quien(args), args.version, args.a, args.revisar, args.nota or "")
    _salida(args, t.to_dict(), _linea(t, fichas))


def cmd_hecha(args, fichas: Fichas) -> None:
    t = fichas.completar(args.id, _quien(args), args.version, args.nota or "")
    _salida(args, t.to_dict(), _linea(t, fichas))


def cmd_soltar(args, fichas: Fichas) -> None:
    t = fichas.mover(args.id, "soltada", _quien(args), args.version, nota=args.nota or "")
    _salida(args, t.to_dict(), _linea(t, fichas))


def cmd_nota(args, fichas: Fichas) -> None:
    t = fichas.anotar(args.id, " ".join(args.texto), _quien(args))
    _salida(args, t.to_dict(), _linea(t, fichas))


def cmd_sub(args, fichas: Fichas) -> None:
    accion = "anadir" if args.accion in ("anadir", "añadir") else args.accion
    t = fichas.subtarea(args.id, accion, " ".join(args.valor), _quien(args), args.version)
    lineas = [f"{i}. [{'x' if s.hecha else ' '}] {s.texto}" for i, s in enumerate(t.subtareas, 1)]
    _salida(args, t.to_dict(), "\n".join([_linea(t, fichas), *lineas]))


def cmd_proyecto(args, fichas: Fichas) -> None:
    p = fichas.proyectos
    if args.accion == "nuevo":
        nuevo = p.crear(" ".join(args.nombre), args.ambito)
        _salida(args, nuevo.to_dict(), f"Proyecto «{nuevo.nombre}» ({nuevo.ambito}) · #{nuevo.slug}")
    elif args.accion == "renombrar":
        if len(args.nombre) != 2:
            raise AgendaError('Uso: agenda proyecto renombrar <proyecto> "Nombre nuevo"')
        cambiado = enlaces.renombrar_proyecto(fichas, Notas(fichas.datos), args.nombre[0], args.nombre[1], _quien(args))
        _salida(args, cambiado.to_dict(), f"Ahora se llama «{cambiado.nombre}» (#{cambiado.slug})")
    else:
        tareas = [t for t in fichas.listar() if t.abierta]
        filas, data = [], []
        for proyecto in p.listar(args.ambito):
            n = sum(1 for t in tareas if t.proyecto == proyecto.slug)
            filas.append(f"{proyecto.ambito:<9} {proyecto.nombre:<24} {n:>3}  #{proyecto.slug}")
            data.append({**proyecto.to_dict(), "abiertas": n})
        _salida(args, data, "\n".join(filas) or "(sin proyectos)")


def cmd_notas(args, fichas: Fichas) -> None:
    notas = Notas(fichas.datos)
    accion, valores = args.accion, args.valores
    if accion == "lista":
        lista = notas.listar()
        _salida(args, [n.to_dict() for n in lista],
                "\n".join(f"{n.slug:<32} {n.titulo}" + (f"  · #{n.proyecto}" if n.proyecto else "") for n in lista) or "(sin notas)")
    elif accion == "ver":
        if len(valores) != 1:
            raise AgendaError("Uso: agenda notas ver <nota>")
        n = notas.obtener(_slug_nota(notas, valores[0]))
        menciones = enlaces.Indice(fichas, notas).menciones("nota", n.slug)
        lineas = [f"# {n.titulo}", f"version {n.version or '(sin crear)'}", "", n.cuerpo]
        if menciones:
            lineas += ["", "Mencionado en:"] + [f"- {m['titulo']}: {m['fragmento']}" for m in menciones]
        _salida(args, {**n.to_dict(con_cuerpo=True), "menciones": menciones}, "\n".join(lineas))
    elif accion == "nueva":
        if not valores:
            raise AgendaError('Uso: agenda notas nueva "Título" [--texto …] [--proyecto …]')
        n = notas.crear(" ".join(valores), args.texto or "", args.proyecto or "")
        _salida(args, n.to_dict(), f"Nota «{n.titulo}» · {n.slug}")
    elif accion in ("anadir", "añadir", "diario"):
        if accion == "diario":
            slug = valores[0] if valores and es_diario(valores[0]) else fechas.iso(fechas.hoy())
            texto = args.texto
        else:
            if not valores:
                raise AgendaError('Uso: agenda notas anadir <nota> --texto "…"')
            slug, texto = _slug_nota(notas, valores[0]), args.texto
        if not texto:
            raise AgendaError("Falta --texto")
        actual = notas.obtener(slug)
        cuerpo = f"{actual.cuerpo}\n\n{texto.strip()}" if actual.cuerpo else texto.strip()
        n = enlaces.guardar_nota(fichas, notas, slug, cuerpo=cuerpo, quien=_quien(args))
        _salida(args, n.to_dict(), f"Añadido a «{n.titulo}»")
    elif accion == "borrar":
        if len(valores) != 1:
            raise AgendaError("Uso: agenda notas borrar <nota>")
        slug = _slug_nota(notas, valores[0])
        nombre = notas.borrar(slug)
        _salida(args, {"papelera": nombre}, f"Nota movida a la papelera: datos/papelera/notas/{nombre}")
    elif accion == "menciones":
        if len(valores) != 1:
            raise AgendaError("Uso: agenda notas menciones <T-012 | nota | proyecto>")
        idx = enlaces.Indice(fichas, notas)
        destino = idx.resolver(valores[0])
        if not destino:
            raise AgendaError(f"«{valores[0]}» no es ninguna tarea, nota ni proyecto", 404)
        lista = idx.menciones(destino.tipo, destino.ref)
        _salida(args, lista, "\n".join(f"{m['tipo']:<6} {m['titulo']}: {m['fragmento']}" for m in lista) or "(nadie lo menciona)")


def _slug_nota(notas: Notas, texto: str) -> str:
    """Accepts a slug, a date or a title."""
    if es_diario(texto):
        return texto
    por_titulo = notas.buscar_titulo(texto)
    return por_titulo.slug if por_titulo else texto


def cmd_ruta(args, fichas: Fichas) -> None:
    print(fichas.datos)


def _campos_tarea(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--titulo")
    parser.add_argument("--ambito", choices=["personal", "laboral"])
    parser.add_argument("--proyecto")
    parser.add_argument("--prioridad", choices=["p1", "p2", "p3", "p4"])
    parser.add_argument("--etiquetas", help="separadas por comas")
    parser.add_argument("--fecha", help="AAAA-MM-DD")
    parser.add_argument("--hora", help="HH:MM")
    parser.add_argument("--duracion", help="minutos")
    parser.add_argument("--repetir", help="cada lunes, cada 3 días…")
    parser.add_argument("--hasta", help="AAAA-MM-DD: último día de la repetición (sin él, no acaba)")
    parser.add_argument("--esperando-a", dest="esperando_a")
    parser.add_argument("--revisar", help="AAAA-MM-DD")
    parser.add_argument("--caso", help="referencia corta: expediente, pedido…")


def construir_parser() -> argparse.ArgumentParser:
    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--json", action="store_true", help="salida en JSON")
    comun.add_argument("--quien", help="quién hace el cambio (para la bitácora)")

    parser = argparse.ArgumentParser(prog="agenda", description=AYUDA, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="orden")

    p = sub.add_parser("anadir", aliases=["añadir", "add"], parents=[comun], help="crea una tarea con quick-add")
    p.add_argument("texto", nargs="+")
    p.add_argument("--probar", action="store_true", help="solo enseña lo que entiende, no crea nada")
    p.add_argument("--ambito", choices=["personal", "laboral"], help="si no hay #proyecto (por defecto, personal)")
    p.set_defaults(func=cmd_anadir)

    p = sub.add_parser("nueva", parents=[comun], help="crea una tarea campo a campo")
    p.add_argument("titulo")
    _campos_tarea(p)
    p.add_argument("--estado", default="pendiente", choices=ESTADOS)
    p.add_argument("--contexto")
    p.add_argument("--subtarea", action="append", default=[])
    p.add_argument("--nota")
    p.set_defaults(func=cmd_nueva)

    p = sub.add_parser("lista", parents=[comun], help="lista tareas")
    p.add_argument("--vista", default="abiertas", choices=vistas.VISTAS)
    p.add_argument("--ambito", choices=["todo", "personal", "laboral"])
    p.add_argument("--proyecto")
    p.add_argument("--estado", choices=ESTADOS)
    p.add_argument("--etiqueta")
    p.set_defaults(func=cmd_lista)

    p = sub.add_parser("ver", parents=[comun], help="enseña una ficha entera")
    p.add_argument("id")
    p.set_defaults(func=cmd_ver)

    p = sub.add_parser("editar", parents=[comun], help="cambia campos (vacío borra)")
    p.add_argument("id")
    _campos_tarea(p)
    p.add_argument("--version", help="rechaza el cambio si la ficha ha cambiado desde esa versión")
    p.set_defaults(func=cmd_editar)

    p = sub.add_parser("mover", parents=[comun], help="cambia el estado")
    p.add_argument("id")
    p.add_argument("estado", choices=ESTADOS)
    p.add_argument("--a", help="a quién esperas")
    p.add_argument("--revisar", help="cuándo vuelves a mirarla (AAAA-MM-DD)")
    p.add_argument("--nota")
    p.add_argument("--version")
    p.set_defaults(func=cmd_mover)

    for nombre, func, ayuda in (("hecha", cmd_hecha, "la cierra (si se repite, pasa a la siguiente fecha)"),
                                ("soltar", cmd_soltar, "la deja sin hacer")):
        p = sub.add_parser(nombre, parents=[comun], help=ayuda)
        p.add_argument("id")
        p.add_argument("--nota")
        p.add_argument("--version")
        p.set_defaults(func=func)

    p = sub.add_parser("nota", parents=[comun], help="apunta una línea en la bitácora")
    p.add_argument("id")
    p.add_argument("texto", nargs="+")
    p.set_defaults(func=cmd_nota)

    p = sub.add_parser("sub", parents=[comun], help="subtareas: anadir TEXTO | marcar N | desmarcar N | quitar N")
    p.add_argument("id")
    p.add_argument("accion", choices=["anadir", "añadir", "marcar", "desmarcar", "quitar"])
    p.add_argument("valor", nargs="+")
    p.add_argument("--version")
    p.set_defaults(func=cmd_sub)

    p = sub.add_parser("proyecto", parents=[comun], help="lista | nuevo NOMBRE --ambito | renombrar PROYECTO NOMBRE")
    p.add_argument("accion", nargs="?", default="lista", choices=["lista", "nuevo", "renombrar"])
    p.add_argument("nombre", nargs="*")
    p.add_argument("--ambito", choices=["personal", "laboral"])
    p.set_defaults(func=cmd_proyecto)

    p = sub.add_parser("notas", parents=[comun],
                       help="lista | ver NOTA | nueva TÍTULO | anadir NOTA --texto | diario [FECHA] --texto | menciones DESTINO | borrar NOTA")
    p.add_argument("accion", nargs="?", default="lista", choices=["lista", "ver", "nueva", "anadir", "añadir", "diario", "menciones", "borrar"])
    p.add_argument("valores", nargs="*")
    p.add_argument("--texto", help="Markdown; admite [[enlaces]] y @etiquetas")
    p.add_argument("--proyecto")
    p.set_defaults(func=cmd_notas)

    p = sub.add_parser("ruta", parents=[comun], help="carpeta de datos")
    p.set_defaults(func=cmd_ruta)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.cmd == "proyecto" and args.accion == "nuevo" and not args.ambito:
        print("Falta --ambito personal|laboral", file=sys.stderr)
        return 2
    try:
        args.func(args, Fichas(datos_dir()))
    except AgendaError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1 if err.status != 409 else 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
