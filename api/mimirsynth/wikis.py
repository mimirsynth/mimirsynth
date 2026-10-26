"""Adaptadores de wiki como fuente de documentos. Cada adaptador se describe a sí mismo (nombre, campos de conexión, cómo llama a sus «colecciones»),
sabe listar colecciones y recorrer sus páginas, y se registra con @register. La interfaz, el cifrado de secretos, la sincronización incremental,
el troceado y el índice son comunes: añadir una wiki es escribir una clase. Solo lectura."""
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterator
from urllib.parse import urlparse

import httpx


class WikiError(RuntimeError):
    pass


@dataclass
class Field:
    """Un dato de conexión que pide el formulario. `secret` se guarda cifrado y nunca se devuelve."""
    name: str
    label: str
    secret: bool = False
    required: bool = True
    placeholder: str = ""
    help: str = ""


@dataclass
class WikiDoc:
    id: str
    title: str
    content: "str | Callable[[], str]"  # el texto, o una función que lo trae: así un reescaneo no descarga las páginas que no han cambiado
    updated_at: datetime
    url: str
    collection: str
    format: str = "markdown"  # markdown | html (el contenido tal como lo da la wiki; el extractor ya sabe leer ambos)

    def read(self) -> str:
        return self.content() if callable(self.content) else self.content


class Adapter:
    """Contrato de un adaptador. Debe ser de solo lectura y no guardar estado entre llamadas."""
    id = ""
    label = ""
    collection_label = "Colecciones"  # cómo las llama la wiki: colecciones, espacios, bases de datos…
    fields: list[Field] = []

    def __init__(self, values: dict):
        for f in self.fields:
            if f.required and not str(values.get(f.name, "")).strip():
                raise WikiError(f"falta «{f.label}»")
        self.v = {f.name: str(values.get(f.name, "")).strip() for f in self.fields}

    def collections(self) -> list[dict]:  # [{id, name, description}]
        raise NotImplementedError

    def documents(self, collection_ids: list[str]) -> Iterator[WikiDoc]:
        raise NotImplementedError


REGISTRY: dict[str, type[Adapter]] = {}


def register(cls: type[Adapter]) -> type[Adapter]:
    REGISTRY[cls.id] = cls
    return cls


def describe() -> list[dict]:
    return [{"id": c.id, "label": c.label, "collection_label": c.collection_label,
             "fields": [{"name": f.name, "label": f.label, "secret": f.secret, "required": f.required, "placeholder": f.placeholder, "help": f.help} for f in c.fields]}
            for c in REGISTRY.values()]


def secret_names(adapter: str) -> set[str]:
    return {f.name for f in REGISTRY[adapter].fields if f.secret} if adapter in REGISTRY else set()


def make(adapter: str, values: dict) -> Adapter:
    if adapter not in REGISTRY:
        raise WikiError(f"adaptador de wiki desconocido: {adapter}")
    return REGISTRY[adapter](values)


def clean_base_url(url: str) -> str:
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        raise WikiError("la URL debe empezar por http:// o https://")
    return f"{u.scheme}://{u.netloc}{u.path.rstrip('/')}"


def _stamp(v: str) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


@register
class Outline(Adapter):
    """Outline (getoutline.com): API RPC con POST y clave de API. Con una clave de alcance limitado a `documents.list` y `collections.list` basta."""
    id, label, collection_label = "outline", "Outline", "Colecciones"
    fields = [Field("base_url", "URL de la wiki", placeholder="https://wiki.ejemplo.com"),
              Field("api_key", "Clave de API", secret=True, help="Crea en Outline una clave solo de lectura (permisos documents.list y collections.list).")]
    PAGE = 100

    def __init__(self, values: dict, timeout: float = 30.0):
        super().__init__(values)
        self.base, self.key, self.timeout = clean_base_url(self.v["base_url"]), self.v["api_key"], timeout

    def _call(self, method: str, body: dict) -> dict:
        for attempt in range(1, 5):
            try:
                r = httpx.post(f"{self.base}/api/{method}", json=body, headers={"Authorization": f"Bearer {self.key}"}, timeout=self.timeout)
            except httpx.HTTPError as e:
                raise WikiError(f"no se pudo conectar con la wiki: {e.__class__.__name__}") from e
            if r.status_code == 429 and attempt < 4:  # límite de tasa de Outline: espera lo que pida
                time.sleep(min(float(r.headers.get("retry-after", 2 * attempt)), 30))
                continue
            if r.status_code in (401, 403):
                raise WikiError("la wiki rechazó la clave de API (o no tiene permiso para esta operación)")
            if r.status_code >= 400:
                raise WikiError(f"la wiki respondió {r.status_code}")
            try:
                return r.json()
            except ValueError as e:
                raise WikiError("la respuesta de la wiki no es JSON: ¿es la URL de una instancia de Outline?") from e
        raise WikiError("la wiki sigue limitando las peticiones")

    def collections(self) -> list[dict]:
        out, offset = [], 0
        while True:
            data = self._call("collections.list", {"limit": self.PAGE, "offset": offset}).get("data", [])
            out += [{"id": c["id"], "name": c.get("name", ""), "description": (c.get("description") or "")[:200]} for c in data]
            if len(data) < self.PAGE:
                return out
            offset += self.PAGE

    def documents(self, collection_ids: list[str]) -> Iterator[WikiDoc]:
        names = {c["id"]: c["name"] for c in self.collections()}
        for cid in collection_ids or list(names):
            offset = 0
            while True:
                data = self._call("documents.list", {"collectionId": cid, "limit": self.PAGE, "offset": offset, "sort": "updatedAt", "direction": "DESC"}).get("data", [])
                for d in data:
                    if d.get("archivedAt") or d.get("deletedAt") or d.get("publishedAt") is None:
                        continue
                    yield WikiDoc(id=d["id"], title=(d.get("title") or "Sin título").strip(), content=d.get("text") or "", updated_at=_stamp(d["updatedAt"]),
                                  url=f"{self.base}{d.get('url', '')}", collection=names.get(cid, ""))
                if len(data) < self.PAGE:
                    break
                offset += self.PAGE


class _Http:
    """Cliente HTTP con la gestión común de errores y del límite de tasa; los adaptadores nuevos lo usan para no repetirla."""

    def __init__(self, base: str, headers: dict, auth=None, timeout: float = 30.0, transport: httpx.BaseTransport | None = None, min_interval: float = 0.0, what: str = "la wiki"):
        self.base, self.what, self.min_interval, self._last = base, what, min_interval, 0.0
        self.client = httpx.Client(headers=headers, auth=auth, timeout=timeout, transport=transport)

    def request(self, method: str, path: str, **kw) -> dict:
        for attempt in range(1, 5):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.client.request(method, f"{self.base}{path}", **kw)
            except httpx.HTTPError as e:
                raise WikiError(f"no se pudo conectar con {self.what}: {e.__class__.__name__}") from e
            if r.status_code == 429 and attempt < 4:
                time.sleep(min(float(r.headers.get("retry-after", 2 * attempt)), 30))
                continue
            if r.status_code in (401, 403):
                raise WikiError(f"{self.what} rechazó las credenciales (o no tienen permiso para esta operación)")
            if r.status_code == 404:
                raise WikiError(f"{self.what} respondió 404: revisa la URL")
            if r.status_code >= 400:
                raise WikiError(f"{self.what} respondió {r.status_code}")
            try:
                return r.json()
            except ValueError as e:
                raise WikiError(f"la respuesta de {self.what} no es JSON: ¿es la URL correcta?") from e
        raise WikiError(f"{self.what} sigue limitando las peticiones")


@register
class Confluence(Adapter):
    """Confluence (Cloud y Data Center) por su API REST v1 (`/rest/api`), solo lectura. Cloud usa correo + token de API; Data Center, un token de acceso personal."""
    id, label, collection_label = "confluence", "Confluence", "Espacios"
    fields = [Field("base_url", "URL de Confluence", placeholder="https://tuempresa.atlassian.net/wiki",
                    help="En Confluence Cloud termina en /wiki. En Data Center es la URL base (p. ej. https://confluence.ejemplo.com)."),
              Field("email", "Correo (solo Cloud)", required=False, placeholder="tu@empresa.com", help="El de la cuenta que creó el token. Déjalo vacío en Data Center."),
              Field("api_token", "Token de API", secret=True, help="Cloud: id.atlassian.com → Seguridad → Crear token de API. Data Center: token de acceso personal con permiso de lectura.")]
    PAGE = 25

    def __init__(self, values: dict, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        super().__init__(values)
        self.base = clean_base_url(self.v["base_url"])
        email, token = self.v["email"], self.v["api_token"]
        self.http = _Http(self.base, {"Accept": "application/json"} | ({} if email else {"Authorization": f"Bearer {token}"}), auth=(email, token) if email else None,
                          timeout=timeout, transport=transport, what="Confluence")

    def collections(self) -> list[dict]:
        out, start = [], 0
        while True:
            data = self.http.request("GET", "/rest/api/space", params={"limit": 100, "start": start, "status": "current", "expand": "description.plain"})
            res = data.get("results", [])
            out += [{"id": c["key"], "name": c.get("name", c["key"]), "description": (((c.get("description") or {}).get("plain") or {}).get("value") or "")[:200]} for c in res]
            if len(res) < 100 or not (data.get("_links") or {}).get("next"):
                return out
            start += len(res)

    def documents(self, collection_ids: list[str]) -> Iterator[WikiDoc]:
        names = {c["id"]: c["name"] for c in self.collections()}
        for key in collection_ids or list(names):
            start = 0
            while True:
                data = self.http.request("GET", "/rest/api/content", params={"spaceKey": key, "type": "page", "status": "current", "expand": "body.storage,version", "limit": self.PAGE, "start": start})
                res = data.get("results", [])
                links = data.get("_links") or {}
                for d in res:
                    when = (d.get("version") or {}).get("when")
                    if not when:
                        continue
                    yield WikiDoc(id=str(d["id"]), title=(d.get("title") or "Sin título").strip(), content=((d.get("body") or {}).get("storage") or {}).get("value") or "",
                                  updated_at=_stamp(when), url=f"{links.get('base') or self.base}{(d.get('_links') or {}).get('webui', '')}", collection=names.get(key, key), format="html")
                if not res or not links.get("next"):
                    break
                start += len(res)


def _rich(parts: list[dict]) -> str:
    """Texto enriquecido de Notion a Markdown mínimo (negrita, cursiva, código, tachado y enlaces)."""
    out = []
    for t in parts or []:
        x = t.get("plain_text", "")
        if not x:
            continue
        a = t.get("annotations") or {}
        if a.get("code"):
            x = f"`{x}`"
        if a.get("bold"):
            x = f"**{x}**"
        if a.get("italic"):
            x = f"*{x}*"
        if a.get("strikethrough"):
            x = f"~~{x}~~"
        if t.get("href"):
            x = f"[{x}]({t['href']})"
        out.append(x)
    return "".join(out)


@register
class Notion(Adapter):
    """Notion por su API pública, solo lectura. Notion no tiene «espacios»: las colecciones son las bases de datos a las que la integración tiene acceso, más
    «Páginas sueltas» (las que no están en una base de datos). El contenido de cada página son sus bloques, convertidos a Markdown."""
    id, label, collection_label = "notion", "Notion", "Bases de datos"
    fields = [Field("token", "Token de la integración", secret=True,
                    help="En notion.so/profile/integrations crea una integración interna (solo permiso de lectura de contenido) y compártela con las páginas o bases de datos que quieras indexar: menú ··· → Conexiones.")]
    BASE = "https://api.notion.com/v1"
    LOOSE = "_pages"
    MAX_DEPTH, MAX_BLOCKS = 6, 4000

    def __init__(self, values: dict, timeout: float = 30.0, transport: httpx.BaseTransport | None = None, min_interval: float = 0.34):
        super().__init__(values)
        self.http = _Http(self.BASE, {"Authorization": f"Bearer {self.v['token']}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"},
                          timeout=timeout, transport=transport, min_interval=min_interval, what="Notion")  # Notion admite unas 3 peticiones por segundo

    def _search(self, kind: str) -> Iterator[dict]:
        cursor = None
        while True:
            body = {"filter": {"property": "object", "value": kind}, "page_size": 100, "sort": {"direction": "descending", "timestamp": "last_edited_time"}}
            if cursor:
                body["start_cursor"] = cursor
            data = self.http.request("POST", "/search", json=body)
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            cursor = data.get("next_cursor")

    @staticmethod
    def _id(x: str) -> str:
        return (x or "").replace("-", "")

    def collections(self) -> list[dict]:
        out = [{"id": self._id(d["id"]), "name": _rich(d.get("title")) or "Sin título", "description": _rich(d.get("description"))[:200]}
               for d in self._search("database") if not d.get("archived") and not d.get("in_trash")]
        return out + [{"id": self.LOOSE, "name": "Páginas sueltas", "description": "Páginas que no están dentro de una base de datos"}]

    def documents(self, collection_ids: list[str]) -> Iterator[WikiDoc]:
        names = {c["id"]: c["name"] for c in self.collections()}
        wanted = set(collection_ids) or set(names)
        for p in self._search("page"):
            if p.get("archived") or p.get("in_trash"):
                continue
            parent = p.get("parent") or {}
            coll = self._id(parent.get("database_id") or parent.get("data_source_id")) if parent.get("type") in ("database_id", "data_source_id") else self.LOOSE
            if coll not in wanted:
                continue
            title = next((_rich(v.get("title")) for v in (p.get("properties") or {}).values() if v.get("type") == "title"), "") or "Sin título"
            yield WikiDoc(id=self._id(p["id"]), title=title.strip(), content=lambda pid=p["id"]: self._markdown(pid), updated_at=_stamp(p["last_edited_time"]),
                          url=p.get("url", ""), collection=names.get(coll, ""))

    def _children(self, block_id: str) -> Iterator[dict]:
        cursor = None
        while True:
            data = self.http.request("GET", f"/blocks/{block_id}/children", params={"page_size": 100, **({"start_cursor": cursor} if cursor else {})})
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            cursor = data.get("next_cursor")

    def _markdown(self, page_id: str) -> str:
        lines: list[str] = []
        self._walk(page_id, 0, lines, [0])
        return "\n".join(lines).strip()

    def _walk(self, block_id: str, depth: int, lines: list[str], count: list[int]) -> None:
        pad = "  " * depth
        for b in self._children(block_id):
            count[0] += 1
            if count[0] > self.MAX_BLOCKS:
                lines.append("\n(página truncada: demasiados bloques)")
                return
            t = b.get("type", "")
            body = b.get(t) or {}
            text = _rich(body.get("rich_text"))
            kids = b.get("has_children") and depth < self.MAX_DEPTH
            if t in ("heading_1", "heading_2", "heading_3"):
                lines += ["", f"{'#' * (int(t[-1]) + 1)} {text}", ""]
            elif t == "bulleted_list_item":
                lines.append(f"{pad}- {text}")
            elif t == "numbered_list_item":
                lines.append(f"{pad}1. {text}")
            elif t == "to_do":
                lines.append(f"{pad}- [{'x' if body.get('checked') else ' '}] {text}")
            elif t == "toggle":
                lines.append(f"{pad}- **{text}**")
            elif t == "quote":
                lines += ["", f"> {text}", ""]
            elif t == "callout":
                lines += ["", f"> {((body.get('icon') or {}).get('emoji') or '')} {text}".replace("> ", "> ", 1).replace(">  ", "> "), ""]
            elif t == "code":
                lines += ["", f"```{body.get('language', '') if body.get('language') != 'plain text' else ''}", "".join(x.get("plain_text", "") for x in body.get("rich_text", [])), "```", ""]
            elif t == "divider":
                lines += ["", "---", ""]
            elif t == "equation":
                lines += ["", f"$${body.get('expression', '')}$$", ""]
            elif t == "table":
                rows = [[_rich(c).replace("|", "\\|") for c in r.get("table_row", {}).get("cells", [])] for r in self._children(b["id"]) if r.get("type") == "table_row"]
                for i, r in enumerate(rows):
                    lines.append("| " + " | ".join(r) + " |")
                    if i == 0:
                        lines.append("|" + "---|" * len(r))
                lines.append("")
                continue
            elif t == "child_page":
                lines += ["", f"(subpágina: {body.get('title', '')})", ""]
                continue
            elif t in ("bookmark", "link_preview", "embed"):
                lines.append(f"{pad}{(body.get('url') or '').strip()}")
            elif t in ("image", "file", "pdf", "video", "audio"):
                cap = _rich(body.get("caption"))
                if cap:
                    lines.append(f"{pad}({t}: {cap})")
            elif t in ("child_database", "unsupported"):
                continue
            elif text:
                lines += [f"{pad}{text}", ""] if t == "paragraph" else [f"{pad}{text}"]
            elif t == "paragraph":
                lines.append("")
            if kids and t not in ("table",):
                self._walk(b["id"], depth + 1, lines, count)
                if count[0] > self.MAX_BLOCKS:
                    return
