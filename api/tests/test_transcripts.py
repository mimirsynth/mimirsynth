"""Chat transcripts among documents (#466): detected while indexing, held without chunking until a person decides, and weighed less
in recall when indexed on request. The ranking itself runs against PostgreSQL in test_docs_pg.py."""
import uuid

import pytest

from test_control import client  # noqa: F401
from test_docs import MD, _upload, fake_index  # noqa: F401
from test_docsources import _FakeOutline, lib  # noqa: F401
from test_gitsource import _commit, origin  # noqa: F401

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


CHANGELOG = "\n\n".join(f"## [1.{i}.0](https://x.test/compare/v1.{i}) (2026-10-{i + 10:02d})\n\n### Features\n\n"
                          f"* **api:** add the export option number {i} ([#{i}](https://x.test/{i})) ([abc{i}](https://x.test/c/{i}))\n"
                          f"* **web:** show the new status in the list {i} ([#{i}](https://x.test/{i}))\n* allow longer names in sources {i}" for i in range(10))
PROS = "\n\n".join(f"**Ventajas:** el servicio arranca mucho más rápido en el nodo {i}\n**Inconvenientes:** gasta más memoria en el nodo {i}" for i in range(5))
ACTIONS = "# Acta de la reunión\n\n" + "\n".join(f"- {'Ana' if i % 2 else 'Luis'}: revisar la configuración del servidor {i} antes del lunes" for i in range(10))
LOG = "\n".join(f"2024-03-12 10:{i:02d}:03 {'INFO' if i % 2 else 'DEBUG'}: connection pool resized to {i} workers" for i in range(10))
BILINGUAL = "\n".join(f"Español: el documento se guarda en la carpeta {i}\nEnglish: the document is stored in folder {i}" for i in range(5))
EXAMPLES = "\n".join(f"**User:**\nuna pregunta de ejemplo {i}\n\n**Assistant:**\nuna respuesta de ejemplo {i}\n" for i in range(2))
PROMPT_GUIDE = ("# Guía de prompts\n\nCómo escribir buenos prompts.\n\n" + EXAMPLES + "\n"
                + "\n".join(f"Un párrafo largo de explicación, el número {i}, con su contenido." for i in range(150)))
SHORT_RUNBOOK = "# Reinicio del nodo\n\nCuando el nodo cae, avisa así al equipo:\n\n" + "\n".join(
    f"{'Ana' if i % 2 else 'Luis'}: el servidor vuelve a estar en marcha {i}" for i in range(6))
CHATGPT = "\n\n".join(f"{'You said:' if i % 2 == 0 else 'ChatGPT said:'}\n\nUn mensaje bastante largo, el número {i}." for i in range(8))


def test_detects_a_copied_chatgpt_conversation():
    assert transcripts.looks_like(CHATGPT)


@pytest.mark.parametrize("text", [MD, FAQ, FAQ_ES, CONFIG, SCORES, RUNBOOK, FEW, MONOLOGUE, "", CHANGELOG, PROS, ACTIONS, LOG, BILINGUAL,
                                  PROMPT_GUIDE, SHORT_RUNBOOK],
                         ids=["markdown", "faq", "faq-es", "config", "scores", "runbook", "too-few", "one-speaker", "empty", "changelog",
                              "pros-cons", "action-items", "log", "bilingual", "prompt-guide", "short-runbook"])
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


def test_forget_finds_a_held_transcript_by_its_stored_text(client, fake_index):
    """A held transcript has no chunks for the right to be forgotten to search: its stored text is read instead, so it is blocked and
    nobody can index it later with the forgotten person in it (#134)."""
    from mimirsynth import forget
    slug = _brain(client)
    _, r = _upload(client, slug, "chat.txt", (CHAT + "[11:00] Ana: Juan Pérez llamó para lo de la factura del servidor\n").encode())
    held = r.json()["id"]
    _, r = _upload(client, slug, "otro.txt", WHATSAPP.encode())
    other = r.json()["id"]
    with _factory()() as db:
        bid = db.get(Document, held).brain_id
        found = forget._named_documents(db, bid, forget.Matcher(["Juan Pérez"]), {})
        assert found == {held: 0}                                   # the other held one does not name him
        assert forget._named_documents(db, bid, forget.Matcher(["Juan Pérez"]), {held: 2}) == {held: 2}
        d = db.get(Document, held)
        d.status = "blocked"
        db.commit()
        assert forget._named_documents(db, bid, forget.Matcher(["Juan Pérez"]), {}) == {}   # already blocked: nothing to do again
    assert other != held
    assert client.post(f"/api/brains/{slug}/docs/{held}/transcript", json={"as": "transcript"}).status_code == 409


@pytest.mark.parametrize("text", ["user" + " " * 5000 + "x", " " * 100000 + "!", " " * 50000 + "-" + " " * 50000 + "!", "**a**" + " " * 100000 + "x",
                                  ("user" + " " * 1000 + "x\n") * 2000, ("a " * 150 + ":" + " x" * 100 + "\n") * 600],
                         ids=["role-tail", "lead", "dash", "heading-tail", "many-lines", "long-label"])
def test_hostile_text_does_not_stall_detection(text):
    import time
    t = time.monotonic()
    transcripts.looks_like(text)
    assert time.monotonic() - t < 1.0


def test_git_resync_keeps_both_choices(client, fake_index, origin):
    _commit(origin, {"docs/chat.md": CHAT, "docs/otro.md": WHATSAPP}, "chats")
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    sid = client.post(f"{base}/sources/git", json={"name": "Repo", "url": origin.as_uri()}).json()["id"]
    ds = _docs(client, slug)
    assert ds["docs/chat.md"]["status"] == ds["docs/otro.md"]["status"] == "transcript"
    client.post(f"{base}/{ds['docs/chat.md']['id']}/transcript", json={"as": "transcript"})
    client.post(f"{base}/{ds['docs/otro.md']['id']}/transcript", json={"as": "document"})
    _commit(origin, {"docs/chat.md": CHAT + "[11:00] Ana: y una cosa más que se me olvidaba decirte\n",
                     "docs/otro.md": WHATSAPP + "\n12/03/24, 11:00 - Ana: y una cosa más que contar del backup\n"}, "más")
    assert _scan(client, slug, sid)["changed"] == 2                                  # the files changed, and the metadata was rebuilt
    ds = _docs(client, slug)
    assert (ds["docs/chat.md"]["status"], ds["docs/chat.md"]["transcript"]) == ("active", "transcript")
    assert (ds["docs/otro.md"]["status"], ds["docs/otro.md"]["transcript"]) == ("active", "document")   # never detected again


def test_a_copy_inherits_the_choice_and_keeps_it_when_promoted(client, fake_index):
    slug = _brain(client)
    base = f"/api/brains/{slug}/docs"
    _, r = _upload(client, slug, "chat.txt", CHAT.encode())
    a = r.json()["id"]
    client.post(f"{base}/{a}/transcript", json={"as": "transcript"})
    _, r = _upload(client, slug, "copia.txt", (CHAT + "\n\n").encode())             # same text for the index, another file
    b = r.json()["id"]
    d = client.get(f"{base}/{b}").json()
    assert (d["status"], d["transcript"]) == ("duplicate", "transcript")
    assert client.delete(f"{base}/{a}").status_code == 200                           # the original goes: the copy is indexed as decided
    d = client.get(f"{base}/{b}").json()
    assert (d["status"], d["transcript"]) == ("active", "transcript") and d["chunks"] > 0


def test_ask_marks_a_conversation_passage():
    from mimirsynth import answer
    doc = {"title": "chat.txt", "heading_path": "", "document_id": 1, "chunk_idx": 0, "text": "Ana: hola"}
    sources, text = answer.evidence({"facts": [], "chunks": [], "documents": [{**doc, "transcript": True}, doc]})
    assert "[D1] chat conversation passage «chat.txt»" in text and "[D2] document passage «chat.txt»" in text
    assert sources[0]["transcript"] is True and "transcript" not in sources[1]


def test_import_with_vectors_leaves_a_held_transcript_unchunked(client, fake_index, tmp_path):
    import json

    from mimirsynth import brainimport
    slug = _brain(client)
    _, r = _upload(client, slug, "chat.txt", CHAT.encode())
    did = r.json()["id"]
    (tmp_path / "vectors").mkdir()
    (tmp_path / "vectors" / "doc_chunks.jsonl").write_text(json.dumps({"document_id": 7, "chunk_idx": 0, "text": "Ana: hola", "embedding": [0.1] * 4}) + "\n",
                                                           encoding="utf-8")
    job = type("J", (), {"check": lambda self: None, "progress": lambda self, *a: None, "note": lambda self, *a: None})()
    with _factory()() as db:
        bid = db.get(Document, did).brain_id
        assert brainimport._doc_chunks(job, db, tmp_path, bid, {7: did}, {did: CHAT}, reuse=True) == {"copied": 0, "computed": 0}
        assert db.get(Document, did).status == "transcript" and did not in fake_index


def test_the_secret_scan_reads_held_transcripts(client, fake_index):
    from mimirsynth import secretguard
    from mimirsynth.models import Brain
    slug = _brain(client)
    _upload(client, slug, "chat.txt", CHAT.encode())
    with _factory()() as db:
        brain = db.query(Brain).filter(Brain.slug == slug).one()
        assert secretguard.audit_existing(db, brain)["documents"] == 1
