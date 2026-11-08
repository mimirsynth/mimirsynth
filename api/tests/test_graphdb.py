"""The graph backend (#357): the modules reach the graph only through it, its Cypher dialect, and FalkorDB's implementation."""
import os
import pathlib
import re

import pytest

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
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
