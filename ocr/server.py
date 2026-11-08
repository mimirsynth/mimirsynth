"""MimirSynth's OCR service: Tesseract (and Poppler, for PDFs) behind a small HTTP API, so that the main image stays as it is (#135).

It only uses the standard library. It has no authentication: run it on the compose network, without publishing its port.

- `GET /health` -> {"ok": true, "tesseract": "5.3.0", "languages": ["eng", "spa", ...]}
- `POST /ocr?lang=spa+eng&pages=1,3` with the file as the body (a PDF, PNG or JPEG, told apart by its first bytes). It answers with
  one JSON line per event, as each page is read, so the caller can show progress and stop by closing the connection:
  {"pages": total, "doing": [1, 3]}, then {"page": 1, "text": "..."} per page, then {"done": true}; or {"error": "..."}.
  `pages` is optional (all of them by default) and is cut to OCR_MAX_PAGES.
- `POST /render?pages=1,3` with a PDF as the body -> the same lines, with each page as a PNG in base64 (`"png"`) instead of its
  text, for a vision model.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("OCR_PORT", "8001"))
MAX_MB = int(os.environ.get("OCR_MAX_MB", "200"))
MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES", "500"))  # a ceiling for any caller; MimirSynth asks for fewer (its own setting)
DPI = int(os.environ.get("OCR_DPI", "300"))
PAGE_TIMEOUT = int(os.environ.get("OCR_PAGE_TIMEOUT", "180"))
WORKERS = threading.Semaphore(int(os.environ.get("OCR_WORKERS", "2")))  # documents read at the same time; each page is one process
LANG = re.compile(r"^[A-Za-z_]{3,20}(\+[A-Za-z_]{3,20}){0,5}$")


def sniff(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def run(args: list[str], timeout: int = PAGE_TIMEOUT) -> bytes:
    p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace").strip()[-300:] or f"{args[0]} failed")
    return p.stdout


def languages() -> list[str]:
    out = run(["tesseract", "--list-langs"], 30).decode("utf-8", "replace")
    return sorted(x.strip() for x in out.splitlines()[1:] if x.strip() and x.strip() != "osd")


def version() -> str:
    p = subprocess.run(["tesseract", "--version"], capture_output=True, timeout=30, check=False)
    first = (p.stdout or p.stderr).decode("utf-8", "replace").splitlines()
    return first[0].split()[-1] if first else ""


def pdf_pages(path: str) -> int:
    m = re.search(rb"^Pages:\s+(\d+)", run(["pdfinfo", path], 60), re.MULTILINE)
    if not m:
        raise RuntimeError("pdfinfo did not say how many pages the PDF has")
    return int(m.group(1))


def render(path: str, page: int, out_dir: str) -> str:
    base = os.path.join(out_dir, f"p{page}")
    run(["pdftoppm", "-r", str(DPI), "-f", str(page), "-l", str(page), "-png", "-singlefile", path, base])
    return base + ".png"


def tesseract(image: str, lang: str) -> str:
    return run(["tesseract", image, "stdout", "-l", lang]).decode("utf-8", "replace")


def wanted(q: dict, total: int) -> list[int]:
    raw = (q.get("pages") or [""])[0]
    pages = sorted({int(x) for x in raw.split(",") if x.strip().isdigit()}) if raw else list(range(1, total + 1))
    return [p for p in pages if 1 <= p <= total][:MAX_PAGES]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # the streamed answer ends when the connection closes
    server_version = "mimirsynth-ocr"

    def log_message(self, fmt, *args):  # one line per request, without the query (it carries nothing secret, but it is noise)
        print(f"{self.address_string()} {self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}", flush=True)

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self, tmp: str) -> str | None:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            self._json(400, {"error": "empty body"})
            return None
        if n > MAX_MB * 1024 * 1024:
            self._json(413, {"error": f"the file is larger than {MAX_MB} MB"})
            return None
        path = os.path.join(tmp, "input")
        with open(path, "wb") as f:
            left = n
            while left:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        return path

    def do_GET(self):
        if urlparse(self.path).path != "/health":
            return self._json(404, {"error": "not found"})
        try:
            self._json(200, {"ok": True, "tesseract": version(), "languages": languages()})
        except Exception as e:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(e)[:300]})

    def do_POST(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path not in ("/ocr", "/render"):
            return self._json(404, {"error": "not found"})
        tmp = tempfile.mkdtemp(prefix="ocr-")
        try:
            path = self._body(tmp)
            if path is None:
                return
            with open(path, "rb") as f:
                kind = sniff(f.read(16))
            if kind is None:
                return self._json(415, {"error": "the file is not a PDF, PNG or JPEG"})
            if url.path == "/render":
                if kind != "pdf":
                    return self._json(415, {"error": "only a PDF has pages to render"})
                return self._stream(path, kind, None, q, tmp)
            lang = (q.get("lang") or ["eng"])[0]
            if not LANG.match(lang):
                return self._json(400, {"error": "invalid language"})
            missing = [x for x in lang.split("+") if x not in languages()]
            if missing:
                return self._json(400, {"error": f"language not installed in the OCR service: {', '.join(missing)}"})
            self._stream(path, kind, lang, q, tmp)
        except Exception as e:  # noqa: BLE001
            try:
                self._json(500, {"error": str(e)[:300]})
            except OSError:
                pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _stream(self, path: str, kind: str, lang: str | None, q: dict, tmp: str) -> None:
        """One JSON line per page read (lang) or rendered (lang None)."""
        with WORKERS:
            total = pdf_pages(path) if kind == "pdf" else 1
            pages = wanted(q, total)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()

            def line(obj: dict) -> None:
                self.wfile.write(json.dumps(obj, ensure_ascii=False).encode() + b"\n")
                self.wfile.flush()

            line({"pages": total, "doing": pages})
            for n in pages:
                try:
                    image = render(path, n, tmp) if kind == "pdf" else path
                    if lang is None:
                        with open(image, "rb") as f:
                            out = {"page": n, "png": base64.b64encode(f.read()).decode()}
                    else:
                        out = {"page": n, "text": tesseract(image, lang)}
                    if kind == "pdf":
                        os.unlink(image)
                except Exception as e:  # noqa: BLE001  one bad page does not lose the rest
                    out = {"page": n, "error": str(e)[:300], **({"text": ""} if lang else {})}
                line(out)  # a closed connection (the caller cancelled) raises here and stops the loop
            line({"done": True})


if __name__ == "__main__":
    print(f"mimirsynth-ocr on :{PORT} (tesseract {version()}, languages {', '.join(languages())})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
