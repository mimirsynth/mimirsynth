"""Detector de secretos (#116). Los valores de prueba se montan concatenando, para que el código fuente no lleve nada con forma de
credencial real (lo detectarían los escáneres del repositorio)."""
import pytest

from mimirsynth import secretscan as S

R = "A1b2C3d4E5f6G7h8J9k0"  # relleno con forma aleatoria
CASES = {
    "private_key": "-----BEGIN RSA " + "PRIVATE KEY-----\nMIIEow" + R + "\n-----END RSA " + "PRIVATE KEY-----",
    "aws_access_key": "AKIA" + "Q7RZ4M2K9WXP3T6N",
    "github_token": "ghp_" + R + R[:16],
    "gitlab_token": "glpat-" + R,
    "slack_token": "xoxb-" + "1234567890-" + R,
    "slack_webhook": "https://hooks.slack.com/services/" + "T0A1B2C3D/B0E1F2G3H/" + R,
    "google_api_key": "AIza" + R + R[:15],
    "ai_api_key": "sk-proj-" + R + R,
    "stripe_key": "sk_" + "live_" + R,
    "npm_token": "npm_" + R + R[:16],
    "huggingface_token": "hf_" + R + R[:14],
    "telegram_bot_token": "123456789:AA" + R + R[:13],
    "sendgrid_key": "SG." + R + "Ab." + R + R + "Abc",
    "jwt": "eyJ" + "hbGciOiJIUzI1NiJ9.eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0." + R,
}


@pytest.mark.parametrize("rule,value", CASES.items())
def test_each_rule_detects_and_masks(rule, value):
    text = f"Nota: el valor es {value} y nada más."
    f = S.scan(text)
    assert [x.rule for x in f] == [rule]
    assert text[f[0].start:f[0].end] == value and f[0].certain
    red = S.redact(text, f)
    assert value not in red and f"[secreto eliminado: {S.BY_ID[rule].label}]" in red and red.endswith("y nada más.")


def test_authorization_and_url_mask_only_the_credential():
    text = "curl -H 'Authorization: Bearer " + R + "' https://api.local\npostgresql://app:" + "s3cr3t-Pa55" + "@db:5432/app"
    f = S.scan(text)
    assert [x.rule for x in f] == ["authorization", "url_credentials"]
    red = S.redact(text, f, marker="[{rule}]")
    assert red == "curl -H 'Authorization: Bearer [authorization]' https://api.local\npostgresql://app:[url_credentials]@db:5432/app"


def test_assigned_secret_is_only_possible_and_never_masked():
    text = "DB_PASSWORD=" + "Zq8!mW2#pL5v" + "\nservice_token: " + "4f9c2a7e-1b3d-4c8e-9a6f-2d5b7e1c3a9f"
    f = S.scan(text)
    assert [(x.rule, x.certain) for x in f] == [("assigned_secret", False), ("assigned_secret", False)]
    assert S.redact(text, f) == text


@pytest.mark.parametrize("text", [
    "sha256: 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",   # suma: sin palabra clave
    "Contenedor 4f9c2a7e1b3d en el host altair",                                     # id de contenedor
    "uuid 4f9c2a7e-1b3d-4c8e-9a6f-2d5b7e1c3a9f del brain",                           # UUID suelto
    "password: hunter2",                                                             # demasiado corto
    "token = ${GITHUB_TOKEN}",                                                       # referencia a variable
    "password: <tu-contraseña-aquí>",                                                # marcador
    "secret_path = /etc/mimirsynth/keys/session.key",                                # una ruta
    "AKIA" + "IOSFODNN7EXAMPLE",                                                     # ejemplo de la documentación de AWS
    "postgresql://user:password@localhost/db",                                       # marcador en la URL
    "authorization: bearer <token>",                                                 # marcador en la cabecera
    "La task-runner-de-ejemplo y el disk-usage no son claves",                       # «sk-» dentro de palabras
    "author: Rafa Puerta",                                                           # «auth» dentro de otra palabra
])
def test_no_false_positives(text):
    assert S.scan(text) == []


def test_allow_list_by_rule_and_by_value():
    text = "a " + CASES["github_token"] + " b " + CASES["jwt"]
    assert {f.rule for f in S.scan(text, "rule:jwt")} == {"github_token"}
    assert {f.rule for f in S.scan(text, "# comentario\n^ghp_")} == {"jwt"}
    with pytest.raises(ValueError, match="regla desconocida"):
        S.parse_allow("rule:nada")
    with pytest.raises(ValueError, match="expresión no válida"):
        S.parse_allow("([")


def test_overlaps_keep_one_finding():
    text = "Authorization: Bearer " + CASES["jwt"]
    assert len(S.scan(text)) == 1
    assert S.redact(text, S.scan(text), marker="X") == "Authorization: Bearer X"


def test_empty_and_labels():
    assert S.scan("") == [] and S.redact("", []) == ""
    f = S.scan(CASES["npm_token"])
    assert S.redact(CASES["npm_token"], f, marker="[{label}]", labels={"npm_token": "npm token"}) == "[npm token]"


def test_long_separator_runs_stay_linear():
    """Un prefijo sin límite en `assigned_secret` hacía la búsqueda cuadrática: 100 KB de «ab-» tardaban más de dos minutos."""
    import time
    t0 = time.time()
    assert S.scan("ab-" * 33000) == [] and S.scan("a-" * 10000) == []
    assert time.time() - t0 < 1.0


def test_quoted_pem_header_masks_nothing():
    text = "Para buscar claves: grep '-----BEGIN PRIVATE KEY-----' en los ficheros.\n" + "texto normal " * 100
    assert S.scan(text) == []
    assert [f.rule for f in S.scan(CASES["private_key"] + "\n\nY después sigue la nota.")] == ["private_key"]


def test_allow_list_rejects_patterns_that_accept_everything():
    for broad in (".*", ".", "\S", "[a-z]*"):
        with pytest.raises(ValueError, match="cualquier valor"):
            S.parse_allow(broad)
    with pytest.raises(ValueError, match="demasiado larga"):
        S.parse_allow("x" * 201)
    S.parse_allow("^ghp_\nrule:jwt")
