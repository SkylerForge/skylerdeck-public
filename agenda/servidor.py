"""HTTP API and the page. Every change goes through fichas.py; see seguridad.py for access."""
from __future__ import annotations

import os
import re
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import __version__, avisos, enlaces, fechas, panel, quickadd, seguridad, semana
from .errores import AgendaError
from .fichas import Fichas
from .notas import Notas
from .proyectos import datos_dir

STATIC = Path(__file__).resolve().parent.parent / "static"


def crear_app(datos: Path | None = None, clave: str | None = None, hosts_extra: set[str] | None = None,
              demo: bool = False) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
    app.config["JSON_AS_ASCII"] = False
    fichas = Fichas(datos or datos_dir())
    notas = Notas(fichas.datos)
    seguridad.instalar(app, "" if demo else (clave or seguridad.leer_o_crear_clave()), hosts_extra or set(), demo)

    def body() -> dict:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise AgendaError("Falta el cuerpo JSON")
        return data

    def indice() -> enlaces.Indice:
        return enlaces.Indice(fichas, notas)

    def ficha(id_: str):
        data = panel.ficha_json(fichas, id_, fechas.ahora())
        data["menciones"] = indice().menciones("tarea", data["id"])
        return jsonify(data)

    def nota_json(slug: str):
        n = notas.obtener(slug)
        data = n.to_dict(con_cuerpo=True)
        data["menciones"] = indice().menciones("nota", n.slug)
        p = fichas.proyectos.buscar(n.proyecto) if n.proyecto else None
        data["proyecto_nombre"] = p.nombre if p else ""
        return jsonify(data)

    @app.errorhandler(AgendaError)
    def _error(err: AgendaError):
        return jsonify(error=str(err)), err.status

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/api/version")
    def version():
        return jsonify(datos=panel.huella(fichas.dir, fichas.proyectos.dir, notas.dir), app=panel.huella(STATIC))

    @app.get("/api/panel")
    def panel_estado():
        return jsonify(panel.construir(fichas, request.args.get("ambito"), fechas.ahora()))

    @app.get("/api/semana")
    def semana_estado():
        desde = request.args.get("desde")
        try:
            dia = fechas.desde_iso(desde) if desde else None
        except ValueError as err:
            raise AgendaError("«desde» debe ser AAAA-MM-DD") from err
        return jsonify(con_notas_dia(semana.construir(fichas, request.args.get("ambito"), fechas.ahora(), dia)))

    @app.get("/api/mes")
    def mes_estado():
        mes = request.args.get("mes")
        if mes and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
            raise AgendaError("«mes» debe ser AAAA-MM")
        return jsonify(con_notas_dia(semana.construir_mes(fichas, request.args.get("ambito"), fechas.ahora(), mes)))

    def con_notas_dia(data: dict) -> dict:
        dias = {d["fecha"] for d in data["dias"]}
        diarios = [n for n in notas.listar() if n.tipo == "diario" and n.slug in dias]
        data["notas_dia"] = sorted(n.slug for n in diarios)
        data["textos_dia"] = {n.slug: n.cuerpo for n in diarios}  # the chosen day shows its note
        return data

    @app.post("/api/parsear")
    def parsear():
        r = quickadd.parsear(str(body().get("texto", ""))[:500])
        data = r.to_dict()
        if r.proyecto:
            p = fichas.proyectos.buscar(r.proyecto)
            data["proyecto_nombre"] = p.nombre if p else None
        return jsonify(data)

    @app.post("/api/tareas")
    def crear():
        data = body()
        texto = str(data.get("texto", "")).strip()[:500]
        if not texto:
            raise AgendaError("Escribe la tarea")
        r = quickadd.parsear(texto)
        if not r.titulo:
            raise AgendaError("No queda título después de leer fechas, proyecto y etiquetas")
        campos = r.campos()
        proyecto = r.proyecto or data.get("proyecto")
        if proyecto:
            campos["proyecto"] = fichas.proyectos.obtener(proyecto).slug
        elif data.get("ambito") in ("personal", "laboral"):
            campos["ambito"] = data["ambito"]
        t = fichas.crear(campos, nota=f"Creada con «{texto}»")
        for dia in r.otras_fechas:  # «el lunes y el miércoles»: one task per day
            fichas.crear({**campos, "fecha": dia}, nota=f"Creada con «{texto}»")
        return jsonify(tarea=panel.ficha_json(fichas, t.id, fechas.ahora()), avisos=r.avisos,
                       otras=len(r.otras_fechas)), 201

    @app.get("/api/tareas/<id_>")
    def ver(id_):
        return ficha(id_)

    @app.patch("/api/tareas/<id_>")
    def editar(id_):
        data = body()
        fichas.editar(id_, data.get("cambios") or {}, version=data.get("version"))
        return ficha(id_)

    @app.post("/api/tareas/<id_>/estado")
    def estado(id_):
        data = body()
        fichas.mover(id_, str(data.get("estado", "")), version=data.get("version"),
                     esperando_a=data.get("esperando_a"), revisar=data.get("revisar"))
        return ficha(id_)

    @app.post("/api/tareas/<id_>/saltar")
    def saltar(id_):
        fichas.saltar(id_, version=body().get("version"))
        return ficha(id_)

    @app.post("/api/tareas/<id_>/contexto")
    def contexto(id_):
        data = body()
        fichas.contexto(id_, str(data.get("texto", "")), version=data.get("version"))
        return ficha(id_)

    @app.post("/api/tareas/<id_>/subtareas")
    def subtareas(id_):
        data = body()
        fichas.subtarea(id_, str(data.get("accion", "")), str(data.get("valor", "")), version=data.get("version"))
        return ficha(id_)

    @app.post("/api/tareas/<id_>/nota")
    def nota(id_):
        fichas.anotar(id_, str(body().get("texto", "")))
        return ficha(id_)

    @app.post("/api/proyectos")
    def proyecto_nuevo():
        data = body()
        p = fichas.proyectos.crear(str(data.get("nombre", "")), str(data.get("ambito", "")))
        return jsonify(p.to_dict()), 201

    @app.patch("/api/proyectos/<slug>")
    def proyecto_renombrar(slug):
        p = enlaces.renombrar_proyecto(fichas, notas, slug, str(body().get("nombre", "")))
        return jsonify(p.to_dict())

    # ---------- reminders (sent by agenda.avisos, not by this process) ----------

    def avisos_json():
        estado = avisos.leer_estado()
        cred = avisos.credenciales()
        return jsonify(ajustes=avisos.leer_ajustes(), antelaciones=list(avisos.ANTELACIONES),
                       configurado=cred is not None,
                       ultima_revision=estado.get("ultima_revision"), ultimo_envio=estado.get("ultimo_envio"),
                       ultimo_error=estado.get("ultimo_error"), copia=avisos.leer_copia(),
                       prueba_pendiente=(avisos.config_dir() / "aviso-prueba").exists(), version=__version__)

    @app.get("/api/avisos")
    def avisos_ver():
        return avisos_json()

    @app.put("/api/avisos")
    def avisos_ajustes():
        avisos.guardar_ajustes(body().get("ajustes") or {})
        return avisos_json()

    @app.post("/api/avisos/prueba")
    def avisos_prueba():
        avisos.pedir_prueba()
        return avisos_json()

    # ---------- notes, links, tags, search ----------

    @app.get("/api/notas")
    def notas_lista():
        lista = notas.listar()
        tipo, proyecto = request.args.get("tipo"), request.args.get("proyecto")
        if tipo:
            lista = [n for n in lista if n.tipo == tipo]
        if proyecto:
            lista = [n for n in lista if n.proyecto == proyecto]
        data = {"notas": [n.to_dict() for n in lista]}
        if proyecto:
            data["menciones"] = indice().menciones("proyecto", proyecto)
        return jsonify(data)

    @app.get("/api/notas/<slug>")
    def nota_ver(slug):
        return nota_json(slug)

    @app.post("/api/notas")
    def nota_nueva():
        data = body()
        n = notas.crear(str(data.get("titulo", "")), str(data.get("cuerpo", "")), str(data.get("proyecto") or ""))
        return nota_json(n.slug), 201

    @app.put("/api/notas/<slug>")
    def nota_guardar(slug):
        data = body()
        enlaces.guardar_nota(fichas, notas, slug, cuerpo=data.get("cuerpo"), titulo=data.get("titulo"),
                             proyecto=data.get("proyecto"), version=data.get("version") or None)
        return nota_json(slug)

    @app.delete("/api/notas/<slug>")
    def nota_borrar(slug):
        nombre = notas.borrar(slug, body().get("version") or None)
        return jsonify(papelera=nombre)

    @app.post("/api/notas/restaurar")
    def nota_restaurar():
        n = notas.restaurar(str(body().get("papelera", "")))
        return nota_json(n.slug)

    @app.get("/api/sugerir")
    def sugerir():
        return jsonify(indice().sugerir(request.args.get("q", "")[:120]))

    @app.post("/api/resolver")
    def resolver():
        destinos = [str(d)[:120] for d in (body().get("destinos") or [])][:300]
        idx = indice()
        return jsonify({d: (r.to_dict() if (r := idx.resolver(d)) else None) for d in destinos})

    @app.post("/api/enlace")
    def abrir_enlace():
        data = body()
        destino = enlaces.crear_desde_enlace(fichas, notas, str(data.get("destino", ""))[:120], str(data.get("proyecto") or ""))
        return jsonify(destino.to_dict())

    @app.get("/api/buscar")
    def buscar():
        return jsonify(indice().buscar(request.args.get("q", "")[:120]))

    @app.get("/api/etiquetas")
    def etiquetas():
        return jsonify(indice().etiquetas())

    @app.get("/api/etiquetas/<etiqueta>")
    def etiqueta(etiqueta):
        idx = indice()
        tareas, lista = idx.con_etiqueta(etiqueta)
        nombres = {p.slug: p.nombre for p in idx.proyectos}
        ahora = fechas.ahora()
        return jsonify(etiqueta=etiqueta.lstrip("@").lower(),
                       tareas=[panel.tarea_json(t, nombres, ahora) for t in tareas],
                       notas=[n.to_dict() for n in lista])

    return app


def hosts_extra() -> set[str]:
    return {h.strip() for h in os.environ.get("AGENDA_HOSTS", "").split(",") if h.strip()}
