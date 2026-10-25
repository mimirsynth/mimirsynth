import os
import tempfile

os.environ["MIMIRSYNTH_DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/t.db"
os.environ["MIMIRSYNTH_AUTH_MODE"] = "off"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from mimirsynth.deps import current_user  # noqa: E402
from mimirsynth.main import app  # noqa: E402
from mimirsynth.models import Membership, User  # noqa: E402
from mimirsynth.roles import allows, rank  # noqa: E402
from mimirsynth.store import _factory  # noqa: E402


@pytest.fixture()
def client():
    from mimirsynth import jobs
    jobs.INLINE = True  # los trabajos corren en el hilo de la petición: resultados deterministas
    with TestClient(app) as c:
        yield c
    jobs.INLINE = False
    app.dependency_overrides.clear()


def test_roles_hierarchy():
    assert rank("owner") > rank("admin") > rank("curator") > rank("contributor") > rank("reader") > rank(None)
    assert allows("curator", "contributor") and not allows("reader", "curator")
    assert not allows("denied", "reader")


def test_admin_creates_and_lists_brains(client):
    assert client.get("/api/me").json()["is_admin"] is True
    r = client.post("/api/brains", json={"slug": "familia", "name": "Familia"})
    assert r.status_code == 201 and r.json()["graph_name"] == "familia"
    assert client.post("/api/brains", json={"slug": "familia", "name": "x"}).status_code == 409
    assert client.post("/api/brains", json={"slug": "Mal Slug", "name": "x"}).status_code == 400
    assert "familia" in [b["slug"] for b in client.get("/api/brains").json()]


def test_members_and_role_limits(client):
    client.post("/api/brains", json={"slug": "equipo", "name": "Equipo"})
    assert client.put("/api/brains/equipo/members", json={"email": "ana@x.com", "role": "curator"}).status_code == 200
    assert client.put("/api/brains/equipo/members", json={"email": "ana@x.com", "role": "jefe"}).status_code == 400
    ms = [m for m in client.get("/api/brains/equipo/members").json() if not m["implicit"]]
    assert [m["email"] for m in ms] == ["ana@x.com"]
    uid = ms[0]["user_id"]
    assert client.delete(f"/api/brains/equipo/members/{uid}").status_code == 200
    assert [m for m in client.get("/api/brains/equipo/members").json() if not m["implicit"]] == []


def _as(email: str, name: str):
    with _factory()() as db:
        u = db.scalar(select(User).where(User.email == email)) or User(email=email, name=name)
        db.add(u); db.commit()
        app.dependency_overrides[current_user] = lambda: u
        return u


def test_non_admin_sees_only_own_brains_and_cannot_admin(client):
    client.post("/api/brains", json={"slug": "dep-a", "name": "Dep A"})
    client.post("/api/brains", json={"slug": "dep-b", "name": "Dep B"})
    client.put("/api/brains/dep-a/members", json={"email": "bob@x.com", "role": "reader"})
    client.put("/api/brains/dep-a/members", json={"email": "cris@x.com", "role": "admin"})
    _as("bob@x.com", "Bob")
    assert [b["slug"] for b in client.get("/api/brains").json()] == ["dep-a"]
    assert client.get("/api/brains/dep-a/members").status_code == 403   # lector no administra
    assert client.get("/api/brains/dep-b/members").status_code == 404   # no revela brains ajenos
    assert client.post("/api/brains", json={"slug": "otro", "name": "x"}).status_code == 403
    assert client.get("/api/users").status_code == 403
    _as("cris@x.com", "Cris")
    r = client.put("/api/brains/dep-a/members", json={"email": "dan@x.com", "role": "owner"})
    assert r.status_code == 403                                           # no asigna por encima de su rol
    assert client.put("/api/brains/dep-a/members", json={"email": "dan@x.com", "role": "curator"}).status_code == 200


def test_audit_records_actions(client):
    client.post("/api/brains", json={"slug": "auditado", "name": "A"})
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert "brain.create" in actions


def test_first_oidc_user_becomes_admin_even_if_local_admin_exists(client, monkeypatch):
    """Tras el modo prototipo existe el usuario 'local-admin'; el primer login OIDC real debe poder ser admin."""
    from sqlalchemy import select as sel

    client.get("/api/me")  # crea local-admin
    with _factory()() as db:
        real_admins = db.scalar(sel(User).where(User.is_admin.is_(True), User.sub != "local-admin"))
    assert real_admins is None


def test_local_admin_retired_in_oidc_mode(monkeypatch):
    import mimirsynth.main as m
    from mimirsynth.config import settings

    with _factory()() as db:
        u = db.scalar(select(User).where(User.sub == "local-admin")) or User(sub="local-admin", name="local", is_admin=True)
        u.is_admin = True
        db.add(u); db.commit()
    monkeypatch.setattr(settings, "auth_mode", "oidc")
    m._retire_local_admin()
    with _factory()() as db:
        assert db.scalar(select(User).where(User.sub == "local-admin")).is_admin is False


def test_chunking_and_rrf():
    from mimirsynth.index import chunk_text, rrf

    long = "\n\n".join(f"Párrafo {i}. " + "texto " * 60 for i in range(6))
    ch = chunk_text(long, size=600, overlap=80)
    assert len(ch) > 3 and all(len(c) < 1200 for c in ch)
    assert chunk_text("") == [] and chunk_text("corto") == ["corto"]
    fused = rrf([["a", "b", "c"], ["c", "a", "d"]])
    assert [x for x, _ in fused][:2] == ["a", "c"]  # los que aparecen en ambas listas suben


def test_token_scoped_to_brain_and_role_cap(client):
    client.post("/api/brains", json={"slug": "uno", "name": "Uno"})
    client.post("/api/brains", json={"slug": "dos", "name": "Dos"})
    assert client.post("/api/brains/uno/tokens", json={"name": "x", "role": "admin"}).status_code == 400  # tope: curador
    r = client.post("/api/brains/uno/tokens", json={"name": "agente", "role": "reader"})
    assert r.status_code == 201 and r.json()["token"].startswith("mst_")
    tok = r.json()["token"]
    app.dependency_overrides.clear()
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/brains/uno/index/status", headers=h).status_code == 200
    assert client.get("/api/brains/dos/index/status", headers=h).status_code == 404   # otro brain
    assert client.post("/api/brains/uno/index/sync", headers=h).status_code == 403    # lector no cura
    assert client.post("/api/brains", json={"slug": "tres", "name": "x"}, headers=h).status_code == 403  # tokens no administran
    assert client.get("/api/brains/uno/index/status", headers={"Authorization": "Bearer mst_falso"}).status_code == 401
    tid = r.json()["id"]
    assert client.delete(f"/api/brains/uno/tokens/{tid}").status_code == 200
    assert client.get("/api/brains/uno/index/status", headers=h).status_code == 401  # revocado


def test_recency_boost_and_intent():
    from datetime import datetime, timedelta, timezone

    from mimirsynth.index import recency_factor
    from mimirsynth.recall import recency_weight

    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    new, old = (now - timedelta(days=2)).isoformat(), (now - timedelta(days=120)).isoformat()
    assert recency_factor(new, 0.45, now) > recency_factor(old, 0.45, now) > 1.0
    assert recency_factor(None, 0.45, now) == 1.0 and recency_factor(new, 0, now) == 1.0
    assert recency_weight("¿Dónde está Nextcloud ahora?") > recency_weight("¿Qué proxy usa Graphiti?")
    assert recency_weight("¿Sigue existiendo Uptime Kuma?") > 0.4
    from mimirsynth.index import _tsquery

    assert _tsquery("¿Dónde está Nextcloud ahora?") == "nextcloud"
    assert _tsquery("nim-proxy: ¿qué es?") == "nim | proxy"  # guiones y signos separan términos


def test_rename_brain_and_implicit_owners(client):
    assert client.post("/api/brains", json={"slug": "viejo", "name": "Viejo"}).status_code == 201
    r = client.patch("/api/brains/viejo", json={"name": "Nuevo"})
    assert r.status_code == 200 and r.json()["name"] == "Nuevo" and r.json()["slug"] == "viejo"
    assert client.patch("/api/brains/viejo", json={"name": "  "}).status_code == 400
    members = client.get("/api/brains/viejo/members").json()
    assert any(m["implicit"] and m["role"] == "owner" for m in members)


@pytest.mark.skipif(not os.environ.get("MIMIRSYNTH_TEST_FALKOR"), reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_rename_slug_and_move_graph(client):
    from mimirsynth.config import settings
    from mimirsynth.db import client as fdb
    settings.falkor_host = os.environ["MIMIRSYNTH_TEST_FALKOR"]; fdb.cache_clear()
    c = fdb()
    for g in ("zz_t_old", "zz_t_new"):
        if g in c.list_graphs():
            c.select_graph(g).delete()
    c.select_graph("zz_t_old").query("CREATE (:Entity {name:'a', group_id:'zz_t_old'})-[:R {group_id:'zz_t_old'}]->(:Entity {name:'b', group_id:'zz_t_old'})")
    try:
        assert client.post("/api/brains", json={"slug": "mov", "name": "Mov", "graph_name": "zz_t_old"}).status_code == 201
        r = client.patch("/api/brains/mov", json={"slug": "movido", "graph_name": "zz_t_new"})
        assert r.status_code == 200, r.text
        assert r.json()["slug"] == "movido" and r.json()["graph_name"] == "zz_t_new" and r.json()["old_graph_kept"] == "zz_t_old"
        assert c.select_graph("zz_t_new").query("MATCH ()-[e]->() RETURN e.group_id").result_set == [["zz_t_new"]]
        assert "zz_t_old" in c.list_graphs()  # el original se conserva
        assert client.patch("/api/brains/movido", json={"graph_name": "zz_t_new"}).status_code in (200, 409)
        assert client.post("/api/brains", json={"slug": "otro", "name": "O"}).status_code == 201
        assert client.patch("/api/brains/otro", json={"slug": "movido"}).status_code == 409
        assert client.patch("/api/brains/otro", json={"graph_name": "zz_t_new"}).status_code == 409
    finally:
        for g in ("zz_t_old", "zz_t_new"):
            if g in c.list_graphs():
                c.select_graph(g).delete()


def test_proposals_quarantine_flow(client):
    client.post("/api/brains", json={"slug": "cuar", "name": "Cuar"})
    mk = lambda role: {"Authorization": "Bearer " + client.post("/api/brains/cuar/tokens", json={"name": role, "role": role}).json()["token"]}
    reader_h, contrib_h, curator_h = mk("reader"), mk("contributor"), mk("curator")
    prop = {"name": "Dato", "body": "Nextcloud está en Helios", "confidence": 0.8}
    assert client.post("/api/brains/cuar/proposals", json=prop, headers=reader_h).status_code == 403
    r = client.post("/api/brains/cuar/proposals", json=prop, headers=contrib_h)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    pid = r.json()["id"]
    assert client.post(f"/api/brains/cuar/proposals/{pid}/approve", json={}, headers=contrib_h).status_code == 403  # no se autoaprueba
    assert client.post("/api/brains/cuar/proposals", json={**prop, "confidence": 2}, headers=contrib_h).status_code == 422
    r2 = client.post("/api/brains/cuar/proposals", json={"name": "Directa", "body": "x"}, headers=curator_h)
    assert r2.json()["status"] == "approved"  # el curador no pasa por cuarentena
    assert len(client.get("/api/brains/cuar/proposals?status=pending", headers=curator_h).json()) == 1
    ok = client.post(f"/api/brains/cuar/proposals/{pid}/approve", json={"note": "ok"}, headers=curator_h)
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["review_note"] == "ok" and ok.json()["review_kind"] == "human"
    assert client.post(f"/api/brains/cuar/proposals/{pid}/reject", json={}, headers=curator_h).status_code == 409
    assert client.post("/api/brains/otro/proposals", json=prop, headers=contrib_h).status_code == 404


def test_ingest_marks_status(client, monkeypatch):
    from mimirsynth import ingest
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "llm_base_url", "http://x"); monkeypatch.setattr(settings, "llm_model", "m")
    calls = []

    async def fake(graph, name, body, source, desc, ref, ontology=None, report=None):
        calls.append(graph)
        if name == "malo":
            raise RuntimeError("LLM caído")
        return "uuid-1"
    monkeypatch.setattr(ingest, "add_episode", fake)
    client.post("/api/brains", json={"slug": "ing", "name": "Ing"})
    ok = client.post("/api/brains/ing/proposals", json={"name": "bueno", "body": "x"}).json()  # admin -> aprobada -> ingesta
    bad = client.post("/api/brains/ing/proposals", json={"name": "malo", "body": "x"}).json()
    st = {p["id"]: p for p in client.get("/api/brains/ing/proposals").json()}
    assert st[ok["id"]]["status"] == "ingested" and st[ok["id"]]["episode_uuid"] == "uuid-1"
    assert st[bad["id"]]["status"] == "failed" and "LLM caído" in st[bad["id"]]["ingest_error"]
    assert calls == ["ing", "ing"]


def test_llm_engines_admin(client, monkeypatch):
    r = client.post("/api/llm-engines", json={"name": "nim", "base_url": "http://gw:4000/v1", "model": "m1", "api_key": "sk-secreto"})
    assert r.status_code == 201 and r.json()["has_key"] and r.json()["is_default"] and "sk-secreto" not in r.text
    eid = r.json()["id"]
    assert "sk-secreto" not in client.get("/api/llm-engines").text
    from mimirsynth import llm
    from mimirsynth.store import _factory
    with _factory()() as db:
        assert llm.resolve(db)["api_key"] == "sk-secreto"  # cifrada en BD, descifrable al usarla
    r2 = client.patch(f"/api/llm-engines/{eid}", json={"name": "nim", "base_url": "http://gw:4000/v1/", "model": "m2"})  # sin clave: se conserva
    assert r2.json()["model"] == "m2" and r2.json()["has_key"] and r2.json()["base_url"] == "http://gw:4000/v1"
    assert client.post("/api/llm-engines", json={"name": "nim", "base_url": "http://x/v1", "model": "m"}).status_code == 409
    b = client.post("/api/llm-engines", json={"name": "local", "base_url": "http://ollama:11434/v1", "model": "q"}).json()
    assert not b["is_default"] and client.post(f"/api/llm-engines/{b['id']}/default").json()["is_default"]
    assert sum(e["is_default"] for e in client.get("/api/llm-engines").json()) == 1
    assert client.delete(f"/api/llm-engines/{eid}").status_code == 200


def test_llm_models_listing(client, monkeypatch):
    import httpx
    class R:
        status_code = 200
        def json(self): return {"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}]}
    seen = {}
    monkeypatch.setattr(httpx, "get", lambda url, headers=None, timeout=0: (seen.update(url=url, h=headers), R())[1])
    r = client.post("/api/llm-engines/models", json={"base_url": "http://gw/v1/", "api_key": "k"})
    assert r.json()["models"] == ["a", "b"] and seen["url"] == "http://gw/v1/models" and seen["h"] == {"Authorization": "Bearer k"}


def test_embedding_engines_guard(client, monkeypatch):
    from mimirsynth import embeddings_admin as ea
    dims = {"nomic": 768, "otro": 1024}
    monkeypatch.setattr(ea, "_probe", lambda url, model, key: dims[model])
    a = client.post("/api/embedding-engines", json={"name": "ollama", "base_url": "http://o/v1", "model": "nomic"}).json()
    assert a["is_default"] and a["dim"] == 768
    b = client.post("/api/embedding-engines", json={"name": "espejo", "base_url": "http://p/v1", "model": "nomic"}).json()
    c = client.post("/api/embedding-engines", json={"name": "grande", "base_url": "http://q/v1", "model": "otro"}).json()
    assert not b["is_default"] and not c["is_default"]
    assert client.post(f"/api/embedding-engines/{b['id']}/default").json()["is_default"]  # mismo modelo y dimensión: permitido
    assert client.post(f"/api/embedding-engines/{c['id']}/default").status_code == 409     # otro modelo: bloqueado
    assert client.patch(f"/api/embedding-engines/{a['id']}", json={"name": "ollama", "base_url": "http://o/v1", "model": "otro"}).status_code == 409
    assert client.delete(f"/api/embedding-engines/{b['id']}").status_code == 409            # es el por defecto
    assert client.delete(f"/api/embedding-engines/{a['id']}").status_code == 200


def test_decider_logic_and_triage(client, monkeypatch):
    from mimirsynth import decider, deciders_admin
    seq = []
    monkeypatch.setattr(decider, "decide", lambda *a, **k: seq.pop(0))
    hi = lambda l, p=0.95: {"letter": l, "prob": p, "probs": {l: p}, "index": ord(l) - 65}
    seq[:] = [hi("A"), hi("A")]
    assert decider.triage("u", "m", "", "t", "b", 0.9, 0.8)["verdict"] == "approve"
    seq[:] = [hi("A"), hi("A", 0.6)]
    assert decider.triage("u", "m", "", "t", "b", 0.9, 0.8)["verdict"] == "review"       # poca confianza: a un curador
    seq[:] = [hi("B"), hi("A")]
    r = decider.triage("u", "m", "", "t", "b", 0.9, 0.8)
    assert r["verdict"] == "review" and "instrucción" in r["note"]                         # nunca aprueba lo no factual
    # flujo completo: un colaborador envía, el decisor aprueba solo y se ingiere
    from mimirsynth import ingest
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "llm_base_url", "http://x"); monkeypatch.setattr(settings, "llm_model", "m")
    async def fake(*a, **k): return "uuid-9"
    monkeypatch.setattr(ingest, "add_episode", fake)
    client.post("/api/brains", json={"slug": "tri", "name": "Tri"})
    d = client.post("/api/decision-engines", json={"name": "tev1", "base_url": "http://o/v1", "model": "tev1", "threshold": 0.8}).json()
    assert d["is_default"] and d["threshold"] == 0.8
    tok = {"Authorization": "Bearer " + client.post("/api/brains/tri/tokens", json={"name": "c", "role": "contributor"}).json()["token"]}
    seq[:] = [hi("A"), hi("A")]
    pid = client.post("/api/brains/tri/proposals", json={"name": "Dato", "body": "Plex corre en Zephyr"}, headers=tok).json()["id"]
    got = client.get(f"/api/brains/tri/proposals/{pid}").json()
    assert got["status"] == "ingested" and got["decision"]["verdict"] == "approve" and got["episode_uuid"] == "uuid-9"
    seq[:] = [hi("A"), hi("B", 0.9)]
    pid2 = client.post("/api/brains/tri/proposals", json={"name": "Dato2", "body": "dudoso"}, headers=tok).json()["id"]
    assert client.get(f"/api/brains/tri/proposals/{pid2}").json()["status"] == "pending"
    assert client.patch(f"/api/decision-engines/{d['id']}", json={"name": "tev1", "base_url": "http://o/v1", "model": "tev1", "threshold": 0.3}).status_code == 422


def test_proposal_counts(client):
    client.post("/api/brains", json={"slug": "cnt", "name": "Cnt"})
    client.post("/api/brains/cnt/proposals", json={"name": "a", "body": "x"})
    c = client.get("/api/brains/cnt/proposals/counts").json()
    assert c["approved"] + c["ingested"] + c["failed"] == 1 and c["all"] == 1 and c["pending"] == 0


def test_additive_migration_adds_new_columns(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text
    from mimirsynth import store
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:  # esquema antiguo de proposals, sin las columnas nuevas
        c.execute(text("CREATE TABLE proposals (id INTEGER PRIMARY KEY, brain_id INTEGER, author_id INTEGER, name VARCHAR(255), body TEXT, status VARCHAR(16))"))
    monkeypatch.setattr(store, "engine", lambda: eng)
    store._add_missing_columns()
    cols = {c["name"] for c in inspect(eng).get_columns("proposals")}
    assert {"review_kind", "decision", "ingest_error", "episode_uuid", "ingested_at", "confidence"} <= cols
    store._add_missing_columns()  # idempotente


def test_ai_status(client, monkeypatch):
    from mimirsynth import aistatus
    s = client.get("/api/ai-status").json()
    assert set(s) == {"llm", "embedding", "decider"} and "healthy" not in s["llm"]  # sin check no se sondea nada
    client.post("/api/llm-engines", json={"name": "estado", "base_url": "http://g/v1", "model": "m"})  # la BD de tests se comparte: ya puede haber un motor por defecto
    monkeypatch.setattr(aistatus, "_llm_ping", lambda *a: (_ for _ in ()).throw(RuntimeError("401")))
    s = client.get("/api/ai-status?check=true").json()
    assert s["llm"]["configured"] and s["llm"]["source"] == "db" and s["llm"]["healthy"] is False and "401" in s["llm"]["error"]


def test_alembic_fresh_and_legacy(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, inspect, text
    from mimirsynth import store
    # BD nueva: se crea entera desde las migraciones y queda en la cabeza
    e1 = create_engine(f"sqlite:///{tmp_path}/new.db")
    monkeypatch.setattr(store, "engine", lambda: e1)
    store.init_db()
    assert {"users", "brains", "proposals", "decision_engines", "alembic_version"} <= set(inspect(e1).get_table_names())
    with e1.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar() == "0016"
    store.init_db()  # idempotente
    # BD heredada (create_all sin alembic_version y sin columnas nuevas): se completa y se marca
    e2 = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    store.Base.metadata.create_all(e2)
    with e2.begin() as c:
        c.execute(text("ALTER TABLE proposals DROP COLUMN ingest_error"))
    monkeypatch.setattr(store, "engine", lambda: e2)
    store.init_db()
    assert "ingest_error" in {c["name"] for c in inspect(e2).get_columns("proposals")}
    with e2.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar() == "0016"


def test_ontology_api_and_graphiti_conversion(client):
    from mimirsynth import ontology as ont
    client.post("/api/brains", json={"slug": "onto", "name": "Onto"})
    assert client.get("/api/brains/onto/ontology").json()["configured"] is False
    r = client.post("/api/brains/onto/ontology/preset/infrastructure")
    assert r.status_code == 200
    got = client.get("/api/brains/onto/ontology").json()
    assert got["configured"] and {"infrastructure", "generic"} <= set(got["presets"]) and any(t["name"] == "HostedOn" for t in got["ontology"]["edge_types"])
    assert client.post("/api/brains/onto/ontology/preset/nope").status_code == 404
    bad = {"entity_types": [{"name": "host", "description": "minúscula inválida"}], "edge_types": [], "edge_type_map": []}
    assert client.put("/api/brains/onto/ontology", json=bad).status_code == 422
    bad2 = {"entity_types": [{"name": "Host", "description": "un servidor"}], "edge_types": [], "edge_type_map": [{"source": "Host", "target": "Nada", "edge_types": []}]}
    assert client.put("/api/brains/onto/ontology", json=bad2).status_code == 400
    args = ont.to_graphiti(got["ontology"])
    assert "Host" in args["entity_types"] and args["entity_types"]["Host"].__doc__.startswith("A Proxmox node")
    assert args["edge_type_map"][("Guest", "Host")] == ["HostedOn", "MigratedTo"]
    assert args["custom_extraction_instructions"] and "Service" in args["custom_extraction_instructions"]
    assert ont.canon("HostedOn") == "HOSTED_ON" and ont.canon("RELATES_TO") == "RELATES_TO"


def test_retype_scan_apply_revert(client, monkeypatch):
    from mimirsynth import decider, retype
    client.post("/api/brains", json={"slug": "ret", "name": "Ret"})
    assert client.post("/api/brains/ret/retype/scan", json={"limit": 5}).status_code == 409  # sin ontología
    client.post("/api/brains/ret/ontology/preset/infrastructure")
    client.post("/api/decision-engines", json={"name": "dec-ret", "base_url": "http://o/v1", "model": "tev1"})
    ents = [{"uuid": "u1", "name": "sonarr", "type": "Organization", "summary": "app"},
            {"uuid": "u2", "name": "Helios", "type": "Location", "summary": "nodo"},
            {"uuid": "u3", "name": "Madrid", "type": "Location", "summary": "ciudad"}]
    monkeypatch.setattr(retype, "_candidates", lambda g, skip, limit: [e for e in ents if e["uuid"] not in skip][:limit])
    monkeypatch.setattr(retype, "_facts", lambda g, u: ["x"])
    calls = []
    monkeypatch.setattr(retype, "_set_label", lambda g, u, old, new: calls.append((u, old, new)))
    types = [t["name"] for t in __import__("mimirsynth.ontology", fromlist=["x"]).presets()["infrastructure"]["entity_types"]]
    answers = {"sonarr": types.index("Service"), "Helios": types.index("Host"), "Madrid": len(types)}  # Madrid -> «Ninguno»
    monkeypatch.setattr(decider, "decide", lambda base, model, key, state, q, opts, **k: {"index": answers[state.split("\n")[0].split(": ")[1]], "letter": "A", "prob": 0.9, "probs": {}})
    assert client.post("/api/brains/ret/retype/scan", json={"limit": 10}).status_code == 202
    o = client.get("/api/brains/ret/retype").json()
    assert o["counts"] == {"pending": 2, "none": 1}
    items = {i["name"]: i for i in o["items"]}
    assert items["sonarr"]["suggested_type"] == "Service" and items["Helios"]["suggested_type"] == "Host"
    r = client.post("/api/brains/ret/retype/apply", json={"ids": [items["sonarr"]["id"]]}).json()
    assert r["applied"] == 1 and calls == [("u1", "Organization", "Service")]
    assert client.post(f"/api/brains/ret/retype/{items['sonarr']['id']}/revert").status_code == 200 and calls[-1] == ("u1", "Service", "Organization")
    assert client.post("/api/brains/ret/retype/reject", json={"ids": [items["Helios"]["id"]]}).json()["rejected"] == 1
    assert client.get("/api/brains/ret/retype").json()["counts"].get("pending", 0) == 0


def test_retype_doubtful_heuristics_and_counts(client, monkeypatch):
    from mimirsynth import decider, retype
    for n, why in [("tools/utils/secrets.py", "fichero"), ("-config-file flag", "opción"), ("Nextcloud 1.36.0", "versión"),
                   ("LXC container network configuration with ip6=auto", "expresión"), ("Anthropic temperature validation bug", "problema"), ("Nextcloud", ""), ("plex.example.com", "")]:
        assert bool(retype.doubtful_reason(n)) == bool(why), n
    client.post("/api/brains", json={"slug": "dud", "name": "Dud"})
    client.post("/api/brains/dud/ontology/preset/infrastructure")
    client.post("/api/decision-engines", json={"name": "dec-dud", "base_url": "http://o/v1", "model": "tev1"})
    ents = [{"uuid": "a", "name": "roulette_spin.py", "type": "Object", "summary": ""}, {"uuid": "b", "name": "Plex", "type": "Organization", "summary": ""},
            {"uuid": "c", "name": "Cosa rara", "type": "Object", "summary": ""}]
    monkeypatch.setattr(retype, "_candidates", lambda g, skip, limit: [e for e in ents if e["uuid"] not in skip])
    monkeypatch.setattr(retype, "_facts", lambda g, u: [])
    types = [t["name"] for t in __import__("mimirsynth.ontology", fromlist=["x"]).presets()["infrastructure"]["entity_types"]]

    def fake(base, model, key, state, q, opts, **k):
        if "entidad concreta" in q:
            return {"index": 1 if "Cosa rara" in state else 0, "letter": "B" if "Cosa rara" in state else "A", "prob": 0.9, "probs": {}}
        return {"index": types.index("Service"), "letter": "A", "prob": 0.95, "probs": {}}
    monkeypatch.setattr(decider, "decide", fake)
    assert client.post("/api/brains/dud/retype/scan", json={"limit": 10}).status_code == 202
    o = client.get("/api/brains/dud/retype").json()
    assert o["counts"] == {"doubtful": 2, "pending": 1}                      # fichero (heurística) y «Cosa rara» (decisor) son dudosas; Plex se propone
    assert [i["name"] for i in o["items"]] == ["Plex"] and o["hidden_below_threshold"] == 0
    assert o["items"][0]["suggested_type"] == "Service"
    d = client.get("/api/brains/dud/retype?status=doubtful").json()["items"]
    assert {i["name"]: bool(i["reason"]) for i in d} == {"roulette_spin.py": True, "Cosa rara": True}
    assert client.post("/api/brains/dud/retype/apply", json={"ids": [i["id"] for i in d]}).json()["applied"] == 0  # las dudosas no se aplican
    assert client.post("/api/brains/dud/retype/reject", json={"ids": [d[0]["id"]]}).json()["rejected"] == 1


def test_retype_none_is_not_same(client, monkeypatch):
    from mimirsynth import decider, retype
    client.post("/api/brains", json={"slug": "nin", "name": "Nin"})
    client.post("/api/brains/nin/ontology/preset/infrastructure")
    client.post("/api/decision-engines", json={"name": "dec-nin", "base_url": "http://o/v1", "model": "tev1"})
    ents = [{"uuid": "x", "name": "Cosa", "type": "Object", "summary": ""}, {"uuid": "y", "name": "Plex", "type": "Service", "summary": ""}]
    monkeypatch.setattr(retype, "_candidates", lambda g, skip, limit: [e for e in ents if e["uuid"] not in skip])
    monkeypatch.setattr(retype, "_facts", lambda g, u: [])
    types = [t["name"] for t in __import__("mimirsynth.ontology", fromlist=["x"]).presets()["infrastructure"]["entity_types"]]
    def fake(base, model, key, state, q, opts, **k):
        if "entidad concreta" in q:
            return {"index": 0, "letter": "A", "prob": 0.9, "probs": {}}
        i = len(types) if "Cosa" in state else types.index("Service")
        return {"index": i, "letter": "A", "prob": 0.8, "probs": {}}
    monkeypatch.setattr(decider, "decide", fake)
    client.post("/api/brains/nin/retype/scan", json={"limit": 5})
    c = client.get("/api/brains/nin/retype").json()["counts"]
    assert c == {"none": 1, "same": 1}                                     # «ninguno» ya no se cuenta como «ya correcto»
    n = client.get("/api/brains/nin/retype?status=none").json()["items"]
    assert [i["name"] for i in n] == ["Cosa"] and n[0]["reason"]


def test_delete_brain_with_confirmation(client, monkeypatch):
    from mimirsynth import brains as bmod
    graphs = []

    class FakeG:
        def __init__(self, n): self.n = n
        def delete(self): graphs.append(self.n)

    class FakeC:
        def select_graph(self, n): return FakeG(n)
    monkeypatch.setattr(bmod, "client", lambda: FakeC())
    client.post("/api/brains", json={"slug": "borra", "name": "Borra", "graph_name": "g-borra"})
    tok = client.post("/api/brains/borra/tokens", json={"name": "t", "role": "reader"}).json()
    client.post("/api/brains/borra/proposals", json={"name": "p", "body": "x"})
    assert client.post("/api/brains/borra/delete", json={"confirm": "otro"}).status_code == 400            # confirmación distinta
    r = client.post("/api/brains/borra/delete", json={"confirm": "borra"})
    assert r.status_code == 200 and r.json()["graph_deleted"] is False and graphs == []                    # el grafo se conserva por defecto
    assert "borra" not in [b["slug"] for b in client.get("/api/brains").json()]
    assert client.get("/api/brains/borra/proposals").status_code == 404
    client.post("/api/brains", json={"slug": "borra2", "name": "B2", "graph_name": "g-borra2"})
    r2 = client.post("/api/brains/borra2/delete", json={"confirm": "borra2", "delete_graph": True})
    assert r2.json()["graph_deleted"] is True and graphs == ["g-borra2"]


def test_bootstrap_only_on_first_run(monkeypatch):
    from mimirsynth import main as mm
    from mimirsynth.config import settings
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        db.query(Brain).delete(); db.commit()
    monkeypatch.setattr(settings, "bootstrap_graphs", "uno:Uno,dos:Dos")
    mm._bootstrap()
    with _factory()() as db:
        assert {b.slug for b in db.query(Brain)} == {"uno", "dos"}
        db.query(Brain).filter(Brain.slug == "uno").delete(); db.commit()  # el usuario borra «uno»
    mm._bootstrap()
    with _factory()() as db:
        assert {b.slug for b in db.query(Brain)} == {"dos"}  # no resucita


def test_vocab_aliases(client):
    from mimirsynth.vocab import resolve
    client.post("/api/brains", json={"slug": "voc", "name": "Voc", "graph_name": "g-voc"})
    assert client.post("/api/brains/voc/vocab/aliases", json={"alias": "hosted_on", "canonical": "runs_on"}).status_code == 201
    assert client.post("/api/brains/voc/vocab/aliases", json={"alias": "hosted_on", "canonical": "x"}).status_code == 409   # alias duplicado
    assert client.post("/api/brains/voc/vocab/aliases", json={"alias": "same", "canonical": "SAME"}).status_code == 400    # alias = canónico
    assert client.post("/api/brains/voc/vocab/aliases", json={"alias": "runs_on", "canonical": "hosted_on"}).status_code in (400, 409)  # ciclo
    items = client.get("/api/brains/voc/vocab/aliases").json()
    assert [(i["alias"], i["canonical"]) for i in items] == [("HOSTED_ON", "RUNS_ON")]
    assert resolve("hostedOn", {"HOSTED_ON": "RUNS_ON"}) == "RUNS_ON"
    assert resolve("A", {"A": "B", "B": "C"}) == "C"
    assert client.delete(f"/api/brains/voc/vocab/aliases/{items[0]['id']}").status_code == 204
    assert client.get("/api/brains/voc/vocab/aliases").json() == []


class FakeTypesGraph:
    """Grafo en memoria que entiende las consultas de entity_types."""
    def __init__(self, nodes): self.nodes = nodes  # uuid -> {"name", "labels": set}

    def query(self, q, params=None):
        import re
        lab = re.findall(r":`(\w+)`", q)
        has = lambda n, ls: all(l in n["labels"] for l in ls)  # noqa: E731
        if "WITH [l IN labels" in q:
            out = []
            for n in self.nodes.values():
                out += [{"label": l, "count": 1} for l in (n["labels"] or {"(sin tipo)"})]
            agg: dict = {}
            for r in out: agg[r["label"]] = agg.get(r["label"], 0) + 1
            return [{"label": k, "count": v} for k, v in agg.items()]
        if "RETURN n.uuid AS u" in q:
            return [{"u": u} for u, n in self.nodes.items() if has(n, lab)]
        if "RETURN n.name AS name" in q:
            return [{"name": n["name"]} for n in self.nodes.values() if has(n, lab)][:8]
        if "RETURN count(n)" in q:
            return [{"n": sum(1 for n in self.nodes.values() if has(n, lab[:1]) and (len(lab) < 2 or "WHERE" not in q or has(n, lab)))}]
        if "REMOVE" in q or "SET" in q:
            ids = (params or {}).get("ids")
            for u, n in self.nodes.items():
                if ids is not None and u not in ids: continue
                if ids is None and lab[0] not in n["labels"]: continue
                if "REMOVE" in q: n["labels"].discard(lab[0])
                n["labels"].add(lab[-1])
            return []
        raise AssertionError(q)


def test_entity_types_edit_move_revert(client, monkeypatch):
    from mimirsynth import deps, entity_types as et
    nodes = {"u1": {"name": "sonarr", "labels": {"Guest"}}, "u2": {"name": "radarr", "labels": {"Guest"}},
             "u3": {"name": "Helios", "labels": {"Machine"}}, "u4": {"name": "x", "labels": {"Guest", "Machine"}}, "u5": {"name": "y", "labels": set()}}
    fg = FakeTypesGraph(nodes)
    monkeypatch.setattr(et, "graph", lambda n: fg); monkeypatch.setattr(et, "rows", lambda r: r); monkeypatch.setattr(deps, "graph", lambda n: fg)
    client.post("/api/brains", json={"slug": "ty", "name": "Ty", "graph_name": "g-ty"})
    base = "/api/brains/ty/vocab"
    assert client.post(f"{base}/types", json={"name": "Machine", "description": "Equipo físico"}).status_code == 201
    assert client.post(f"{base}/types", json={"name": "Machine", "description": "Equipo físico"}).status_code == 409
    assert client.post(f"{base}/types", json={"name": "mala forma", "description": "xx yy"}).status_code in (400, 422)
    lst = client.get(f"{base}/types").json()
    by = {i["name"]: i for i in lst["items"]}
    assert by["Machine"]["in_ontology"] and by["Machine"]["count"] == 2 and not by["Guest"]["in_ontology"] and by["Guest"]["count"] == 3 and lst["untyped"] == 1
    assert client.put(f"{base}/types/Machine", json={"description": "Servidor o equipo"}).status_code == 200
    pv = client.get(f"{base}/types/Guest/preview", params={"to": "Machine"}).json()
    assert pv["entities"] == 3
    r = client.post(f"{base}/types/Guest/move", json={"to": "Machine"}).json()      # fusionar
    assert r["entities"] == 3 and all("Guest" not in n["labels"] and "Machine" in n["labels"] for n in nodes.values() if n["labels"])
    ops = client.get(f"{base}/types").json()["ops"]
    assert client.post(f"{base}/ops/{ops[2]['id']}/revert").status_code == 409        # no es el último
    assert client.post(f"{base}/ops/{ops[0]['id']}/revert").status_code == 200       # deshace la fusión
    assert nodes["u1"]["labels"] == {"Guest"} and nodes["u4"]["labels"] == {"Guest", "Machine"} and nodes["u3"]["labels"] == {"Machine"}
    assert client.post(f"{base}/types/Machine/move", json={"to": "Host"}).status_code == 200  # renombrar: hereda descripción
    onto = client.get("/api/brains/ty/ontology").json()["ontology"]
    assert [t["name"] for t in onto["entity_types"]] == ["Host"] and onto["entity_types"][0]["description"] == "Servidor o equipo"
    assert client.delete(f"{base}/types/Host").status_code == 200
    assert client.get("/api/brains/ty/ontology").json()["ontology"]["entity_types"] == []


@pytest.mark.skipif(not os.environ.get("MIMIRSYNTH_TEST_FALKOR"), reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_merge_entities_real_falkor(client):
    import falkordb
    from mimirsynth.config import settings
    host = os.environ["MIMIRSYNTH_TEST_FALKOR"]
    settings.falkor_host = host
    from mimirsynth import db as dbm
    dbm.client.cache_clear() if hasattr(dbm.client, "cache_clear") else None
    c = falkordb.FalkorDB(host=host, port=6379)
    name = "zz-test-merge"
    try: c.select_graph(name).delete()
    except Exception: pass
    g = c.select_graph(name)
    g.query("CREATE (k:Entity {uuid:'k', name:'Nextcloud'}), (d:Entity {uuid:'d', name:'Nextcloud 1.37'}), (b:Entity {uuid:'b', name:'Notus'}), (e:Episodic {uuid:'e'}), "
            "(d)-[:RELATES_TO {uuid:'r1', fact:'runs on notus'}]->(b), (b)-[:RELATES_TO {uuid:'r2', fact:'hosts'}]->(d), (e)-[:MENTIONS {uuid:'m1'}]->(d), (d)-[:RELATES_TO {uuid:'r3', fact:'same'}]->(k)")
    try:
        client.post("/api/brains", json={"slug": "mg", "name": "Mg", "graph_name": name})
        base = "/api/brains/mg/vocab"
        pv = client.post(f"{base}/duplicates/preview", json={"keeper": "k", "merge": ["d"]}).json()
        assert pv["items"][0]["facts"] == 2 and pv["items"][0]["mentions"] == 1 and pv["items"][0]["between"] == 1
        assert client.post(f"{base}/duplicates/merge", json={"keeper": "k", "merge": ["k"]}).status_code == 400
        assert client.post(f"{base}/duplicates/merge", json={"keeper": "k", "merge": ["d"]}).status_code == 200
        n = lambda q: g.query(q).result_set[0][0]  # noqa: E731
        assert n("MATCH (:Entity {uuid:'k'})-[r]-() RETURN count(r)") == 4 and n("MATCH (d:Entity {uuid:'d'}) RETURN count(d)") == 0
        assert n("MATCH (d:Merged {uuid:'d'}) RETURN d.merged_into") == "k"
        op = client.get(f"{base}/types").json()["ops"][0]
        assert client.post(f"{base}/ops/{op['id']}/revert").status_code == 200
        assert n("MATCH (:Entity {uuid:'d'})-[r]-() RETURN count(r)") == 4 and n("MATCH (:Entity {uuid:'k'})-[r]-() RETURN count(r)") == 1
    finally:
        g.delete()
        for x in c.list_graphs():
            if x.startswith(f"_snap_{name}_"): c.select_graph(x).delete()


def test_ignore_duplicate_group(client):
    client.post("/api/brains", json={"slug": "ig", "name": "Ig", "graph_name": "g-ig"})
    base = "/api/brains/ig/vocab/duplicates/ignore"
    assert client.post(base, json={"key": "Debian"}).status_code == 201
    assert client.post(base, json={"key": "debian"}).status_code == 201     # idempotente
    assert client.delete(base, params={"key": "debian"}).status_code == 200


@pytest.mark.skipif(not os.environ.get("MIMIRSYNTH_TEST_FALKOR"), reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_vocab_apply_after_ingest(client):
    import falkordb
    from mimirsynth import vocab_apply
    from mimirsynth.config import settings
    from mimirsynth.models import Brain
    host = os.environ["MIMIRSYNTH_TEST_FALKOR"]
    settings.falkor_host = host
    c = falkordb.FalkorDB(host=host, port=6379)
    name = "zz-test-apply"
    try: c.select_graph(name).delete()
    except Exception: pass
    g = c.select_graph(name)
    g.query("CREATE (k:Entity {uuid:'k', name:'Vesta', aliases:['Vesta']}), (n:Entity {uuid:'n', name:'Vesta'}), (o:Entity {uuid:'o', name:'Notus'}), (x:Entity {uuid:'x', name:'Otro'}), "
            "(n)-[:RELATES_TO {uuid:'e1', name:'HOSTED_ON', fact:'f1'}]->(o), (x)-[:RELATES_TO {uuid:'e2', name:'RunsOn', fact:'f2'}]->(o)")
    try:
        client.post("/api/brains", json={"slug": "ap", "name": "Ap", "graph_name": name})
        client.post("/api/brains/ap/vocab/aliases", json={"alias": "hosted_on", "canonical": "runs_on"})
        from sqlalchemy import select
        with _factory()() as db:
            brain = db.scalar(select(Brain).where(Brain.slug == "ap"))
            rep = {"_edges": [("e1", "HOSTED_ON"), ("e2", "RunsOn")], "_nodes": [("n", "Vesta", True), ("o", "Notus", True), ("x", "Otro", False)]}
            vocab_apply.apply(db, brain, rep)
        assert rep["aliased_edges"] == 1 and rep["auto_merged"] == ["Vesta"] and "_edges" not in rep
        n = lambda q: g.query(q).result_set[0][0]  # noqa: E731
        assert n("MATCH ()-[r {uuid:'e1'}]->() RETURN r.name") == "RUNS_ON" and n("MATCH ()-[r {uuid:'e2'}]->() RETURN r.name") == "RunsOn"
        assert n("MATCH (:Entity {uuid:'k'})-[r:RELATES_TO]->() RETURN count(r)") == 1 and n("MATCH (m:Entity {uuid:'n'}) RETURN count(m)") == 0
        ops = client.get("/api/brains/ap/vocab/types").json()["ops"]
        assert ops[0]["summary"].startswith("Auto:")
        assert client.post(f"/api/brains/ap/vocab/ops/{ops[0]['id']}/revert").status_code == 200
        assert n("MATCH (:Entity {uuid:'n'})-[r:RELATES_TO]->() RETURN count(r)") == 1
    finally:
        g.delete()


@pytest.mark.skipif(not os.environ.get("MIMIRSYNTH_TEST_FALKOR"), reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_fact_edit_invalidate_delete_undo(client, monkeypatch):
    import falkordb
    from mimirsynth import facts_admin
    from mimirsynth.config import settings
    host = os.environ["MIMIRSYNTH_TEST_FALKOR"]
    settings.falkor_host = host
    monkeypatch.setattr(facts_admin, "get_embedder", lambda: type("E", (), {"embed": lambda self, t: [[0.1] * 4 for _ in t]})())
    c = falkordb.FalkorDB(host=host, port=6379)
    name = "zz-test-facts"
    try: c.select_graph(name).delete()
    except Exception: pass
    g = c.select_graph(name)
    g.query("CREATE (a:Entity {uuid:'a', name:'Vesta'}), (b:Entity {uuid:'b', name:'Cloudco'}), (e:Episodic {uuid:'e1', entity_edges:['f1']}), "
            "(a)-[:RELATES_TO {uuid:'f1', name:'HOSTED_ON', fact:'Vesta esta en Cloudco', episodes:['e1'], group_id:name, created_at:'2026-01-01T00:00:00+00:00', fact_embedding: vecf32([0.5,0.5,0.5,0.5])}]->(b)".replace("group_id:name", "group_id:'x'"))
    n = lambda q: g.query(q).result_set[0][0]  # noqa: E731
    try:
        client.post("/api/brains", json={"slug": "fa", "name": "Fa", "graph_name": name})
        base = "/api/brains/fa"
        assert client.patch(f"{base}/facts/f1", json={}).status_code == 400
        r = client.patch(f"{base}/facts/f1", json={"fact": "Vesta es un servidor de copias remoto en Cloudco", "name": "runs on"}).json()
        assert n("MATCH ()-[r {uuid:'f1'}]->() RETURN r.fact") == "Vesta es un servidor de copias remoto en Cloudco" and n("MATCH ()-[r {uuid:'f1'}]->() RETURN r.name") == "RUNS_ON"
        assert client.post(f"{base}/vocab/ops/{r['op']}/revert").status_code == 200
        assert n("MATCH ()-[r {uuid:'f1'}]->() RETURN r.fact") == "Vesta esta en Cloudco" and n("MATCH ()-[r {uuid:'f1'}]->() RETURN r.name") == "HOSTED_ON"
        r = client.post(f"{base}/facts/f1/invalidate").json()
        assert n("MATCH ()-[r {uuid:'f1'}]->() RETURN r.invalid_at") is not None and client.post(f"{base}/facts/f1/invalidate").status_code == 409
        assert client.post(f"{base}/vocab/ops/{r['op']}/revert").status_code == 200 and n("MATCH ()-[r {uuid:'f1'}]->() RETURN r.invalid_at") is None
        r = client.delete(f"{base}/facts/f1").json()
        assert n("MATCH ()-[r:RELATES_TO]->() RETURN count(r)") == 0 and n("MATCH (e:Episodic) RETURN size(e.entity_edges)") == 0
        assert client.post(f"{base}/vocab/ops/{r['op']}/revert").status_code == 200
        assert n("MATCH (:Entity {uuid:'a'})-[r {uuid:'f1'}]->(:Entity {uuid:'b'}) RETURN r.fact") == "Vesta esta en Cloudco" and n("MATCH (e:Episodic) RETURN e.entity_edges") == ["f1"]
        assert n("MATCH ()-[r {uuid:'f1'}]->() RETURN r.fact_embedding IS NOT NULL") is True
    finally:
        g.delete()


def test_settings_admin(client):  # noqa: F811
    """Ajustes de la instancia: valor por defecto, cambio, validación, restaurar."""
    r = client.get("/api/settings"); assert r.status_code == 200
    item = {i["key"]: i for i in r.json()["items"]}["doc_passages"]
    assert item["value"] == item["default"] and not item["changed"]
    assert client.put("/api/settings/doc_passages", json={"value": 5}).json()["value"] == 5
    item = {i["key"]: i for i in client.get("/api/settings").json()["items"]}["doc_passages"]
    assert item["value"] == 5 and item["changed"]
    assert client.put("/api/settings/doc_passages", json={"value": 99}).status_code == 422
    assert client.put("/api/settings/public_url", json={"value": "ftp://x"}).status_code == 422
    assert client.put("/api/settings/nope", json={"value": 1}).status_code == 404
    assert client.delete("/api/settings/doc_passages").status_code == 200
    assert {i["key"]: i for i in client.get("/api/settings").json()["items"]}["doc_passages"]["changed"] is False


def test_settings_secret_is_sealed_and_never_returned(client):  # noqa: F811
    """El secreto se guarda cifrado y nunca vuelve en claro."""
    from mimirsynth import appsettings
    assert client.put("/api/settings/secret/smtp_password", json={"value": "s3cr3t"}).status_code == 200
    body = client.get("/api/settings").json()
    assert body["secrets"]["smtp_password"]["set"] is True and "s3cr3t" not in str(body)
    assert appsettings.get_secret("smtp_password") == "s3cr3t"
    from mimirsynth.models import AppSetting
    from mimirsynth.store import _factory
    with _factory()() as db:
        assert "s3cr3t" not in str(db.get(AppSetting, "smtp_password").value)
    assert client.put("/api/settings/secret/oidc_client_secret", json={"value": "x"}).status_code == 404  # ahora vive en cada proveedor
    client.delete("/api/settings/smtp_password")
