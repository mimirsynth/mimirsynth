"""Export of a brain to a package (#130): contents, what stays out, secrets, download once, expiry and encryption."""
import io
import json
import os
import tarfile
from datetime import datetime, timedelta, timezone

import pytest

from test_control import client  # noqa: F401

from mimirsynth import packcrypt

FALKOR = os.environ.get("MIMIRSYNTH_TEST_FALKOR")
GRAPH = "zz-test-export"
TOKEN = "ghp_A1b2C3d4E5f6G7h8J9k0A1b2C3d4E5f6G7h8"  # fake, with the right format


def test_packcrypt_roundtrip_and_wrong_password(tmp_path):
    src, enc, out = tmp_path / "a.bin", tmp_path / "a.enc", tmp_path / "a.out"
    data = os.urandom(packcrypt.CHUNK * 2 + 123)  # three chunks, the last one short
    src.write_bytes(data)
    packcrypt.encrypt_file(src, enc, "correct horse battery")
    assert packcrypt.is_encrypted(enc) and data[:64] not in enc.read_bytes()
    packcrypt.decrypt_file(enc, out, "correct horse battery")
    assert out.read_bytes() == data
    buf = io.BytesIO()
    packcrypt.decrypt_file(enc, buf, "correct horse battery")                   # an open file, as the command line does with «-»
    assert buf.getvalue() == data
    with pytest.raises(packcrypt.BadPassword):
        packcrypt.decrypt_file(enc, out, "wrong horse battery")
    cut = tmp_path / "cut.enc"
    raw = enc.read_bytes()
    cut.write_bytes(raw[: len(raw) - (len(data) % packcrypt.CHUNK) - 16 - 4])  # without its last chunk
    with pytest.raises(packcrypt.BadPassword):
        packcrypt.decrypt_file(cut, out, "correct horse battery")
    with pytest.raises(ValueError):
        packcrypt.encrypt_file(src, enc, "short")
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    packcrypt.encrypt_file(empty, enc, "correct horse battery")
    packcrypt.decrypt_file(enc, out, "correct horse battery")
    assert out.read_bytes() == b""


@pytest.fixture()
def falkor(monkeypatch):
    from mimirsynth import db as dbm
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "falkor_host", FALKOR)
    dbm.client.cache_clear()
    c = dbm.client()
    for g in (GRAPH, f"_snap_{GRAPH}_20260101000000"):
        if g in c.list_graphs():
            c.select_graph(g).delete()
    g = c.select_graph(GRAPH)
    g.query("CREATE (:Episodic {uuid:'e1', name:'ep', content:'Polaris hosts the wiki', group_id:$g})", {"g": GRAPH})
    g.query("CREATE (a:Entity {uuid:'a', name:'wiki', group_id:$g, name_embedding: vecf32([0.1, 0.2])})"
            "-[:RELATES_TO {uuid:'f1', name:'HOSTED_ON', fact:'wiki runs on Polaris', group_id:$g, fact_embedding: vecf32([0.3, 0.4])}]->"
            "(:Entity:Host {uuid:'b', name:'Polaris', group_id:$g})", {"g": GRAPH})
    c.select_graph(f"_snap_{GRAPH}_20260101000000").query("CREATE (:Entity {uuid:'old'})")
    yield g
    for x in (GRAPH, f"_snap_{GRAPH}_20260101000000"):
        if x in c.list_graphs():
            c.select_graph(x).delete()
    dbm.client.cache_clear()


def _seed(slug: str) -> dict:
    """Proposals, tokens, documents and curation for the brain, straight into the database and the document store."""
    from mimirsynth import docstore
    from mimirsynth.models import (ApiToken, Brain, BrainOntology, DocSource, Document, Proposal, RefQuery, User, VocabAlias)
    from mimirsynth.store import _factory
    with _factory()() as db:
        b = db.query(Brain).filter(Brain.slug == slug).one()
        u = db.query(User).first()
        db.add(BrainOntology(brain_id=b.id, data={"entity_types": [{"name": "Host", "description": "A machine"}]}))
        db.add(VocabAlias(brain_id=b.id, alias="RUNS_ON", canonical="HOSTED_ON"))
        db.add(RefQuery(brain_id=b.id, query="Where does the wiki run?", expect=[{"text": "Polaris", "kind": "fact"}]))
        db.add(ApiToken(user_id=u.id, brain_id=b.id, name="agent", role="contributor", prefix="ms_x", token_hash="h" * 64))
        db.add(Proposal(brain_id=b.id, author_id=u.id, name="clean", body="The wiki runs on Polaris"))
        db.add(Proposal(brain_id=b.id, author_id=u.id, name="leaky", body=f"deploy with {TOKEN} please"))  # «warn» left it as it was
        up = DocSource(brain_id=b.id, kind="upload", name="uploads")
        wiki = DocSource(brain_id=b.id, kind="wiki", name="wiki", config={"adapter": "outline", "settings": {"url": "https://wiki.example"},
                                                                          "secrets": {"api_key": "sealed-value"}})
        db.add_all([up, wiki])
        db.flush()
        docs = {}
        for key, text, meta in (("clean", "Polaris is in rack 4.", {}),
                                ("masked", "token [secreto eliminado: token de GitHub]", {"secrets": [{"rule": "github_token", "action": "masked", "count": 1}]}),
                                ("leaky", f"use {TOKEN}", {}),
                                ("unindexed", None, {})):
            d = Document(brain_id=b.id, source_id=up.id, external_id=key, filename=f"{key}.md", sha256=key, status="active" if text else "error", meta=meta)
            db.add(d)
            db.flush()
            ddir = docstore.doc_dir(b.id, up.id, d.id)
            ddir.mkdir(parents=True, exist_ok=True)
            orig = ddir / "orig.md"
            orig.write_text(f"original of {key} {TOKEN if key != 'clean' else ''}", encoding="utf-8")
            d.storage_ref = docstore.rel(orig)
            if text:
                (ddir / "norm.txt").write_text(text, encoding="utf-8")
                d.text_ref = docstore.rel(ddir / "norm.txt")
            docs[key] = d.id
        db.commit()
        return docs


def _members(tar: tarfile.TarFile) -> dict[str, bytes]:
    return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_export_contents_secrets_and_download_once(client, falkor):  # noqa: F811
    from mimirsynth import brainexport
    from mimirsynth.models import Audit
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "exp", "name": "Export", "graph_name": GRAPH}).status_code == 201
    docs = _seed("exp")
    r = client.post("/api/brains/exp/exports", json={})
    assert r.status_code == 202
    jid = r.json()["id"]
    item = client.get("/api/brains/exp/exports").json()["items"][0]
    assert item["id"] == jid and item["state"] == "ready", item
    assert item["graph"]["dump_omitted"] is None and item["graph"]["nodes"] == 3 and item["graph"]["edges"] == 1
    assert item["secrets"]["masked"] == {"github_token": 2}                      # the proposal and the leaky document
    got = client.get(f"/api/brains/exp/exports/{jid}/download")
    assert got.status_code == 200 and "exp-" in got.headers["content-disposition"]
    with tarfile.open(fileobj=io.BytesIO(got.content), mode="r:gz") as t:
        assert t.getmembers()[0].name == "manifest.json"                          # first, so an importer reads it before the rest
        files = _members(t)
    man = json.loads(files["manifest.json"])
    assert man["format"] == "mimirsynth-brain" and man["format_version"] == 1 and man["brain"] == {"slug": "exp", "graph_name": GRAPH}
    assert man["falkordb"].get("graph_module") and man["embedding"]["model"]
    assert {f["path"] for f in man["files"]} == set(files) - {"manifest.json"}
    assert all(f["size"] == len(files[f["path"]]) for f in man["files"])
    assert set(man["excluded"]) >= {"members", "api_tokens", "ai_engines", "notification_channels", "graph_snapshots"}
    blob = b"".join(files.values())
    assert TOKEN.encode() not in blob and b"sealed-value" not in blob and b"token_hash" not in blob and b"old" not in files["graph/nodes.jsonl"]
    nodes = [json.loads(x) for x in files["graph/nodes.jsonl"].splitlines()]
    assert {n["props"]["uuid"] for n in nodes} == {"e1", "a", "b"} and not any("vectors" in n for n in nodes)   # no vectors without the option
    edge = json.loads(files["graph/edges.jsonl"])
    assert edge["type"] == "RELATES_TO" and edge["props"]["fact"] == "wiki runs on Polaris" and "fact_embedding" not in edge["props"]
    props = [json.loads(x) for x in files["proposals.jsonl"].splitlines()]
    assert [p["name"] for p in props] == ["clean", "leaky"] and "[secreto eliminado: token de GitHub]" in props[1]["body"]
    assert props[1]["masked_on_export"] and "author_id" not in props[1] and props[1]["author"]
    meta = {d["external_id"]: d for d in map(json.loads, files["documents/documents.jsonl"].splitlines())}
    assert meta["clean"]["original"] == f"documents/{docs['clean']}/original.md" and files[meta["clean"]["original"]].startswith(b"original of clean")
    assert (meta["masked"]["original_omitted"], meta["leaky"]["original_omitted"], meta["unindexed"]["original_omitted"]) == ("secrets", "secrets", "unchecked")
    assert files[meta["leaky"]["text"]] == "use [secreto eliminado: token de GitHub]".encode()
    sources = {s["name"]: s for s in json.loads(files["documents/sources.json"])}
    assert sources["wiki"]["config"] == {"adapter": "outline", "settings": {"url": "https://wiki.example"}} and sources["wiki"]["secrets_removed"] == ["api_key"]
    assert json.loads(files["ontology.json"])["entity_types"][0]["name"] == "Host"
    assert json.loads(files["vocabulary.json"])["aliases"][0]["alias"] == "RUNS_ON"
    assert json.loads(files["ref_queries.json"])["queries"][0]["query"] == "Where does the wiki run?"
    assert json.loads(files["brain.json"])["slug"] == "exp"
    # once: the second download and the listing say so, and the package is gone from disk
    assert client.get(f"/api/brains/exp/exports/{jid}/download").status_code == 410
    assert client.get("/api/brains/exp/exports").json()["items"][0]["state"] == "downloaded"
    assert not brainexport._dir(jid).exists()
    with _factory()() as db:
        acts = [a.action for a in db.query(Audit).filter(Audit.action.like("brain.export%"))]
    assert acts == ["brain.export", "brain.export.download"]
    # the dump restores the same graph, under its own name (the payload carries it)
    dump = files["graph/graph.dump"]
    falkor.delete()
    from mimirsynth.db import client as fc
    fc().connection.restore(GRAPH, 0, dump)
    assert fc().select_graph(GRAPH).query("MATCH (n) RETURN count(n)").result_set[0][0] == 3


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_graph_with_a_secret_goes_without_dump_and_vectors_on_request(client, falkor):  # noqa: F811
    falkor.query("MATCH (e:Episodic) SET e.content = $c", {"c": f"the deploy token is {TOKEN}"})
    assert client.post("/api/brains", json={"slug": "exp2", "name": "Export 2", "graph_name": GRAPH}).status_code == 201
    jid = client.post("/api/brains/exp2/exports", json={"vectors": True}).json()["id"]
    with tarfile.open(fileobj=io.BytesIO(client.get(f"/api/brains/exp2/exports/{jid}/download").content), mode="r:gz") as t:
        files = _members(t)
    man = json.loads(files["manifest.json"])
    assert man["graph"]["dump"] is None and man["graph"]["dump_omitted"] == "secrets" and "graph/graph.dump" not in files
    assert TOKEN.encode() not in files["graph/nodes.jsonl"] and man["secrets"]["masked"] == {"github_token": 1}
    nodes = {n["props"]["uuid"]: n for n in map(json.loads, files["graph/nodes.jsonl"].splitlines())}
    assert nodes["a"]["vectors"]["name_embedding"] == pytest.approx([0.1, 0.2])
    assert man["options"]["vectors"] is True and man["vectors"] == {"skipped_reason": "no_index"}   # SQLite: no search index


@pytest.mark.skipif(not FALKOR, reason="necesita un FalkorDB desechable (MIMIRSYNTH_TEST_FALKOR=host)")
def test_encrypted_export_expiry_and_purge(client, falkor, tmp_path):  # noqa: F811
    from mimirsynth import brainexport
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    assert client.post("/api/brains", json={"slug": "exp3", "name": "Export 3", "graph_name": GRAPH}).status_code == 201
    assert client.post("/api/brains/exp3/exports", json={"password": "short"}).status_code == 400
    jid = client.post("/api/brains/exp3/exports", json={"password": "a long enough password"}).json()["id"]
    detail = client.get(f"/api/brains/exp3/jobs/{jid}").json()
    assert "a long enough password" not in json.dumps(detail) and not brainexport._PASSWORDS   # never stored, gone once used
    body = client.get(f"/api/brains/exp3/exports/{jid}/download")
    assert body.headers["content-disposition"].endswith('.mimirsynth.tar.gz.enc"')
    enc, out = tmp_path / "p.enc", tmp_path / "p.tar.gz"
    enc.write_bytes(body.content)
    with pytest.raises(tarfile.ReadError):
        tarfile.open(enc, mode="r:gz")
    with pytest.raises(packcrypt.BadPassword):
        packcrypt.decrypt_file(enc, out, "not the password at all")
    assert packcrypt.main(["decrypt", str(enc)]) == 2                    # usage
    os.environ["MIMIRSYNTH_PACK_PASSWORD"] = "a long enough password"
    try:
        assert packcrypt.main(["decrypt", str(enc), str(out)]) == 0
    finally:
        del os.environ["MIMIRSYNTH_PACK_PASSWORD"]
    with tarfile.open(out, mode="r:gz") as t:
        assert json.loads(t.extractfile("manifest.json").read())["options"]["encrypted"] is True
    # an expired package answers 410 and the purge removes it
    jid = client.post("/api/brains/exp3/exports", json={}).json()["id"]
    with _factory()() as db:
        j = db.get(Job, jid)
        j.result = {**j.result, "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        db.commit()
    assert client.get("/api/brains/exp3/exports").json()["items"][0]["state"] == "expired"
    assert client.get(f"/api/brains/exp3/exports/{jid}/download").status_code == 410
    assert brainexport._dir(jid).exists() and brainexport.purge() >= 1 and not brainexport._dir(jid).exists()


def test_export_cut_by_a_restart_says_to_export_again(client):  # noqa: F811
    """Review of #147: the password only lives in memory, so after a restart the failed job has to say to export again."""
    from mimirsynth import brainexport, jobs
    from mimirsynth.models import Job
    from mimirsynth.store import _factory
    with _factory()() as db:
        j = Job(kind=brainexport.KIND, brain_id=None, params={"encrypted": True, "key": "k"}, title="Export", status="running")
        db.add(j)
        db.commit()
        jid = j.id
    jobs.recover()
    with _factory()() as db:
        j = db.get(Job, jid)
        assert j.status == "failed" and "vuelve a exportar" in j.error and "contraseña" in j.error


def test_export_needs_brain_admin(client):  # noqa: F811
    from mimirsynth.models import Brain, Membership, User
    from mimirsynth.store import _factory
    from mimirsynth.deps import current_user
    from mimirsynth.main import app
    assert client.post("/api/brains", json={"slug": "exp4", "name": "Export 4"}).status_code == 201
    with _factory()() as db:
        u = User(email="curator-exp@example.com", name="Cur", status="active")
        db.add(u)
        db.flush()
        db.add(Membership(user_id=u.id, brain_id=db.query(Brain).filter(Brain.slug == "exp4").one().id, role="curator"))
        db.commit()
        uid = u.id
    app.dependency_overrides[current_user] = lambda: _factory()().get(User, uid)
    try:
        assert client.post("/api/brains/exp4/exports", json={}).status_code == 403
        assert client.get("/api/brains/exp4/exports").status_code == 403
    finally:
        app.dependency_overrides.pop(current_user)
