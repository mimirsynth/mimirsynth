"""OCR for scanned PDFs and images (#135).

Tesseract runs in a service apart (`ocr/` in the repository, `MIMIRSYNTH_OCR_URL`), so the main image does not grow. A brain can turn
on the vision model of a configured LLM engine instead: it reads each page as an image, and Tesseract takes over for the pages it
could not read. The service also turns PDF pages into images for it, so a scanned PDF always needs the service; a lone image does not.

The service answers with one JSON line per page as it reads them: the indexing job shows the progress and stops between pages when
it is cancelled, by closing the connection.
"""
import base64
import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import appsettings, usage
from .config import settings

log = logging.getLogger("mimirsynth.ocr")
IMAGE_KINDS = {"png": "image/png", "jpeg": "image/jpeg"}
PAGE_TIMEOUT = 300  # seconds the service may take over one page before the call is given up
VISION_MAX_MB = 20  # larger images are not sent to a vision model
VISION_PROMPT = ("Transcribe all the text in this image exactly as it is written, in its original language. Keep each heading, list item "
                 "and table row on its own line. Do not describe the image, translate, summarise or comment. If there is no text, answer "
                 "with nothing.")
HOW = ("hace falta el servicio OCR: arranca el servicio «ocr» del docker-compose y define MIMIRSYNTH_OCR_URL (por ejemplo "
       "http://ocr:8001); lo explica la guía de instalación, en «OCR»")


class Unavailable(Exception):
    """No way to read this file's text: the message says how to enable one."""


def sniff(head: bytes) -> str | None:
    """The file's type by its first bytes, whatever its extension says: pdf, png, jpeg or None."""
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def configured() -> bool:
    return bool((settings.ocr_url or "").strip())


def _url(path: str) -> str:
    return settings.ocr_url.strip().rstrip("/") + path


@dataclass
class Reader:
    """How a document's pages are read: the brain's vision engine (None: Tesseract only), on whose behalf, and the job's hooks."""
    vision: dict | None = None
    brain_id: int = 0
    progress: Callable[[int, int], None] | None = None
    check: Callable[[], None] | None = None
    info: dict = field(default_factory=dict)  # what was done, kept in the document's meta

    def tick(self, done: int, total: int) -> None:
        if self.check:
            self.check()
        if self.progress:
            self.progress(done, total)


def _body(path: Path) -> Iterator[bytes]:
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            yield chunk


def _stream(endpoint: str, path: Path, params: dict) -> Iterator[dict]:
    """POSTs the file to the service and yields each JSON line of its answer. Leaving the loop early closes the connection, which
    stops the service."""
    headers = {"Content-Length": str(path.stat().st_size), "Content-Type": "application/octet-stream"}
    timeout = httpx.Timeout(10, read=PAGE_TIMEOUT, write=120)
    try:
        with httpx.stream("POST", _url(endpoint), params=params, content=_body(path), headers=headers, timeout=timeout) as r:
            if r.status_code != 200:
                r.read()
                try:
                    msg = r.json().get("error") or r.text
                except ValueError:
                    msg = r.text
                raise RuntimeError(f"el servicio OCR respondió {r.status_code}: {str(msg)[:200]}")
            for line in r.iter_lines():
                if line.strip():
                    yield json.loads(line)
    except httpx.HTTPError as e:
        raise RuntimeError(f"el servicio OCR no responde ({settings.ocr_url}): {type(e).__name__}") from e


def _tesseract(path: Path, pages: list[int] | None, rd: Reader, done0: int = 0, total: int = 0) -> tuple[int, dict[int, str], list[int]]:
    """Reads the pages (all of them when None) with the service. Returns (pages in the file, text per page, pages that failed)."""
    params = {"lang": appsettings.get("ocr_languages") or "spa+eng"}
    if pages is not None:
        params["pages"] = ",".join(map(str, pages))
    count, texts, failed, done = 0, {}, [], done0
    for ev in _stream("/ocr", path, params):
        if "error" in ev and "page" not in ev:
            raise RuntimeError(f"el servicio OCR: {ev['error'][:200]}")
        if "pages" in ev:
            count = ev["pages"]
            total = total or len(ev.get("doing") or [])
            rd.tick(done, total)
        elif "page" in ev:
            if ev.get("error"):
                failed.append(ev["page"])
                log.warning("OCR: la página %s no se pudo leer: %s", ev["page"], ev["error"])
            texts[ev["page"]] = ev.get("text") or ""
            done += 1
            rd.tick(done, total)
    return count, texts, failed


def vision(eng: dict, image: bytes, mime: str) -> str:
    """One page read by a vision model through an OpenAI-compatible engine, counted as the brain's AI usage for OCR."""
    url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    body = {"model": eng["model"], "temperature": 0, "max_tokens": 4000,
            "messages": [{"role": "user", "content": [{"type": "text", "text": VISION_PROMPT}, {"type": "image_url", "image_url": {"url": url}}]}]}
    r = httpx.post(f"{eng['base_url'].rstrip('/')}/chat/completions", json=body, timeout=180,
                   headers={"Authorization": f"Bearer {eng['api_key']}"} if eng.get("api_key") else {})
    usage.observe("llm", eng["model"], r)
    r.raise_for_status()
    return (r.json()["choices"][0]["message"].get("content") or "").strip()


def _vision_pages(path: Path, pages: list[int], rd: Reader) -> tuple[int, dict[int, str], list[int]]:
    """Renders each page with the service and reads it with the vision model. The pages it fails on are returned to be read with
    Tesseract."""
    count, texts, failed, done = 0, {}, [], 0
    with usage.scope(rd.brain_id, "ocr"):
        for ev in _stream("/render", path, {"pages": ",".join(map(str, pages))}):
            if "error" in ev and "page" not in ev:
                raise RuntimeError(f"el servicio OCR: {ev['error'][:200]}")
            if "pages" in ev:
                count = ev["pages"]
                rd.tick(0, len(pages))
                continue
            if "page" not in ev:
                continue
            n = ev["page"]
            try:
                if ev.get("error"):
                    raise RuntimeError(ev["error"])
                texts[n] = vision(rd.vision, base64.b64decode(ev["png"]), "image/png")
            except Exception as e:  # noqa: BLE001
                log.warning("OCR: el modelo de visión no leyó la página %s: %s", n, str(e)[:200])
                failed.append(n)
            done += 1
            rd.tick(done, len(pages))
    return count, texts, failed


def read_pdf(path: Path, pages: list[int], rd: Reader) -> dict[int, str]:
    """Reads these pages of a PDF (already cut to the setting's maximum). Raises Unavailable when no service is configured."""
    if not configured():
        raise Unavailable(HOW)
    failed: list[int] = []
    texts: dict[int, str] = {}
    if rd.vision:
        _, texts, failed = _vision_pages(path, pages, rd)
        rd.info["engine"] = "vision"
        if failed:  # Tesseract takes over the pages the vision model could not read
            _, more, failed = _tesseract(path, failed, rd)
            texts.update(more)
            rd.info["tesseract"] = len(more)
    else:
        _, texts, failed = _tesseract(path, pages, rd)
        rd.info["engine"] = "tesseract"
    if failed:
        rd.info["failed"] = sorted(failed)
    return texts


def read_image(path: Path, kind: str, rd: Reader) -> str:
    """The text of a PNG or JPEG image. With the vision model on, it does not need the service; Tesseract reads it otherwise, or
    when the model fails and the service is there."""
    if rd.vision and path.stat().st_size <= VISION_MAX_MB * 1024 * 1024:
        rd.tick(0, 1)
        try:
            with usage.scope(rd.brain_id, "ocr"):
                text = vision(rd.vision, path.read_bytes(), IMAGE_KINDS[kind])
            rd.info["engine"] = "vision"
            rd.tick(1, 1)
            return text
        except Exception as e:
            if not configured():
                raise RuntimeError(f"el modelo de visión no pudo leer la imagen: {str(e)[:200]}") from e
            log.warning("OCR: el modelo de visión no leyó la imagen, se usa Tesseract: %s", str(e)[:200])
    if not configured():
        raise Unavailable(HOW + ", o activa el modelo de visión en el brain")
    _, texts, failed = _tesseract(path, None, rd)
    if failed:
        raise RuntimeError("el servicio OCR no pudo leer la imagen")
    rd.info["engine"] = "tesseract"
    return texts.get(1, "")


def status() -> dict:
    """Whether the service is configured and answers, with its languages, for Administration and the documents page."""
    out = {"configured": configured(), "languages": appsettings.get("ocr_languages"), "max_pages": appsettings.get("ocr_max_pages")}
    if not out["configured"]:
        return out
    try:
        r = httpx.get(_url("/health"), timeout=5)
        r.raise_for_status()
        h = r.json()
        wanted = [x for x in str(out["languages"]).split("+") if x]
        out.update(reachable=True, tesseract=h.get("tesseract", ""), installed=h.get("languages", []),
                   missing=[x for x in wanted if x not in h.get("languages", [])])
    except Exception as e:  # noqa: BLE001
        out.update(reachable=False, error=type(e).__name__)
    return out
