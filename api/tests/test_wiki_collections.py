"""Changing the collections of a wiki source from «Edit» (#185): adding scans them, removing drops exactly their pages after a confirmation
with the count, a failed scan removes nothing, and only the instance administrator may do it."""
from datetime import datetime, timezone

from sqlalchemy import select

from test_control import _as, client  # noqa: F401
from test_docs import fake_index  # noqa: F401
from test_docsources import _brain, _docs

from mimirsynth import wikis
from mimirsynth.main import app
from mimirsynth.models import Audit, Document
from mimirsynth.store import _factory

PAGES = {"C": [("c1", "Uno"), ("c2", "Dos")], "D": [("d1", "Tres")]}
NAMES = {"C": "Colección C", "D": "Colección D"}


def _fake(monkeypatch, state):
    monkeypatch.setattr(wikis, "REGISTRY", dict(wikis.REGISTRY))

    @wikis.register
    class Toy(wikis.Adapter):
        id, label = "toycols", "Juguete"
        fields = [wikis.Field("site", "Sitio")]

        def collections(self):
            if state.get("down"):
                raise wikis.WikiError("la wiki no responde")
            return [{"id": k, "name": v, "description": ""} for k, v in NAMES.items()]

        def documents(self, ids):
            for cid in ids or list(PAGES):
                for pid, title in PAGES[cid]:
                    if state.get("down"):
                        raise wikis.WikiError("la wiki no responde")
                    yield wikis.WikiDoc(pid, title, f"Contenido de {pid}", datetime(2026, 10, 20, tzinfo=timezone.utc), f"https://t.test/{pid}", NAMES[cid], collection_id=cid)


def _last_update():
    with _factory()() as db:
        return db.scalars(select(Audit).where(Audit.action == "docsource.update").order_by(Audit.id.desc())).first().detail


def test_add_and_remove_collections(client, fake_index, monkeypatch):  # noqa: F811
    state: dict = {}
    _fake(monkeypatch, state)
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    r = client.post(f"{base}/sources/wiki", json={"adapter": "toycols", "values": {"site": "t.test"}, "name": "Toy", "collection_ids": ["C"]})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert set(_docs(client, slug)) == {"c1", "c2"}
    got = client.get(f"{base}/sources/{sid}/wiki/collections").json()
    assert got["selected"] == ["C"] and got["documents"] == {"C": 2}

    # adding a collection scans it at once
    r = client.patch(f"{base}/sources/{sid}", json={"collection_ids": ["C", "D"]})
    assert r.status_code == 200 and r.json()["job"] and r.json()["documents_removed"] == 0
    docs = _docs(client, slug)
    assert set(docs) == {"c1", "c2", "d1"} and docs["d1"]["status"] == "active" and fake_index[docs["d1"]["id"]]
    assert _last_update() == {"id": sid, "collections_added": ["Colección D"], "collections_removed": [], "documents_removed": 0}

    # removing one asks for the count first, then drops only its pages; a page indexed before the id was stored is found by its name
    with _factory()() as db:
        d = db.scalar(select(Document).where(Document.source_id == sid, Document.external_id == "c2"))
        d.meta = {"collection": "Colección C", "title_auto": False}
        db.commit()
    assert client.get(f"{base}/sources/{sid}/wiki/collections").json()["documents"] == {"C": 2, "D": 1}
    r = client.patch(f"{base}/sources/{sid}", json={"collection_ids": ["D"]})
    assert r.status_code == 409 and "2 documentos" in r.json()["detail"]
    assert client.patch(f"{base}/sources/{sid}", json={"collection_ids": ["D"], "confirm_removed": 1}).status_code == 409   # the count must match
    assert set(_docs(client, slug)) == {"c1", "c2", "d1"}
    r = client.patch(f"{base}/sources/{sid}", json={"collection_ids": ["D"], "confirm_removed": 2})
    assert r.status_code == 200 and r.json() == {"ok": True, "documents_removed": 2, "job": None}
    assert set(_docs(client, slug)) == {"d1"}
    assert _last_update() == {"id": sid, "collections_added": [], "collections_removed": ["Colección C"], "documents_removed": 2}

    # with the wiki down, the other fields are saved and no document is removed, even if the scan of a new collection fails
    state["down"] = True
    assert client.get(f"{base}/sources/{sid}/wiki/collections").status_code == 400
    r = client.patch(f"{base}/sources/{sid}", json={"name": "Toy 2", "collection_ids": ["D", "C"]})
    assert r.status_code == 200 and r.json()["job"]
    assert set(_docs(client, slug)) == {"d1"}
    src = next(s for s in client.get(f"{base}/sources").json()["sources"] if s["id"] == sid)
    assert src["name"] == "Toy 2" and src["config"]["collection_ids"] == ["D", "C"]
    state["down"] = False


def test_only_the_instance_administrator_changes_collections(client, fake_index, monkeypatch):  # noqa: F811
    _fake(monkeypatch, {})
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    sid = client.post(f"{base}/sources/wiki", json={"adapter": "toycols", "values": {"site": "t.test"}, "name": "Toy", "collection_ids": ["C"]}).json()["id"]
    assert client.put(f"/api/brains/{slug}/members", json={"email": "bea@x.com", "role": "admin"}).status_code == 200
    _as("bea@x.com", "Bea")
    assert client.patch(f"{base}/sources/{sid}", json={"collection_ids": ["C", "D"]}).status_code == 403
    assert client.get(f"{base}/sources/{sid}/wiki/collections").status_code == 403
    assert client.patch(f"{base}/sources/{sid}", json={"name": "Renamed"}).status_code == 200      # the rest stays with the brain admin
    app.dependency_overrides.clear()
    assert set(_docs(client, slug)) == {"c1", "c2"}
