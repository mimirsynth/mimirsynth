"""Import of a brain from a package (#136): both ways in (dump and JSON), structure only, tampered packages rejected before writing
anything, encryption, and nothing left behind by a failure or a restart."""
import hashlib
import io
import json
import os
import tarfile

import pytest

from test_brain_export import GRAPH, TOKEN, _seed, falkor  # noqa: F401
from test_control import client  # noqa: F401

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
needs_falkor = pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")


@pytest.fixture()
def fake_embedder(monkeypatch):
    from mimirsynth import embed
    dim = embed.resolve_embedding()["dim"]
    monkeypatch.setattr(embed, "get_embedder", lambda: type("E", (), {"embed": lambda self, t: [[0.5] * dim for _ in t]})())
    return dim


@pytest.fixture()
def graphs():
    """The graphs the tests import into, removed before and after."""
    from mimirsynth.db import client as fc
    names = [f"imp{i}" for i in range(1, 10)]

    def clean():
        for g in names:
            if FALKOR and g in fc().list_graphs():
                fc().select_graph(g).delete()
    clean()
    yield names
    clean()


def _export(client, slug: str, **body) -> bytes:  # noqa: F811
    jid = client.post(f"/api/brains/{slug}/exports", json=body).json()["id"]
    r = client.get(f"/api/brains/{slug}/exports/{jid}/download")
    assert r.status_code == 200
    return r.content


def _upload(client, data: bytes, name: str = "brain.mimirsynth.tar.gz") -> dict:  # noqa: F811
    r = client.post("/api/brain-imports/uploads", json={"filename": name, "size": len(data)})
    assert r.status_code == 201, r.text
    uid, step = r.json()["upload_id"], max(len(data) // 3, 1)
    for i, off in enumerate(range(0, len(data), step)):
        assert client.put(f"/api/brain-imports/uploads/{uid}/parts/{i}", content=data[off:off + step]).status_code == 200
    r = client.post(f"/api/brain-imports/uploads/{uid}/complete")
    assert r.status_code == 200, r.text
    return r.json()


def _import(client, uid: str, slug: str, **body) -> dict:  # noqa: F811
    r = client.post("/api/brain-imports", json={"upload_id": uid, "slug": slug, "name": slug.upper(), **body})
    assert r.status_code == 202, r.text
    return next(i for i in client.get("/api/brain-imports").json()["items"] if i["id"] == r.json()["id"])


def _files(data: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers() if m.isfile()}


def _repack(files: dict[str, bytes], manifest=None, links: tuple = ()) -> bytes:
    """A package with these files and a manifest that lists them (or `manifest`, as given)."""
    man = json.loads(files["manifest.json"])
    man["files"] = [{"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()} for p, b in files.items() if p != "manifest.json"]
    man = manifest(man) if manifest else man
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for p, b in [("manifest.json", json.dumps(man).encode())] + [(p, b) for p, b in files.items() if p != "manifest.json"]:
            info = tarfile.TarInfo(p)
            info.size = len(b)
            t.addfile(info, io.BytesIO(b))
        for name, target in links:
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, target
            t.addfile(info)
    return buf.getvalue()


def _left(slug: str, graph: str | None = None) -> list[str]:
    """What an import that failed should not have left behind."""
    from mimirsynth.db import client as fc
    from mimirsynth.models import Brain
    from mimirsynth.store import _factory
    with _factory()() as db:
        out = ["brain"] if db.query(Brain).filter(Brain.slug == slug).count() else []
    return out + (["graph"] if (graph or slug) in fc().list_graphs() else [])


@needs_falkor
def test_import_through_json_with_another_name(client, falkor, graphs, fake_embedder):  # noqa: F811
    """The original graph is still here, so its dump cannot be restored under its own name: the JSON copy goes in, with
    `group_id` rewritten and Graphiti's vectors computed again (the package did not bring them)."""
    from mimirsynth import brainimport, docstore
    from mimirsynth.models import (
        ApiToken,
        Audit,
        Brain,
        BrainOntology,
        DocSource,
        Document,
        Membership,
        Proposal,
        RefQuery,
        VocabAlias,
    )
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "src1", "name": "Source", "graph_name": GRAPH}).status_code == 201
    docs = _seed("src1")
    up = _upload(client, _export(client, "src1"))
    man = up["manifest"]
    assert not up["encrypted"] and man["slug"] == "src1" and man["graph"] == {"nodes": 3, "edges": 1, "dump": True, "same_falkordb": True}
    assert man["embedding"]["same"] is True
    item = _import(client, up["upload_id"], "imp1")
    assert item["state"] == "done", item
    assert item["graph"]["method"] == "json" and item["graph"]["fallback_reason"] == "name_taken"
    assert (item["graph"]["nodes"], item["graph"]["edges"]) == (3, 1) and item["vectors"]["graph_computed"] == 3   # two entities, one fact
    from mimirsynth.db import client as fc
    g = fc().select_graph("imp1")
    assert {r[0] for r in g.query("MATCH (n) RETURN n.uuid").result_set} == {"e1", "a", "b"}
    assert {r[0] for r in g.query("MATCH (n) RETURN DISTINCT n.group_id").result_set} == {"imp1"}
    assert g.query("MATCH (n:Entity:Host) RETURN n.name").result_set == [["Polaris"]]
    [[gid, fact, vec]] = g.query("MATCH ()-[e:RELATES_TO]->() RETURN e.group_id, e.fact, e.fact_embedding").result_set
    assert (gid, fact, len(vec)) == ("imp1", "wiki runs on Polaris", fake_embedder)
    assert fc().select_graph(GRAPH).query("MATCH (n) RETURN count(n)").result_set[0][0] == 3       # the source is untouched
    with _factory()() as db:
        b = db.query(Brain).filter(Brain.slug == "imp1").one()
        assert b.name == "IMP1" and b.graph_name == "imp1"
        assert [(m.role, m.user_id) for m in db.query(Membership).filter(Membership.brain_id == b.id)] == [("owner", b.created_by)]
        assert not db.query(ApiToken).filter(ApiToken.brain_id == b.id).count()                        # never in a package
        assert db.get(BrainOntology, b.id).data["entity_types"][0]["name"] == "Host"
        assert [a.alias for a in db.query(VocabAlias).filter(VocabAlias.brain_id == b.id)] == ["RUNS_ON"]
        assert [q.query for q in db.query(RefQuery).filter(RefQuery.brain_id == b.id)] == ["Where does the wiki run?"]
        props = db.query(Proposal).filter(Proposal.brain_id == b.id).order_by(Proposal.id).all()
        assert [p.name for p in props] == ["clean", "leaky"] and TOKEN not in props[1].body and props[1].ingest_report["imported"]["author"]
        sources = {s.name: s for s in db.query(DocSource).filter(DocSource.brain_id == b.id)}
        assert sources["uploads"].enabled and not sources["wiki"].enabled and "credenciales" in sources["wiki"].last_error
        assert "secrets" not in sources["wiki"].config
        got = {d.external_id: d for d in db.query(Document).filter(Document.brain_id == b.id)}
        assert set(got) == {"clean", "masked", "leaky", "unindexed"} and got["clean"].id != docs["clean"]
        assert docstore.resolve(got["clean"].storage_ref).read_text(encoding="utf-8").startswith("original of clean")
        assert docstore.resolve(got["clean"].text_ref).read_text(encoding="utf-8") == "Polaris is in rack 4."
        assert not got["leaky"].storage_ref and got["unindexed"].status == "error"
        acts = [a.action for a in db.query(Audit).filter(Audit.action.like("brain.import%"))]
        assert acts == ["brain.import", "brain.import.done"]
    assert not (brainimport._base() / up["upload_id"]).exists()                                       # the upload is gone
    assert client.get("/api/brains").json() and any(x["slug"] == "imp1" for x in client.get("/api/brains").json())


@needs_falkor
def test_import_restores_the_dump_and_rewrites_group_id(client, falkor, graphs, fake_embedder):  # noqa: F811
    """Same FalkorDB and the original graph gone (another instance): the dump goes in exactly, then to its new name."""
    from mimirsynth.db import client as fc
    assert client.post("/api/brains", json={"slug": "src2", "name": "Source", "graph_name": GRAPH}).status_code == 201
    data = _export(client, "src2")
    falkor.delete()
    up = _upload(client, data)
    item = _import(client, up["upload_id"], "imp2")
    assert item["state"] == "done", item
    assert item["graph"]["method"] == "dump" and item["vectors"] == {"reused": True, "graph_computed": 1}   # only Polaris had none
    assert GRAPH not in fc().list_graphs()                                                         # restored under its name, then moved
    g = fc().select_graph("imp2")
    assert {r[0] for r in g.query("MATCH (n) RETURN DISTINCT n.group_id").result_set} == {"imp2"}
    assert g.query("MATCH (n:Entity {uuid:'a'}) RETURN n.name_embedding").result_set[0][0] == pytest.approx([0.1, 0.2])  # the dump's own


@needs_falkor
def test_import_only_the_structure(client, falkor, graphs):  # noqa: F811
    from mimirsynth.models import Brain, BrainOntology, Document, Proposal, VocabAlias
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "src3", "name": "Source", "graph_name": GRAPH}).status_code == 201
    _seed("src3")
    up = _upload(client, _export(client, "src3"))
    assert client.post("/api/brain-imports", json={"upload_id": up["upload_id"], "slug": "imp3", "name": "x", "mode": "nope"}).status_code == 400
    assert client.post("/api/brain-imports", json={"upload_id": up["upload_id"], "slug": "src3", "name": "x"}).status_code == 409
    assert client.post("/api/brain-imports", json={"upload_id": up["upload_id"], "slug": "No Vale", "name": "x"}).status_code == 400
    item = _import(client, up["upload_id"], "imp3", mode="structure")
    assert item["state"] == "done" and item["counts"]["curation"] == {"ontology": True, "aliases": 1}
    from mimirsynth.db import client as fc
    assert "imp3" not in fc().list_graphs()
    with _factory()() as db:
        bid = db.query(Brain).filter(Brain.slug == "imp3").one().id
        assert db.get(BrainOntology, bid) and db.query(VocabAlias).filter(VocabAlias.brain_id == bid).count() == 1
        assert not db.query(Proposal).filter(Proposal.brain_id == bid).count() and not db.query(Document).filter(Document.brain_id == bid).count()


@needs_falkor
def test_a_tampered_package_is_rejected_without_writing_anything(client, falkor, graphs):  # noqa: F811
    from mimirsynth import brainimport
    assert client.post("/api/brains", json={"slug": "src4", "name": "Source", "graph_name": GRAPH}).status_code == 201
    files = _files(_export(client, "src4"))
    nodes = files["graph/nodes.jsonl"].decode().splitlines()
    bad_label = [json.dumps({**json.loads(nodes[0]), "labels": ["Entity) DETACH DELETE (x"]})] + nodes[1:]
    edge = json.loads(files["graph/edges.jsonl"])
    cases = {
        "ruta no admitida": _repack({**files, "../evil.txt": b"x"}),
        "no está en su manifiesto": _repack(files, links=(("documents/1/text.txt", "/etc/passwd"),)),
        "no es un fichero normal": _repack({k: v for k, v in files.items() if k != "brain.json"},
                                           manifest=lambda m: {**m, "files": m["files"] + [{"path": "brain.json", "size": 0, "sha256": "0" * 64}]},
                                           links=(("brain.json", "/etc/passwd"),)),
        "tamaño": _repack(files, manifest=lambda m: {**m, "files": [{**f, "size": f["size"] + 1} if f["path"] == "brain.json" else f for f in m["files"]]}),
        "huella": _repack(files, manifest=lambda m: {**m, "files": [{**f, "sha256": "1" * 64} if f["path"] == "brain.json" else f for f in m["files"]]}),
        "versión de paquete": _repack(files, manifest=lambda m: {**m, "format_version": 99}),
        "elementos que dice el manifiesto": _repack(files, manifest=lambda m: {**m, "graph": {**m["graph"], "nodes": 7}}),
        "apunta a un nodo": _repack({**files, "graph/edges.jsonl": json.dumps({**edge, "target": 999}).encode()}),
        "etiqueta de nodo": _repack({**files, "graph/nodes.jsonl": "\n".join(bad_label).encode()}),
        "faltan ficheros obligatorios": _repack({k: v for k, v in files.items() if k != "vocabulary.json"}),
    }
    for i, (why, data) in enumerate(cases.items(), start=5):
        slug = f"imp{min(i, 9)}"
        r = client.post("/api/brain-imports/uploads", json={"filename": "p.tar.gz", "size": len(data)})
        uid = r.json()["upload_id"]
        client.put(f"/api/brain-imports/uploads/{uid}/parts/0", content=data)
        done = client.post(f"/api/brain-imports/uploads/{uid}/complete")
        if done.status_code == 400:                                   # the manifest alone already gives it away
            assert why in done.json()["detail"], (why, done.json())
            assert not (brainimport._base() / uid).exists()
            continue
        item = _import(client, uid, slug)
        assert item["state"] == "failed" and "paquete rechazado" in item["error"] and why in item["error"], (why, item["error"])
        assert _left(slug) == [] and not (brainimport._base() / uid).exists()
    assert falkor.query("MATCH (n) RETURN count(n)").result_set[0][0] == 3   # the injected label never ran


@needs_falkor
def test_encrypted_package_wrong_then_right_password(client, falkor, graphs, fake_embedder):  # noqa: F811
    from mimirsynth import brainimport
    assert client.post("/api/brains", json={"slug": "src5", "name": "Source", "graph_name": GRAPH}).status_code == 201
    up = _upload(client, _export(client, "src5", password="a long enough password"), "p.tar.gz.enc")
    assert up == {"upload_id": up["upload_id"], "encrypted": True, "manifest": None}
    r = client.post("/api/brain-imports", json={"upload_id": up["upload_id"], "slug": "imp5", "name": "x"})
    assert r.status_code == 400 and "contraseña" in r.json()["detail"]
    item = _import(client, up["upload_id"], "imp5", password="not the password at all")
    assert item["state"] == "failed" and "contraseña incorrecta" in item["error"] and item["retry_password"] is True
    assert _left("imp5") == [] and not brainimport._PASSWORDS
    item = _import(client, up["upload_id"], "imp5", password="a long enough password")
    assert item["state"] == "done" and (item["graph"]["nodes"], item["graph"]["edges"]) == (3, 1)


@needs_falkor
def test_a_failure_in_the_middle_leaves_nothing(client, falkor, graphs, fake_embedder, monkeypatch):  # noqa: F811
    from mimirsynth import brainimport, docstore
    from mimirsynth.models import Brain, BrainOntology, RefQuery
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "src6", "name": "Source", "graph_name": GRAPH}).status_code == 201
    _seed("src6")
    up = _upload(client, _export(client, "src6"))
    seen = {}

    def boom(db, stage, bid, user_id):
        seen["bid"] = bid
        raise RuntimeError("disk full")
    monkeypatch.setattr(brainimport, "_proposals", boom)
    item = _import(client, up["upload_id"], "imp6")
    assert item["state"] == "failed" and "disk full" in item["error"]
    assert _left("imp6") == []                                       # the graph was already in: it is gone too
    with _factory()() as db:
        assert not db.get(Brain, seen["bid"]) and not db.get(BrainOntology, seen["bid"])
        assert not db.query(RefQuery).filter(RefQuery.brain_id == seen["bid"]).count()
    assert not (docstore.root() / str(seen["bid"])).exists()


@needs_falkor
def test_an_import_cut_by_a_restart_is_undone_on_start(client, falkor, graphs):  # noqa: F811
    from mimirsynth import brainimport, jobs
    from mimirsynth.db import client as fc
    from mimirsynth.models import Brain, Job, Membership, User
    from mimirsynth.store import _factory
    with _factory()() as db:
        u = db.query(User).first()
        b = Brain(slug="imp7", name="half", graph_name="imp7", created_by=u.id)
        db.add(b)
        db.flush()
        db.add(Membership(user_id=u.id, brain_id=b.id, role="owner"))
        j = Job(kind=brainimport.KIND, params={"upload_id": "f" * 32}, title="Import", status="running")
        db.add(j)
        db.commit()
        bid, jid = b.id, j.id
    fc().select_graph("imp7").query("CREATE (:Entity {uuid:'x'})")
    work = brainimport._base() / ("f" * 32)
    work.mkdir(parents=True, exist_ok=True)
    brainimport._mark(work, {"slug": "imp7", "brain_id": bid, "graph": "imp7", "restored": None})
    assert brainimport.purge() == 0                                  # still «running»: not touched
    jobs.recover()
    with _factory()() as db:
        assert "vuelve a subir el paquete" in db.get(Job, jid).error
    assert brainimport.purge() == 1
    assert _left("imp7") == [] and not work.exists()


def test_import_needs_the_instance_admin_and_a_free_slug(client):  # noqa: F811
    from mimirsynth.deps import current_user
    from mimirsynth.main import app
    from mimirsynth.models import Brain, Membership, User
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "imp8", "name": "Taken"}).status_code == 201
    r = client.post("/api/brain-imports/uploads", json={"filename": "p.tar.gz", "size": 3})
    uid = r.json()["upload_id"]
    client.put(f"/api/brain-imports/uploads/{uid}/parts/0", content=b"abc")
    assert client.post(f"/api/brain-imports/uploads/{uid}/complete").status_code == 400   # not a package: rejected and removed
    r = client.post("/api/brain-imports/uploads", json={"filename": "p.tar.gz", "size": 10 ** 15})
    assert r.status_code == 413
    with _factory()() as db:
        u = User(email="owner-imp@example.com", name="Own", status="active")
        db.add(u)
        db.flush()
        db.add(Membership(user_id=u.id, brain_id=db.query(Brain).filter(Brain.slug == "imp8").one().id, role="owner"))
        db.commit()
        uid2 = u.id
    app.dependency_overrides[current_user] = lambda: _factory()().get(User, uid2)
    try:
        assert client.post("/api/brain-imports/uploads", json={"filename": "p.tar.gz", "size": 3}).status_code == 403
        assert client.get("/api/brain-imports").status_code == 403
    finally:
        app.dependency_overrides.pop(current_user)
