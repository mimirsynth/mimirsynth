"""Cola general de trabajos: ejecución, fallo, cancelación, reintento, deduplicado, recuperación tras reinicio y API."""
import threading

import pytest

from test_control import client  # noqa: F401

from mimirsynth import jobs
from mimirsynth.models import Job
from mimirsynth.store import _factory


@pytest.fixture()
def kinds(monkeypatch):
    monkeypatch.setattr(jobs, "_KINDS", dict(jobs._KINDS))
    calls = []

    @jobs.register("t.ok", "Prueba ok")
    def ok(ctx, p):
        ctx.progress(1, 4, "paso 1"); ctx.note("hola"); ctx.progress(4, 4)
        calls.append(p)
        return {"x": p.get("x")}

    @jobs.register("t.fail", "Prueba fallo")
    def fail(ctx, p):
        ctx.retrying("reintento interno")
        raise RuntimeError("explotó")

    @jobs.register("t.cancel", "Prueba cancelar")
    def cancel_me(ctx, p):
        jobs._CANCEL.add(ctx.id)
        ctx.check()

    @jobs.register("t.resume", "Prueba reanudar", resume=True)
    def resume(ctx, p):
        calls.append("resumed")
    return calls


def _brain(client):
    import uuid
    slug = "j" + uuid.uuid4().hex[:8]
    client.post("/api/brains", json={"slug": slug, "name": slug})
    from sqlalchemy import delete, select
    from mimirsynth.models import Brain
    with _factory()() as db:
        bid = db.scalar(select(Brain.id).where(Brain.slug == slug))
        db.execute(delete(Job).where(Job.brain_id == bid))  # la BD de pruebas se comparte y SQLite reutiliza ids de brains borrados
        db.commit()
        return bid, slug


def test_job_lifecycle_and_api(client, kinds):
    bid, sl = _brain(client)
    ok = jobs.submit("t.ok", bid, {"x": 7}, "Todo bien")
    bad = jobs.submit("t.fail", bid, {}, "Todo mal")
    can = jobs.submit("t.cancel", bid, {}, "Cancelado")
    r = client.get(f"/api/brains/{sl}/jobs").json()
    by = {j["id"]: j for j in r["items"]}
    assert by[ok]["status"] == "done" and by[ok]["done"] == 4 and by[ok]["total"] == 4
    assert by[bad]["status"] == "failed" and "explotó" in by[bad]["error"] and by[bad]["attempts"] == 2
    assert by[can]["status"] == "cancelled"
    assert r["counts"] == {"done": 1, "failed": 1, "cancelled": 1} and [k["kind"] for k in r["kinds"]] == ["t.cancel", "t.fail", "t.ok"]
    d = client.get(f"/api/brains/{sl}/jobs/{ok}").json()
    assert d["result"] == {"x": 7} and d["params"] == {"x": 7} and any(l["msg"] == "hola" for l in d["log"])
    assert client.get(f"/api/brains/{sl}/jobs?status=failed").json()["items"][0]["id"] == bad
    assert client.get(f"/api/brains/{sl}/jobs/summary").json()["active"] == 0
    assert client.get(f"/api/brains/{sl}x/jobs/{ok}").status_code == 404


def test_retry_and_cancel_rules(client, kinds):
    bid, sl = _brain(client)
    bad = jobs.submit("t.fail", bid, {"a": 1}, "Falla")
    assert client.post(f"/api/brains/{sl}/jobs/{bad}/retry").status_code == 201
    items = client.get(f"/api/brains/{sl}/jobs").json()["items"]
    assert len(items) == 2 and items[0]["retry_of"] == bad and items[0]["status"] == "failed"
    ok = jobs.submit("t.ok", bid, {}, "ok")
    assert client.post(f"/api/brains/{sl}/jobs/{ok}/retry").status_code == 409                 # solo fallidos o cancelados
    assert client.post(f"/api/brains/{sl}/jobs/{ok}/cancel").json()["result"] == "finished"


def test_dedupe_and_queue_cancel(client, kinds, monkeypatch):
    bid, sl = _brain(client)
    monkeypatch.setattr(jobs, "INLINE", False)
    gate = threading.Event()
    @jobs.register("t.slow", "Lento", limit=1)
    def slow(ctx, p):
        gate.wait(5)
    a = jobs.submit("t.slow", bid, {}, "a", dedupe_key="k")
    assert jobs.submit("t.slow", bid, {}, "a otra vez", dedupe_key="k") == a                   # mismo trabajo activo: no se duplica
    b = jobs.submit("t.slow", bid, {}, "b")
    assert jobs.cancel(b) == "cancelled"                                                        # en cola: se cancela al instante
    gate.set()
    for _ in range(50):
        with _factory()() as db:
            if db.get(Job, a).status == "done":
                break
        threading.Event().wait(0.1)
    with _factory()() as db:
        assert db.get(Job, a).status == "done" and db.get(Job, b).status == "cancelled"


def test_recover_marks_interrupted_and_resumes(client, kinds):
    bid, sl = _brain(client)
    with _factory()() as db:
        db.add_all([Job(brain_id=bid, kind="t.ok", title="a medias", status="running"), Job(brain_id=bid, kind="t.resume", title="idempotente", status="queued")])
        db.commit()
    assert jobs.recover() == {"interrupted": 2, "resumed": 1}
    st = {j["title"]: j for j in client.get(f"/api/brains/{sl}/jobs").json()["items"]}
    assert st["a medias"]["status"] == "failed" and "reinicio" in st["a medias"]["error"] and "resumed" in kinds


def test_jobs_list_pagination(client, kinds):
    bid, sl = _brain(client)
    for i in range(5):
        jobs.submit("t.ok", bid, {"x": i}, f"trabajo {i}")
    r = client.get(f"/api/brains/{sl}/jobs", params={"limit": 2, "offset": 0}).json()
    assert r["total"] == 5 and [j["title"] for j in r["items"]] == ["trabajo 4", "trabajo 3"]
    assert [j["title"] for j in client.get(f"/api/brains/{sl}/jobs", params={"limit": 2, "offset": 4}).json()["items"]] == ["trabajo 0"]


def test_jobs_list_text_filter_and_order(client, kinds):
    bid, sl = _brain(client)
    for t in ("Indexar alfa", "Indexar beta_1", "Escanear gamma"):
        jobs.submit("t.ok", bid, {}, t)
    names = lambda **p: [j["title"] for j in client.get(f"/api/brains/{sl}/jobs", params=p).json()["items"]]  # noqa: E731
    assert names(q="indexar") == ["Indexar beta_1", "Indexar alfa"] and names(q="a_1") == ["Indexar beta_1"] and names(q="%") == []
    assert names(order="asc")[0] == "Indexar alfa"


def test_prune_scheduled_noise_sooner(client):  # noqa: F811
    """Los reescaneos programados terminados sin incidencias se retiran a los pocos días; fallidos y lanzados por una persona, no."""
    from datetime import timedelta
    old = jobs._now() - timedelta(days=jobs.settings.jobs_keep_scheduled_days + 1)
    with _factory()() as db:
        for status, dk, by in [("done", "doc.scan:1", None), ("failed", "doc.scan:1", None), ("done", "doc.scan:1", 1), ("done", "", None)]:
            db.add(Job(kind="t.prune", title="x", status=status, dedupe_key=dk, created_by=by, finished_at=old))
        db.commit()
    assert jobs.prune() == 1
    with _factory()() as db:
        assert sorted(((j.status, j.dedupe_key, j.created_by) for j in db.query(Job).filter(Job.kind == "t.prune")), key=str) == sorted([("failed", "doc.scan:1", None), ("done", "doc.scan:1", 1), ("done", "", None)], key=str)
