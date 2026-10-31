"""Office documents (#124): Word (.docx), PowerPoint (.pptx), Excel (.xlsx) and OpenDocument text (.odt), read with the standard
library: they are zip files with XML inside.

The text keeps the structure the chunker uses (`chunk` cuts by Markdown headings): headings become `#` lines, a table becomes one
line per row with its cells separated by « | », each slide starts with its title (or its number) and each sheet with its name.

They come from outside, so before reading anything:
- the zip may not declare more than MAX_MEMBERS entries nor more than MAX_UNZIPPED bytes uncompressed (a zip bomb), and an XML part
  is read only up to MAX_PART bytes;
- an XML part with a DOCTYPE or an entity declaration is rejected: nothing an Office file needs, and the way to an entity expansion.
"""
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_MEMBERS = 5000
MAX_UNZIPPED = 512 << 20
MAX_PART = 128 << 20
_DTD = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"
DC = "{http://purl.org/dc/elements/1.1/}"
T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TB = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"


class OfficeError(ValueError):
    pass


def _open(path: Path) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise OfficeError("no es un documento de Office válido (no se puede abrir como zip)") from e
    infos = z.infolist()
    if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_UNZIPPED:
        z.close()
        raise OfficeError("el documento declara demasiado contenido descomprimido")
    return z


def _xml(z: zipfile.ZipFile, name: str, required: bool = True):
    try:
        info = z.getinfo(name)
    except KeyError:
        if required:
            raise OfficeError(f"al documento le falta {name}") from None
        return None
    if info.file_size > MAX_PART:
        raise OfficeError(f"{name} es demasiado grande")
    with z.open(info) as f:
        raw = f.read(MAX_PART + 1)
    if len(raw) > MAX_PART:
        raise OfficeError(f"{name} es demasiado grande")
    if _DTD.search(raw[:4096]) or _DTD.search(raw):
        raise OfficeError("el documento lleva declaraciones DOCTYPE o de entidades, que no se admiten")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as e:
        raise OfficeError(f"{name} no es XML válido") from e


def _title(z: zipfile.ZipFile) -> str:
    core = _xml(z, "docProps/core.xml", required=False)
    t = core.find(f"{DC}title") if core is not None else None
    return (t.text or "").strip() if t is not None else ""


def _row(cells: list[str]) -> str:
    cells = [c.strip().replace("\n", " ") for c in cells]
    while cells and not cells[-1]:
        cells.pop()
    return " | ".join(cells)


# --- Word ------------------------------------------------------------------------------------------

_HEADING = re.compile(r"(?i)^(heading|t[ií]?tulo|ttulo|berschrift|titre)\s*([1-9])$")


def _w_text(el) -> str:
    out = []
    for n in el.iter():
        if n.tag == f"{W}t":
            out.append(n.text or "")
        elif n.tag == f"{W}tab":
            out.append("\t")
        elif n.tag in (f"{W}br", f"{W}cr"):
            out.append("\n")
    return "".join(out)


def _w_level(p) -> int:
    ppr = p.find(f"{W}pPr")
    st = ppr.find(f"{W}pStyle") if ppr is not None else None
    val = (st.get(f"{W}val") or "") if st is not None else ""
    if val.lower() == "title":
        return 1
    m = _HEADING.match(val)
    if m:
        return int(m.group(2))
    lvl = ppr.find(f"{W}outlineLvl") if ppr is not None else None
    v = lvl.get(f"{W}val", "") if lvl is not None else ""
    return int(v) + 1 if v.isdigit() and int(v) < 6 else 0


def _docx(z) -> str:
    body = _xml(z, "word/document.xml").find(f"{W}body")
    lines = []
    for el in list(body) if body is not None else []:
        if el.tag == f"{W}p":
            text = _w_text(el).strip()
            if text:
                lvl = _w_level(el)
                lines.append(f"{'#' * min(lvl, 6)} {text}" if lvl else text)
        elif el.tag == f"{W}tbl":
            for tr in el.iter(f"{W}tr"):
                row = _row([_w_text(tc) for tc in tr.findall(f"{W}tc")])
                if row:
                    lines.append(row)
            lines.append("")
    return "\n\n".join(x for x in lines)


# --- PowerPoint ------------------------------------------------------------------------------------

def _pptx(z) -> str:
    slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))
    parts = []
    for i, name in enumerate(slides, 1):
        root = _xml(z, name)
        title, body = "", []
        for sp in root.iter(f"{P}sp"):
            ph = sp.find(f".//{P}nvPr/{P}ph")
            paras = ["".join(t.text or "" for t in para.iter(f"{A}t")).strip() for para in sp.iter(f"{A}p")]
            paras = [x for x in paras if x]
            if ph is not None and ph.get("type") in ("title", "ctrTitle") and not title:
                title = " ".join(paras)
            else:
                body += paras
        for tbl in root.iter(f"{A}tbl"):
            for tr in tbl.iter(f"{A}tr"):
                row = _row(["".join(t.text or "" for t in tc.iter(f"{A}t")) for tc in tr.findall(f"{A}tc")])
                if row:
                    body.append(row)
        parts.append("\n\n".join([f"## {title or i}", *body]))
    return "\n\n".join(parts)


# --- Excel -----------------------------------------------------------------------------------------

def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref or "A").group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx(z) -> str:
    shared = []
    sst = _xml(z, "xl/sharedStrings.xml", required=False)
    if sst is not None:
        shared = ["".join(t.text or "" for t in si.iter(f"{S}t")) for si in sst.findall(f"{S}si")]
    wb = _xml(z, "xl/workbook.xml")
    rels = _xml(z, "xl/_rels/workbook.xml.rels", required=False)
    targets = {r.get("Id"): r.get("Target", "") for r in rels.findall(f"{PR}Relationship")} if rels is not None else {}
    parts = []
    for i, sh in enumerate(wb.iter(f"{S}sheet"), 1):
        target = targets.get(sh.get(f"{R}id"), f"worksheets/sheet{i}.xml").lstrip("/")
        path = target if target.startswith("xl/") else f"xl/{target}"
        root = _xml(z, path, required=False)
        if root is None:
            continue
        lines = [f"## {sh.get('name') or i}"]
        for row in root.iter(f"{S}row"):
            cells: dict[int, str] = {}
            for c in row.findall(f"{S}c"):
                t, v = c.get("t"), c.find(f"{S}v")
                if t == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{S}t"))
                else:
                    val = v.text if v is not None and v.text else ""
                if val:
                    cells[_col(c.get("r", ""))] = val
            if cells:
                lines.append(_row([cells.get(k, "") for k in range(max(cells) + 1)]))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# --- OpenDocument text -----------------------------------------------------------------------------

def _o_text(el) -> str:
    out = [el.text or ""]
    for n in el:
        if n.tag == f"{T}s":
            out.append(" " * int(n.get(f"{T}c", "1") or 1))
        elif n.tag == f"{T}tab":
            out.append("\t")
        elif n.tag == f"{T}line-break":
            out.append("\n")
        else:
            out.append(_o_text(n))
        out.append(n.tail or "")
    return "".join(out)


def _odt(z) -> str:
    office = _xml(z, "content.xml")
    lines = []

    def walk(el):
        for n in el:
            if n.tag == f"{T}h":
                text = _o_text(n).strip()
                if text:
                    lines.append(f"{'#' * min(int(n.get(f'{T}outline-level', '1') or 1), 6)} {text}")
            elif n.tag == f"{T}p":
                text = _o_text(n).strip()
                if text:
                    lines.append(text)
            elif n.tag == f"{TB}table":
                for tr in n.iter(f"{TB}table-row"):
                    row = _row([_o_text(p) for tc in tr.findall(f"{TB}table-cell") for p in tc.iter(f"{T}p")])
                    if row:
                        lines.append(row)
                lines.append("")
            else:
                walk(n)
    walk(office)
    return "\n\n".join(lines)


def extract(path: Path, ext: str) -> tuple[str, str]:
    """(text, suggested title) of an Office document."""
    reader = {".docx": _docx, ".pptx": _pptx, ".xlsx": _xlsx, ".odt": _odt}[ext]
    with _open(path) as z:
        try:
            text = reader(z)
        except OfficeError:
            raise
        except Exception as e:  # noqa: BLE001  (a document that is not what its extension says)
            raise OfficeError(f"documento ilegible: {str(e)[:120]}") from e
        title = _title(z) if ext != ".odt" else ""
        if ext == ".odt":
            meta = _xml(z, "meta.xml", required=False)
            t = meta.find(f".//{DC}title") if meta is not None else None
            title = (t.text or "").strip() if t is not None else ""
    return re.sub(r"\n{3,}", "\n\n", text).strip(), title
