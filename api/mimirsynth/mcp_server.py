"""Servidor MCP propio (Model Context Protocol, transporte HTTP «streamable» sin estado) para que los agentes usen la memoria de un brain.

Un endpoint por brain, `POST /api/brains/{slug}/mcp`, con el mismo token de API (`Authorization: Bearer mst_…`) y los mismos roles que la API REST:
  · `recall`   (rol lector): contexto de memoria para una consulta (hechos vigentes y caducados, fragmentos de episodios y pasajes de documentos).
  · `remember` (rol colaborador): propone una memoria. Un colaborador entra en cuarentena; un curador la aprueba al instante, como en la API.
Solo herramientas, sin SSE ni sesiones: cada petición se resuelve sola. Solo se admiten tokens de API (nunca la cookie de sesión del navegador)."""
import json
import logging
from importlib.metadata import version as _version
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from . import appsettings
from .deps import BrainCtx, brain_access
from .memory import RecallIn, federated_kwargs
from .proposals import ProposalIn, create
from .recall import recall
from .roles import allows

log = logging.getLogger("mimirsynth.mcp")
router = APIRouter(prefix="/api/brains/{slug}/mcp")
reader = brain_access("reader")
SUPPORTED = ["2025-06-18", "2025-03-26", "2024-11-05"]

TOOLS = [
    {"name": "recall", "title": "Consultar la memoria", "description": "Busca en la memoria del brain y devuelve contexto listo para usar: hechos vigentes (y algunos caducados, marcados), fragmentos de episodios y pasajes de documentos, con su procedencia. Úsala antes de responder sobre decisiones, configuraciones o historia del proyecto.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Qué quieres recordar, en lenguaje natural."},
         "facts": {"type": "integer", "minimum": 0, "maximum": 30, "description": "Máximo de hechos (por defecto 8)."},
         "chunks": {"type": "integer", "minimum": 0, "maximum": 15, "description": "Máximo de fragmentos de episodios (por defecto 4)."},
         "docs": {"type": "integer", "minimum": 0, "maximum": 6, "description": "Máximo de pasajes de documentos; 0 = sin documentos."},
         "max_chars": {"type": "integer", "minimum": 500, "maximum": 30000, "description": "Tamaño máximo del contexto devuelto (por defecto 6000)."},
         "federated": {"type": "boolean", "description": "Incluir lo que otros brains prestan a este (por defecto sí); false = solo la memoria propia."}},
         "required": ["query"]}, "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}},
    {"name": "remember", "title": "Proponer una memoria", "description": "Propone guardar un conocimiento que persista (una decisión, una configuración, un arreglo, un patrón). Según tu rol queda en cuarentena hasta que un curador la apruebe, o se aprueba al instante. No guardes datos efímeros ni secretos.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "maxLength": 255, "description": "Título corto y descriptivo."},
         "body": {"type": "string", "maxLength": 50000, "description": "El contenido: qué se sabe, con el contexto necesario para entenderlo sin la conversación."},
         "source": {"type": "string", "enum": ["text", "message", "json"], "description": "Tipo de contenido (por defecto text)."},
         "source_description": {"type": "string", "maxLength": 255, "description": "De dónde viene (por ejemplo, el agente o la sesión)."},
         "reference_time": {"type": "string", "format": "date-time", "description": "Cuándo ocurrió (ISO 8601); por defecto, ahora."},
         "confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Tu confianza en que es cierto."}},
         "required": ["name", "body"]}, "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}},
]


def _ok(rid, result) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _text(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": error}


def _call(ctx: BrainCtx, request: Request, bg: BackgroundTasks, name: str, args: dict) -> dict:
    """Resultado de una herramienta. Los fallos propios de la herramienta vuelven como `isError` (que el modelo puede leer y corregir)."""
    try:
        if name == "recall":
            body = RecallIn(**args)
            out = recall(ctx.brain.id, ctx.brain.graph_name, body.query, body.facts, body.chunks, body.max_chars, n_docs=body.docs, **federated_kwargs(ctx, body))
            return _text(out["context"] or "No hay nada relevante en la memoria para esa consulta.")
        if name == "remember":
            if not allows(ctx.role, "contributor"):
                return _text("Este token solo puede leer (rol de lector): no puede proponer memorias.", True)
            p = create(ctx, request, bg, ProposalIn(**args))
            msg = "Memoria guardada y aprobada; se ingiere en el grafo." if p.status == "approved" else "Memoria propuesta: queda en cuarentena hasta que un curador la apruebe."
            return _text(f"{msg} (propuesta #{p.id})")
    except ValidationError as e:
        return _text("Argumentos no válidos: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()), True)
    except Exception as e:  # noqa: BLE001
        log.warning("herramienta %s falló: %s", name, e)
        return _text(f"La herramienta falló: {e}", True)
    raise KeyError(name)


def _handle(msg, ctx: BrainCtx, request: Request, bg: BackgroundTasks) -> dict | None:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "petición no válida")
    rid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:  # notificación (p. ej. notifications/initialized): sin respuesta
        return None
    if method == "initialize":
        wanted = params.get("protocolVersion")
        return _ok(rid, {"protocolVersion": wanted if wanted in SUPPORTED else SUPPORTED[0], "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": "mimirsynth", "title": "MimirSynth", "version": _version("mimirsynth")},
                         "instructions": f"Memoria del brain «{ctx.brain.name}». Usa `recall` antes de responder sobre su historia y `remember` para proponer conocimiento que deba persistir."})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in {t["name"] for t in TOOLS} or not isinstance(args, dict):
            return _err(rid, -32602, f"herramienta desconocida o argumentos no válidos: {name}")
        return _ok(rid, _call(ctx, request, bg, name, args))
    return _err(rid, -32601, f"método no soportado: {method}")


def _check_origin(request: Request) -> None:
    """Protección contra DNS rebinding: un navegador envía `Origin`; solo se acepta el propio (los clientes de agentes no lo envían)."""
    origin = request.headers.get("origin")
    if not origin:
        return
    mine = {urlparse(str(request.base_url)).netloc, urlparse(appsettings.get("public_url")).netloc} - {""}
    if urlparse(origin).netloc not in mine:
        raise HTTPException(403, "origen no permitido")


@router.post("")
async def mcp(request: Request, bg: BackgroundTasks, ctx: BrainCtx = Depends(reader)):
    _check_origin(request)
    if getattr(request.state, "token", None) is None:
        raise HTTPException(401, "el servidor MCP solo admite tokens de API (Authorization: Bearer mst_…)", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = json.loads(await request.body())
    except ValueError:
        return JSONResponse(_err(None, -32700, "JSON no válido"), status_code=400)
    from starlette.concurrency import run_in_threadpool
    if isinstance(payload, list):  # lote (2025-03-26)
        out = [r for r in [await run_in_threadpool(_handle, m, ctx, request, bg) for m in payload] if r is not None]
        return JSONResponse(out) if out else Response(status_code=202)
    out = await run_in_threadpool(_handle, payload, ctx, request, bg)
    return JSONResponse(out) if out is not None else Response(status_code=202)


@router.get("")
@router.delete("")
def no_stream(slug: str):
    """Sin flujo SSE ni sesiones: el cliente usa solo POST."""
    return Response(status_code=405, headers={"Allow": "POST"})
