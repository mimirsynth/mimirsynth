"""Adaptadores Confluence y Notion contra respuestas simuladas con el formato documentado de cada API (no contra una instancia real)."""
import base64
import json
from datetime import datetime, timezone

import httpx
import pytest

from test_control import client  # noqa: F401
from test_docs import fake_index  # noqa: F401
from test_docsources import _brain, _docs  # noqa: F401

from mimirsynth import wikis


# ---------------------------------------------------------------- Confluence
def _confluence(handler_calls):
    spaces = [{"id": 1, "key": "ENG", "name": "Ingeniería", "type": "global", "description": {"plain": {"value": "Notas técnicas"}}},
              {"id": 2, "key": "HR", "name": "Personas", "type": "global"}]
    pages = {"ENG": [{"id": "101", "title": "Despliegue", "body": {"storage": {"value": "<h2>Pasos</h2><p>Usar <b>blue/green</b>.</p>"}}, "version": {"when": "2026-10-20T10:00:00.000Z"}, "_links": {"webui": "/spaces/ENG/pages/101/Despliegue"}},
                    {"id": "102", "title": "Sin fecha", "body": {"storage": {"value": "x"}}, "_links": {"webui": "/x"}}],
             "HR": [{"id": "201", "title": "Vacaciones", "body": {"storage": {"value": "<p>22 días.</p>"}}, "version": {"when": "2026-10-21T10:00:00.000Z"}, "_links": {"webui": "/spaces/HR/pages/201"}}]}

    def handler(req: httpx.Request) -> httpx.Response:
        handler_calls.append((req.url.path, dict(req.url.params), req.headers.get("authorization")))
        if req.url.path.endswith("/rest/api/space"):
            return httpx.Response(200, json={"results": spaces, "size": 2, "_links": {}})
        if req.url.path.endswith("/rest/api/content"):
            key, start = req.url.params["spaceKey"], int(req.url.params["start"])
            res = pages[key][start:start + 1]  # un resultado por página: obliga a paginar
            nxt = {"next": "/rest/api/content?next"} if start + 1 < len(pages[key]) else {}
            return httpx.Response(200, json={"results": res, "_links": {"base": "https://emp.atlassian.net/wiki", **nxt}})
        return httpx.Response(404)
    return handler


def test_confluence_spaces_pages_pagination_and_auth():
    calls = []
    cloud = wikis.Confluence({"base_url": "https://emp.atlassian.net/wiki/", "email": "yo@emp.com", "api_token": "tok"}, transport=httpx.MockTransport(_confluence(calls)))
    assert [(c["id"], c["name"], c["description"]) for c in cloud.collections()] == [("ENG", "Ingeniería", "Notas técnicas"), ("HR", "Personas", "")]
    docs = list(cloud.documents(["ENG"]))
    assert [d.id for d in docs] == ["101"]  # la página sin fecha de versión se ignora; la paginación se recorre entera
    d = docs[0]
    assert d.title == "Despliegue" and d.format == "html" and "<b>blue/green</b>" in d.read() and d.collection == "Ingeniería"
    assert d.url == "https://emp.atlassian.net/wiki/spaces/ENG/pages/101/Despliegue" and d.updated_at == datetime(2026, 10, 20, 10, tzinfo=timezone.utc)
    assert [x.id for x in cloud.documents([])] == ["101", "201"]  # sin selección: todos los espacios
    assert calls[0][2] == "Basic " + base64.b64encode(b"yo@emp.com:tok").decode()  # Cloud: correo + token
    dc = wikis.Confluence({"base_url": "https://conf.ejemplo.com", "api_token": "pat"}, transport=httpx.MockTransport(_confluence(calls)))
    dc.collections()
    assert calls[-1][2] == "Bearer pat"  # Data Center: token personal sin correo


def test_confluence_errors_are_readable():
    def deny(req): return httpx.Response(401)
    with pytest.raises(wikis.WikiError, match="rechazó las credenciales"):
        wikis.Confluence({"base_url": "https://x.test", "api_token": "t"}, transport=httpx.MockTransport(deny)).collections()
    with pytest.raises(wikis.WikiError, match="revisa la URL"):
        wikis.Confluence({"base_url": "https://x.test", "api_token": "t"}, transport=httpx.MockTransport(lambda r: httpx.Response(404))).collections()
    with pytest.raises(wikis.WikiError, match="falta «Token de API»"):
        wikis.Confluence({"base_url": "https://x.test"})


# -------------------------------------------------------------------- Notion
def _rt(text, **ann): return {"plain_text": text, "annotations": ann, "href": None}


BLOCKS = {
    "page-a": [
        {"id": "b1", "type": "heading_1", "heading_1": {"rich_text": [_rt("Plan")]}, "has_children": False},
        {"id": "b2", "type": "paragraph", "paragraph": {"rich_text": [_rt("Texto con "), _rt("negrita", bold=True), _rt(" y "), {"plain_text": "enlace", "annotations": {}, "href": "https://ej.com"}]}, "has_children": False},
        {"id": "b3", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_rt("Uno")]}, "has_children": True},
        {"id": "b4", "type": "to_do", "to_do": {"rich_text": [_rt("Hecho")], "checked": True}, "has_children": False},
        {"id": "b5", "type": "code", "code": {"rich_text": [_rt("print(1)")], "language": "python"}, "has_children": False},
        {"id": "b6", "type": "table", "table": {"has_column_header": True}, "has_children": True},
        {"id": "b7", "type": "child_page", "child_page": {"title": "Subpágina"}, "has_children": True},
        {"id": "b8", "type": "quote", "quote": {"rich_text": [_rt("Cita")]}, "has_children": False},
    ],
    "b3": [{"id": "b3a", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_rt("Anidado")]}, "has_children": False}],
    "b6": [{"id": "r1", "type": "table_row", "table_row": {"cells": [[_rt("A")], [_rt("B")]]}}, {"id": "r2", "type": "table_row", "table_row": {"cells": [[_rt("1")], [_rt("2")]]}}],
}


def _notion(calls, pages=None):
    pages = pages or [
        {"object": "page", "id": "aaaa-1111", "url": "https://notion.so/a", "last_edited_time": "2026-10-22T08:00:00.000Z", "parent": {"type": "database_id", "database_id": "dbdb-0001"},
         "properties": {"Etiqueta": {"type": "select"}, "Nombre": {"type": "title", "title": [_rt("Plan de proyecto")]}}},
        {"object": "page", "id": "bbbb-2222", "url": "https://notion.so/b", "last_edited_time": "2026-10-21T08:00:00.000Z", "parent": {"type": "workspace", "workspace": True},
         "properties": {"title": {"type": "title", "title": [_rt("Página suelta")]}}},
        {"object": "page", "id": "cccc-3333", "url": "https://notion.so/c", "last_edited_time": "2026-10-20T08:00:00.000Z", "parent": {"type": "page_id", "page_id": "bbbb-2222"}, "archived": True,
         "properties": {"title": {"type": "title", "title": [_rt("Archivada")]}}},
    ]

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        assert req.headers["authorization"] == "Bearer secret_x" and req.headers["notion-version"] == "2022-06-28"
        if req.url.path == "/v1/search":
            body = json.loads(req.content)
            if body["filter"]["value"] == "database":
                return httpx.Response(200, json={"results": [{"object": "database", "id": "dbdb-0001", "title": [_rt("Proyectos")], "description": [_rt("Todos los proyectos")]}], "has_more": False})
            if not body.get("start_cursor"):  # dos hojas de resultados
                return httpx.Response(200, json={"results": pages[:1], "has_more": True, "next_cursor": "c2"})
            return httpx.Response(200, json={"results": pages[1:], "has_more": False})
        if req.url.path.startswith("/v1/blocks/"):
            bid = req.url.path.split("/")[3]
            return httpx.Response(200, json={"results": BLOCKS.get(bid.replace("aaaa-1111", "page-a"), []), "has_more": False})
        return httpx.Response(404)
    return handler


def test_notion_collections_are_databases_plus_loose_pages_and_content_is_lazy():
    calls = []
    n = wikis.Notion({"token": "secret_x"}, transport=httpx.MockTransport(_notion(calls)), min_interval=0)
    assert [(c["id"], c["name"]) for c in n.collections()] == [("dbdb0001", "Proyectos"), ("_pages", "Páginas sueltas")]
    docs = list(n.documents([]))
    assert [(d.id, d.title, d.collection) for d in docs] == [("aaaa1111", "Plan de proyecto", "Proyectos"), ("bbbb2222", "Página suelta", "Páginas sueltas")]  # la archivada no entra
    assert not any(p.startswith("/v1/blocks") for _, p in calls)  # listar no descarga contenido
    assert [d.id for d in n.documents(["_pages"])] == ["bbbb2222"] and [d.id for d in n.documents(["dbdb0001"])] == ["aaaa1111"]  # filtra por colección
    md = docs[0].read()
    assert "## Plan" in md  # heading_1 → «##» (el título de la página ya es «#»)
    assert "Texto con **negrita** y [enlace](https://ej.com)" in md
    assert "- Uno\n  - Anidado" in md and "- [x] Hecho" in md
    assert "```python\nprint(1)\n```" in md and "| A | B |\n|---|---|\n| 1 | 2 |" in md
    assert "(subpágina: Subpágina)" in md and "> Cita" in md
    assert docs[0].updated_at == datetime(2026, 10, 22, 8, tzinfo=timezone.utc) and docs[0].url == "https://notion.so/a"


def test_notion_retries_rate_limit_and_reports_bad_token(monkeypatch):
    monkeypatch.setattr(wikis.time, "sleep", lambda s: None)
    seen = []
    def limited(req):
        seen.append(1)
        return httpx.Response(429, headers={"retry-after": "1"}) if len(seen) < 3 else httpx.Response(200, json={"results": [], "has_more": False})
    assert wikis.Notion({"token": "t"}, transport=httpx.MockTransport(limited), min_interval=0).collections()[-1]["id"] == "_pages" and len(seen) == 3
    with pytest.raises(wikis.WikiError, match="rechazó las credenciales"):
        wikis.Notion({"token": "mala"}, transport=httpx.MockTransport(lambda r: httpx.Response(401)), min_interval=0).collections()


# -------------------------------------------- integración: reescaneo sin descargar lo que no cambió
def test_rescan_only_reads_changed_pages(client, fake_index, monkeypatch):  # noqa: F811
    monkeypatch.setattr(wikis, "REGISTRY", dict(wikis.REGISTRY))
    reads = []
    state = {"v": 1}

    @wikis.register
    class Lazy(wikis.Adapter):
        id, label = "lazy", "Perezoso"
        fields = [wikis.Field("site", "Sitio")]
        def collections(self): return [{"id": "C", "name": "Colección C", "description": ""}, {"id": "D", "name": "Colección D", "description": ""}]
        def documents(self, ids):
            for pid, title, day in (("p1", "Uno", 20), ("p2", "Dos", 21 if state["v"] == 1 else 22)):
                yield wikis.WikiDoc(pid, title, (lambda pid=pid: reads.append(pid) or f"Contenido de {pid} versión {state['v']}"), datetime(2026, 10, day, tzinfo=timezone.utc), f"https://l.test/{pid}", "Colección C")

    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    r = client.post(f"{base}/sources/wiki", json={"adapter": "lazy", "values": {"site": "l.test"}, "name": "Lazy", "collection_ids": ["C"]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert sorted(reads) == ["p1", "p2"]  # primera vez: se leen las dos
    reads.clear(); state["v"] = 2
    assert client.post(f"{base}/sources/{sid}/scan").status_code in (200, 202)
    assert reads == ["p2"]  # solo cambió la fecha de p2: p1 no cuesta ninguna lectura
    # colecciones disponibles y seleccionadas de una fuente ya conectada (credenciales guardadas)
    got = client.get(f"{base}/sources/{sid}/wiki/collections").json()
    assert [c["id"] for c in got["collections"]] == ["C", "D"] and got["selected"] == ["C"]
    assert client.patch(f"{base}/sources/{sid}", json={"collection_ids": ["C", "D"]}).status_code == 200
    assert client.get(f"{base}/sources/{sid}/wiki/collections").json()["selected"] == ["C", "D"]
