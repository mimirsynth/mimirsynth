# The compiled web is static: it is built once and shared by every architecture.
FROM --platform=$BUILDPLATFORM node:26-slim AS web
WORKDIR /w
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.15-slim
ARG VERSION=dev
LABEL org.opencontainers.image.title="MimirSynth" org.opencontainers.image.description="Memory for AI agents on a temporal knowledge graph" org.opencontainers.image.licenses="Apache-2.0" org.opencontainers.image.source="https://github.com/MimirSynth/mimirsynth" org.opencontainers.image.version="${VERSION}"
ENV PYTHONUNBUFFERED=1 MIMIRSYNTH_STATIC_DIR=/srv/web
WORKDIR /srv
COPY api ./api
# The API answers in the caller's language with the same server catalogue the web uses (see mimirsynth/i18n.py).
COPY web/src/i18n/en.server.json ./api/mimirsynth/en.server.json
RUN pip install --no-cache-dir "./api[pdf]"
COPY --from=web /w/dist /srv/web
WORKDIR /srv/api
RUN useradd -u 10001 -r mimirsynth && mkdir -p /data/documents && chown -R mimirsynth /srv /data/documents
USER mimirsynth
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["uvicorn", "mimirsynth.main:app", "--host", "0.0.0.0", "--port", "8000"]
