"""The graph database connection saved from Administration → Graph (#358): the environment wins and is read-only, a connection that does
not pass its test is never saved, the password never comes back, the saved one is only reused for the same server, the installer can
test with the first-start code, and saving switches the backend without a restart."""
import os
import socket

import pytest

from test_control import client  # noqa: F401  (fixture with the app and the test database)

from mimirsynth import graphconn as G
from mimirsynth.config import settings
from mimirsynth.graphdb import Connection, backend
from mimirsynth.models import GraphConnection
from mimirsynth.store import _factory

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
NEO4J = os.environ.get("MIMIRSYNTH_TEST_NEO4J")
needs_falkor = pytest.mark.skipif(not FALKOR or bool(NEO4J), reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


@pytest.fixture()
def no_env(monkeypatch):
    """As an installation whose .env says nothing about the graph: the connection comes from the database or is the bundled one."""
    monkeypatch.setattr(G, "env_defines", lambda: False)
    with _factory()() as db:
        db.query(GraphConnection).delete()
        db.commit()
    backend.cache_clear()
    yield
    with _factory()() as db:
        db.query(GraphConnection).delete()
        db.commit()
    backend.cache_clear()


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --- where it comes from --------------------------------------------------------------------------

def test_an_empty_variable_does_not_count_and_a_set_one_wins(monkeypatch):
    from mimirsynth.config import Settings
    for k in ("MIMIRSYNTH_GRAPH_BACKEND", "MIMIRSYNTH_FALKOR_HOST", "MIMIRSYNTH_NEO4J_URI"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MIMIRSYNTH_FALKOR_HOST", "")    # what compose passes for a variable that is not set
    monkeypatch.setenv("MIMIRSYNTH_FALKOR_PORT", "")
    s = Settings(_env_file=None)
    monkeypatch.setattr(G, "settings", s)
    assert s.falkor_port == 6379 and not G.env_defines() and G.env_connection() is None
    monkeypatch.setenv("MIMIRSYNTH_NEO4J_URI", "bolt+s://graph.example.com:7688")
    monkeypatch.setattr(G, "settings", Settings(_env_file=None))
    c = G.env_connection()
    assert (c.backend, c.host, c.port, c.tls, c.uri, c.user) == ("neo4j", "graph.example.com", 7688, True, "bolt+s://graph.example.com:7688", "neo4j")
    monkeypatch.setenv("MIMIRSYNTH_GRAPH_BACKEND", "falkordb")
    monkeypatch.setenv("MIMIRSYNTH_FALKOR_HOST", "")
    monkeypatch.setenv("MIMIRSYNTH_FALKOR_BUNDLED_HOST", "falkordb")
    monkeypatch.setattr(G, "settings", Settings(_env_file=None))
    assert G.env_connection().address() == "falkordb:6379"      # FalkorDB chosen without a host: the bundled one's
    monkeypatch.setenv("MIMIRSYNTH_GRAPH_BACKEND", "mongo")
    monkeypatch.setattr(G, "settings", Settings(_env_file=None))
    with pytest.raises(ValueError, match="falkordb"):
        G.env_connection()


def test_without_env_or_a_saved_one_it_is_the_bundled_falkordb(client, no_env, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "falkor_bundled_host", "falkordb")
    conn, source = G.current()
    assert source == "default" and conn.address() == "falkordb:6379"
    d = client.get("/api/admin/graph").json()
    assert d["source"] == "default" and d["editable"] and d["backend"] == "falkordb" and d["address"] == "falkordb:6379"
    assert d["bundled_host"] == "falkordb" and d["has_password"] is False


def test_the_environment_is_read_only(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(G, "env_defines", lambda: True)
    monkeypatch.setattr(G, "env_connection", lambda: Connection("neo4j", "n4j", 7687, "neo4j", "s3cret", uri="bolt://n4j:7687"))
    d = client.get("/api/admin/graph").json()
    assert d["source"] == "env" and not d["editable"] and d["address"] == "bolt://n4j:7687" and d["has_password"] is True
    assert "s3cret" not in str(d)
    r = client.put("/api/admin/graph", json={"backend": "falkordb", "host": "127.0.0.1", "port": _closed_port()})
    assert r.status_code == 409 and ".env" in r.json()["detail"]


# --- the test -----------------------------------------------------------------------------------

def test_each_failure_names_its_cause(client):  # noqa: F811
    port = _closed_port()
    r = client.post("/api/admin/graph/test", json={"backend": "falkordb", "host": "127.0.0.1", "port": port}).json()
    assert r["ok"] is False and r["error"]["code"] == "refused" and r["error"]["step"] == "reach"
    assert f"127.0.0.1:{port}" in r["error"]["message"] and r["steps"] == [{"step": "reach", "ok": False, "ms": r["steps"][0]["ms"]}]
    r = client.post("/api/admin/graph/test", json={"backend": "neo4j", "host": "no-such-host.invalid"}).json()
    assert r["error"]["code"] == "dns" and r["address"] == "bolt://no-such-host.invalid:7687"
    assert client.post("/api/admin/graph/test", json={"backend": "mongo", "host": "x"}).status_code == 422
    assert client.post("/api/admin/graph/test", json={"backend": "neo4j", "host": "bolt://x"}).status_code == 422   # a host, not a URI


def test_a_server_that_is_not_the_backend_says_so():
    """A port that answers something else: the right address, the wrong service (or TLS where it is not used)."""
    import threading
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]

    def answer():
        for _ in range(4):
            try:
                c, _ = srv.accept()
            except OSError:
                return
            c.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            c.close()
    threading.Thread(target=answer, daemon=True).start()
    try:
        r = G.probe(Connection("falkordb", "127.0.0.1", port), timeout=3)
        assert not r["ok"] and r["error"]["code"] in ("protocol", "other") and r["error"]["step"] == "auth"
        r = G.probe(Connection("falkordb", "127.0.0.1", port, tls=True), timeout=3)
        assert not r["ok"] and r["error"]["code"] == "tls" and r["error"]["step"] == "reach"
    finally:
        srv.close()


def test_the_saved_password_is_only_reused_for_the_same_server(client, no_env):  # noqa: F811
    from mimirsynth.secretbox import seal
    with _factory()() as db:
        db.add(GraphConnection(id=1, backend="neo4j", host="n4j.example.com", port=7687, username="neo4j", password_enc=seal("s3cret")))
        db.commit()
        same = G._connection(G.ConnIn(backend="neo4j", host="n4j.example.com", user="neo4j"), db)
        other = G._connection(G.ConnIn(backend="neo4j", host="evil.example.com", user="neo4j"), db)
        typed = G._connection(G.ConnIn(backend="neo4j", host="evil.example.com", user="neo4j", password="mine"), db)
    assert same.password == "s3cret" and other.password == "" and typed.password == "mine"
    d = client.get("/api/admin/graph").json()
    assert d["source"] == "db" and d["has_password"] is True and "s3cret" not in str(d) and "password" not in d


def test_a_failing_connection_is_never_saved(client, no_env):  # noqa: F811
    r = client.put("/api/admin/graph", json={"backend": "falkordb", "host": "127.0.0.1", "port": _closed_port()})
    assert r.status_code == 422 and "no se guarda" in r.json()["detail"]
    with _factory()() as db:
        assert db.get(GraphConnection, 1) is None
    assert client.get("/api/admin/graph").json()["source"] == "default"


def test_the_installer_tests_with_the_first_start_code_while_there_is_no_admin(monkeypatch):
    from fastapi.testclient import TestClient
    from mimirsynth import auth, ratelimit
    from mimirsynth.main import app
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(ratelimit, "allow", lambda *a, **k: True)
    monkeypatch.setattr(auth, "_SETUP_TOKEN", "the-code")
    body = {"backend": "falkordb", "host": "127.0.0.1", "port": _closed_port()}
    with TestClient(app) as c:
        monkeypatch.setattr(auth, "setup_required", lambda db: True)
        monkeypatch.setattr(auth, "_SETUP_TOKEN", "the-code")  # the start of the app drew a new one
        assert c.post("/api/admin/graph/test", json=body).status_code == 401                               # no session, no code
        assert c.post("/api/admin/graph/test", json=body, headers={"X-Setup-Code": "wrong"}).status_code == 403
        r = c.post("/api/admin/graph/test", json=body, headers={"X-Setup-Code": "the-code"})
        assert r.status_code == 200 and r.json()["error"]["code"] == "refused"
        assert c.put("/api/admin/graph", json=body, headers={"X-Setup-Code": "the-code"}).status_code == 401  # saving needs an admin
        monkeypatch.setattr(auth, "setup_required", lambda db: False)
        assert c.post("/api/admin/graph/test", json=body, headers={"X-Setup-Code": "the-code"}).status_code == 401  # once there is one


def test_health_and_ai_status_say_which_backend(client):  # noqa: F811
    assert client.get("/api/health").json()["backend"] in ("falkordb", "neo4j")
    g = client.get("/api/ai-status").json()["graph"]
    assert g["configured"] and g["backend"] in ("falkordb", "neo4j") and g["source"] in ("env", "db", "default") and "address" in g


# --- with a real FalkorDB -----------------------------------------------------------------------

@needs_falkor
def test_a_real_falkordb_passes_lists_its_graphs_and_leaves_nothing_behind(client, monkeypatch):  # noqa: F811
    from falkordb import FalkorDB
    c = FalkorDB(host=FALKOR, port=6379)
    for g in ("zz_conn_a", "zz_conn_b"):
        if g in c.list_graphs():
            c.select_graph(g).delete()
    c.select_graph("zz_conn_a").query("CREATE (:Entity {name:'a'})-[:R]->(:Entity {name:'b'})")
    client.post("/api/brains", json={"slug": "zz-conn", "name": "Conn", "graph_name": "zz_conn_a"})
    try:
        r = client.post("/api/admin/graph/test", json={"backend": "falkordb", "host": FALKOR}).json()
        assert r["ok"], r
        assert [s["step"] for s in r["steps"]] == ["reach", "auth", "version", "write", "list"] and all(s["ok"] for s in r["steps"])
        assert r["server"]["server"] == "FalkorDB" and r["server"]["version"]
        a = next(g for g in r["graphs"] if g["name"] == "zz_conn_a")
        assert a == {"name": "zz_conn_a", "nodes": 2, "brain": "zz-conn"}
        assert not any(g.startswith(G.PROBE_PREFIX) for g in c.list_graphs())          # the probe graph is gone
        assert not any(g["name"].startswith("_") for g in r["graphs"])
        bad = client.post("/api/admin/graph/test", json={"backend": "falkordb", "host": FALKOR, "user": "nobody", "password": "x"}).json()
        assert bad["error"]["code"] == "auth" and bad["error"]["step"] == "auth"
    finally:
        client.post("/api/brains/zz-conn/delete", json={"confirm": "zz-conn", "delete_graph": True})
        for g in ("zz_conn_a", "zz_conn_b"):
            if g in c.list_graphs():
                c.select_graph(g).delete()


@pytest.mark.skipif(not NEO4J, reason="necesita un Neo4j desechable (MIMIRSYNTH_TEST_NEO4J=bolt://host:7687)")
def test_a_real_neo4j_passes_and_lists_its_group_ids(client):  # noqa: F811
    from neo4j import GraphDatabase
    b = backend()
    b.graph("zz_conn_n").query("CREATE (:Entity {name: 'a'})-[:R]->(:Entity {name: 'b'})")   # scoped: both get the group_id
    try:
        r = client.post("/api/admin/graph/test").json()                                       # no body: the connection in force
        assert r["ok"], r
        assert r["server"]["server"] == "Neo4j" and r["server"]["database"] and r["address"] == settings.neo4j_uri
        assert {"name": "zz_conn_n", "nodes": 2, "brain": None} in r["graphs"]
        with GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user or "neo4j", settings.neo4j_password)) as d:
            assert d.execute_query("MATCH (n:MimirSynthProbe) RETURN count(n) AS c").records[0]["c"] == 0
        host, port, _ = G._split_uri(settings.neo4j_uri)
        bad = client.post("/api/admin/graph/test", json={"backend": "neo4j", "host": host, "port": port, "password": "not-it"}).json()
        assert bad["error"]["code"] == "auth"
    finally:
        b.delete_graph("zz_conn_n")


@needs_falkor
def test_saving_switches_the_backend_without_a_restart(client, no_env, monkeypatch):  # noqa: F811
    from mimirsynth import graphdb
    monkeypatch.setattr(settings, "falkor_bundled_host", "127.0.0.1")
    monkeypatch.setattr(graphdb, "CLOSE_AFTER", 0.01)
    before = backend()
    assert before.host == "127.0.0.1"
    r = client.put("/api/admin/graph", json={"backend": "falkordb", "host": FALKOR, "port": 6379})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"] == "db" and d["address"] == f"{FALKOR}:6379" and d["test"]["ok"] and d["changed"] == (FALKOR != "127.0.0.1")
    after = backend()
    assert after is not before and after.host == FALKOR                                 # the next call uses the new connection
    assert client.get("/api/health").json()["graph"] is True
    from sqlalchemy import select
    from mimirsynth.models import Audit
    with _factory()() as db:
        a = db.scalars(select(Audit).where(Audit.action == "graph.connection").order_by(Audit.id.desc())).first()
        assert a.detail["address"] == f"{FALKOR}:6379" and "password" not in str(a.detail)
