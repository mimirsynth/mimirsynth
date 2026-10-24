FROM node:22-slim AS web
WORKDIR /w
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 MIMIRSYNTH_STATIC_DIR=/srv/web
WORKDIR /srv
COPY api ./api
RUN pip install --no-cache-dir "./api[pdf]"
COPY --from=web /w/dist /srv/web
WORKDIR /srv/api
RUN useradd -u 10001 -r mimirsynth && mkdir -p /data/documents && chown -R mimirsynth /srv /data/documents
USER mimirsynth
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["uvicorn", "mimirsynth.main:app", "--host", "0.0.0.0", "--port", "8000"]
