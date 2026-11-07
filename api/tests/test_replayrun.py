"""Shadow replay (#291, second part): the recall sample asked again with a candidate configuration, a report of what each question would
gain, lose or reorder and of how many would come back empty or outdated, bounded per run and per hour, for brain administrators; and a
real question promoted to a reference query."""
from test_control import client  # noqa: F401
from test_recall_ratings import OUT

from mimirsynth import replayrun as RR


def test_the_diff():
    before = [{"kind": "fact", "id": "a"}, {"kind": "fact", "id": "b"}, {"kind": "chunk", "id": ":7"}]
    assert RR.diff(before, before)["changed"] is False
    d = RR.diff(before, [{"kind": "fact", "id": "b"}, {"kind": "fact", "id": "a"}, {"kind": "doc", "id": ":3:1"}])
    assert d["gained"] == [{"kind": "doc", "id": ":3:1"}] and d["lost"] == [{"kind": "chunk", "id": ":7"}] and d["reordered"] and d["changed"]
    assert RR.diff(before, [])["empty_after"] is True and RR.diff([], [])["empty_before"] is True


def test_a_run_reports_what_would_change_and_a_question_is_promoted(client, monkeypatch):  # noqa: F811
    from mimirsynth import memory, recall as R
    from mimirsynth.models import RecallSample, RefQuery
    from mimirsynth.store import _factory
    monkeypatch.setattr(memory, "recall", lambda *a, **k: dict(OUT))
    client.post("/api/brains", json={"slug": "rr", "name": "RR"})
    assert client.post("/api/brains/rr/replay/runs", json={}).status_code == 409             # nothing in the sample yet
    client.put("/api/brains/rr/replay/settings", json={"enabled": True})
    for q in ("where does nextcloud run", "ok go on"):
        client.post("/api/brains/rr/recall", json={"query": q})
    seen = []

    def candidate(bid, graph, query, *a, **k):                                                # a stricter threshold: the vague one comes back empty
        seen.append(k.get("min_similarity"))
        return {"facts": [OUT["facts"][0]], "chunks": [], "documents": [], "context": "x"} if "nextcloud" in query else {"facts": [], "context": ""}
    monkeypatch.setattr(R, "recall", candidate)
    rid = client.post("/api/brains/rr/replay/runs", json={"candidate": {"min_similarity": 0.7}, "sample": 10}).json()["run"]
    run = client.get(f"/api/brains/rr/replay/runs/{rid}").json()
    s = run["summary"]
    assert run["status"] == "done" and seen == [0.7, 0.7] and run["params"] == {"min_similarity": 0.7}
    assert s["questions"] == 2 and s["changed"] == 2 and s["empty_after"] == 0.5 and s["empty_before"] == 0
    nc = next(r for r in run["results"] if "nextcloud" in r["query"])
    assert {"kind": "fact", "id": "f2"} in nc["lost"] and nc["gained"] == []
    with _factory()() as db:
        sid = db.query(RecallSample).filter(RecallSample.query == "where does nextcloud run").one().id
    qid = client.post(f"/api/brains/rr/replay/samples/{sid}/promote", json={"expect": ["Notus"]}).json()["refquery"]
    with _factory()() as db:
        q = db.get(RefQuery, qid)
        assert q.query == "where does nextcloud run" and q.expect == [{"text": "Notus", "kind": "any"}]
    tok = client.post("/api/brains/rr/tokens", json={"name": "c", "role": "curator"}).json()["token"]
    assert client.get("/api/brains/rr/replay/runs", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_runs_per_hour_are_bounded(client, monkeypatch):  # noqa: F811
    from mimirsynth import memory, recall as R
    monkeypatch.setattr(memory, "recall", lambda *a, **k: dict(OUT))
    monkeypatch.setattr(R, "recall", lambda *a, **k: dict(OUT))
    monkeypatch.setattr(RR, "RUNS_PER_HOUR", 2)
    client.post("/api/brains", json={"slug": "rr2", "name": "RR2"})
    client.put("/api/brains/rr2/replay/settings", json={"enabled": True})
    client.post("/api/brains/rr2/recall", json={"query": "q"})
    codes = [client.post("/api/brains/rr2/replay/runs", json={}).status_code for _ in range(3)]
    assert codes == [202, 202, 429]
