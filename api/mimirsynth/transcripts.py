"""Chat transcripts among documents (#466). A raw conversation exported from a chat or a meeting is not curated documentation:
indexed like a page, its passages would come back in recall with the same weight as the documentation. While indexing, a
document whose text is mostly the turns of a conversation is held without chunking until a person decides.

The choice lives in `Document.meta["transcript"]`:
- absent: an ordinary document, or one never detected;
- "held": detected; not chunked, no embeddings, status `transcript`;
- "transcript": a person asked to index it as a conversation; its passages weigh `WEIGHT` in the ranking;
- "document": a person said it is not a conversation; indexed as an ordinary document and never checked again.
"""
import re

WEIGHT = 0.8          # rank of a conversation's passage against a document's of equal relevance (cf. recall.FED_WEIGHT)
HELD, TRANSCRIPT, DOCUMENT = "held", "transcript", "document"
CHOSEN = (TRANSCRIPT, DOCUMENT)   # what a person decided: detection never overrides it

MIN_TURNS = 8         # a page's example exchange is shorter
MIN_SWITCH = 0.5      # share of consecutive turns where the speaker changes
MIN_COVER = 0.6       # share of the text (in characters) inside the turns
MIN_WORDY = 0.5       # share of the turns that say something (3 words or more): «key: value» lists say one or two
MAX_CHARS = 200_000   # enough to tell; a huge file is not read to the end
MIN_ROLES = 4
MAX_LEAD = 0.25       # lines before the first role heading (an export's title and metadata)

# Every line is normalised first (`_line`): no leading or trailing blanks, one space between words, at most LINE_CHARS. The patterns
# below rely on it: single optional spaces instead of blank runs, so a hostile file cannot make them backtrack (ReDoS).
LINE_CHARS = 300
# a time stamp and/or a date before the speaker: «[10:15]», «12/03/24, 10:15 -», «2024-03-12 10:15:03»
_STAMP = r"(?:[\[(]?\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4},? ?)?(?:[\[(]?\d{1,2}:\d{2}(?::\d{2})? ?(?:[ap]\.? ?m\.?)?[\])]? ?)?"
_TURN = re.compile(r"^(?P<bullet>[-*>] )?(?P<stamp>" + _STAMP + r")(?:[-–] ?)?(?P<bold>\*\*|__)?(?P<who>[^\W\d_][\w .'’@()-]{0,39}?)(?:\*\*|__)? ?:(?:\*\*|__)? (?P<say>\S.*)$")
_ROLE = re.compile(r"^(?:#{1,6} |\*\*|__)?(?P<role>user|assistant|human|ai|chatgpt|gpt-?[\w.]*|claude|gemini|copilot|bot|you|tú|tu|usuario|asistente|yo)(?: said| dijo)?"
                   r"(?:\*\*|__)?:?(?:\*\*|__)?:?$", re.I)
_HEADING = re.compile(r"^(?:#{1,6} \S|(?:\*\*|__)[^*_]+(?:\*\*|__) ?:?$)")
# labels that are a document's keys, not people: FAQs, notes, configuration, runbooks
_KEYS = {
    "q", "a", "p", "r", "question", "answer", "pregunta", "respuesta", "note", "nota", "notes", "notas", "warning", "aviso", "tip", "consejo",
    "important", "importante", "example", "ejemplo", "e.g", "todo", "fixme", "status", "estado", "date", "fecha", "host", "hostname", "port",
    "puerto", "url", "path", "ruta", "version", "versión", "owner", "responsable", "description", "descripción", "title", "título", "name",
    "nombre", "type", "tipo", "error", "step", "paso", "result", "resultado", "input", "output", "entrada", "salida", "cause", "causa", "fix",
    "solution", "solución", "problem", "problema", "summary", "resumen", "goal", "objetivo", "context", "contexto", "decision", "decisión",
    "pros", "cons", "why", "por qué", "how", "cómo", "see", "ver", "source", "fuente", "default", "value", "valor", "command", "comando",
    "ventajas", "inconvenientes", "advantages", "disadvantages", "correcto", "incorrecto", "correct", "incorrect", "right", "wrong", "good",
    "bad", "do", "don't", "antes", "después", "before", "after", "síntoma", "diagnóstico", "symptom", "diagnosis", "added", "changed",
    "fixed", "removed", "deprecated", "security", "feat", "chore", "docs", "refactor", "perf", "test", "build", "ci", "info", "debug",
    "warn", "trace", "fatal", "critical", "notice", "message", "mensaje", "severity", "severidad", "level", "nivel", "id", "rule", "regla",
    "key", "clave", "kind", "español", "castellano", "english", "inglés", "français", "francés", "deutsch", "alemán", "português", "portugués",
    "català", "catalán", "euskara", "galego",
}
_ROLES = {"user", "assistant", "human", "ai", "chatgpt", "claude", "gemini", "copilot", "bot", "you", "tú", "tu", "usuario", "asistente", "yo"}


def _line(ln: str) -> str:
    return " ".join(ln.split())[:LINE_CHARS]


def kept(meta: dict | None) -> dict:
    """What a re-sync that rebuilds a document's metadata must carry over: the transcript mark, above all a person's choice."""
    v = (meta or {}).get("transcript")
    return {"transcript": v} if v in (HELD, *CHOSEN) else {}


def _speaker(m: re.Match) -> str | None:
    who = " ".join(m.group("who").split()).casefold()
    if not who or who in _KEYS or len(who.split()) > 4:
        return None
    if not m.group("stamp").strip() and (m.group("bullet") or (m.group("bold") and who not in _ROLES)):
        return None   # «- **api:** …» and «**Ventajas:** …» are a list's labels; a chat's bullet or bold turn carries its time
    return who


def _switches(seq: list[str]) -> float:
    return sum(1 for a, b in zip(seq, seq[1:]) if a != b) / max(len(seq) - 1, 1)


def _by_labels(lines: list[str]) -> bool:
    """Turns as «Speaker: what they said», one after another, with optional time stamps."""
    turns: list[tuple[str, str]] = []
    covered = in_turn = 0
    for ln in lines:
        if not ln:
            in_turn = 0
            continue
        m = _TURN.match(ln)
        who = _speaker(m) if m else None
        if who:
            turns.append((who, m.group("say"))); in_turn = 1
        covered += len(ln) if in_turn else 0
    if len(turns) < MIN_TURNS:
        return False
    seq = [w for w, _ in turns]
    counts: dict[str, int] = {}
    for w in seq:
        counts[w] = counts.get(w, 0) + 1
    if sum(1 for n in counts.values() if n >= 2) < 2 or len(counts) > max(2, len(seq) // 2):
        return False
    wordy = sum(1 for _, s in turns if len(s.split()) >= 3) / len(turns)
    return _switches(seq) >= MIN_SWITCH and covered / max(sum(len(ln) for ln in lines), 1) >= MIN_COVER and wordy >= MIN_WORDY


def _by_roles(lines: list[str]) -> bool:
    """An exported AI chat: a role on its own line («## User», «**Assistant:**») before each message."""
    body = [ln for ln in lines if ln]
    roles = [(i, m.group("role").casefold().split()[0]) for i, ln in enumerate(body) if (m := _ROLE.match(ln))]
    if len(roles) < MIN_ROLES or len({r for _, r in roles}) < 2 or _switches([r for _, r in roles]) < MIN_SWITCH:
        return False
    headings = sum(1 for ln in body if _HEADING.match(ln) or _ROLE.match(ln))
    covered = in_msg = 0   # a message runs from its role to the next heading that is not a role
    for ln in body:
        if _ROLE.match(ln):
            in_msg = 1
        elif _HEADING.match(ln):
            in_msg = 0
        covered += len(ln) if in_msg else 0
    first, last = roles[0][0], roles[-1][0]
    tail = len(body) - 1 - last   # after the last role, about one message: not a page that goes on after its examples
    return (len(roles) / max(headings, 1) >= MIN_COVER and first <= MAX_LEAD * len(body) and tail <= max(5, 3 * (last - first) / (len(roles) - 1))
            and covered / max(sum(len(ln) for ln in body), 1) >= MIN_COVER)


def looks_like(text: str) -> bool:
    """Whether a document's text is mostly a chat or meeting transcript. Errs on the side of «document»: a page with a short example
    dialogue, an FAQ or a list of keys stays a document, and a person can always decide otherwise."""
    lines = [_line(ln) for ln in (text or "")[:MAX_CHARS].splitlines()]
    return _by_labels(lines) or _by_roles(lines)
