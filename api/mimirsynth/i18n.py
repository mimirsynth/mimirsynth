"""Idioma de lo que la API y el MCP devuelven a quien llama (errores, descripciones de herramientas, encabezados del recall).
El idioma de origen es el español y el catálogo inglés es el mismo que usa la interfaz (`web/src/i18n/en.server.json`; en la imagen
Docker se copia junto a este módulo). Se elige, por orden: la cabecera `Accept-Language`, el idioma de la persona dueña de la sesión
o del token y el idioma por defecto de la instancia. Los datos de la memoria (hechos, documentos) no se traducen."""
import json
import re
from functools import lru_cache
from pathlib import Path

from starlette.requests import Request

from . import appsettings
from .i18n_extract import CATALOG

SOURCE = "es"
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


@lru_cache
def _catalogs() -> dict[str, dict[str, str]]:
    local = Path(__file__).with_name("en.server.json")
    path = local if local.exists() else CATALOG
    return {"en": {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if v}}


def languages() -> set[str]:
    return {SOURCE, *_catalogs()}


@lru_cache
def _templates(lang: str) -> list[tuple[re.Pattern, list[str], str]]:
    out = []
    for k, v in _catalogs()[lang].items():
        if "{{" not in k:
            continue
        parts = _PLACEHOLDER.split(k)
        out.append((re.compile("^" + "".join("([\\s\\S]+?)" if i % 2 else re.escape(p) for i, p in enumerate(parts)) + "$"), parts[1::2], v))
    return out


def tr(key: str, lang: str, **values) -> str:
    """Un texto propio del servidor, con sus `{{valores}}` sustituidos después de traducirlo (los valores no se traducen)."""
    text = _catalogs().get(lang, {}).get(key, key) if lang != SOURCE else key
    return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)


def translate(msg: str, lang: str) -> str:
    """Un mensaje ya formado (el `detail` de un error): coincidencia exacta o con una plantilla del catálogo, como hace la interfaz."""
    if lang == SOURCE or not msg:
        return msg
    cat = _catalogs().get(lang, {})
    if msg in cat:
        return cat[msg]
    for rx, names, to in _templates(lang) if cat else []:
        m = rx.match(msg)
        if m:
            return _PLACEHOLDER.sub(lambda p: translate(m.group(names.index(p.group(1)) + 1), lang) if p.group(1) in names else "", to)
    return msg


def _accepted(header: str) -> list[str]:
    """Idiomas de `Accept-Language` por preferencia (solo la etiqueta principal; `*` y `q=0` no cuentan)."""
    ranked = []
    for i, part in enumerate(header.split(",")):
        tag, _, params = part.strip().partition(";")
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        tag = tag.strip().split("-")[0].lower()
        if tag and tag != "*" and q > 0:
            ranked.append((-q, i, tag))
    return [t for _, _, t in sorted(ranked)]


def language(request: Request) -> str:
    supported = languages()
    for lang in _accepted(request.headers.get("accept-language", "")):
        if lang in supported:
            return lang
    own = getattr(request.state, "locale", "") or ""
    if own in supported:
        return own
    default = appsettings.get("default_language")
    return default if default in supported else SOURCE
