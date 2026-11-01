import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from . import appsettings, brand, i18n,settings_admin, mcp_server, oidc_providers, users_admin, mfa, aistatus, auth, retype, ontology, brains, deciders_admin, embeddings_admin, graphapi, index, llm, memory, proposals, vocab, entity_types, facts_admin, docs, docindex, docstore, account, jobs, jobs_api, docsources, docroots, docbridge, federation, passkeys, notifications, notify, refqueries, conflicts, corrections, entity_page, brainexport, brainimport, retention
from .config import settings
from .db import list_graphs
from .models import Brain, User
from .store import _factory, engine, init_db


def _bootstrap() -> None:
    """Adopta como brains los grafos listados en MIMIRSYNTH_BOOTSTRAP_GRAPHS ("docs:Docs,otro") SOLO en el primer arranque (sin brains).
    Si no, un brain renombrado o borrado resucitaría en cada reinicio."""
    items = [x.strip() for x in settings.bootstrap_graphs.split(",") if x.strip()]
    if not items:
        return
    with _factory()() as db:
        if db.scalar(select(Brain.id).limit(1)) is not None:
            return
        for it in items:
            slug, _, name = it.partition(":")
            if not (brains.SLUG.match(slug) and brains.GRAPH.match(slug)):
                logging.getLogger("mimirsynth").warning("MIMIRSYNTH_BOOTSTRAP_GRAPHS: se ignora «%s» (slug no válido; formato slug:Nombre)", it)
                continue
            if not db.scalar(select(Brain).where(Brain.slug == slug)):
                db.add(Brain(slug=slug, name=name or slug, graph_name=slug))
        db.commit()


def _retire_local_admin() -> None:
    """En modo OIDC el administrador local del prototipo deja de ser administrador (cuenta huérfana con privilegios)."""
    if settings.auth_mode == "off":
        return
    with _factory()() as db:
        u = db.scalar(select(User).where(User.sub == "local-admin"))
        if u and u.is_admin:
            u.is_admin = False
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auth_mode != "off" and settings.session_secret in ("", "change-me"):
        raise RuntimeError("define MIMIRSYNTH_SESSION_SECRET (p. ej. openssl rand -hex 32): firma las sesiones y cifra los secretos guardados")
    init_db()
    index.init_index()
    try:  # antes de servir: un cambio de modelo de embeddings cortado a medias deja cada grafo coherente con el motor por defecto
        from . import reembed
        reembed.recover_switch()
    except Exception:  # noqa: BLE001  (sin FalkorDB no se puede comprobar; no impide arrancar)
        logging.getLogger("mimirsynth").exception("no se pudo comprobar si quedó un cambio de modelo de embeddings a medias")
    try:
        docstore.purge_stale_uploads()
    except OSError:  # volumen aún no montado o sin permisos: no impide arrancar
        pass
    _bootstrap()
    _retire_local_admin()
    with _factory()() as db:
        auth.ensure_setup_token(db)
    try:
        jobs.recover()
        jobs.prune()
        brainexport.purge()  # after recover: an export cut by the restart is no longer «running»
        brainimport.purge()  # and an import cut by it is undone
    except Exception:  # noqa: BLE001  (la cola no debe impedir arrancar)
        pass
    task = asyncio.create_task(memory.periodic_sync())
    task2 = asyncio.create_task(docsources.periodic())
    task3 = asyncio.create_task(notify.worker(VERSION))
    yield
    task.cancel()
    task2.cancel()
    task3.cancel()


try:
    from importlib.metadata import version as _version
    VERSION = _version("mimirsynth")  # única fuente de verdad: api/pyproject.toml
except Exception:  # noqa: BLE001  (ejecutado sin instalar)
    VERSION = "0.0.0"
app = FastAPI(title=f"{brand.NAME} API", version=VERSION, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, https_only=settings.cookie_secure,
                   same_site="lax", max_age=14 * 24 * 3600)


@app.exception_handler(StarletteHTTPException)
async def localized_errors(request, exc: StarletteHTTPException):
    """Los errores se escriben en español; aquí se traducen al idioma de quien llama (ver i18n.language)."""
    if isinstance(exc.detail, str):
        exc.detail = i18n.translate(exc.detail, i18n.language(request))
    return await http_exception_handler(request, exc)


app.add_middleware(
    CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip() != "*"] or ["http://localhost:5173"],
    allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(brains.router)
app.include_router(graphapi.router)
app.include_router(vocab.router)
app.include_router(entity_types.router)
app.include_router(facts_admin.router)
app.include_router(docs.router)
app.include_router(docsources.router)
app.include_router(docbridge.router)
app.include_router(docroots.router)
app.include_router(jobs_api.router)
app.include_router(account.router)
app.include_router(federation.router)
app.include_router(memory.router)
app.include_router(mcp_server.router)
app.include_router(llm.router)
app.include_router(retype.router)
app.include_router(ontology.router)
app.include_router(aistatus.router)
app.include_router(deciders_admin.router)
app.include_router(embeddings_admin.router)
app.include_router(settings_admin.router)
app.include_router(oidc_providers.router)
app.include_router(users_admin.router)
app.include_router(mfa.router)
app.include_router(passkeys.router)
app.include_router(notifications.router)
app.include_router(corrections.router)
app.include_router(proposals.router)
app.include_router(refqueries.router)
app.include_router(conflicts.router)
app.include_router(entity_page.router)
app.include_router(brainexport.router)
app.include_router(brainimport.router)
app.include_router(retention.router)


@app.get("/api/config")
def get_config():
    return {"name": brand.NAME, "auth_mode": settings.auth_mode, "version": VERSION, "links": brand.links(), "default_language": appsettings.get("default_language"),
            "token_max_days": int(appsettings.get("token_max_days"))}


HEALTH_TIMEOUT = 2.0  # segundos por comprobación: el HEALTHCHECK del contenedor corta a los 3


def _db_ping() -> None:
    with engine().connect() as c:
        c.execute(text("SELECT 1"))


async def _probe(what: str, fn):
    """(True, resultado) si `fn` responde a tiempo; si falla o se pasa de HEALTH_TIMEOUT, (False, None) y el motivo solo al log."""
    try:
        return True, await asyncio.wait_for(asyncio.to_thread(fn), HEALTH_TIMEOUT)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("mimirsynth").warning("health: %s no responde: %s", what, str(e)[:300] or type(e).__name__)
        return False, None


@app.get("/api/health")
async def health():
    """Responder ya dice que la app está viva; `db` (PostgreSQL) y `graph` (FalkorDB) dicen si llega a cada uno. Con alguno caído
    responde 503 con el mismo cuerpo, para que un monitor externo distinga «app caída» (sin respuesta) de «app viva, BD caída»:
    las notificaciones no pueden avisar de la caída de PostgreSQL porque se guardan en él. Es pública: sin detalles del error."""
    (db_ok, _), (graph_ok, graphs) = await asyncio.gather(_probe("PostgreSQL", _db_ping), _probe("FalkorDB", list_graphs))
    body = {"ok": db_ok and graph_ok, "db": db_ok, "graph": graph_ok, "graphs": len(graphs) if graph_ok else None}
    return JSONResponse(body, status_code=200 if body["ok"] else 503)


# --- SPA (build de web/) servida por la propia API: un solo contenedor ---
_static = Path(settings.static_dir) if settings.static_dir else None
if _static and _static.is_dir():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _static / path
        return FileResponse(f if path and f.is_file() else _static / "index.html")
