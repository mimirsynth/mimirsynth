"""Detector de secretos (#116): encuentra credenciales en un texto antes de guardarlo en la memoria.

Solo biblioteca estándar y sin importar nada del paquete, para que un cliente (el plugin de agentes, un SDK) pueda llevarse este fichero
tal cual y redactar igual antes de enviar.

Dos clases de hallazgo:
- **Seguro** (`certain=True`): patrones con formato inconfundible (claves de nube, tokens de GitHub/GitLab, claves privadas PEM, JWT,
  cabeceras `Authorization`, URLs con usuario y contraseña). Son los únicos que se enmascaran o bloquean.
- **Posible** (`certain=False`): un valor de entropía alta asignado a una palabra como `password`, `secret` o `token`. Solo avisa: la
  entropía sola confundiría hashes, UUID e identificadores de contenedor, que son contenido legítimo en documentación técnica.

Nunca se devuelve el valor detectado fuera de `text[start:end]`: quien llame decide qué guarda (la regla y la posición, no el valor).
"""
import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    pattern: re.Pattern
    group: int = 0  # grupo del patrón que es el secreto (0 = todo)
    certain: bool = True


@dataclass(frozen=True)
class Finding:
    rule: str
    label: str
    start: int
    end: int
    certain: bool


def _rx(p: str, flags: int = 0) -> re.Pattern:
    return re.compile(p, flags)


RULES: list[Rule] = [
    Rule("private_key", "clave privada", _rx(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----[\s\S]*?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|\Z)")),
    Rule("aws_access_key", "clave de acceso de AWS", _rx(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")),
    Rule("github_token", "token de GitHub", _rx(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b")),
    Rule("gitlab_token", "token de GitLab", _rx(r"\bgl(?:pat|dt|rt|cbt|ptt|ft|imt|agent|oas)-[A-Za-z0-9_\-]{20,}")),
    Rule("slack_token", "token de Slack", _rx(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    Rule("slack_webhook", "webhook de Slack", _rx(r"https://hooks\.slack\.com/(?:services|workflows)/[A-Za-z0-9/_\-]{20,}")),
    Rule("google_api_key", "clave de API de Google", _rx(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    Rule("ai_api_key", "clave de API de un proveedor de IA", _rx(r"\bsk-(?:proj-|ant-(?:api|admin)\d\d-|or-v1-)?[A-Za-z0-9_\-]{32,}")),
    Rule("stripe_key", "clave de Stripe", _rx(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    Rule("npm_token", "token de npm", _rx(r"\bnpm_[A-Za-z0-9]{36}\b")),
    Rule("huggingface_token", "token de Hugging Face", _rx(r"\bhf_[A-Za-z0-9]{34,}\b")),
    Rule("telegram_bot_token", "token de bot de Telegram", _rx(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b")),
    Rule("sendgrid_key", "clave de SendGrid", _rx(r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b")),
    Rule("jwt", "JWT", _rx(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    Rule("authorization", "cabecera Authorization", _rx(r"\bauthorization\s*[:=]\s*[\"']?(?:bearer|basic|token|bot)\s+([A-Za-z0-9._~+/=\-]{8,})", re.IGNORECASE), group=1),
    Rule("url_credentials", "contraseña en una URL", _rx(r"\b[a-z][a-z0-9+.\-]{1,20}://[^\s:/@\"'<>]{1,128}:([^\s@/\"'<>]{1,256})@[^\s@/\"'<>]", re.IGNORECASE), group=1),
    Rule("assigned_secret", "posible secreto asignado", _rx(
        r"\b(?:[a-z0-9]+[_\-.])*(?:password|passwd|pwd|secret|token|api[_\-.]?key|access[_\-.]?key|private[_\-.]?key|client[_\-.]?secret|auth)"
        r"(?:[_\-.][a-z0-9]+)*[\"']?\s*(?::=|=|:)\s*[\"']?([^\s\"'`,;<>(){}\[\]]{12,256})", re.IGNORECASE), group=1, certain=False),
]
BY_ID = {r.id: r for r in RULES}

# Valores que tienen forma de secreto pero son marcadores o ejemplos de documentación.
_PLACEHOLDER = re.compile(r"example|placeholder|changeme|your[_\-]?|xxxx|\*{3}|\.\.\.|<[^>]*>|\$\{|\{\{|%\(|^\$[A-Za-z_]", re.IGNORECASE)


def entropy(s: str) -> float:
    """Entropía de Shannon por carácter."""
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))


def _looks_random(v: str) -> bool:
    """Un valor asignado a «password» que parece generado y no una palabra o una ruta."""
    classes = sum(bool(re.search(p, v)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if "/" in v and not re.search(r"[A-Za-z0-9+/]{20,}={0,2}$", v):
        return False  # una ruta
    return classes >= 3 and entropy(v) >= 3.0


def parse_allow(lines: str) -> tuple[set[str], list[re.Pattern]]:
    """Excepciones de un brain: una por línea. `rule:<id>` desactiva una regla; cualquier otra línea es una expresión regular que, si
    encaja en el valor detectado, lo da por bueno. Lanza ValueError con la línea que no se entiende."""
    off, pats = set(), []
    for raw in (lines or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("rule:"):
            rid = line[5:].strip()
            if rid not in BY_ID:
                raise ValueError(f"regla desconocida: {rid}")
            off.add(rid)
            continue
        try:
            pats.append(re.compile(line))
        except re.error as e:
            raise ValueError(f"expresión no válida «{line[:60]}»: {e}") from e
    return off, pats


def scan(text: str, allow: str = "") -> list[Finding]:
    """Hallazgos ordenados por posición y sin solaparse (si dos reglas cubren el mismo trozo, gana la que empieza antes y es segura)."""
    off, pats = parse_allow(allow)
    found: list[Finding] = []
    for r in RULES:
        if r.id in off:
            continue
        for m in r.pattern.finditer(text or ""):
            a, b = m.span(r.group)
            v = text[a:b]
            if _PLACEHOLDER.search(v) or any(p.search(v) for p in pats):
                continue
            if r.id == "url_credentials" and v.lower() in {"password", "pass", "secret", "pwd"}:
                continue
            if not r.certain and not _looks_random(v):
                continue
            found.append(Finding(r.id, r.label, a, b, r.certain))
    found.sort(key=lambda f: (f.start, not f.certain, -(f.end - f.start)))
    out: list[Finding] = []
    for f in found:
        if out and f.start < out[-1].end:
            continue
        out.append(f)
    return out


def redact(text: str, findings: list[Finding], marker: str = "[secreto eliminado: {label}]", labels=None, everything: bool = False,
           spans: list | None = None) -> str:
    """Sustituye los hallazgos seguros (o todos, con `everything`) por el marcador; los posibles se dejan como están.
    Si se pasa `spans`, añade `(hallazgo, inicio, fin, enmascarado)` con la posición de cada uno en el texto resultante."""
    out, last, pos = [], 0, 0
    for f in findings:
        out.append(text[last:f.start])
        pos += f.start - last
        mask = f.certain or everything
        piece = marker.format(label=(labels or {}).get(f.rule, f.label), rule=f.rule) if mask else text[f.start:f.end]
        out.append(piece)
        if spans is not None:
            spans.append((f, pos, pos + len(piece), mask))
        pos += len(piece)
        last = f.end
    out.append(text[last:])
    return "".join(out)
