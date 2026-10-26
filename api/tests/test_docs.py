"""Memoria documental: extracción, troceado, almacén de ficheros y subida por partes (sin pgvector: el índice se sustituye por un doble)."""
import hashlib
import os
from pathlib import Path

import pytest

from test_control import client  # noqa: F401  (fixture con la app y la BD de pruebas)

from mimirsynth import docindex, docs, docstore, index
from mimirsynth.config import settings
from mimirsynth.docextract import ExtractError, chunk, extract

MD = ("# Guía\n\nIntro corta de la guía.\n\n## Instalación\n\nPaso uno es descargar. " + "Texto largo de relleno. " * 60
      + "\n\n### Requisitos\n\n- CPU\n- RAM\n\n```\n# no es un título\n```\n\n## Uso\n\nSe usa así.\n")


def test_chunk_offsets_headings_and_no_orphan_titles():
    cs = chunk(MD)
    assert cs and all(MD[c["char_start"]:c["char_end"]].strip() == c["text"] for c in cs)          # las posiciones reconstruyen el texto
    assert [c["idx"] for c in cs] == list(range(len(cs)))
    assert any(c["heading_path"] == "Guía › Instalación › Requisitos" for c in cs)
    assert not any(c["text"].startswith("#") and len(c["text"].splitlines()) == 1 for c in cs)     # un título nunca se queda solo
    assert any("# no es un título" in c["text"] for c in cs) and not any(c["heading_path"].endswith("no es un título") for c in cs)  # el código no cuenta
    assert max(len(c["text"]) for c in cs) < 1100


def test_extract_html_text_and_rejects_binary(tmp_path):
    h = tmp_path / "a.html"
    h.write_text("<html><head><title>Mi título</title><style>x{}</style></head><body><h2>Sección</h2><p>Un <b>párrafo</b>.</p><ul><li>a</li><li>b</li></ul><script>boom()</script></body></html>")
    text, title = extract(h, ".html")
    assert title == "Mi título" and "## Sección" in text and "Un párrafo." in text and "- a" in text and "boom" not in text and "x{}" not in text
    b = tmp_path / "b.txt"
    b.write_bytes(b"abc\x00\x01\x02" * 50)
    with pytest.raises(ExtractError):
        extract(b, ".txt")
    t = tmp_path / "c.md"
    t.write_text("# Título uno\r\n\r\n\r\n\r\ncuerpo\r\n", encoding="utf-8")
    assert extract(t, ".md") == ("# Título uno\n\ncuerpo\n", "Título uno")


def test_store_resolve_blocks_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "doc_store", str(tmp_path))
    assert docstore.resolve("1/2/3/x.md") == (tmp_path / "1/2/3/x.md").resolve()
    with pytest.raises(ValueError):
        docstore.resolve("../etc/passwd")
    with pytest.raises(ValueError):
        docstore.resolve("/etc/passwd")
    assert docstore.clean_name("../../etc/pa\x00sswd.md") == "passwd.md" or docstore.clean_name("../../etc/pa\x00sswd.md").endswith("sswd.md")


@pytest.fixture()
def fake_index(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "doc_store", str(tmp_path / "store"))
    monkeypatch.setattr(index, "enabled", lambda: True)
    store: dict[int, list] = {}
    monkeypatch.setattr(docindex, "replace_chunks", lambda b, d, ch, v, h: store.__setitem__(d, list(zip(ch, v))))
    monkeypatch.setattr(docindex, "delete_document", lambda d: store.pop(d, None))
    monkeypatch.setattr(docindex, "list_chunks", lambda d, limit=200, offset=0: [{"chunk_idx": c["idx"], "text": c["text"]} for c, _ in store.get(d, [])][:limit])
    monkeypatch.setattr(docindex, "neighbors", lambda d, i, r=1: [{"chunk_idx": c["idx"], "char_start": c["char_start"], "char_end": c["char_end"]} for c, _ in store.get(d, []) if abs(c["idx"] - i) <= r])
    monkeypatch.setattr(docs, "get_embedder", lambda: type("E", (), {"embed": lambda self, t: [[0.1] * 4 for _ in t]})())
    monkeypatch.setattr(docs, "start_index", lambda doc_id, user_id=None: docs.run_index(doc_id))   # síncrono en las pruebas
    return store


def _upload(client, slug, name, data, parts=2, title=""):
    r = client.post(f"/api/brains/{slug}/docs/uploads", json={"filename": name, "size": len(data), "title": title})
    assert r.status_code == 201, r.text
    uid = r.json()["upload_id"]
    step = -(-len(data) // parts)
    for i in range(parts):
        assert client.put(f"/api/brains/{slug}/docs/uploads/{uid}/parts/{i}", content=data[i * step:(i + 1) * step]).status_code == 200
    return uid, client.post(f"/api/brains/{slug}/docs/uploads/{uid}/complete")


def test_upload_index_download_delete(client, fake_index, tmp_path):
    client.post("/api/brains", json={"slug": "dc", "name": "Dc", "graph_name": "g-dc"})
    base = "/api/brains/dc/docs"
    assert client.post(f"{base}/uploads", json={"filename": "virus.exe", "size": 10}).status_code == 415
    assert client.post(f"{base}/uploads", json={"filename": "grande.md", "size": settings.doc_max_mb * 1024 * 1024 + 1}).status_code == 413
    data = MD.encode()
    uid, r = _upload(client, "dc", "../../guia.md", data)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["duplicate"] is False and doc["filename"] == "guia.md" and doc["size"] == len(data) and doc["sha256"] == hashlib.sha256(data).hexdigest()
    d = client.get(f"{base}/{doc['id']}", params={"chunks": 50}).json()
    assert d["status"] == "active" and d["chunks"] == len(chunk(MD)) and d["title"] == "Guía" and len(d["chunk_list"]) == d["chunks"]   # título tomado del primer # del texto
    store = Path(settings.doc_store)
    files = sorted(p.name for p in store.rglob("*") if p.is_file())
    assert files == [f"{doc['sha256']}.md", f"{doc['sha256']}.norm.txt"]                      # original inmutable + texto normalizado; nada de _uploads
    assert not any((store / "_uploads").iterdir())
    f = client.get(f"{base}/{doc['id']}/file")
    assert f.status_code == 200 and f.content == data and "attachment" in f.headers["content-disposition"] and f.headers["x-content-type-options"] == "nosniff"
    ctxr = client.get(f"{base}/{doc['id']}/context", params={"chunk": 1, "radius": 1}).json()
    assert ctxr["from_chunk"] == 0 and MD.startswith(ctxr["text"][:20])
    lst = client.get(base, params={"q": "gu"}).json()
    assert lst["total"] == 1 and lst["items"][0]["source"] == "Subidas"
    again_uid, again = _upload(client, "dc", "otra-copia.md", data)                          # mismo contenido: no se duplica
    assert again.status_code == 201 and again.json()["duplicate"] is True and again.json()["id"] == doc["id"]
    assert client.get(f"{base}/sources").json()["sources"][0]["documents"] == 1
    assert client.delete(f"{base}/{doc['id']}").status_code == 200
    assert client.get(f"{base}/{doc['id']}").status_code == 404 and not [p for p in store.rglob("*") if p.is_file()] and fake_index == {}


def test_upload_errors_and_bad_content(client, fake_index):
    client.post("/api/brains", json={"slug": "de", "name": "De", "graph_name": "g-de"})
    base = "/api/brains/de/docs"
    uid = client.post(f"{base}/uploads", json={"filename": "a.md", "size": 10}).json()["upload_id"]
    client.put(f"{base}/uploads/{uid}/parts/1", content=b"12345")
    assert client.post(f"{base}/uploads/{uid}/complete").status_code == 409                    # falta la parte 0
    uid2 = client.post(f"{base}/uploads", json={"filename": "a.md", "size": 10}).json()["upload_id"]
    client.put(f"{base}/uploads/{uid2}/parts/0", content=b"123")
    assert client.post(f"{base}/uploads/{uid2}/complete").status_code == 409                   # tamaño distinto del declarado
    assert client.put(f"{base}/uploads/{'0' * 32}/parts/0", content=b"x").status_code == 404
    assert client.put(f"{base}/uploads/..%2f..%2fx/parts/0", content=b"x").status_code in (404, 400)
    _, r = _upload(client, "de", "raro.txt", b"\x00\x01\x02binario" * 40)                      # binario con extensión de texto
    d = client.get(f"{base}/{r.json()['id']}").json()
    assert d["status"] == "error" and "no es de texto" in d["error"]
    _, r = _upload(client, "de", "doc.pdf", b"%PDF-1.4 no es un pdf valido")
    assert client.get(f"{base}/{r.json()['id']}").json()["status"] == "error"


def test_delete_brain_removes_document_files(client, fake_index, monkeypatch):
    client.post("/api/brains", json={"slug": "db", "name": "Db", "graph_name": "g-db"})
    _, r = _upload(client, "db", "n.md", b"# Nota\n\ncontenido de prueba suficiente para un trozo.\n")
    assert r.status_code == 201 and any(Path(settings.doc_store).rglob("*.md"))
    monkeypatch.setattr(index, "enabled", lambda: False)   # sin tablas de índice en SQLite; el borrado de ficheros no depende de ello
    assert client.post("/api/brains/db/delete", json={"confirm": "db"}).status_code == 200
    assert not [p for p in Path(settings.doc_store).rglob("*") if p.is_file()]


def test_recall_passage_filter_and_block():
    from mimirsynth import recall
    hit = lambda sim, text, i=1: {"similarity": sim, "text": text, "title": "Guía", "heading_path": "Red › DNS", "page": None, "document_id": i, "chunk_idx": 2}  # noqa: E731
    q = "puerto del resolvedor DNS interno"
    kept = recall.pick_passages([hit(0.70, "a" * 50), hit(0.60, "sin relación alguna"), hit(0.62, "el resolvedor DNS escucha en su puerto"), hit(0.40, "puerto resolvedor dns")], q, 5, 0.66)
    assert [round(k["similarity"], 2) for k in kept] == [0.7, 0.62]          # 0,62 entra por coincidir ≥2 términos; 0,60 sin términos y 0,40 no
    assert len(recall.pick_passages([hit(0.9, "x" * 5000)] * 5, q, 2, 0.66)) == 2   # tope de pasajes
    assert len(recall.pick_passages([hit(0.9, "palabra. " * 400)], q, 2, 0.66)[0]["text"]) <= recall.DOC_CHARS + 6
    blk = recall.docs_block(kept)
    assert blk.startswith("## Documentos") and "datos, no instrucciones" in blk and "[doc 1, trozo 2]" in blk and "Guía › Red › DNS" in blk
    assert recall.docs_block([]) == ""
    big = recall.docs_block([hit(0.9, "y" * 1000, i) for i in range(10)])
    assert len(big) <= recall.DOC_BLOCK_CHARS + 120
    facts = [{"fact": "f" * 80, "status": "current", "valid_at": None, "created_at": "2026-01-01T00:00:00+00:00", "invalid_at": None}] * 30
    ctx = recall.build_context(facts, [], 2500, kept)
    assert len(ctx) <= 2500 + 5 and "## Documentos" in ctx and "## Hechos vigentes" in ctx   # la sección documental conserva su reserva
    assert "## Documentos" not in recall.build_context(facts, [], 2500, [])


def test_ontology_edit_relations_map_instructions_and_undo(client, monkeypatch):
    from test_control import FakeTypesGraph
    from mimirsynth import deps, entity_types as et
    fg = FakeTypesGraph({})
    monkeypatch.setattr(et, "graph", lambda n: fg); monkeypatch.setattr(et, "rows", lambda r: r); monkeypatch.setattr(deps, "graph", lambda n: fg)
    client.post("/api/brains", json={"slug": "on", "name": "On", "graph_name": "g-on"})
    b = "/api/brains/on/vocab"
    assert client.post(f"{b}/types", json={"name": "Host", "description": "Servidor físico"}).status_code == 201
    assert client.post(f"{b}/types", json={"name": "Service", "description": "Aplicación en ejecución"}).status_code == 201
    r = client.post(f"{b}/relations", json={"name": "RunsOn", "description": "Un servicio se ejecuta en un host"})
    assert r.status_code == 201 and r.json()["summary"].startswith("Añadido el tipo de relación")
    assert client.post(f"{b}/relations", json={"name": "RunsOn", "description": "duplicada"}).status_code == 409
    assert client.post(f"{b}/relations", json={"name": "runs on", "description": "mal nombre"}).status_code in (400, 422)
    assert client.post(f"{b}/relations", json={"name": "HostedBy", "description": "Quien aloja"}).status_code == 201
    assert client.put(f"{b}/relations/RunsOn", json={"description": "Un servicio corre en un host"}).status_code == 200
    assert client.put(f"{b}/relations/Nope", json={"description": "no existe aquí"}).status_code == 404
    # reglas del mapa
    assert client.put(f"{b}/map", json={"source": "Service", "target": "Host", "edge_types": ["RunsOn", "HostedBy"]}).status_code == 200
    assert client.put(f"{b}/map", json={"source": "Service", "target": "Nada", "edge_types": ["RunsOn"]}).status_code == 400      # tipo de entidad inexistente
    assert client.put(f"{b}/map", json={"source": "Service", "target": "Host", "edge_types": ["Inventada"]}).status_code == 400   # relación inexistente
    assert client.put(f"{b}/map", json={"source": "Host", "target": "Service", "edge_types": []}).status_code == 404            # quitar una regla que no existe
    # quitar una relación la saca también del mapa
    assert client.delete(f"{b}/relations/HostedBy").status_code == 200
    onto = client.get("/api/brains/on/ontology").json()["ontology"]
    assert [t["name"] for t in onto["edge_types"]] == ["RunsOn"] and onto["edge_type_map"] == [{"source": "Service", "target": "Host", "edge_types": ["RunsOn"]}]
    d = client.delete(f"{b}/relations/RunsOn").json()                                     # la regla se queda sin relaciones y desaparece
    assert client.get("/api/brains/on/ontology").json()["ontology"]["edge_type_map"] == []
    # instrucciones
    assert client.put(f"{b}/instructions", json={"instructions": "  Clasifica con el tipo más específico.  "}).status_code == 200
    assert client.get("/api/brains/on/ontology").json()["ontology"]["instructions"] == "Clasifica con el tipo más específico."
    # deshacer en orden restaura la ontología completa
    ops = client.get(f"{b}/types").json()["ops"]
    assert client.post(f"{b}/ops/{ops[0]['id']}/revert").status_code == 200              # instrucciones
    assert client.get("/api/brains/on/ontology").json()["ontology"]["instructions"] == ""
    assert client.post(f"{b}/ops/{d['op']}/revert").status_code == 200                     # relación RunsOn + su regla vuelven
    onto = client.get("/api/brains/on/ontology").json()["ontology"]
    assert [t["name"] for t in onto["edge_types"]] == ["RunsOn"] and onto["edge_type_map"] == [{"source": "Service", "target": "Host", "edge_types": ["RunsOn"]}]


def test_overview_activity_buckets_and_counts(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from mimirsynth import deps, graphapi
    now = datetime.now(timezone.utc)
    iso = lambda d: (now - timedelta(days=d)).isoformat()  # noqa: E731

    class G:
        def query(self, q, p=None):
            return q

    def fake_rows(q):
        if "Episodic" in q:
            return [{"t": iso(0)}, {"t": iso(2)}, {"t": iso(9)}, {"t": iso(900)}]            # el último queda fuera de la ventana
        if "RELATES_TO]->() RETURN r.name" in q:
            return [{"name": "RunsOn", "v": iso(30), "i": None, "x": None, "c": iso(3)}, {"name": "runs-on", "v": iso(30), "i": iso(1), "x": None, "c": iso(10)},
                    {"name": "HostedOn", "v": iso(30), "i": None, "x": None, "c": iso(3)}]
        return [{"name": "Vesta", "degree": 9, "labels": ["Service"]}]
    monkeypatch.setattr(graphapi, "rows", fake_rows)
    monkeypatch.setattr(deps, "graph", lambda n: G())
    client.post("/api/brains", json={"slug": "ac", "name": "Ac", "graph_name": "g-ac"})
    r = client.get("/api/brains/ac/overview/activity", params={"weeks": 8}).json()
    assert len(r["weeks"]) == 8 and sum(r["episodes"]) == 3 and r["episodes"][-1] >= 1               # el último bucket es la semana actual
    assert sum(r["facts_learned"]) == 3 and sum(r["facts_invalidated"]) == 1
    assert r["fact_status"] == {"current": 2, "invalidated": 1, "future": 0}
    assert r["top_relations"][0] == {"name": "RUNS_ON", "count": 2}                                  # RunsOn y runs-on se cuentan juntas
    assert r["top_entities"][0]["name"] == "Vesta" and r["documents"] == {"by_status": {}, "total": 0, "chunks": 0}


PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082")


def test_account_profile_avatar_tokens_and_sessions(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "doc_store", str(tmp_path / "store"))
    monkeypatch.setattr(settings, "account_url", "https://id.example.com/settings/account")
    p = client.get("/api/me/profile").json()
    assert p["email"] is None and p["is_admin"] is True and p["avatar"] == "" and p["account_url"] == "https://id.example.com/settings/account"
    assert client.patch("/api/me/profile", json={"display_name": "  Alex   P  "}).json()["name"] == "Alex P"       # espacios normalizados
    assert client.get("/api/me").json()["name"] == "Alex P"
    assert client.patch("/api/me/profile", json={"display_name": ""}).json()["name"] == "Administrador local"      # vacío = el del proveedor
    # avatar
    assert client.post("/api/me/avatar", content=b"no es una imagen").status_code == 415
    assert client.post("/api/me/avatar", content=PNG + b"\x00" * (1024 * 1024)).status_code == 413
    r = client.post("/api/me/avatar", content=PNG)
    assert r.status_code == 200 and r.json()["avatar"].startswith(f"/api/users/{p['id']}/avatar?v=")
    g = client.get(f"/api/users/{p['id']}/avatar")
    assert g.status_code == 200 and g.content == PNG and g.headers["content-type"] == "image/png" and g.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/me/profile").json()["has_custom_avatar"] is True
    assert client.delete("/api/me/avatar").json()["avatar"] == "" and client.get(f"/api/users/{p['id']}/avatar").status_code == 404
    # tokens personales de todos los brains
    client.post("/api/brains", json={"slug": "acta", "name": "Acta", "graph_name": "g-acta"})
    client.post("/api/brains", json={"slug": "actb", "name": "Actb", "graph_name": "g-actb"})
    t1 = client.post("/api/brains/acta/tokens", json={"name": "portátil", "role": "contributor"}).json()
    client.post("/api/brains/actb/tokens", json={"name": "hook", "role": "reader"})
    mine = [t for t in client.get("/api/me/tokens").json() if t["name"] in ("portátil", "hook")]   # la BD de pruebas es compartida (SQLite reutiliza ids)
    assert sorted((t["brain_slug"], t["name"]) for t in mine) == [("acta", "portátil"), ("actb", "hook")] and "token" not in mine[0]
    client.delete(f"/api/brains/acta/tokens/{t1['id']}")
    assert [t["name"] for t in client.get("/api/me/tokens").json() if t["name"] in ("portátil", "hook")] == ["hook"]
    # actividad y sesiones
    assert any(a["action"] == "account.avatar" for a in client.get("/api/me/activity").json())
    assert client.post("/api/me/sessions/revoke-others").json() == {"ok": True}


def test_public_config_official_links(client, monkeypatch):
    from mimirsynth import brand
    c = client.get("/api/config").json()
    assert c["name"] == "MimirSynth" and c["links"]["repo"] == brand.REPO_URL == "https://github.com/MimirSynth/mimirsynth"
    monkeypatch.setattr(brand, "PUBLISHED", False)  # un fork sin repositorio público puede ocultar los enlaces
    assert client.get("/api/config").json()["links"] == {"docs": "", "repo": "", "feedback": ""}