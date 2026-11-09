"""The graph database connection (#358): where it comes from, testing one before it is saved, and Administration → Graph.

- **Where it comes from**, in this order:
  1. The environment, when MIMIRSYNTH_GRAPH_BACKEND, MIMIRSYNTH_FALKOR_HOST or MIMIRSYNTH_NEO4J_URI has a value (compose passes the ones
     not set as empty values, which do not count). It is shown read-only: it changes in `.env`, with a restart.
  2. The connection saved here: one row, with the password sealed like the AI engines' keys.
  3. The bundled FalkorDB (MIMIRSYNTH_FALKOR_BUNDLED_HOST, port 6379), which is what an installation with neither uses.
- **The test** connects to a connection that has not been saved and checks, in order: the address resolves and accepts a connection
  (with TLS when asked), the credentials, the server's version, that it can write (a probe node, created and removed at once in a hidden
  partition) and what the database holds (graphs, or Graphiti group_ids, with their node counts). A failure names its cause.
- **Saving** runs the test again on the server, so a connection that does not pass is never saved, and switches the backend without a
  restart (`graphdb.reload`). The data is not moved: a brain whose graph is not in the new database comes up empty.

During the first start (no administrator yet) the test also answers to the first-start code in `X-Setup-Code`, so the installer can
check an existing database before anyone has an account. Saving always needs an administrator.
"""
import hmac
import logging
import socket
import ssl
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, i18n, ratelimit
from .config import settings
from .deps import audit, current_user, require_admin
from .graphdb import BACKENDS, DEFAULT_PORTS, Connection, reload
from .graphdb.probe import PROBE_PREFIX, Unsupported, cause, opener  # noqa: F401  (PROBE_PREFIX: for the tests)
from .models import Brain, GraphConnection, User, now
from .secretbox import seal, unseal
from .store import _factory, get_db

router = APIRouter(prefix="/api/admin/graph")
log = logging.getLogger("mimirsynth")

ROW = 1  # the one saved connection
TIMEOUT = 10.0  # seconds each step of the test may take
MAX_LISTED = 500  # graphs or group_ids the test lists at most
_ENV_KEYS = ("graph_backend", "falkor_host", "neo4j_uri")


# --- where the connection comes from ---------------------------------------------------------------

def env_defines() -> bool:
    """Whether the environment chooses the graph database: one of its variables is set and not empty."""
    return any(k in settings.model_fields_set and str(getattr(settings, k) or "").strip() for k in _ENV_KEYS)


def _split_uri(uri: str) -> tuple[str, int, bool]:
    u = urlsplit(uri.strip())
    return u.hostname or "", u.port or DEFAULT_PORTS["neo4j"], u.scheme.endswith(("+s", "+ssc"))


def env_connection() -> Connection | None:
    if not env_defines():
        return None
    kind = (settings.graph_backend or "").strip().lower() or ("neo4j" if settings.neo4j_uri.strip() else "falkordb")
    if kind not in BACKENDS:
        raise ValueError(f"MIMIRSYNTH_GRAPH_BACKEND={settings.graph_backend!r}: it must be «falkordb» or «neo4j»")
    if kind == "neo4j":
        if not settings.neo4j_uri.strip():
            raise ValueError("MIMIRSYNTH_GRAPH_BACKEND=neo4j needs MIMIRSYNTH_NEO4J_URI (bolt://host:7687)")
        host, port, tls = _split_uri(settings.neo4j_uri)
        return Connection("neo4j", host, port, settings.neo4j_user or "neo4j", settings.neo4j_password, tls, settings.neo4j_database,
                          uri=settings.neo4j_uri.strip())
    return Connection("falkordb", settings.falkor_host.strip() or bundled().host, settings.falkor_port, settings.falkor_username,
                      settings.falkor_password)


def bundled() -> Connection:
    return Connection("falkordb", settings.falkor_bundled_host.strip() or "localhost", DEFAULT_PORTS["falkordb"])


def _from_row(row: GraphConnection, password: str | None = None) -> Connection:
    return Connection(row.backend, row.host, row.port, row.username, unseal(row.password_enc) if password is None else password, row.tls,
                      row.database)


def current(db: Session | None = None) -> tuple[Connection, str]:
    """The connection in force and where it comes from: `env`, `db` or `default` (the bundled FalkorDB)."""
    env = env_connection()
    if env:
        return env, "env"
    if db is None:
        with _factory()() as s:
            return current(s)
    row = db.get(GraphConnection, ROW)
    return (_from_row(row), "db") if row else (bundled(), "default")


def describe(db: Session) -> dict:
    """The connection in force for Administration → Graph and the setup wizard; never its password."""
    env, row = env_connection(), None
    if env:
        c, source = env, "env"
    else:
        row = db.get(GraphConnection, ROW)
        c, source = (_from_row(row, password=""), "db") if row else (bundled(), "default")
    return {"source": source, "editable": source != "env", "backend": c.backend, "label": c.label, "host": c.host,
            "port": c.port or DEFAULT_PORTS[c.backend], "user": c.user, "tls": c.tls, "database": c.database, "address": c.address(),
            "has_password": bool(row.password_enc) if row else bool(c.password), "bundled_host": bundled().host,
            "updated_at": row.updated_at if row else None}


# --- the test ----------------------------------------------------------------------------------

class Failure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _reach(conn: Connection, timeout: float, lang: str) -> None:
    """The name resolves, the port accepts a connection and, with TLS, the handshake and the certificate pass."""
    host, port = conn.host, conn.port or DEFAULT_PORTS[conn.backend]
    address = f"{host}:{port}"
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise Failure("dns", i18n.tr("No se encuentra el servidor «{{host}}»: revisa el nombre.", lang, host=host)) from None
    try:
        s = socket.create_connection((host, port), timeout)
    except ConnectionRefusedError:
        raise Failure("refused", i18n.tr("{{address}} rechaza la conexión: comprueba que el servidor está en marcha y escucha en ese puerto.",
                                         lang, address=address)) from None
    except TimeoutError:
        raise Failure("timeout", i18n.tr("{{address}} no responde a tiempo: revisa la dirección, el puerto y el cortafuegos.", lang,
                                         address=address)) from None
    except OSError as e:
        raise Failure("unreachable", i18n.tr("No se llega a {{address}}: {{error}}", lang, address=address, error=str(e)[:150])) from None
    try:
        if conn.tls:
            ctx = ssl.create_default_context()
            if conn.uri.split("://", 1)[0].endswith("+ssc"):  # Neo4j's «self-signed certificate» schemes
                ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            try:
                ctx.wrap_socket(s, server_hostname=host).close()
            except ssl.SSLCertVerificationError as e:
                raise Failure("tls", i18n.tr("El certificado TLS de {{host}} no es válido: {{error}}", lang, host=host,
                                             error=(e.verify_message or str(e))[:150])) from None
            except (ssl.SSLError, OSError) as e:
                raise Failure("tls", i18n.tr("Falla el TLS con {{address}}: ¿usa TLS el servidor? ({{error}})", lang, address=address,
                                             error=str(e)[:150])) from None
    finally:
        s.close()


def _unsupported(e: Unsupported, conn: Connection, lang: str) -> str:
    if e.what == "redis":
        return i18n.tr("{{address}} es un servidor Redis sin el módulo de grafos: hace falta FalkorDB.", lang, address=conn.address())
    if e.what == "neo4j":
        return i18n.tr("Neo4j {{version}} no está soportado: hace falta la 5.26 o posterior.", lang, version=e.version)
    return i18n.tr("FalkorDB {{version}} no está soportado: hace falta la 4.0 o posterior.", lang, version=e.version)


def _classify(e: Exception, conn: Connection, lang: str) -> tuple[str, str]:
    """The code and the message of a failed step, in the caller's language."""
    if isinstance(e, Failure):
        return e.code, e.message
    if isinstance(e, Unsupported):
        return "version", _unsupported(e, conn, lang)
    code = cause(e)
    if code == "auth":
        return code, i18n.tr("El servidor rechaza el usuario o la contraseña.", lang)
    if code == "permission":
        return code, i18n.tr("El usuario no puede escribir: MimirSynth necesita permiso de lectura y escritura.", lang)
    if code == "database":
        return code, i18n.tr("El servidor no tiene la base de datos «{{database}}».", lang, database=conn.database)
    if code == "timeout" or isinstance(e, TimeoutError):
        return "timeout", i18n.tr("{{address}} no responde a tiempo: revisa la dirección, el puerto y el cortafuegos.", lang,
                                  address=conn.address())
    if code == "protocol":
        return code, i18n.tr("{{address}} acepta la conexión pero no responde como {{label}}: ¿es el puerto de {{label}}, y con TLS si "
                             "el servidor lo pide?", lang, address=conn.address(), label=conn.label)
    if code == "redis":
        return "version", _unsupported(Unsupported("redis"), conn, lang)
    return "other", i18n.tr("La prueba ha fallado: {{error}}", lang, error=str(e)[:200] or type(e).__name__)


def probe(conn: Connection, lang: str = i18n.SOURCE, timeout: float = TIMEOUT) -> dict:
    """Tests a connection step by step and stops at the first that fails. `graphs` is what the database holds, the hidden partitions
    left out; `truncated` says there were more than MAX_LISTED."""
    steps: list[dict] = []
    out: dict = {"ok": False, "backend": conn.backend, "label": conn.label, "address": conn.address(), "steps": steps, "server": None,
                 "graphs": [], "truncated": False, "error": None}
    step, t0, p = "reach", time.monotonic(), None

    def done(name: str) -> None:
        nonlocal step, t0
        steps.append({"step": step, "ok": True, "ms": round((time.monotonic() - t0) * 1000)})
        step, t0 = name, time.monotonic()

    try:
        _reach(conn, timeout, lang)
        done("auth")
        p = opener(conn, timeout)
        p.auth()
        done("version")
        out["server"] = p.version()
        done("write")
        p.write()
        done("list")
        graphs = p.graphs(MAX_LISTED + 1)
        out["graphs"], out["truncated"] = graphs[:MAX_LISTED], len(graphs) > MAX_LISTED
        done("")
        out["ok"] = True
    except Exception as e:  # noqa: BLE001  (every failure is an answer, with its cause)
        code, message = _classify(e, conn, lang)
        if code == "other":
            log.warning("graph connection test against %s failed at %s", conn.address(), step, exc_info=True)
        steps.append({"step": step, "ok": False, "ms": round((time.monotonic() - t0) * 1000)})
        out["error"] = {"step": step, "code": code, "message": message}
    finally:
        if p is not None:
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass
    return out


# --- Administration → Graph ----------------------------------------------------------------------

class ConnIn(BaseModel):
    backend: str = Field(pattern="^(falkordb|neo4j)$")
    host: str = Field(min_length=1, max_length=255, pattern=r"^[^\s/@?#]+$")
    port: int = Field(0, ge=0, le=65535)  # 0: the backend's usual port
    user: str = Field("", max_length=255)
    password: str | None = Field(None, max_length=1024)  # None: the saved one, for the same server
    tls: bool = False
    database: str = Field("", max_length=255)


def _connection(body: ConnIn, db: Session) -> Connection:
    """What the form describes. The saved password is only reused for the same server, so it is never sent anywhere else."""
    password = body.password
    host = body.host.strip()
    port = body.port or DEFAULT_PORTS[body.backend]
    if password is None:
        row = db.get(GraphConnection, ROW)
        same = row and (row.backend, row.host, row.port) == (body.backend, host, port)
        password = unseal(row.password_enc) if same else ""
    return Connection(body.backend, host, port, body.user.strip(), password, body.tls,
                      body.database.strip() if body.backend == "neo4j" else "")


def admin_or_setup(request: Request, db: Session = Depends(get_db)) -> User | None:
    """An instance administrator or, while there is none, whoever has the first-start code (the installer)."""
    code = request.headers.get("x-setup-code")
    if code is not None and auth.setup_required(db):
        if not ratelimit.allow(f"setup:{auth._ip(request)}", 10, 600):
            raise HTTPException(429, "demasiados intentos")
        if not auth._SETUP_TOKEN or not hmac.compare_digest(code.strip(), auth._SETUP_TOKEN):
            raise HTTPException(403, "código de instalación incorrecto (míralo en el log del servicio)")
        return None
    return require_admin(request, current_user(request, db))


def _with_brains(result: dict, db: Session) -> dict:
    """Marks the graphs that are already a brain's."""
    taken = {g: s for s, g in db.execute(select(Brain.slug, Brain.graph_name))}
    for g in result["graphs"]:
        g["brain"] = taken.get(g["name"])
    return result


@router.get("")
def get_connection(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return describe(db)


@router.post("/test")
def test_connection(request: Request, body: ConnIn | None = Body(None), _: User | None = Depends(admin_or_setup), db: Session = Depends(get_db)):
    """Tests the connection in the body, without saving it; with no body, the one in force."""
    conn = _connection(body, db) if body else current(db)[0]
    return _with_brains(probe(conn, i18n.language(request)), db)


@router.put("")
def save_connection(body: ConnIn, request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if env_defines():
        raise HTTPException(409, "la conexión del grafo viene de las variables de entorno: cámbiala en .env y reinicia")
    conn = _connection(body, db)
    result = probe(conn, i18n.language(request))
    if not result["ok"]:
        raise HTTPException(422, f"no se guarda: la prueba de conexión falla. {result['error']['message']}")
    before = describe(db)
    row = db.get(GraphConnection, ROW) or GraphConnection(id=ROW)
    row.backend, row.host, row.port, row.username = conn.backend, conn.host, conn.port, conn.user
    row.password_enc, row.tls, row.database = seal(conn.password), conn.tls, conn.database
    row.updated_at, row.updated_by = now(), user.id
    db.add(row)
    db.commit()
    changed = before["backend"] != conn.backend or before["address"] != conn.address() or before["database"] != conn.database
    audit(db, user, "graph.connection", backend=conn.backend, address=conn.address(), database=conn.database or None, moved=changed)
    reload()
    return {**describe(db), "changed": changed, "test": _with_brains(result, db)}
