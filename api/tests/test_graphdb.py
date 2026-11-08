"""The graph backend (#357): the modules reach the graph only through it, its Cypher dialect, and the FalkorDB and Neo4j
implementations. The partition tests run against the backend the suite is on (MIMIRSYNTH_TEST_FALKOR, or MIMIRSYNTH_TEST_NEO4J)."""
import os
import pathlib
import re

import pytest

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
NEO4J = os.environ.get("MIMIRSYNTH_TEST_NEO4J")
needs_falkor = pytest.mark.skipif(not FALKOR or bool(NEO4J), reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
needs_neo4j = pytest.mark.skipif(not NEO4J, reason="necesita un Neo4j desechable (MIMIRSYNTH_TEST_NEO4J=bolt://host:7687)")
GRAPH = "zz-test-graphdb"
PKG = pathlib.Path(__file__).resolve().parents[1] / "mimirsynth"


def test_no_module_talks_to_a_driver_of_its_own():
    """Only `graphdb/` imports the graph drivers or writes the Cypher that only one database understands."""
    driver = re.compile(r"^\s*(from|import) (falkordb|neo4j)\b|graphiti_core\.driver\.\w+_driver", re.M)
    dialect = re.compile(r"\bvecf32\(|vec\.cosineDistance|\.select_graph\(|\.connection\.")
    offenders = []
    for p in PKG.rglob("*.py"):
        if "graphdb" in p.parts:
            continue
        code = "\n".join(line for line in p.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))
        if driver.search(code) or dialect.search(code):
            offenders.append(p.name)
    assert offenders == []


def test_falkor_dialect_and_values():
    from falkordb.edge import Edge as FEdge
    from falkordb.node import Node as FNode
    from falkordb.path import Path as FPath

    from mimirsynth.graphdb import Edge, Node, Path
    from mimirsynth.graphdb.falkor import FalkorBackend
    b = FalkorBackend("localhost", 6379)
    assert b.vector("$v") == "vecf32($v)"
    assert b.cosine("r.fact_embedding", "vecf32($v)") == "(2 - vec.cosineDistance(r.fact_embedding, vecf32($v)))/2"
    a, c = FNode(node_id=1, labels=["Entity"], properties={"name": "a"}), FNode(node_id=2, labels=["Entity"], properties={"name": "c"})
    e = FEdge(1, "RELATES_TO", 2, edge_id=7, properties={"fact": "a c"})
    assert b.value(a) == Node("1", ["Entity"], {"name": "a"})
    assert b.value(e) == Edge("7", "RELATES_TO", "1", "2", {"fact": "a c"})
    p = b.value(FPath([a, c], [e]))
    assert isinstance(p, Path) and [n.id for n in p.nodes] == ["1", "2"] and [x.id for x in p.edges] == ["7"]
    assert b.value(3) == 3 and b.value("x") == "x"


@pytest.fixture()
def backend(monkeypatch):
    from mimirsynth import graphdb
    from mimirsynth.config import settings
    if not NEO4J:
        monkeypatch.setattr(settings, "falkor_host", FALKOR)
    graphdb.backend.cache_clear()
    b = graphdb.backend()
    for g in (GRAPH, f"_{GRAPH}_copy"):
        if b.exists(g):
            b.delete_graph(g)
    yield b
    for g in (GRAPH, f"_{GRAPH}_copy"):
        if b.exists(g):
            b.delete_graph(g)
    graphdb.backend.cache_clear()


@needs_falkor
def test_falkor_partitions_copy_delete_and_dump(backend):
    from mimirsynth import db
    g = backend.graph(GRAPH)
    g.query(f"CREATE (:Entity {{uuid:'a', name:'wiki', name_embedding: {db.vector('$v')}}})", {"v": [1.0, 0.0]})
    assert backend.exists(GRAPH) and GRAPH in db.list_graphs()
    backend.copy_graph(GRAPH, f"_{GRAPH}_copy")
    assert f"_{GRAPH}_copy" in backend.list_graphs() and f"_{GRAPH}_copy" not in db.list_graphs()   # hidden: a snapshot
    score = db.rows(g.ro_query(f"MATCH (n:Entity) RETURN {db.cosine('n.name_embedding', db.vector('$v'))} AS s", {"v": [1.0, 0.0]}))
    assert score[0]["s"] == pytest.approx(1.0)
    assert backend.can_dump()
    payload = backend.dump(GRAPH)
    backend.delete_graph(GRAPH)
    backend.restore(GRAPH, payload)  # under its own name, as the import does: a FalkorDB dump carries it
    assert backend.graph(GRAPH).query("MATCH (n:Entity {uuid:'a'}) RETURN n.name").result_set == [["wiki"]]
    backend.delete_graph(f"_{GRAPH}_copy")
    assert not backend.exists(f"_{GRAPH}_copy")
    assert backend.version().get("graph_module")
    used, limit = backend.memory()
    assert used > 0 and limit > 0


def test_the_setting_picks_the_backend(monkeypatch):
    from mimirsynth import graphdb
    from mimirsynth.config import settings
    from mimirsynth.graphdb.falkor import FalkorBackend
    from mimirsynth.graphdb.neo4j import Neo4jBackend
    try:
        for kind, cls in (("falkordb", FalkorBackend), ("neo4j", Neo4jBackend), (" Neo4j ", Neo4jBackend)):
            monkeypatch.setattr(settings, "graph_backend", kind)
            monkeypatch.setattr(settings, "neo4j_uri", "bolt://localhost:7687")
            graphdb.backend.cache_clear()
            assert isinstance(graphdb.backend(), cls)   # nothing connects until the first query
        monkeypatch.setattr(settings, "graph_backend", "memgraph")
        graphdb.backend.cache_clear()
        with pytest.raises(ValueError, match="falkordb"):
            graphdb.backend()
        monkeypatch.setattr(settings, "graph_backend", "neo4j")
        monkeypatch.setattr(settings, "neo4j_uri", "")
        graphdb.backend.cache_clear()
        with pytest.raises(ValueError, match="MIMIRSYNTH_NEO4J_URI"):
            graphdb.backend()
    finally:
        graphdb.backend.cache_clear()


def test_neo4j_dialect_and_values():
    from datetime import datetime, timezone

    from neo4j.time import DateTime

    from mimirsynth.graphdb.neo4j import Neo4jBackend, _out, _param
    b = Neo4jBackend("bolt://localhost:7687", "neo4j", "x")
    assert b.vector("$v") == "$v" and b.cosine("a", "b") == "vector.similarity.cosine(a, b)"
    assert not b.can_dump() and b.memory() is None and b.shared_database
    d = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
    assert _param("2026-01-02T03:04:05.123456+00:00") == d and _param("2026-01-02T03:04:05Z") == d.replace(microsecond=0)
    assert _param({"rows": [{"t": "2026-01-02T03:04:05Z", "n": "wiki"}]}) == {"rows": [{"t": d.replace(microsecond=0), "n": "wiki"}]}
    assert _param("2026-01-02T03:04:05") == d.replace(microsecond=0)              # without a zone: UTC, as Graphiti writes them
    assert _param("2026-01-02") == "2026-01-02" and _param("wiki") == "wiki"      # a date alone is not a datetime
    assert _out(DateTime.from_native(d)) == "2026-01-02T03:04:05.123456+00:00"    # as FalkorDB keeps Graphiti's dates


P = "{group_id: $mimirsynth_partition}"


@pytest.mark.parametrize("q, want", [
    ("MATCH (n:Entity) RETURN count(n)", f"MATCH (n:Entity {P}) RETURN count(n)"),
    ("MATCH ()-[r:RELATES_TO {uuid:$u}]->() DELETE r", f"MATCH ({P})-[r:RELATES_TO {{uuid:$u}}]->({P}) DELETE r"),
    ("MATCH (n:Entity:`Person x`) RETURN n", f"MATCH (n:Entity:`Person x` {P}) RETURN n"),
    ("MATCH (a {uuid:'x', group_id:'other'}) RETURN a",                       # a group_id of the query's own does not win
     "MATCH (a {uuid:'x', group_id:'other', group_id: $mimirsynth_partition}) RETURN a"),
    ("MATCH (a)<-[:MENTIONS]-(e:Episodic) WHERE e.name = '(x)' RETURN a",
     f"MATCH (a {P})<-[:MENTIONS]-(e:Episodic {P}) WHERE e.name = '(x)' RETURN a"),
    ("MATCH (a:Entity), (b:Entity) WHERE a.uuid = $a RETURN a, b", f"MATCH (a:Entity {P}), (b:Entity {P}) WHERE a.uuid = $a RETURN a, b"),
    ("MATCH (n) WHERE EXISTS { (n)-->(m) } RETURN n", f"MATCH (n {P}) WHERE EXISTS {{ (n {P})-->(m {P}) }} RETURN n"),
    ("RETURN COUNT { (n) } AS c", f"RETURN COUNT {{ (n {P}) }} AS c"),
    ("MERGE (n:Entity {uuid:$u}) ON CREATE SET n.c = 1", "MERGE (n:Entity {uuid:$u, group_id: $mimirsynth_partition}) ON CREATE SET n.c = 1"),
    # what a query creates: new nodes get the partition, the ones it already holds are left as they are
    ("CREATE (:Entity {uuid:'a'})", "CREATE (:Entity {uuid:'a', group_id: $mimirsynth_partition})"),
    ("MATCH (a:Entity), (b:Entity) CREATE (a)-[:R]->(b)", f"MATCH (a:Entity {P}), (b:Entity {P}) CREATE (a)-[:R]->(b)"),
    ("UNWIND $rows AS r CREATE (n:Entity) SET n += r.p", f"UNWIND $rows AS r CREATE (n:Entity {P}) SET n += r.p"),
    # what is not a node pattern stays: calls, expressions, strings, comments
    ("MATCH (n:Entity) RETURN count(n), (2 - n.x) AS y, toLower('(a)-->(b)') // (c)-->(d)",
     f"MATCH (n:Entity {P}) RETURN count(n), (2 - n.x) AS y, toLower('(a)-->(b)') // (c)-->(d)"),
])
def test_neo4j_scopes_the_cypher_to_the_brain(q, want):
    from mimirsynth.graphdb.neo4j import scope
    assert scope(q) == want


@pytest.mark.skipif(not FALKOR, reason="necesita un grafo desechable (MIMIRSYNTH_TEST_FALKOR o MIMIRSYNTH_TEST_NEO4J)")
def test_brains_do_not_see_each_other(backend):
    """Two brains with the same uuids: each query sees its own, and deleting in one leaves the other."""
    from mimirsynth import db
    other = f"{GRAPH}-other"
    try:
        for name, n in ((GRAPH, "a"), (other, "b")):
            backend.graph(name).query("CREATE (x:Entity {uuid:'u1', name:$n})-[:RELATES_TO {uuid:'f1', fact:$n}]->(:Entity {uuid:'u2'})", {"n": n})
        for name, n in ((GRAPH, "a"), (other, "b")):
            g = backend.graph(name)
            assert db.rows(g.ro_query("MATCH (x:Entity {uuid:'u1'}) RETURN x.name AS n")) == [{"n": n}]
            assert db.rows(g.ro_query("MATCH ()-[r:RELATES_TO]->() RETURN r.fact AS f")) == [{"f": n}]
            assert g.ro_query("MATCH (x) RETURN count(x)").result_set == [[2]]
        backend.graph(other).query("MATCH (x:Entity {uuid:'u1'}) DETACH DELETE x")
        assert backend.graph(GRAPH).ro_query("MATCH (x:Entity {uuid:'u1'}) RETURN count(x)").result_set == [[1]]
    finally:
        if backend.exists(other):
            backend.delete_graph(other)


@needs_neo4j
def test_neo4j_partitions_copy_delete_and_dates(backend):
    from mimirsynth import db
    g = backend.graph(GRAPH)
    g.query(f"CREATE (:Entity {{uuid:'a', name:'wiki', created_at:$t, name_embedding: {db.vector('$v')}}})-[:RELATES_TO {{uuid:'f', group_id:$g}}]->"
            "(:Entity {uuid:'b', name:'polaris'})", {"v": [1.0, 0.0], "t": "2026-01-02T03:04:05+00:00", "g": GRAPH})
    assert backend.exists(GRAPH) and GRAPH in db.list_graphs()
    assert db.rows(g.ro_query("MATCH (n:Entity {uuid:'a'}) WHERE n.created_at >= $s RETURN n.created_at AS t",
                              {"s": "2026-01-01T00:00:00+00:00"})) == [{"t": "2026-01-02T03:04:05+00:00"}]
    backend.copy_graph(GRAPH, f"_{GRAPH}_copy")
    assert f"_{GRAPH}_copy" in backend.list_graphs() and f"_{GRAPH}_copy" not in db.list_graphs()
    copy = backend.graph(f"_{GRAPH}_copy")
    assert db.rows(copy.ro_query("MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) RETURN a.name AS a, r.group_id AS g, b.name AS b, labels(a) AS l")) \
        == [{"a": "wiki", "g": f"_{GRAPH}_copy", "b": "polaris", "l": ["Entity"]}]
    with pytest.raises(ValueError):
        backend.copy_graph(GRAPH, f"_{GRAPH}_copy")
    score = db.rows(g.ro_query(f"MATCH (n:Entity {{uuid:'a'}}) RETURN {db.cosine('n.name_embedding', db.vector('$v'))} AS s", {"v": [1.0, 0.0]}))
    assert score[0]["s"] == pytest.approx(1.0)
    backend.delete_graph(f"_{GRAPH}_copy")
    assert not backend.exists(f"_{GRAPH}_copy") and backend.exists(GRAPH)
    assert backend.version().get("edition") in ("community", "enterprise")


@needs_neo4j
def test_neo4j_refuses_a_value_of_another_brain(backend):
    """What scoping cannot see (a procedure's results) does not come back as another brain's node."""
    other = f"{GRAPH}-other"
    try:
        backend.graph(other).query("CREATE (:Entity {uuid:'secret', name:'theirs'})")
        backend._run("CREATE FULLTEXT INDEX zz_test_graphdb IF NOT EXISTS FOR (n:Entity) ON EACH [n.name]")
        backend._run("CALL db.awaitIndexes(60)")
        with pytest.raises(PermissionError):
            backend.graph(GRAPH).ro_query("CALL db.index.fulltext.queryNodes('zz_test_graphdb', 'theirs') YIELD node RETURN node")
    finally:
        backend._run("DROP INDEX zz_test_graphdb IF EXISTS")
        backend.delete_graph(other)
