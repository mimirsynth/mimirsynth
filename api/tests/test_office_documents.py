"""Office documents (#124): Word, PowerPoint, Excel and OpenDocument text become text with the structure the chunker uses (headings,
one line per table row, slide titles, sheet names), and a crafted file is rejected before it is read."""
import io
import zipfile

import pytest

from test_control import client  # noqa: F401
from test_docs import _upload, fake_index  # noqa: F401

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
CORE = ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{}</dc:title></cp:coreProperties>')


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def docx(title: str = "Inventario") -> bytes:
    p = lambda text, style="": (f'<w:p>{f"<w:pPr><w:pStyle w:val=\"{style}\"/></w:pPr>" if style else ""}'  # noqa: E731
                                f'<w:r><w:t>{text}</w:t></w:r></w:p>')
    cell = lambda text: f"<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>"  # noqa: E731
    body = (p("Servidores", "Heading1") + p("Notus aloja Nextcloud.") + p("Red", "Ttulo2") + p("La VLAN 20 es la de servicios.")
            + f"<w:tbl><w:tr>{cell('Host')}{cell('IP')}</w:tr><w:tr>{cell('Notus')}{cell('10.0.0.9')}</w:tr></w:tbl>")
    return _zip({"word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>", "docProps/core.xml": CORE.format(title)})


def pptx() -> bytes:
    ns = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    def slide(title, *paras):
        sp = lambda ph, texts: (f'<p:sp><p:nvSpPr><p:nvPr>{f"<p:ph type=\"{ph}\"/>" if ph else ""}</p:nvPr></p:nvSpPr>'  # noqa: E731
                                f'<p:txBody>{"".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in texts)}</p:txBody></p:sp>')
        return f"<p:sld {ns}><p:cSld><p:spTree>{sp('title', [title]) if title else ''}{sp('', paras)}</p:spTree></p:cSld></p:sld>"
    return _zip({"ppt/slides/slide2.xml": slide("Plan de copias", "Diarias a las 3:00", "Retención 30 días"),
                 "ppt/slides/slide1.xml": slide("Arquitectura", "Tres nodos"), "ppt/slides/slide10.xml": slide("", "Sin título")})


def xlsx() -> bytes:
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    return _zip({
        "xl/workbook.xml": f'<workbook {ns}><sheets><sheet name="Equipos" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": f'<sst {ns}><si><t>Host</t></si><si><t>Notus</t></si><si><t>Rack</t></si></sst>',
        "xl/worksheets/sheet1.xml": f'<worksheet {ns}><sheetData>'
                                    '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>2</v></c></row>'
                                    '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2" t="inlineStr"><is><t>principal</t></is></c><c r="C2"><v>4</v></c></row>'
                                    '</sheetData></worksheet>'})


def odt() -> bytes:
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"')
    content = (f'<office:document-content {ns}><office:body><office:text>'
               '<text:h text:outline-level="1">Procedimiento</text:h><text:p>Paso uno:<text:s text:c="2"/>parar el servicio.</text:p>'
               '<table:table><table:table-row><table:table-cell><text:p>Paso</text:p></table:table-cell>'
               '<table:table-cell><text:p>Quién</text:p></table:table-cell></table:table-row></table:table>'
               '</office:text></office:body></office:document-content>')
    meta = ('<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<office:meta><dc:title>Runbook</dc:title></office:meta></office:document-meta>')
    return _zip({"content.xml": content, "meta.xml": meta})


@pytest.mark.parametrize("ext,data,want,title", [
    (".docx", docx(), ["# Servidores", "Notus aloja Nextcloud.", "## Red", "Host | IP", "Notus | 10.0.0.9"], "Inventario"),
    (".pptx", pptx(), ["## Arquitectura", "Tres nodos", "## Plan de copias", "Diarias a las 3:00", "## 3", "Sin título"], ""),
    (".xlsx", xlsx(), ["## Equipos", "Host |  | Rack", "Notus | principal | 4"], ""),
    (".odt", odt(), ["# Procedimiento", "Paso uno:  parar el servicio.", "Paso | Quién"], "Runbook"),
])
def test_office_text_keeps_its_structure(tmp_path, ext, data, want, title):
    from mimirsynth.docextract import extract
    f = tmp_path / f"doc{ext}"
    f.write_bytes(data)
    text, got_title = extract(f, ext)
    pos = [text.find(w) for w in want]
    assert all(p >= 0 for p in pos), (text, want)
    assert pos == sorted(pos)                                                    # in the document's order (slides by number)
    assert got_title == title                                                  # core.xml / meta.xml, or else the first «# » heading


def test_a_crafted_or_broken_file_is_rejected(tmp_path, monkeypatch):
    from mimirsynth import officeextract
    from mimirsynth.docextract import ExtractError, extract
    bomb = '<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]><w:document ' + W + "><w:body/></w:document>"
    cases = {"entities": _zip({"word/document.xml": bomb}), "not a zip": b"PK\x03\x04 broken", "missing part": _zip({"other.xml": "<a/>"})}
    for why, data in cases.items():
        f = tmp_path / "x.docx"
        f.write_bytes(data)
        with pytest.raises(ExtractError):
            extract(f, ".docx")
    empty = tmp_path / "empty.docx"
    empty.write_bytes(_zip({"word/document.xml": f"<w:document {W}><w:body/></w:document>"}))
    with pytest.raises(ExtractError, match="no tiene texto"):
        extract(empty, ".docx")
    monkeypatch.setattr(officeextract, "MAX_UNZIPPED", 100)                     # what a zip bomb declares is checked before reading
    f = tmp_path / "big.docx"
    f.write_bytes(docx())
    with pytest.raises(ExtractError, match="demasiado contenido"):
        extract(f, ".docx")


def test_a_declaration_in_utf16_is_rejected_too(tmp_path):
    """Review of #160: a regex on the bytes did not see `<!DOCTYPE` in a UTF-16 part, and expat expanded the entity."""
    from mimirsynth.docextract import ExtractError, extract
    evil = (f'<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ENTITY x "INYECTADO">]><w:document {W}><w:body>'
            '<w:p><w:r><w:t>Hola &x;</w:t></w:r></w:p></w:body></w:document>')
    f = tmp_path / "evil.docx"
    f.write_bytes(_zip_bytes({"word/document.xml": evil.encode("utf-16")}))
    with pytest.raises(ExtractError, match="DOCTYPE"):
        extract(f, ".docx")
    plain = (f'<?xml version="1.0" encoding="UTF-16"?><w:document {W}><w:body><w:p><w:r><w:t>Hola en UTF-16</w:t></w:r></w:p>'
             '</w:body></w:document>')
    f.write_bytes(_zip_bytes({"word/document.xml": plain.encode("utf-16")}))
    assert extract(f, ".docx")[0].strip() == "Hola en UTF-16"                     # a normal UTF-16 part still works


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_upload_and_index_a_word_document(client, fake_index):  # noqa: F811
    assert client.post("/api/brains", json={"slug": "of1", "name": "Of1", "graph_name": "g-of1"}).status_code == 201
    uid, r = _upload(client, "of1", "inventario.docx", docx("Inventario de servidores"))
    assert r.status_code == 201, r.text
    doc = r.json()
    d = client.get(f"/api/brains/of1/docs/{doc['id']}", params={"chunks": 10}).json()
    assert d["status"] == "active" and d["title"] == "Inventario de servidores"
    assert d["mime"].endswith("wordprocessingml.document")
    assert any("Notus | 10.0.0.9" in c["text"] for c in d["chunk_list"])
    assert client.post("/api/brains/of1/docs/uploads", json={"filename": "x.doc", "size": 10}).status_code == 415   # old binary formats: no
