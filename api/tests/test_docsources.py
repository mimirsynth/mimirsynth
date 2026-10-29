"""Fuente de directorio: referencia sin copiar, reescaneo por tamaño/fecha/sha256, borrados y protecciones."""
import os
import uuid

import pytest

from test_control import client  # noqa: F401
from test_docs import MD, fake_index  # noqa: F401

from mimirsynth import docstore
from mimirsynth.config import settings


@pytest.fixture()
def lib(monkeypatch, tmp_path, fake_index):
    root = tmp_path / "notas"
    (root / "sub").mkdir(parents=True)
    (root / ".oculta").mkdir()
    (root / "a.md").write_text(MD, encoding="utf-8", newline="")
    (root / "sub" / "b.txt").write_text("Texto de la nota b.\n" * 5, encoding="utf-8", newline="")
    (root / ".oculta" / "x.md").write_text("no debe entrar", encoding="utf-8", newline="")
    (root / "binario.exe").write_bytes(b"MZ")
    (tmp_path / "fuera.md").write_text("fuera de la raíz", encoding="utf-8", newline="")
    os.symlink(tmp_path / "fuera.md", root / "escapa.md")
    monkeypatch.setattr(settings, "doc_roots_base", str(tmp_path))
    from sqlalchemy import delete
    from mimirsynth.models import DocRoot
    from mimirsynth.store import _factory
    with _factory()() as db:
        db.execute(delete(DocRoot))
        db.add(DocRoot(name="notas", path=str(root)))
        db.commit()
    return root


def _brain(client):
    slug = "d" + uuid.uuid4().hex[:8]
    assert client.post("/api/brains", json={"slug": slug, "name": slug, "graph_name": "g-" + slug}).status_code == 201
    return slug


def _docs(client, slug):
    return {d["external_id"]: d for d in client.get(f"/api/brains/{slug}/docs").json()["items"]}


def test_directory_source_scan_lifecycle(client, lib):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    assert client.get(f"{base}/roots").json()["roots"] == [{"name": "notas", "available": True}]
    assert client.post(f"{base}/sources", json={"name": "x", "root": "inexistente"}).status_code == 400
    assert client.post(f"{base}/sources", json={"name": "x", "root": "notas", "subpath": "../.."}).status_code == 400
    r = client.post(f"{base}/sources", json={"name": "Notas", "root": "notas", "sync_interval": 30})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    ds = _docs(client, slug)
    assert sorted(ds) == ["a.md", "sub/b.txt"]                                    # sin ocultos, sin .exe, sin el enlace que escapa
    assert all(d["status"] == "active" and d["chunks"] > 0 for d in ds.values())
    assert not list(os.scandir(settings.doc_store)) or not any(p.name == "a.md" for p in __import__("pathlib").Path(settings.doc_store).rglob("*"))  # no se copia el original
    f = client.get(f"{base}/{ds['a.md']['id']}/file")
    assert f.status_code == 200 and f.content == MD.encode()
    job = client.get(f"/api/brains/{slug}/jobs?kind=doc.scan").json()["items"][0]
    assert job["status"] == "done"
    res = client.get(f"/api/brains/{slug}/jobs/{job['id']}").json()["result"]
    assert res == {"added": 2, "changed": 0, "unchanged": 0, "removed": 0, "indexed": 2, "errors": 0}

    r = client.post(f"{base}/sources/{sid}/scan")                                  # sin cambios
    res = client.get(f"/api/brains/{slug}/jobs/{r.json()['job']}").json()["result"]
    assert res["added"] == 0 and res["unchanged"] == 2 and res["indexed"] == 0

    (lib / "a.md").write_text(MD + "\nUna sección nueva.\n", encoding="utf-8", newline="")                        # cambiado
    (lib / "sub" / "c.md").write_text("# Nota c\n\nCuerpo.\n", encoding="utf-8", newline="")                      # nuevo
    (lib / "sub" / "b.txt").unlink()                                                # desaparecido
    res = client.get(f"/api/brains/{slug}/jobs/{client.post(f'{base}/sources/{sid}/scan').json()['job']}").json()["result"]
    assert (res["added"], res["changed"], res["removed"], res["indexed"]) == (1, 1, 1, 2)
    ds = _docs(client, slug)
    assert sorted(ds) == ["a.md", "sub/c.md"]
    src = client.get(f"{base}/sources").json()["sources"]
    assert [s["name"] for s in src] == ["Notas"] and src[0]["documents"] == 2 and src[0]["config"] == {"root": "notas", "subpath": ""}

    assert client.delete(f"{base}/{ds['a.md']['id']}").status_code == 409          # un documento de carpeta no se borra suelto
    assert client.get(f"{base}/sources").json()["sources"][0]["status"] == "idle"


def test_scheduled_scan_refuses_to_wipe_but_manual_can(client, lib):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    sid = client.post(f"{base}/sources", json={"name": "N", "root": "notas"}).json()["id"]
    for f in [lib / "a.md", lib / "sub" / "b.txt"]:
        f.unlink()
    from mimirsynth import docsources, jobs
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    jid = jobs.submit("doc.scan", None, {"source_id": sid, "manual": False}, "programado")          # el escaneo programado no vacía el índice
    with _factory()() as db:
        j = db.get(Job, jid)
        assert j.status == "failed" and "No se ha borrado nada" in j.error
    assert len(_docs(client, slug)) == 2                                                            # los documentos siguen ahí
    assert client.get(f"{base}/sources").json()["sources"][0]["status"] == "error"
    jid = client.post(f"{base}/sources/{sid}/scan").json()["job"]                                   # el manual es una orden explícita: vacía
    assert client.get(f"/api/brains/{slug}/jobs/{jid}").json()["status"] == "done"
    assert _docs(client, slug) == {} and client.get(f"{base}/sources").json()["sources"][0]["status"] == "idle"


def test_delete_source_keeps_originals(client, lib):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    sid = client.post(f"{base}/sources", json={"name": "N", "root": "notas"}).json()["id"]
    r = client.delete(f"{base}/sources/{sid}")
    assert r.json() == {"ok": True, "documents_removed": 2}
    assert (lib / "a.md").exists() and (lib / "sub" / "b.txt").exists() and _docs(client, slug) == {}


def test_source_paths_cannot_escape(lib):
    with pytest.raises(ValueError):
        docstore.source_file({"root": "notas"}, "../fuera.md")
    with pytest.raises(ValueError):
        docstore.source_base({"root": "otra"})
    assert docstore.source_file({"root": "notas"}, "a.md") == (lib / "a.md").resolve()


def test_roots_admin_api(client, lib, tmp_path):
    from mimirsynth.models import DocRoot
    from mimirsynth.store import _factory
    from sqlalchemy import delete
    with _factory()() as db:
        db.execute(delete(DocRoot)); db.commit()
    (tmp_path / "otra").mkdir()
    r = client.get("/api/doc-roots").json()
    assert r["base"] == str(tmp_path.resolve()) and r["roots"] == [] and str(tmp_path / "otra") in r["suggestions"]
    assert client.post("/api/doc-roots", json={"name": "Mal Nombre", "path": str(tmp_path / "otra")}).status_code == 400
    assert client.post("/api/doc-roots", json={"name": "x", "path": "/etc"}).status_code == 400                      # fuera de la base
    assert client.post("/api/doc-roots", json={"name": "x", "path": str(tmp_path)}).status_code == 400               # la propia base no
    assert client.post("/api/doc-roots", json={"name": "x", "path": str(tmp_path / "no-existe")}).status_code == 400
    assert client.post("/api/doc-roots", json={"name": "x", "path": str(tmp_path / "notas" / ".." / ".." / "etc")}).status_code == 400
    ok = client.post("/api/doc-roots", json={"name": "otra", "path": str(tmp_path / "otra"), "description": "prueba"})
    assert ok.status_code == 201 and ok.json()["available"] is True
    assert client.post("/api/doc-roots", json={"name": "otra", "path": str(tmp_path / "notas")}).status_code == 409
    slug = _brain(client)
    assert client.post(f"/api/brains/{slug}/docs/sources", json={"name": "S", "root": "otra"}).status_code == 201
    assert client.get("/api/doc-roots").json()["roots"][0]["sources"] == 1
    assert client.delete(f"/api/doc-roots/{ok.json()['id']}").status_code == 409                                    # en uso


# --- wiki (Outline) ---------------------------------------------------------------------------

class _FakeOutline:
    """Sustituye a httpx.post: una wiki con dos colecciones y páginas editables."""
    def __init__(self):
        self.pages = {"p1": ("Guía de red", "## VLANs\n\nLa VLAN 20 es Servicios.\n", "2026-10-20T10:00:00.000Z", "c1"),
                      "p2": ("Backups", "# PBS\n\nBunda hace backup incremental.\n", "2026-10-21T10:00:00.000Z", "c1"),
                      "p3": ("Otra colección", "Contenido ajeno.\n", "2026-10-21T10:00:00.000Z", "c2")}
        self.key_ok = True
        self.calls = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        import httpx
        self.calls.append((url, json))
        method = url.rsplit("/api/", 1)[1]
        if not self.key_ok or headers.get("Authorization") != "Bearer clave-de-prueba":
            return httpx.Response(401, json={"error": "authentication_required"})
        if method == "collections.list":
            return httpx.Response(200, json={"data": [{"id": "c1", "name": "Infra"}, {"id": "c2", "name": "Personal"}]})
        assert method == "documents.list"
        data = [{"id": k, "title": t, "text": x, "updatedAt": u, "url": f"/doc/{k}", "collectionId": c, "publishedAt": "2026-01-01T00:00:00Z"}
                for k, (t, x, u, c) in self.pages.items() if c == json["collectionId"]]
        return httpx.Response(200, json={"data": data})


def test_wiki_source_lifecycle(client, lib, monkeypatch):
    from mimirsynth import wikis
    fake = _FakeOutline()
    monkeypatch.setattr(wikis.httpx, "post", fake)
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    ad = {a["id"]: a for a in client.get(f"{base}/wiki/adapters").json()["adapters"]}
    assert [f["name"] for f in ad["outline"]["fields"]] == ["base_url", "api_key"] and ad["outline"]["fields"][1]["secret"] is True
    conn = {"adapter": "outline", "values": {"base_url": "https://wiki.test", "api_key": "clave-de-prueba"}}
    assert [c["name"] for c in client.post(f"{base}/wiki/collections", json=conn).json()["collections"]] == ["Infra", "Personal"]
    assert client.post(f"{base}/wiki/collections", json={**conn, "values": {**conn["values"], "api_key": "otra-clave-mala"}}).status_code == 400
    assert client.post(f"{base}/wiki/collections", json={**conn, "values": {**conn["values"], "base_url": "ftp://x.y/z"}}).status_code == 400
    assert client.post(f"{base}/wiki/collections", json={**conn, "values": {"base_url": "https://wiki.test"}}).json()["detail"] == "falta «Clave de API»"
    assert client.post(f"{base}/wiki/collections", json={"adapter": "nada", "values": {}}).status_code == 400
    r = client.post(f"{base}/sources/wiki", json={**conn, "name": "Outline", "collection_ids": ["c1"], "sync_interval": 30})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    ds = _docs(client, slug)
    assert sorted(d["title"] for d in ds.values()) == ["Backups", "Guía de red"]                      # solo la colección elegida
    assert all(d["status"] == "active" and d["chunks"] > 0 for d in ds.values())
    src = [x for x in client.get(f"{base}/sources").json()["sources"] if x["id"] == sid][0]
    assert src["kind"] == "wiki" and src["config"] == {"adapter": "outline", "settings": {"base_url": "https://wiki.test"}, "collection_ids": ["c1"], "secrets_set": ["api_key"]}
    assert "clave-de-prueba" not in client.get(f"{base}/sources").text                              # la clave nunca sale
    from mimirsynth.models import DocSource
    from mimirsynth.store import _factory
    with _factory()() as db:
        assert "clave-de-prueba" not in str(db.get(DocSource, sid).config)                           # y se guarda cifrada
    p1 = next(d for d in ds.values() if d["title"] == "Guía de red")
    assert client.get(f"{base}/{p1['id']}").json()["url"] == "https://wiki.test/doc/p1"
    f = client.get(f"{base}/{p1['id']}/file")
    assert f.status_code == 200 and f.text.startswith("# Guía de red") and "VLAN 20" in f.text

    n = len(fake.calls)
    res = client.get(f"/api/brains/{slug}/jobs/{client.post(f'{base}/sources/{sid}/scan').json()['job']}").json()["result"]
    assert (res["added"], res["changed"], res["unchanged"], res["removed"]) == (0, 0, 2, 0)           # sin cambios: nada que reindexar

    fake.pages["p1"] = ("Guía de red", "## VLANs\n\nLa VLAN 20 es Servicios y la 30 es Aislada.\n", "2026-10-23T09:00:00.000Z", "c1")
    fake.pages["p4"] = ("Nueva", "Una página nueva.\n", "2026-10-23T09:00:00.000Z", "c1")
    del fake.pages["p2"]
    res = client.get(f"/api/brains/{slug}/jobs/{client.post(f'{base}/sources/{sid}/scan').json()['job']}").json()["result"]
    assert (res["added"], res["changed"], res["removed"], res["indexed"]) == (1, 1, 1, 2)
    assert sorted(d["title"] for d in _docs(client, slug).values()) == ["Guía de red", "Nueva"]
    assert "Aislada" in client.get(f"{base}/{p1['id']}/file").text
    assert client.delete(f"{base}/{p1['id']}").status_code == 409                                    # una página no se borra suelta

    fake.key_ok = False                                                                              # la wiki falla: no se borra nada
    j = client.get(f"/api/brains/{slug}/jobs/{client.post(f'{base}/sources/{sid}/scan').json()['job']}").json()
    assert j["status"] == "failed" and "rechazó la clave" in j["error"] and len(_docs(client, slug)) == 2

    assert client.delete(f"{base}/sources/{sid}").json() == {"ok": True, "documents_removed": 2}
    assert _docs(client, slug) == {}


def test_new_adapter_plugs_in_with_html_pages(client, lib, monkeypatch):
    """Añadir una wiki es escribir una clase: aquí un adaptador de juguete con contenido HTML (como el de Confluence) y un campo secreto propio."""
    from mimirsynth import wikis
    from datetime import datetime, timezone
    monkeypatch.setattr(wikis, "REGISTRY", dict(wikis.REGISTRY))

    @wikis.register
    class Toy(wikis.Adapter):
        id, label, collection_label = "toy", "Juguete", "Espacios"
        fields = [wikis.Field("site", "Sitio"), wikis.Field("user", "Usuario"), wikis.Field("token", "Token", secret=True)]
        def collections(self):
            return [{"id": "S1", "name": "Espacio uno", "description": ""}]
        def documents(self, ids):
            yield wikis.WikiDoc("a1", "Página <html>", "<h2>Sección</h2><p>Texto con <b>negrita</b>.</p>", datetime(2026, 10, 23, tzinfo=timezone.utc), "https://toy.test/a1", "Espacio uno", format="html")

    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    vals = {"site": "toy.test", "user": "alex", "token": "token-secreto-1"}
    assert client.get(f"{base}/wiki/adapters").json()["adapters"][-1]["collection_label"] == "Espacios"
    r = client.post(f"{base}/sources/wiki", json={"adapter": "toy", "values": vals, "name": "Toy", "collection_ids": ["S1"]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    (d,) = _docs(client, slug).values()
    assert d["title"] == "Página <html>" and d["status"] == "active" and d["chunks"] > 0 and d["filename"].endswith(".html")
    f = client.get(f"{base}/{d['id']}/file")
    assert f.headers["content-type"].startswith("text/html") and "<h2>Sección</h2>" in f.text
    src = [x for x in client.get(f"{base}/sources").json()["sources"] if x["id"] == sid][0]
    assert src["config"]["settings"] == {"site": "toy.test", "user": "alex"} and src["config"]["secrets_set"] == ["token"] and "token-secreto-1" not in str(src)
    assert client.patch(f"{base}/sources/{sid}", json={"values": {"token": ""}}).status_code == 200  # un secreto vacío conserva el guardado
    assert client.patch(f"{base}/sources/{sid}", json={"values": {"user": "otra"}}).status_code == 200


def test_legacy_wiki_config_is_migrated(tmp_path, monkeypatch):
    import importlib.util, json, sqlalchemy as sa
    from mimirsynth.config import settings
    from mimirsynth.secretbox import seal
    eng = sa.create_engine(f"sqlite:///{tmp_path}/m.db")
    with eng.begin() as c:
        c.execute(sa.text("create table doc_sources (id integer primary key, kind text, config json)"))
        old = {"adapter": "outline", "base_url": "https://w.test", "collection_ids": ["c1"], "api_key_enc": seal("k")}
        c.execute(sa.text("insert into doc_sources values (1, 'wiki', :c)"), {"c": json.dumps(old)})
        c.execute(sa.text("insert into doc_sources values (2, 'directory', :c)"), {"c": json.dumps({"root": "notas"})})
    spec = importlib.util.spec_from_file_location("m11", str(__import__("pathlib").Path(__file__).parent.parent / "mimirsynth/migrations/versions/0011_wiki_config_generic.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with eng.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            mod.upgrade()
    with eng.connect() as c:
        got = {r[0]: json.loads(r[1]) for r in c.execute(sa.text("select id, config from doc_sources"))}
    assert got[1] == {"adapter": "outline", "settings": {"base_url": "https://w.test"}, "secrets": {"api_key": old["api_key_enc"]}, "collection_ids": ["c1"]}
    assert got[2] == {"root": "notas"}


def test_obsidian_markdown_conventions(tmp_path):
    from mimirsynth.docextract import extract
    f = tmp_path / "nota.md"
    f.write_text('---\ntitle: "Mi nota"\ntags: [a, b]\n---\n# Encabezado\n\nVer [[Otra nota|la otra]] y [[Archivo#Sección]] y [[Simple]].\n![[imagen.png]]\n%%comentario privado%%\nLínea con marca ^abc123\n', encoding="utf-8", newline="")
    text, title = extract(f, ".md")
    assert title == "Mi nota" and "tags" not in text and "title:" not in text
    assert "la otra" in text and "Otra nota" not in text and "Archivo › Sección" in text and "Simple" in text and "[[" not in text
    assert "imagen.png" not in text and "comentario privado" not in text and "^abc123" not in text and "Línea con marca" in text
    # #83: la misma nota guardada con saltos de Windows (CRLF) da el mismo resultado
    f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
    assert extract(f, ".md") == (text, title)


def test_documents_list_filters_sort_and_pagination(client, lib):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    (lib / "sub" / "z_100%.md").write_text("# Zeta 100%\n\nCuerpo.\n", encoding="utf-8", newline="")
    client.post(f"{base}/sources", json={"name": "N", "root": "notas"})
    names = lambda **p: [d["external_id"] for d in client.get(base, params=p).json()["items"]]  # noqa: E731
    assert sorted(names()) == ["a.md", "sub/b.txt", "sub/z_100%.md"]
    r = client.get(base, params={"limit": 2, "offset": 0, "sort": "title", "order": "asc"}).json()
    assert r["total"] == 3 and len(r["items"]) == 2 and r["limit"] == 2 and r["status_counts"] == {"active": 3}
    assert names(limit=2, offset=2, sort="title", order="asc") == ["sub/z_100%.md"]                    # segunda página
    assert names(sort="title", order="desc")[0] == "sub/z_100%.md" and names(sort="size", order="asc")[0] in ("sub/b.txt", "sub/z_100%.md")
    assert names(path="sub") == ["sub/b.txt", "sub/z_100%.md"] or sorted(names(path="sub")) == ["sub/b.txt", "sub/z_100%.md"]
    assert names(path="su") == []                                                                      # carpeta, no prefijo de texto
    assert names(q="100%") == ["sub/z_100%.md"] and names(q="_") == ["sub/z_100%.md"] and names(q="%") == ["sub/z_100%.md"]   # % y _ no son comodines
    assert names(q="zzz") == [] and names(status="error") == []
    sid = client.get(f"{base}/sources").json()["sources"][-1]["id"]
    assert len(names(source_id=sid)) == 3 and names(source_id=sid + 999) == []
    assert client.get(base, params={"limit": 1000}).status_code == 422


def test_full_text_endpoint(client, lib):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    client.post(f"{base}/sources", json={"name": "N", "root": "notas"})
    d = next(x for x in _docs(client, slug).values() if x["external_id"] == "a.md")
    t = client.get(f"{base}/{d['id']}/text").json()
    assert t["truncated"] is False and t["text"].startswith("# Guía") and t["chars"] == len(t["text"]) and "### Requisitos" in t["text"]
    assert client.get(f"{base}/999999/text").status_code == 404


def test_edit_source_interval_name_and_subpath(client, lib):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    sid = client.post(f"{base}/sources", json={"name": "N", "root": "notas", "sync_interval": 60}).json()["id"]
    get = lambda: [x for x in client.get(f"{base}/sources").json()["sources"] if x["id"] == sid][0]  # noqa: E731
    assert client.patch(f"{base}/sources/{sid}", json={"sync_interval": 15, "name": "Notas 2"}).status_code == 200
    assert get()["sync_interval"] == 15 and get()["name"] == "Notas 2"
    assert client.patch(f"{base}/sources/{sid}", json={"clear_interval": True}).status_code == 200 and get()["sync_interval"] is None
    assert client.patch(f"{base}/sources/{sid}", json={"sync_interval": 2}).status_code == 422                       # mínimo 5 minutos
    assert client.patch(f"{base}/sources/{sid}", json={"subpath": "sub"}).status_code == 200 and get()["config"]["subpath"] == "sub"
    assert client.patch(f"{base}/sources/{sid}", json={"subpath": "../.."}).status_code == 400
