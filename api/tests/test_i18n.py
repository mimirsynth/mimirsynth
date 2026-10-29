"""El catálogo inglés del servidor cubre todos los textos que la API muestra, y cada traducción conserva sus {{valores}}."""
import json
import re
from pathlib import Path

from test_control import client  # noqa: F401

from mimirsynth import i18n_extract

WEB = Path(i18n_extract.CATALOG).parent


def test_server_catalog_is_complete_and_consistent():
    cat = json.loads((WEB / "en.server.json").read_text(encoding="utf-8"))
    keys = i18n_extract.collect()
    assert sorted(k for k in keys if k not in cat) == [], "faltan traducciones: python -m mimirsynth.i18n_extract --missing"
    assert sorted(k for k in cat if k not in keys) == [], "sobran claves en en.server.json"
    for k, v in cat.items():
        assert v.strip(), k
        assert sorted(re.findall(r"\{\{(\w+)\}\}", k)) == sorted(re.findall(r"\{\{(\w+)\}\}", v)), k


def test_ui_catalog_keeps_placeholders():
    cat = json.loads((WEB / "en.json").read_text(encoding="utf-8"))
    for k, v in cat.items():
        assert v.strip(), k
        assert sorted(re.findall(r"\{\{(\w+)\}\}", k)) == sorted(re.findall(r"\{\{(\w+)\}\}", v)), k


def test_mails_and_profile_language(client, monkeypatch):  # noqa: F811
    from mimirsynth import mail, userlib
    sent = []
    monkeypatch.setattr(mail, "try_send", lambda to, subject, body: sent.append((subject, body)) or True)
    class U:  # noqa: N801
        locale = "en"
    userlib.email_invite("a@example.com", "Ana", "https://x/acceso/t", "invite", U())
    assert sent[-1][0].startswith("You have been invited") and "single use" in sent[-1][1]
    U.locale = ""
    from mimirsynth.config import settings
    monkeypatch.setattr(settings, "default_language", "es")
    userlib.email_invite("a@example.com", "Ana", "https://x/acceso/t", "reset")
    assert sent[-1][0].startswith("Restablece")  # idioma por defecto de la instancia: español
    assert client.patch("/api/me/profile", json={"locale": "en"}).status_code == 200
    assert client.get("/api/me/profile").json()["locale"] == "en"
    assert client.patch("/api/me/profile", json={"locale": "fr"}).status_code == 422
    client.patch("/api/me/profile", json={"locale": ""})


def test_language_priority_and_translation(monkeypatch):
    from starlette.requests import Request

    from mimirsynth import i18n
    from mimirsynth.config import settings
    assert i18n._accepted("en-GB;q=0.8, es-ES, *;q=0.5, fr;q=0") == ["es", "en"]
    assert i18n._accepted("*") == [] and i18n._accepted("") == []

    def req(header="", locale=""):
        r = Request({"type": "http", "headers": [(b"accept-language", header.encode())] if header else []})
        r.state.locale = locale
        return r
    monkeypatch.setattr(settings, "default_language", "es")
    assert i18n.language(req()) == "es"                                  # la instancia
    assert i18n.language(req(locale="en")) == "en"                       # la persona manda sobre la instancia
    assert i18n.language(req("es-ES,es;q=0.9", locale="en")) == "es"     # y la cabecera, sobre la persona
    assert i18n.language(req("fr, *", locale="en")) == "en"              # un idioma sin catálogo no cuenta
    # mensajes ya formados: exactos o con plantilla (y el valor interpolado también se traduce si es un texto del servidor)
    assert i18n.translate("token inválido", "en") == "invalid token" and i18n.translate("token inválido", "es") == "token inválido"
    assert i18n.translate("requiere rol curator o superior", "en") == "requires role curator or higher"
    assert i18n.translate("un texto que no está en el catálogo", "en") == "un texto que no está en el catálogo"
    assert i18n.tr("método no soportado: {{method}}", "en", method="x/y") == "unsupported method: x/y"
    assert i18n.tr("método no soportado: {{method}}", "es", method="x/y") == "método no soportado: x/y"


def test_api_errors_follow_the_caller(client, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from mimirsynth.config import settings
    from mimirsynth.main import app
    monkeypatch.setattr(settings, "default_language", "es")
    anon = TestClient(app)
    bad = {"Authorization": "Bearer mst_falso"}
    assert anon.get("/api/brains", headers=bad).json()["detail"] == "token inválido"
    assert anon.get("/api/brains", headers={**bad, "Accept-Language": "en-US,en;q=0.9"}).json()["detail"] == "invalid token"
    monkeypatch.setattr(settings, "default_language", "en")
    assert anon.get("/api/brains", headers=bad).json()["detail"] == "invalid token"
    # un token habla el idioma de su dueño, aunque la instancia esté en español
    monkeypatch.setattr(settings, "default_language", "es")
    client.post("/api/brains", json={"slug": "lang1", "name": "L"})
    tok = client.post("/api/brains/lang1/tokens", json={"name": "t", "role": "reader"}).json()["token"]
    agent = TestClient(app, headers={"Authorization": f"Bearer {tok}"})
    assert agent.get("/api/brains/otro/overview").json()["detail"] == "brain no encontrado"
    client.patch("/api/me/profile", json={"locale": "en"})
    try:
        assert agent.get("/api/brains/otro/overview").json()["detail"] == "brain not found"
        assert agent.get("/api/brains/otro/overview", headers={"Accept-Language": "es"}).json()["detail"] == "brain no encontrado"
        # el MCP también: descripciones de las herramientas, instrucciones y errores del protocolo
        rpc = lambda method, **p: agent.post("/api/brains/lang1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": p}).json()  # noqa: E731
        tools = rpc("tools/list")["result"]["tools"]
        assert tools[0]["title"] == "Query the memory" and tools[0]["inputSchema"]["properties"]["query"]["description"].startswith("What you want")
        assert "Use `recall`" in rpc("initialize", protocolVersion="2025-06-18")["result"]["instructions"]
        assert rpc("no/existe")["error"]["message"] == "unsupported method: no/existe"
    finally:
        client.patch("/api/me/profile", json={"locale": ""})
    assert agent.post("/api/brains/lang1/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"][0]["title"] == "Consultar la memoria"


def test_recall_context_headings_follow_the_caller():
    from mimirsynth.recall import build_context
    facts = [{"fact": "Plex corre en Antares", "status": "current", "valid_at": "2026-01-01T00:00:00Z", "created_at": None, "origin": "otro"},
             {"fact": "Plex corría en Notus", "status": "invalidated", "valid_at": "2025-01-01T00:00:00Z", "invalid_at": "2026-01-01T00:00:00Z"}]
    passages = [{"title": "Guía", "heading_path": "", "page": None, "document_id": 1, "chunk_idx": 2, "text": "texto"}]
    en = build_context(facts, [], 6000, passages, lang="en")
    assert "## Current facts\n- Plex corre en Antares (since 2026-01-01) · from «otro»" in en   # el hecho se queda como se guardó
    assert "- Plex corría en Notus (valid 2025-01-01 → invalidated 2026-01-01)" in en and "## Documents" in en and "[doc 1, chunk 2]" in en
    es = build_context(facts, [], 6000, passages)
    assert "## Hechos vigentes\n- Plex corre en Antares (desde 2026-01-01) · de «otro»" in es and "[doc 1, trozo 2]" in es
