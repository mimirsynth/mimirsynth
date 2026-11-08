"""OCR for scanned PDFs and images (#135). The service is the real `ocr/server.py`, run in a thread with Tesseract and Poppler
replaced by stand-ins, so the streamed protocol, the page selection and the cancellation are the real ones."""
import base64
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from test_control import client  # noqa: F401
from test_docs import _upload, fake_index  # noqa: F401

from mimirsynth import docstore, jobs, ocr
from mimirsynth.config import settings
from mimirsynth.docextract import ExtractError, chunk, extract

SERVER = Path(__file__).resolve().parents[2] / "ocr" / "server.py"


def make_pdf(pages: list[str | None]) -> bytes:
    """A PDF whose pages carry this text, or none at all (None: a scanned page)."""
    n = len(pages)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{4 + 2 * i} 0 R" for i in range(n)), n)).encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, t in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({t}) Tj ET".encode() if t else b""
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SCANNED = "Texto escaneado de la pagina {n}: la bomba P-204 se revisa cada seis meses y el filtro en marzo."


class Calls(list):
    srv = None


@pytest.fixture()
def service(monkeypatch):
    """The OCR service on a free port. `calls` records what it was asked to read."""
    spec = importlib.util.spec_from_file_location("ocr_server", SERVER)
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    calls = Calls()
    calls.srv = srv

    def pdf_pages(path):
        from pypdf import PdfReader
        return len(PdfReader(path).pages)

    def render(path, page, out_dir):
        p = Path(out_dir) / f"p{page}.png"
        p.write_bytes(PNG + str(page).encode())
        return str(p)

    def tesseract(image, lang):
        data = Path(image).read_bytes()
        calls.append({"lang": lang, "image": data[len(PNG):].decode() or "image"})
        return SCANNED.format(n=data[len(PNG):].decode() or 1)

    monkeypatch.setattr(srv, "languages", lambda: ["eng", "spa"])
    monkeypatch.setattr(srv, "version", lambda: "5.5.0")
    monkeypatch.setattr(srv, "pdf_pages", pdf_pages)
    monkeypatch.setattr(srv, "render", render)
    monkeypatch.setattr(srv, "tesseract", tesseract)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "ocr_url", f"http://127.0.0.1:{httpd.server_address[1]}")
    yield calls
    httpd.shutdown()


def test_sniffs_content_and_says_how_to_enable_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ocr_url", "")
    assert [ocr.sniff(x) for x in (b"%PDF-1.7", PNG, b"\xff\xd8\xff\xe0", b"PK\x03\x04")] == ["pdf", "png", "jpeg", None]
    fake = tmp_path / "nota.png"
    fake.write_text("solo texto", encoding="utf-8")
    with pytest.raises(ExtractError, match="no es lo que dice la extensión"):
        extract(fake, ".png")
    scanned = tmp_path / "escaneo.pdf"
    scanned.write_bytes(make_pdf([None, None]))
    with pytest.raises(ExtractError, match="MIMIRSYNTH_OCR_URL") as e:
        extract(scanned, ".pdf")
    assert "escaneado" in str(e.value)
    img = tmp_path / "foto.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    with pytest.raises(ExtractError, match="MIMIRSYNTH_OCR_URL.*modelo de visión"):
        extract(img, ".jpg")
    named_txt = tmp_path / "en-realidad-pdf.txt"  # by its content, not its name
    named_txt.write_bytes(make_pdf(["Hello from a text page that pypdf can read without any OCR at all"]))
    assert "Hello from a text page" in extract(named_txt, ".txt")[0]
    rd = ocr.Reader()
    mixed = tmp_path / "mixto.pdf"
    mixed.write_bytes(make_pdf(["A page with plenty of real text in it for pypdf to read", None]))
    text, _ = extract(mixed, ".pdf", rd)
    assert "plenty of real text" in text and rd.info == {"unread": 1}  # without OCR a mixed PDF keeps its text pages and says so
    assert not docstore.scannable("diagrama.png") and docstore.scannable("guia.md")


def test_scanned_pdf_reads_only_its_blank_pages_up_to_the_maximum(tmp_path, service, monkeypatch):
    p = tmp_path / "mixto.pdf"
    p.write_bytes(make_pdf(["Cover page with enough text of its own to need no OCR", None, None, None]))
    seen: list[tuple[int, int]] = []
    rd = ocr.Reader(progress=lambda d, t: seen.append((d, t)))
    from mimirsynth import appsettings
    real = appsettings.get
    monkeypatch.setattr(appsettings, "get", lambda k: 2 if k == "ocr_max_pages" else real(k))
    text, _ = extract(p, ".pdf", rd)
    assert [c["image"] for c in service] == ["2", "3"] and {c["lang"] for c in service} == {"spa+eng"}
    pages = text.split("\f")
    assert pages[0].startswith("Cover page") and "pagina 2" in pages[1] and "pagina 3" in pages[2] and pages[3] == ""
    assert rd.info == {"engine": "tesseract", "pages": 2, "of": 4, "skipped": 1} and seen[0] == (0, 2) and seen[-1] == (2, 2)
    assert {c["page"] for c in chunk(text) if "pagina 3" in c["text"]} == {3}  # the citation gives the page


def test_cancelling_stops_between_pages_and_a_bad_page_does_not_lose_the_rest(tmp_path, service):
    import time
    real = service.srv.tesseract
    service.srv.tesseract = lambda image, lang: (time.sleep(0.3), real(image, lang))[1]
    p = tmp_path / "escaneo.pdf"
    p.write_bytes(make_pdf([None] * 6))

    def stop():
        if len(service) >= 1:
            raise jobs.Cancelled()
    with pytest.raises(jobs.Cancelled):
        extract(p, ".pdf", ocr.Reader(check=stop))
    assert len(service) < 6
    service.srv.tesseract = real
    texts = ocr.read_pdf(p, [1, 99], ocr.Reader())  # 99 does not exist: the service drops it
    assert list(texts) == [1]


def test_vision_model_reads_and_tesseract_takes_over_what_it_cannot(tmp_path, service, monkeypatch):
    asked: list[str] = []

    def vision(eng, image, mime):
        asked.append(mime)
        if image.endswith(b"2"):
            raise RuntimeError("the model refused")
        return "Lo que leyó el modelo de visión en esta página, con todo su texto."
    monkeypatch.setattr(ocr, "vision", vision)
    p = tmp_path / "escaneo.pdf"
    p.write_bytes(make_pdf([None, None]))
    rd = ocr.Reader(vision={"model": "m", "base_url": "http://x"})
    text, _ = extract(p, ".pdf", rd)
    first, second = text.split("\f")
    assert "modelo de visión" in first and "pagina 2" in second and [c["image"] for c in service] == ["2"]
    assert rd.info["engine"] == "vision" and rd.info["tesseract"] == 1
    monkeypatch.setattr(settings, "ocr_url", "")  # a lone image needs no service with the vision model
    img = tmp_path / "foto.png"
    img.write_bytes(PNG)
    assert "modelo de visión" in extract(img, ".png", ocr.Reader(vision={"model": "m", "base_url": "http://x"}))[0]
    assert asked[-1] == "image/png"


def test_vision_call_uses_an_image_message(monkeypatch):
    sent = {}

    class R:
        status_code, content, headers = 200, b"{}", {}

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": " texto \n"}}]}
    monkeypatch.setattr(ocr.httpx, "post", lambda url, json, timeout, headers: sent.update(url=url, body=json) or R())
    assert ocr.vision({"model": "vis", "base_url": "http://e/v1/", "api_key": "k"}, b"abc", "image/jpeg") == "texto"
    part = sent["body"]["messages"][0]["content"][1]["image_url"]["url"]
    assert sent["url"] == "http://e/v1/chat/completions" and part == "data:image/jpeg;base64," + base64.b64encode(b"abc").decode()


def test_scanned_upload_is_indexed_with_ocr_and_says_so(client, fake_index, service):
    client.post("/api/brains", json={"slug": "oc", "name": "Oc", "graph_name": "g-oc"})
    base = "/api/brains/oc/docs"
    st = client.get(f"{base}/ocr").json()
    assert st["configured"] and st["reachable"] and st["missing"] == [] and st["vision"] is False
    _, r = _upload(client, "oc", "escaneo.pdf", make_pdf([None, None]))
    d = client.get(f"{base}/{r.json()['id']}", params={"chunks": 10}).json()
    assert d["status"] == "active" and d["ocr"] == {"engine": "tesseract", "pages": 2, "of": 2}
    assert any("pagina 2" in c["text"] for c in d["chunk_list"])
    _, r = _upload(client, "oc", "foto.png", PNG + b"7")
    d = client.get(f"{base}/{r.json()['id']}").json()
    assert d["status"] == "active" and d["mime"] == "image/png" and d["ocr"]["engine"] == "tesseract"
    assert client.patch("/api/brains/oc", json={"ocr_vision": True}).json()["ocr_vision"] is True
    assert client.get(f"{base}/ocr").json()["vision"] is True


def test_secrets_in_scanned_text_are_masked(client, fake_index, service, monkeypatch):
    srv_text = "Credenciales del servidor: ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
    monkeypatch.setattr(ocr, "_tesseract", lambda path, pages, rd, *a: (1, {1: srv_text}, []))
    client.post("/api/brains", json={"slug": "os", "name": "Os", "graph_name": "g-os"})
    _, r = _upload(client, "os", "escaneo.pdf", make_pdf([None]))
    d = client.get(f"/api/brains/os/docs/{r.json()['id']}", params={"chunks": 10}).json()
    assert d["status"] == "active" and d["secrets"] and not any("ghp_" in c["text"] for c in d["chunk_list"])


def test_the_service_refuses_what_it_should(service):
    import httpx
    base = settings.ocr_url
    assert httpx.post(f"{base}/ocr", content=b"hola").status_code == 415
    assert httpx.post(f"{base}/ocr", params={"lang": "spa;rm"}, content=make_pdf([None])).status_code == 400
    assert "not installed" in httpx.post(f"{base}/ocr", params={"lang": "fra"}, content=make_pdf([None])).json()["error"]
    assert httpx.post(f"{base}/render", content=PNG).status_code == 415
    lines = [json.loads(x) for x in httpx.post(f"{base}/render", params={"pages": "2"}, content=make_pdf([None, None])).text.splitlines()]
    assert lines[0] == {"pages": 2, "doing": [2]} and base64.b64decode(lines[1]["png"]).endswith(b"2") and lines[-1] == {"done": True}
    assert httpx.get(f"{base}/health").json()["languages"] == ["eng", "spa"]
