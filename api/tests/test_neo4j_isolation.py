"""Brain isolation in the read-only Cypher console (#389). On Neo4j every brain shares one database, and only the scoping of the
Cypher (`graphdb/neo4j.py`) keeps a reader of one brain out of the others. Two brains with known data, and a battery of console
queries from a reader of brain A, the bypasses found in the review among them: none may return a value of brain B, as a node or as a
scalar. The ones the console cannot scope are refused, and the battery first proves on the real database that each of them is valid
Cypher that, run as written, reaches brain B.

It runs against the backend the suite is on (MIMIRSYNTH_TEST_FALKOR or MIMIRSYNTH_TEST_NEO4J); on FalkorDB a brain is a graph of its
own, so only «nothing of B comes back» is checked there."""
import json
import os

import pytest

from test_attention import _tok
from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
NEO4J = bool(os.environ.get("MIMIRSYNTH_TEST_NEO4J"))
A, B = "zz-iso-a", "zz-iso-b"
BS, Q = "\\", "'"
pytestmark = pytest.mark.skipif(not FALKOR, reason="necesita un grafo desechable (MIMIRSYNTH_TEST_FALKOR o MIMIRSYNTH_TEST_NEO4J)")

# What the console runs and scopes: every row comes from brain A.
SCOPED = [
    "MATCH (n) RETURN n.name",
    "MATCH (n) RETURN n",
    "MATCH (n:Entity) RETURN n.name, n.summary, labels(n), properties(n)",
    "MATCH ()-[r]->() RETURN r.fact",
    "MATCH (a)-[r:RELATES_TO]->(b) RETURN a, r, b",
    "MATCH (a)-[r]->(b) RETURN startNode(r).name, endNode(r).name, properties(b)",
    "MATCH (n:Entity {uuid:'a1'}) RETURN n.name",                          # a uuid both brains have
    "MATCH (n) WHERE elementId(n) IS NOT NULL RETURN elementId(n), n.name",
    "MATCH (n) WHERE id(n) >= 0 RETURN n.name",
    "MATCH (n:Entity), (m) RETURN m.name",
    "MATCH (n:Entity) WITH n MATCH (m) RETURN m.name",
    "MATCH (n:Entity) OPTIONAL MATCH (m) RETURN m.name",
    "UNWIND [1] AS x MATCH (m) RETURN m.name",
    "MATCH (n:Entity) RETURN n.name AS x UNION MATCH (m) RETURN m.name AS x",
    "MATCH (n:Entity) RETURN n.name AS x UNION ALL MATCH (m) RETURN m.name AS x",
    "MATCH (n) WHERE n.name = 'x' OR true RETURN n.name",
    "MATCH ( n ) RETURN n.name",
    "MATCH(n)RETURN n.name",
    "MATCH\t(n)\nRETURN n.name",
    "MATCH (n:Entity) RETURN n {.name, .summary} AS m",
    "MATCH (n:Entity) RETURN CASE WHEN n.name = 'alpha' THEN n.summary ELSE n.name END",
    "MATCH (a:Entity) RETURN [(a)-->(b) | b.name]",
    "MATCH (a:Entity) RETURN [p = (a)-->(b) | [x IN nodes(p) | x.name]]",
    "MATCH (n:Entity) WHERE n.name =~ 'al.*' AND NOT (n)-->() RETURN n.name",
    "MATCH (n) RETURN collect(n.name), count(*), count(DISTINCT n.name)",
    "MATCH (e:Episodic) RETURN e.content",
    # bypasses of `scope()` before #389, scoped now
    "MATCH p=(n) RETURN n.name",
    "MATCH p = (n:Entity) RETURN [x IN nodes(p) | x.name]",
    "MATCH (n WHERE true) RETURN n.name",
    "MATCH (n:Entity WHERE n.name IS NOT NULL) RETURN n.name",
    "MATCH (n:Entity {uuid:'b1'} WHERE n.name IS NOT NULL) RETURN n.name",
    "MATCH ANY (n) RETURN n.name",
    "MATCH p = ANY (n) RETURN n.name",
    "MATCH SHORTEST 1 (n) RETURN n.name",
    "MATCH ALL SHORTEST (a:Entity)-->(b) RETURN b.name",
    "RETURN COUNT { (a), (b) } AS pairs",
    "RETURN COLLECT { MATCH (m) RETURN m.name } AS x",
    "RETURN [x IN [1] | COLLECT { MATCH (m) RETURN m.name }] AS x",
    "RETURN {a: COLLECT { MATCH (m) RETURN m.name }} AS x",
    "RETURN CASE WHEN true THEN COUNT { (m) } END AS x",
    "MATCH (n:Entity {name: head(COLLECT { MATCH (m) WHERE m.uuid = 'b1' RETURN m.name })}) RETURN n.name",
    "MATCH (n:Entity {name: [(x)-->(y) | y.name][0]}) RETURN n.name",
    "MATCH (n:Entity {name: CASE WHEN EXISTS { (x {uuid:'b1'}) } THEN 'alpha' ELSE 'zz' END}) RETURN n.name",   # an oracle on B
]

# What the console refuses on Neo4j: each one is valid Cypher that reaches brain B when it is run as written (proved below).
REFUSED = [
    ("MATCH (n:%) RETURN n.name", "pattern"),
    ("MATCH (n IS Entity) RETURN n.name", "pattern"),
    ("MATCH (n:(Entity|Episodic)) RETURN n.name", "pattern"),
    ("MATCH (n:$(['Entity'])) RETURN n.name", "param"),
    ("MATCH (n:$any(['Entity'])) RETURN n.name", "param"),
    ("MATCH (n /* c */ :Entity) RETURN n.name", "comment"),
    ("MATCH (n:Entity) RETURN n.name AS x // c\rUNION MATCH (m) RETURN m.name AS x", "comment"),
    ("MATCH (n:Entity) RETURN n.name AS x // c\x0bUNION MATCH (m) RETURN m.name AS x", "comment"),
    ("MATCH (n:Entity) RETURN n.name AS x // c\x0cUNION MATCH (m) RETURN m.name AS x", "comment"),
    (f"RETURN {Q}a{BS}u0027 AS x UNION MATCH (m) RETURN m.name AS x //{Q}", "char"),   # Neo4j decodes ' before it reads
    (f"MATCH (n:{BS}u0045ntity) RETURN n.name", "char"),
    ("MATCH (n:Entity) RETURN n.name", "char"),
    ("MATCH (a:Entity {uuid:'a2'})-[*1..3]-(z) RETURN z.name", "varlength"),
    ("MATCH (a:Entity {uuid:'a2'})-->+(z) RETURN z.name", "varlength"),
    ("MATCH (a:Entity {uuid:'a2'})-->{1,2}(z) RETURN z.name", "varlength"),
    ("MATCH (a:Entity {uuid:'a2'}) ((x)-->(y)){1,2} (z) RETURN z.name", "varlength"),
    ("MATCH p = shortestPath((a:Entity {uuid:'a2'})-[*]-(b {uuid:'b2'})) RETURN [x IN nodes(p) | x.name]", "varlength"),
    ("MATCH (a:Entity {uuid:'a2'}) RETURN [(a)-[*1..2]->(b) | b.name]", "varlength"),
    ("CALL db.index.fulltext.listAvailableAnalyzers() YIELD analyzer RETURN analyzer", "call"),
    ("SHOW TRANSACTIONS", "call"),
    ("TERMINATE TRANSACTIONS 'neo4j-transaction-1'", "call"),
    ("MATCH (n) WHERE n.group_id = $mimirsynth_partition RETURN n.name", "param"),
    ("RETURN apoc.cypher.runFirstColumnSingle('MATCH (m) RETURN collect(m.name)', {}) AS x", "function"),
    ("RETURN apoc . cypher . runFirstColumnMany('MATCH (m) RETURN m.name', {}) AS x", "function"),
    ("RETURN `apoc`.cypher.runFirstColumnSingle('MATCH (m) RETURN collect(m.name)', {}) AS x", "function"),
    ("RETURN db.nameFromElementId('x') AS x", "function"),
    ("MATCH (n:Entity) USING INDEX n:Entity(uuid) RETURN n.name", "function"),
]
# Refused vectors whose raw run needs a plugin or another database, or cannot read data: not proved against the database.
_NOT_PROVED = {"call", "function"}


def _rows(r) -> str:
    """What a console answer carries of the graph: rows, nodes and edges (not the error, which may quote the query)."""
    body = r.json()
    return json.dumps([body["rows"], body["nodes"], body["edges"]])


@pytest.fixture()
def brains(client, monkeypatch):  # noqa: F811
    """Brains A and B with the same shape and a uuid in common; B's values all say SECRET, and B has more nodes than A. On Neo4j a
    relationship also crosses from A to B, as nothing the app writes does: the defence in depth for what traverses."""
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    if not NEO4J:
        monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.backend.cache_clear()
    b = dbm.backend()
    for g in (A, B):
        if b.exists(g):
            b.delete_graph(g)
    b.graph(A).query("CREATE (:Entity {uuid:'a1', name:'alpha', summary:'mine'})-[:RELATES_TO {uuid:'fa', name:'KNOWS', fact:'alpha knows'}]->"
                     "(:Entity {uuid:'a2', name:'alpha2'}), (:Episodic {uuid:'ea', name:'ep-a', content:'told alpha'})")
    b.graph(B).query("CREATE (:Entity {uuid:'b1', name:'SECRET-b1', summary:'SECRET-sum'})-[:RELATES_TO {uuid:'fb', name:'KNOWS', "
                     "fact:'SECRET-fact'}]->(:Entity {uuid:'b2', name:'SECRET-b2'}), (:Episodic {uuid:'eb', name:'SECRET-ep', "
                     "content:'SECRET-content'}), (:Entity {uuid:'a1', name:'SECRET-twin'})")
    b.graph(B).query("UNWIND range(1, 5) AS i CREATE (:Entity {uuid:'bx' + toString(i), name:'SECRET-' + toString(i)})")
    if NEO4J:
        b._run("MATCH (a {group_id:$a, uuid:'a2'}), (x {group_id:$b, uuid:'b1'}) CREATE (a)-[:RELATES_TO {uuid:'bridge'}]->(x)", {"a": A, "b": B})
    for slug, g in (("zz-iso-a", A), ("zz-iso-b", B)):
        assert client.post("/api/brains", json={"slug": slug, "name": slug, "graph_name": g}).status_code in (201, 409)  # 409: an earlier test
    yield b, _tok(client, "zz-iso-a", "reader")
    for g in (A, B):
        if b.exists(g):
            b.delete_graph(g)
    dbm.backend.cache_clear()


def _console(client, headers, q):  # noqa: F811
    return client.post("/api/brains/zz-iso-a/query", json={"query": q}, headers=headers)


def test_a_reader_of_one_brain_gets_nothing_of_another(client, brains):  # noqa: F811
    _, reader = brains
    for q in SCOPED + [q for q, _ in REFUSED]:
        r = _console(client, reader, q)
        assert r.status_code in (200, 400), (q, r.text)
        if r.status_code == 200:
            assert "SECRET" not in _rows(r), q
        if NEO4J:
            assert (r.status_code == 200) == (q in SCOPED), (q, r.text)


@pytest.mark.skipif(not NEO4J, reason="the shared database is Neo4j's")
def test_each_refused_query_reaches_the_other_brain_when_run_as_written(brains):
    """The refused queries are not refused for being invalid: on this Neo4j, run without the console, each reads brain B."""
    backend, _ = brains
    for q, code in REFUSED:
        if code in _NOT_PROVED:
            continue
        rows = backend._run(q.replace("$mimirsynth_partition", "'zz-iso-b'"), read=True)
        assert "SECRET" in json.dumps([dict(r) for r in rows], default=str), q


@pytest.mark.skipif(not NEO4J, reason="the shared database is Neo4j's")
def test_the_console_says_why_it_refuses_and_scalars_count_one_brain(client, brains):  # noqa: F811
    from mimirsynth.graphdb.neo4j import Unscopable, check_console
    _, reader = brains
    for q, code in REFUSED:
        with pytest.raises(Unscopable) as e:
            check_console(q)
        assert e.value.code == code, q
    assert "comentarios" in _console(client, reader, "MATCH (n) // x\nRETURN n").json()["detail"]
    assert "APOC" in _console(client, reader, "RETURN apoc.version()").json()["detail"]
    counts = _console(client, reader, "MATCH (n) RETURN count(n) AS n, COUNT { (a), (b) } AS pairs").json()["rows"]
    assert counts == [[3, 9]]                                     # A's three nodes, not B's ten
    hops = _console(client, reader, "MATCH (:Entity {uuid:'a2'})-->(x) RETURN x.name").json()["rows"]
    assert hops == []                                             # the relationship that crosses into B ends outside the brain
    oracle = _console(client, reader, "MATCH (n:Entity {name: CASE WHEN EXISTS { (x {uuid:'b1'}) } THEN 'alpha' ELSE 'zz' END}) "
                                      "RETURN n.name").json()["rows"]
    assert oracle == []                                           # B's b1 does not exist for a query of A
