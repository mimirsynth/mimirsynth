"""Extracción de texto y troceado de documentos. Los trozos llevan su posición (char_start/char_end) dentro del texto normalizado,
la ruta de títulos y, si el formato tiene páginas, la página."""
import re
from html.parser import HTMLParser
from pathlib import Path

from . import appsettings
from .config import settings
from .docstore import HTML_EXT, PDF_EXT, TEXT_EXT

PAGE_BREAK = "\f"
CHUNK_SIZE = 900
OVERLAP = 120
MIN_CHUNK = 60


class ExtractError(ValueError):
    pass


class _Html(HTMLParser):
    """HTML -> texto con títulos en Markdown (#), listas con guiones y párrafos separados por línea en blanco."""
    SKIP = {"script", "style", "noscript", "svg", "head"}
    BLOCK = {"p", "div", "section", "article", "table", "tr", "ul", "ol", "pre", "blockquote", "header", "footer", "main", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False

    def _nl(self, n=2):
        if self.out and not "".join(self.out[-2:]).endswith("\n" * n):
            self.out.append("\n" * n)

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.skip += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self._nl(); self.out.append("#" * int(tag[1]) + " ")
        elif tag == "li":
            self._nl(1); self.out.append("- ")
        elif tag == "br":
            self.out.append("\n")
        elif tag in self.BLOCK:
            self._nl()

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif re.fullmatch(r"h[1-6]", tag) or tag in self.BLOCK:
            self._nl()
        elif tag == "li":
            self._nl(1)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skip:
            self.out.append(re.sub(r"[ \t\r\n]+", " ", data) if not self.out or not self.out[-1].endswith("\n") else re.sub(r"[ \t\r\n]+", " ", data).lstrip())


def _decode(raw: bytes) -> str:
    if b"\x00" in raw[:8192]:
        raise ExtractError("el fichero no es de texto")
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1")


def _normalize(t: str) -> str:
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip() + "\n"


_FRONT = re.compile(r"\A---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*\n", re.S)


def _markdown(text: str) -> tuple[str, str]:
    """Markdown con convenciones de Obsidian y similares: quita el frontmatter YAML (tomando `title:` si lo hay), deja el texto visible de los
    [[enlaces internos]] y descarta incrustaciones ![[...]], comentarios %%...%% y marcas de bloque ^id."""
    title = ""
    m = _FRONT.match(text)
    if m:
        t = re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", m.group(1), re.M)
        title = t.group(1).strip() if t else ""
        text = text[m.end():]
    text = re.sub(r"%%.*?%%", "", text, flags=re.S)
    text = re.sub(r"!\[\[[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[([^\]|#]*)(?:#[^\]|]*)?\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]|]+)\]\]", lambda mm: mm.group(1).replace("#", " › "), text)
    text = re.sub(r"[ \t]+\^[\w-]+$", "", text, flags=re.M)
    return text, title


def extract(path: Path, ext: str) -> tuple[str, str]:
    """Devuelve (texto normalizado, título sugerido). El texto de un PDF separa páginas con \\f."""
    cap = appsettings.get("doc_text_max_mb") * 1024 * 1024
    ext = ext.lower()
    if ext in PDF_EXT:
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise ExtractError("leer PDF requiere el extra opcional «pdf» (pypdf)") from e
        try:
            rd = PdfReader(str(path))
            pages = [(p.extract_text() or "").strip() for p in rd.pages]
        except Exception as e:  # noqa: BLE001
            raise ExtractError(f"PDF ilegible: {str(e)[:120]}") from e
        text = PAGE_BREAK.join(pages)
        title = str((rd.metadata or {}).get("/Title") or "") if rd.metadata else ""
        if not text.replace(PAGE_BREAK, "").strip():
            raise ExtractError("el PDF no tiene texto extraíble (¿escaneado?)")
        return text, title.strip()
    if path.stat().st_size > cap:
        raise ExtractError(f"el fichero supera el máximo de texto ({appsettings.get('doc_text_max_mb')} MB)")
    raw = path.read_bytes()
    if ext in HTML_EXT:
        p = _Html(); p.feed(_decode(raw)); p.close()
        return _normalize("".join(p.out)), p.title.strip()
    if ext in TEXT_EXT:
        raw_text = _decode(raw)
        front_title = ""
        if ext in (".md", ".markdown"):
            raw_text, front_title = _markdown(raw_text)
        text = _normalize(raw_text)
        m = re.search(r"^#\s+(.+)$", text, re.M)
        return text, front_title or (m.group(1).strip() if m else "")
    raise ExtractError(f"formato no admitido: {ext or 'sin extensión'}")


_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _sections(text: str):
    """Divide en secciones por títulos Markdown (ignorando bloques de código). Devuelve (heading_path, start, end) del cuerpo."""
    out, stack, fence, pos = [], [], False, 0
    start, path = 0, ""
    for line in text.splitlines(keepends=True):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
        m = None if fence else _HEAD.match(s)
        if m:
            if pos > start:
                out.append((path, start, pos))
            lvl = len(m.group(1))
            stack = [h for h in stack if h[0] < lvl] + [(lvl, m.group(2))]
            path = " › ".join(h[1] for h in stack)
            start = pos
        pos += len(line)
    if len(text) > start:
        out.append((path, start, len(text)))
    return out


def _split_long(text: str, a: int, b: int, size: int, overlap: int):
    """Parte un tramo largo sin párrafos en trozos de ~size, cortando en frase o salto de línea."""
    while b - a > size:
        seg = text[a:a + size]
        cut = max(seg.rfind(". "), seg.rfind("\n"))
        cut = cut + 1 if cut > size // 2 else size
        yield a, a + cut
        a = max(a + cut - overlap, a + 1)
    yield a, b


def chunk(text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[dict]:
    """Trocea por secciones y párrafos. Cada trozo: {text, char_start, char_end, heading_path, page, idx}."""
    chunks: list[dict] = []
    page_starts = [m.end() for m in re.finditer(PAGE_BREAK, text)]
    has_pages = bool(page_starts)

    def page_at(pos: int):
        if not has_pages:
            return None
        return 1 + sum(1 for s in page_starts if s <= pos)

    def emit(path, a, b):
        raw = text[a:b]
        lead = len(raw) - len(raw.lstrip())
        t = raw.strip().replace(PAGE_BREAK, "\n").strip()
        if t:
            chunks.append({"text": t, "char_start": a + lead, "char_end": a + lead + len(raw.strip()), "heading_path": path, "page": page_at(a + lead)})

    for path, s0, e0 in _sections(text):
        paras = [(s0 + m.start(), s0 + m.end()) for m in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text[s0:e0])]
        cur_a = cur_b = None
        for a, b in paras:
            only_head = cur_a is not None and bool(_HEAD.match(text[cur_a:cur_b].strip()))  # un título nunca se queda solo
            if b - a > size:                         # párrafo largo: se parte aparte
                if only_head:
                    a, cur_a, cur_b = cur_a, None, None
                elif cur_a is not None:
                    emit(path, cur_a, cur_b); cur_a = cur_b = None
                for x, y in _split_long(text, a, b, size, overlap):
                    emit(path, x, y)
                continue
            if cur_a is not None and b - cur_a > size and not only_head:
                emit(path, cur_a, cur_b); cur_a = None
            if cur_a is None:
                cur_a = a
            cur_b = b
        if cur_a is not None:
            emit(path, cur_a, cur_b)
    merged: list[dict] = []                          # los trozos diminutos se unen al anterior de su misma sección
    for c in chunks:
        if merged and len(c["text"]) < MIN_CHUNK and merged[-1]["heading_path"] == c["heading_path"] and c["char_start"] - merged[-1]["char_end"] < 4:
            p = merged[-1]; p["text"] += "\n" + c["text"]; p["char_end"] = c["char_end"]
        else:
            merged.append(c)
    for i, c in enumerate(merged):
        c["idx"] = i
    return merged
