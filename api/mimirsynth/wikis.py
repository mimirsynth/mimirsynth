"""Adaptadores de wiki como fuente de documentos. Cada adaptador se describe a sí mismo (nombre, campos de conexión, cómo llama a sus «colecciones»),
sabe listar colecciones y recorrer sus páginas, y se registra con @register. La interfaz, el cifrado de secretos, la sincronización incremental,
el troceado y el índice son comunes: añadir una wiki es escribir una clase. Solo lectura."""
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator
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
    content: str
    updated_at: datetime
    url: str
    collection: str
    format: str = "markdown"  # markdown | html (el contenido tal como lo da la wiki; el extractor ya sabe leer ambos)


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
