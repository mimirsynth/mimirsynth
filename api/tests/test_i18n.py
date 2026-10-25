"""El catálogo inglés del servidor cubre todos los textos que la API muestra, y cada traducción conserva sus {{valores}}."""
import json
import re
from pathlib import Path

from test_control import client  # noqa: F401

from mimirsynth import i18n_extract

WEB = Path(i18n_extract.CATALOG).parent


def test_server_catalog_is_complete_and_consistent():
    cat = json.loads((WEB / "en.server.json").read_text())
    keys = i18n_extract.collect()
    assert sorted(k for k in keys if k not in cat) == [], "faltan traducciones: python -m mimirsynth.i18n_extract --missing"
    assert sorted(k for k in cat if k not in keys) == [], "sobran claves en en.server.json"
    for k, v in cat.items():
        assert v.strip(), k
        assert sorted(re.findall(r"\{\{(\w+)\}\}", k)) == sorted(re.findall(r"\{\{(\w+)\}\}", v)), k


def test_ui_catalog_keeps_placeholders():
    cat = json.loads((WEB / "en.json").read_text())
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
