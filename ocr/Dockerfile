# MimirSynth's optional OCR service (#135): Tesseract and Poppler, apart from the main image so that it does not grow.
# Build: docker build -t mimirsynth-ocr ocr/
# More languages: --build-arg LANGS="spa eng cat fra" (Debian's tesseract-ocr-<code> packages).
FROM debian:trixie-slim
ARG VERSION=dev
ARG LANGS="spa eng"
LABEL org.opencontainers.image.title="MimirSynth OCR" org.opencontainers.image.description="Optional OCR service for MimirSynth's document memory (Tesseract)" org.opencontainers.image.licenses="Apache-2.0" org.opencontainers.image.source="https://github.com/MimirSynth/mimirsynth" org.opencontainers.image.version="${VERSION}"
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 tesseract-ocr poppler-utils $(for l in $LANGS; do echo "tesseract-ocr-$l"; done) \
 && rm -rf /var/lib/apt/lists/*
COPY server.py /srv/server.py
ENV PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1
USER nobody
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=8)"]
CMD ["python3", "/srv/server.py"]
