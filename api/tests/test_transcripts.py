"""Chat transcripts among documents (#466): detected while indexing, held without chunking until a person decides, and weighed less
in recall when indexed on request. The ranking itself runs against PostgreSQL in test_docs_pg.py."""
import uuid

import pytest

from test_control import client  # noqa: F401
from test_docs import MD, _upload, fake_index  # noqa: F401
from test_docsources import _FakeOutline, lib  # noqa: F401

from mimirsynth import recall, transcripts
from mimirsynth.models import Document
from mimirsynth.store import _factory

CHAT = "\n".join(f"[10:{i:02d}] {'Ana' if i % 2 else 'Luis'}: vale, mañana reviso el servidor {i} y te cuento qué ha pasado" for i in range(12)) + "\n"
WHATSAPP = "\n".join(f"12/03/24, 10:{i:02d} - {'Ana' if i % 2 else 'Luis'}: el backup {i} ya ha terminado bien" for i in range(8))
MEETING = "\n\n".join(f"{'Speaker 1' if i % 2 else 'Speaker 2'}: creo que deberíamos mover la base de datos al otro nodo" for i in range(8))
AI_LABELS = "\n\n".join(f"{'User' if i % 2 == 0 else 'Assistant'}: una pregunta o una respuesta bastante larga, la número {i}" for i in range(8))
AI_ROLES = "# Chat export\n\nExported 2026-11-20\n\n" + "\n\n".join(
    f"## {'User' if i % 2 == 0 else 'Assistant'}\n\nUn mensaje largo, el número {i}.\n\nCon un segundo párrafo." for i in range(6))
FAQ = "\n".join(f"Q: ¿Cómo se reinicia el servicio {i}?\nA: Con systemctl restart y esperando un minuto {i}." for i in range(8))
FAQ_ES = "\n\n".join(f"Pregunta: ¿qué hago si falla el paso {i}?\nRespuesta: revisa los registros del paso {i} antes de nada." for i in range(6))
CONFIG = "\n".join(f"Host: h{i}\nUser: root\nPort: 22" for i in range(6))
SCORES = "\n".join("Ana: 3\nLuis: 4" for _ in range(6))
RUNBOOK = ("# Runbook\n\n" + "Un paso normal del procedimiento, con su explicación.\n" * 40 + "\nEjemplo de aviso al equipo:\n\n"
           + "\n".join(f"{'Ana' if i % 2 else 'Luis'}: el servidor vuelve a estar en marcha {i}" for i in range(6)))
FEW = "\n".join(f"{'Ana' if i % 2 else 'Luis'}: hola, qué tal va el servidor" for i in range(4))
MONOLOGUE = "\n".join(f"Ana: nota número {i} sobre el servidor de copias" for i in range(10))


@pytest.mark.parametrize("text", [CHAT, WHATSAPP, MEETING, AI_LABELS, AI_ROLES], ids=["stamps", "whatsapp", "meeting", "ai-labels", "ai-roles"])
def test_detects_transcripts(text):
    assert transcripts.looks_like(text)


@pytest.mark.parametrize("text", [MD, FAQ, FAQ_ES, CONFIG, SCORES, RUNBOOK, FEW, MONOLOGUE, ""],
                         ids=["markdown", "faq", "faq-es", "config", "scores", "runbook", "too-few", "one-speaker", "empty"])
def test_documents_stay_documents(text):
    assert not transcripts.looks_like(text)


def test_kept_only_carries_the_mark():
    assert transcripts.kept({"transcript": "transcript", "ocr": {}}) == {"transcript": "transcript"}
    assert transcripts.kept({"transcript": "held"}) == {"transcript": "held"}
    assert transcripts.kept({"transcript": "raro"}) == {} and transcripts.kept(None) == {}


def _brain(client):
    slug = "t" + uuid.uuid4().hex[:8]
    assert client.post("/api/brains", json={"slug": slug, "name": slug, "graph_name": "g-" + slug}).status_code == 201
    return slug


def test_upload_holds_a_transcript_until_a_person_decides(client, fake_index):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    _, r = _upload(client, slug, "chat.txt", CHAT.encode())
    doc = r.json()
    d = client.get(f"{base}/{doc['id']}").json()
    assert (d["status"], d["chunks"], d["transcript"]) == ("transcript", 0, "held") and doc["id"] not in fake_index   # not chunked
    assert client.get(f"{base}/{doc['id']}/text").json()["text"].startswith("[10:00] Luis:")                          # but readable
    assert client.get(base, params={"status": "transcript"}).json()["status_counts"]["transcript"] == 1
    assert client.post(f"{base}/{doc['id']}/reindex").status_code == 200                                             # reindexing looks again
    assert client.get(f"{base}/{doc['id']}").json()["status"] == "transcript"

    assert client.post(f"{base}/{doc['id']}/transcript", json={"as": "transcript"}).status_code == 200
    d = client.get(f"{base}/{doc['id']}").json()
    assert (d["status"], d["transcript"]) == ("active", "transcript") and d["chunks"] > 0 and len(fake_index[doc["id"]]) == d["chunks"]
    assert client.post(f"{base}/{doc['id']}/reindex").status_code == 200                                             # the choice stands
    assert client.get(f"{base}/{doc['id']}").json()["status"] == "active"

    assert client.post(f"{base}/{doc['id']}/transcript", json={"as": "document"}).status_code == 200
    d = client.get(f"{base}/{doc['id']}").json()
    assert (d["status"], d["transcript"]) == ("active", "document") and d["chunks"] > 0
    from mimirsynth.models import Audit
    with _factory()() as db:
        acts = [a.detail for a in db.query(Audit).filter(Audit.action == "document.transcript")]
    assert {"id": doc["id"], "index_as": "transcript"} in acts and {"id": doc["id"], "index_as": "document"} in acts


def test_an_ordinary_document_is_not_held(client, fake_index):
    slug = _brain(client)
    _, r = _upload(client, slug, "guia.md", MD.encode())
    d = client.get(f"/api/brains/{slug}/docs/{r.json()['id']}").json()
    assert d["status"] == "active" and d["transcript"] is None


def test_choice_refused(client, fake_index):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    _, r = _upload(client, slug, "chat.txt", CHAT.encode())
    did = r.json()["id"]
    assert client.post(f"{base}/{did}/transcript", json={"as": "otro"}).status_code == 422
    assert client.post(f"{base}/{did}/transcript", json={}).status_code == 422
    assert client.post(f"{base}/999999/transcript", json={"as": "document"}).status_code == 404
    tok = client.post(f"/api/brains/{slug}/tokens", json={"name": "c", "role": "contributor"}).json()["token"]
    assert client.post(f"{base}/{did}/transcript", json={"as": "document"}, headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    for status in ("indexing", "blocked"):
        with _factory()() as db:
            db.get(Document, did).status = status
            db.commit()
        assert client.post(f"{base}/{did}/transcript", json={"as": "document"}).status_code == 409
    with _factory()() as db:
        assert (db.get(Document, did).meta or {}).get("transcript") == "held"     # nothing changed on a refusal


def _docs(client, slug):
    return {d["external_id"]: d for d in client.get(f"/api/brains/{slug}/docs").json()["items"]}


def _scan(client, slug, sid):
    return client.get(f"/api/brains/{slug}/jobs/{client.post(f'/api/brains/{slug}/docs/sources/{sid}/scan').json()['job']}").json()["result"]


def test_folder_rescan_keeps_the_choice_and_looks_again_at_a_held_file(client, lib):
    (lib / "chat.txt").write_text(CHAT, encoding="utf-8", newline="")
    (lib / "otro.txt").write_text(WHATSAPP, encoding="utf-8", newline="")
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    sid = client.post(f"{base}/sources", json={"name": "Notas", "root": "notas"}).json()["id"]
    ds = _docs(client, slug)
    assert ds["chat.txt"]["status"] == ds["otro.txt"]["status"] == "transcript" and ds["a.md"]["status"] == "active"
    client.post(f"{base}/{ds['chat.txt']['id']}/transcript", json={"as": "transcript"})
    (lib / "chat.txt").write_text(CHAT + "[11:00] Ana: y una cosa más que se me olvidaba decirte\n", encoding="utf-8", newline="")
    (lib / "otro.txt").write_text("# Otra guía\n\nYa no es una conversación, sino una nota normal.\n", encoding="utf-8", newline="")  # no longer a chat
    assert _scan(client, slug, sid)["changed"] == 2
    ds = _docs(client, slug)
    assert (ds["chat.txt"]["status"], ds["chat.txt"]["transcript"]) == ("active", "transcript")
    assert (ds["otro.txt"]["status"], ds["otro.txt"]["transcript"]) == ("active", None)


def test_wiki_rescan_keeps_the_choice(client, lib, monkeypatch):
    from mimirsynth import wikis
    fake = _FakeOutline()
    fake.pages["p5"] = ("Chat del despliegue", CHAT, "2026-10-21T10:00:00.000Z", "c1")
    monkeypatch.setattr(wikis.httpx, "post", fake)
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    conn = {"adapter": "outline", "values": {"base_url": "https://wiki.test", "api_key": "clave-de-prueba"}}
    sid = client.post(f"{base}/sources/wiki", json={**conn, "name": "Outline", "collection_ids": ["c1"]}).json()["id"]
    chat = _docs(client, slug)["p5"]
    assert chat["status"] == "transcript"
    client.post(f"{base}/{chat['id']}/transcript", json={"as": "transcript"})
    fake.pages["p5"] = ("Chat del despliegue", CHAT, "2026-10-22T10:00:00.000Z", "c1")   # only the date: the metadata is rebuilt
    assert _scan(client, slug, sid)["unchanged"] == 3
    assert _docs(client, slug)["p5"]["transcript"] == "transcript"
    fake.pages["p5"] = ("Chat del despliegue", CHAT + "[11:00] Ana: y otra cosa más que se me olvidaba\n", "2026-10-23T10:00:00.000Z", "c1")
    assert _scan(client, slug, sid)["changed"] == 1
    p5 = _docs(client, slug)["p5"]
    assert (p5["status"], p5["transcript"]) == ("active", "transcript")


def test_brain_import_leaves_a_held_transcript_unchunked(client, fake_index):
    from mimirsynth import brainimport
    slug = _brain(client)
    _, r = _upload(client, slug, "chat.txt", CHAT.encode())
    did = r.json()["id"]
    job = type("J", (), {"check": lambda self: None, "progress": lambda self, *a: None, "note": lambda self, *a: None})()
    with _factory()() as db:
        bid = db.get(Document, did).brain_id
        out = brainimport._doc_chunks(job, db, None, bid, {}, {did: CHAT}, reuse=False)
        assert out == {"copied": 0, "computed": 0} and db.get(Document, did).status == "transcript" and did not in fake_index


def test_recall_says_a_passage_is_a_conversation():
    p = {"title": "chat.txt", "heading_path": "", "page": None, "document_id": 1, "chunk_idx": 0, "text": "Ana: hola"}
    assert "conversación de chat" in recall.docs_block([{**p, "transcript": True}], "es")
    assert "chat conversation" in recall.docs_block([{**p, "transcript": True}], "en")
    assert "conversación" not in recall.docs_block([p], "es")
