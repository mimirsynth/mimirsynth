"""The embedding engine down is said for people: a 503 naming the engine and where to fix it, in Ask (recall), in the agents' recall and
in Answer, never a socket error such as «[WinError 10061]». Anything else that breaks a recall stays a 502 with its own text."""
import httpx

from test_control import client  # noqa: F401


class Down:
    def embed(self, texts):
        raise httpx.ConnectError("[WinError 10061] No se puede establecer una conexión")


def test_an_engine_that_does_not_answer_is_named_not_quoted(client, monkeypatch):  # noqa: F811
    from mimirsynth import recall
    assert client.post("/api/brains", json={"slug": "down1", "name": "Down1"}).status_code == 201
    monkeypatch.setattr(recall, "get_embedder", lambda: Down())
    for path in ("/api/brains/down1/recall", "/api/brains/down1/answer"):
        r = client.post(path, json={"query": "¿dónde corre el servicio de rutas?"})
        assert r.status_code == 503, (path, r.text)
        detail = r.json()["detail"]
        assert "motor de embeddings no responde" in detail and "Embeddings" in detail and "WinError" not in detail
    r = client.post("/api/brains/down1/recall", json={"query": "q"}, headers={"Accept-Language": "en"})
    assert r.status_code == 503 and "embedding engine is not answering" in r.json()["detail"]


def test_an_unexpected_failure_keeps_its_text(client, monkeypatch):  # noqa: F811
    from mimirsynth import recall

    class Broken:
        def embed(self, texts):
            raise ValueError("vector de dimensión inesperada")

    assert client.post("/api/brains", json={"slug": "down2", "name": "Down2"}).status_code == 201
    monkeypatch.setattr(recall, "get_embedder", lambda: Broken())
    r = client.post("/api/brains/down2/recall", json={"query": "q"})
    assert r.status_code == 502 and "dimensión inesperada" in r.json()["detail"]
