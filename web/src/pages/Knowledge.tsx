import { T, locale, translateServer } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { fmt, get, langHeaders, send } from "../api";
import { Block, Btn, CellText, Check, Toggle, ClearFilters, ColHead, DataState, DataTable, DialogActions, FillArea, Loading, Modal, Notice, NumberField, Page, Pager, PasswordField, Sheet, SheetRow, ViewBar, Pill, ProgressBar, SelectField, SidePanel, Tabs, TextArea, TextField, useTableView, type ColSort, type SortDir, type Tone, MutationError, ConfirmDialog, EmptyState, PageHeader, Segments, SearchBar, useServerTableView, useTabParam, ListCard, FilePicker } from "../ui";
import { SecretsNotice, type SecretFinding } from "./Secrets";
import { Link, useSearchParams } from "react-router-dom";

type Doc = {
  url?: string; id: number; source: string; title: string; filename: string; size: number; status: string; error: string; chunks: number;
  progress: { done: number; total: number } | null; created_at: string; updated_at: string; sha256: string; secrets?: SecretFinding[]; duplicate_of?: number | null; ocr?: OcrInfo | null;
};
// what OCR did with a scanned PDF or an image (issue 135)
type OcrInfo = { engine?: "tesseract" | "vision"; pages?: number; of?: number; skipped?: number; unread?: number; failed?: number[]; tesseract?: number };
type OcrStatus = { configured: boolean; reachable?: boolean; missing?: string[]; languages: string; vision: boolean };
type Chunk = { chunk_idx: number; heading_path: string; page: number | null; text: string };
type Hit = { document_id: number; chunk: number; title: string; citation: string; text: string; similarity: number; updated_at: string };
type Source = { id: number; kind: string; name: string; documents: number; by_status: Record<string, number>; last_sync_at: string | null; last_error: string; status: string; enabled: boolean;
  sync_interval: number | null; config: { root?: string; subpath?: string; adapter?: string; settings?: Record<string, string>; collection_ids?: string[]; secrets_set?: string[];
    url?: string; web?: string | null; branch?: string; include?: string[]; commit?: string | null; matched?: Record<string, number> | null } };
type Adapter = { id: string; label: string; collection_label: string; fields: { name: string; label: string; secret: boolean; required: boolean; placeholder: string; help: string }[] };
type Up = { key: string; name: string; size: number; done: number; state: "subiendo" | "listo" | "duplicado" | "error"; msg?: string };
const UP_LABEL: Record<Up["state"], string> = { subiendo: T("subiendo"), listo: T("subido"), duplicado: T("duplicado"), error: T("error") };

const TONE: Record<string, Tone> = { active: "success", indexing: "warn", pending: "warn", error: "danger", duplicate: "neutral" };
const LABEL: Record<string, string> = { active: T("indexado"), indexing: T("indexando"), pending: T("en cola"), error: T("error"), duplicate: T("duplicado"), blocked: T("bloqueado por un derecho al olvido") };
// what a source is, in the table and its filter
const KIND: Record<string, string> = { upload: T("subidas"), wiki: T("wiki"), git: T("repositorio"), directory: T("carpeta") };
// the paths a new Git source indexes, one per line in the form (the server checks them again)
const GIT_PATHS = ["README*", "docs/**", "**/adr/**", "CHANGELOG*"];
const lines = (text: string) => text.split("\n").map((l) => l.trim()).filter(Boolean);
// a Git source whose paths took no file at its last sync (issue 214): it is shown as a warning, not as an empty «done»
const noFiles = (s: Source) => s.kind === "git" && !!s.config.matched && Object.values(s.config.matched).every((n) => n === 0);
type Repo = { name: string; url: string; branch: string; include: string; username: string; token: string; interval: number | "" };
const human = (n: number) => (n >= 1 << 30 ? `${(n / (1 << 30)).toFixed(1)} GB` : n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);
const ACCEPT = ".md,.markdown,.txt,.rst,.log,.html,.htm,.pdf,.docx,.pptx,.xlsx,.odt,.png,.jpg,.jpeg";

function OcrNotice({ ocr }: { ocr?: OcrInfo | null }) {
  const { t } = useTranslation();
  if (!ocr) return null;
  const read = ocr.engine === "vision" ? t("Leído con el modelo de visión.") : ocr.engine === "tesseract" ? t("Leído con OCR (Tesseract).") : "";
  return (
    <Notice tone={ocr.unread || ocr.skipped || ocr.failed?.length ? "warn" : "info"} title={t("Texto leído con OCR")}>
      <Stack gap={2}>
        {read && <Text size="sm">{read} {ocr.of ? t("{{pages}} de {{of}} páginas, las que no tenían texto.", { pages: ocr.pages, of: ocr.of }) : ""}</Text>}
        {!!ocr.tesseract && <Text size="sm">{t("{{n}} páginas que el modelo no pudo leer se leyeron con Tesseract.", { n: ocr.tesseract })}</Text>}
        {!!ocr.skipped && <Text size="sm">{t("{{n}} páginas escaneadas se quedaron sin leer por el máximo de páginas con OCR por documento (Administración → Ajustes).", { n: ocr.skipped })}</Text>}
        {!!ocr.unread && <Text size="sm">{t("{{n}} páginas parecen escaneadas y no se han leído: no hay servicio OCR. Se indexó el texto del resto.", { n: ocr.unread })}</Text>}
        {!!ocr.failed?.length && <Text size="sm">{t("No se pudieron leer las páginas {{pages}}.", { pages: ocr.failed.join(", ") })}</Text>}
      </Stack>
    </Notice>);
}

const PART = 32 * 1024 * 1024; // las partes son más pequeñas que el límite habitual de los proxies (~100 MB)

async function uploadFile(slug: string, file: File, progress: (done: number) => void): Promise<{ duplicate: boolean }> {
  const init = await send<{ upload_id: string; part_size: number }>("POST", "docs/uploads", { filename: file.name, size: file.size }, { graph: slug });
  const step = Math.min(init.part_size, PART);
  for (let i = 0, off = 0; off < file.size; i++, off += step) {
    const r = await fetch(`/api/brains/${slug}/docs/uploads/${init.upload_id}/parts/${i}`, { method: "PUT", credentials: "include", headers: langHeaders(), body: file.slice(off, off + step) });
    if (!r.ok) { await send("DELETE", `docs/uploads/${init.upload_id}`, undefined, { graph: slug }).catch(() => undefined); throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText); }
    progress(Math.min(off + step, file.size));
  }
  return send("POST", `docs/uploads/${init.upload_id}/complete`, undefined, { graph: slug });
}

type Relation = { uuid: string; source_uuid: string; source: string; target_uuid: string; target: string; name: string; fact: string; valid_at: string | null; invalid_at: string | null; status: string };
type EntitiesOut = { entities: { uuid: string; name: string; type: string; count: number }[]; relations: Relation[]; total: number; expired_count: number };

export default function Knowledge({ graph, role, instanceAdmin = false }: { graph: string; role: string; instanceAdmin?: boolean }) {
  const { t } = useTranslation();
  const canUpload = ["contributor", "curator", "admin", "owner"].includes(role);
  const isAdmin = ["admin", "owner"].includes(role);
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [ups, setUps] = useState<Up[]>([]);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useTabParam("docs");
  const [open, setOpenState] = useState<number | null>(() => (Number(params.get("doc")) || null));
  const setOpen = (id: number | null) => { setOpenState(id); const p = new URLSearchParams(params); id ? p.set("doc", String(id)) : p.delete("doc"); setParams(p, { replace: true }); };
  const [openChunks, setOpenChunks] = useState<Set<number>>(new Set());
  const [fullText, setFullText] = useState<number | null>(null);
  const [promo, setPromo] = useState<{ doc: number; chunk: number; title: string; text: string; name: string } | null>(null);
  const [ctxOf, setCtxOf] = useState<Hit | null>(null);
  const [del, setDel] = useState<Doc | null>(null);
  const [newSrc, setNewSrc] = useState<{ name: string; root: string; subpath: string; interval: number | "" } | null>(null);
  const [delSrc, setDelSrc] = useState<Source | null>(null);
  const [repo, setRepo] = useState<Repo | null>(null);
  const [wiki, setWiki] = useState<{ adapter: string; name: string; values: Record<string, string>; cols: { id: string; name: string; description: string }[] | null; picked: string[]; interval: number | "" } | null>(null);

  const { f, sent, setFilter, sortProps, sort, page, setPage, active, clear } = useServerTableView({ q: "", status: "", source: "", path: "" }, { debounced: ["q", "path"], firstDir: { title: "asc" } });
  const docs = useQuery({ queryKey: ["docs", graph, sent.q, sent.status, sent.source, sent.path, sort?.key ?? "updated", sort?.dir ?? "desc", page.offset, page.limit], placeholderData: keepPreviousData,
    queryFn: () => get<{ total: number; status_counts: Record<string, number>; items: Doc[] }>("docs", { graph, q: sent.q, status: sent.status, source_id: sent.source ? Number(sent.source) : undefined, path: sent.path, sort: sort?.key ?? "updated", order: sort?.dir ?? "desc", limit: page.limit, offset: page.offset }),
    refetchInterval: (qr) => (qr.state.data?.items.some((d) => d.status === "indexing" || d.status === "pending") ? 2000 : false) });
  const sources = useQuery({ queryKey: ["docs-sources", graph], queryFn: () => get<{ enabled: boolean; sources: Source[] }>("docs/sources", { graph }),
    refetchInterval: (qr) => (qr.state.data?.sources.some((x) => x.status === "scanning") ? 3000 : false) });
  const sv = useTableView(sources.data?.sources ?? [], {
    name: { get: (x: Source) => x.name }, kind: { get: (x: Source) => KIND[x.kind] ?? x.kind, label: (k: string) => t(k), exact: true }, docs: { get: (x: Source) => x.documents },
    state: { get: (x: Source) => (x.status === "scanning" ? "escaneando" : x.status === "error" ? t("con error") : !x.enabled ? "pausada" : t("al día")), exact: true }, last: { get: (x: Source) => x.last_sync_at ?? "" } });
  const [editSrc, setEditSrc] = useState<{ s: Source; name: string; interval: number | ""; subpath: string; values: Record<string, string>; picked: string[] | null;
    branch: string; include: string; username: string; token: string; clearToken: boolean } | null>(null);
  const hits = useQuery({ queryKey: ["docs-search", graph, query], enabled: query.length >= 2, queryFn: () => get<{ enabled: boolean; results: Hit[] }>("docs/search", { graph, q: query, k: 8 }) });
  const detail = useQuery({ queryKey: ["doc", graph, open], enabled: open !== null, queryFn: () => get<Doc & { chunk_list: Chunk[] }>(`docs/${open}`, { graph, chunks: 200 }) });
  const context = useQuery({ queryKey: ["doc-ctx", graph, ctxOf?.document_id, ctxOf?.chunk], enabled: !!ctxOf,
    queryFn: () => get<{ title: string; text: string; from_chunk: number; to_chunk: number }>(`docs/${ctxOf!.document_id}/context`, { graph, chunk: ctxOf!.chunk, radius: 1 }) });
  const full = useQuery({ queryKey: ["doc-text", graph, fullText], enabled: fullText !== null, queryFn: () => get<{ title: string; chars: number; truncated: boolean; text: string }>(`docs/${fullText}/text`, { graph }) });
  const [relMax, setRelMax] = useState(30); const [relExpired, setRelExpired] = useState(false);
  useEffect(() => { setRelMax(30); setRelExpired(false); }, [open]);   // cada documento empieza con sus relaciones vigentes
  const entities = useQuery({ queryKey: ["doc-entities", graph, open, relMax, relExpired], enabled: open !== null, staleTime: 60_000, placeholderData: keepPreviousData,
    queryFn: () => get<EntitiesOut>(`docs/${open}/entities`, { graph, relations: relMax, expired: relExpired ? "true" : undefined }) });
  const promote = useMutation({ mutationFn: (p: NonNullable<typeof promo>) => send<{ id: number; status: string }>("POST", `docs/${p.doc}/promote`, { chunk: p.chunk, text: p.text, name: p.name || undefined }, { graph }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["proposals", graph] }); qc.invalidateQueries({ queryKey: ["jobs", graph] }); } });
  const remove = useMutation({ mutationFn: (d: Doc) => send("DELETE", `docs/${d.id}`, undefined, { graph }), onSuccess: () => { setDel(null); setOpen(null); qc.invalidateQueries({ queryKey: ["docs", graph] }); qc.invalidateQueries({ queryKey: ["docs-sources", graph] }); } });
  const dedupe = useMutation({ mutationFn: () => send<{ job: number }>("POST", "docs/duplicates", undefined, { graph }) });
  const dedupeJob = useQuery({ queryKey: ["job", graph, dedupe.data?.job], enabled: !!dedupe.data, queryFn: () => get<{ status: string; error?: string; result: { hashed: number; marked: number } | null }>(`jobs/${dedupe.data!.job}`, { graph }),
    refetchInterval: (qr) => (["queued", "running"].includes(qr.state.data?.status ?? "queued") ? 1500 : false) });
  const dedupeDone = dedupeJob.data?.status === "done" ? dedupeJob.data.result : null;
  useEffect(() => { if (dedupeDone) { qc.invalidateQueries({ queryKey: ["docs", graph] }); qc.invalidateQueries({ queryKey: ["docs-sources", graph] }); } }, [dedupeDone, graph, qc]);
  const reindex = useMutation({ mutationFn: (id: number) => send("POST", `docs/${id}/reindex`, undefined, { graph }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["docs", graph] }); qc.invalidateQueries({ queryKey: ["doc", graph] }); } });

  const roots = useQuery({ queryKey: ["docs-roots", graph], enabled: isAdmin, queryFn: () => get<{ roots: { name: string; available: boolean }[] }>("docs/roots", { graph }) });
  const refreshSrc = () => { for (const k of ["docs", "docs-sources", "jobs", "jobs-summary"]) qc.invalidateQueries({ queryKey: [k, graph] }); };
  const addSrc = useMutation({ mutationFn: (b: NonNullable<typeof newSrc>) => send("POST", "docs/sources", { name: b.name, root: b.root, subpath: b.subpath, sync_interval: b.interval === "" ? null : b.interval }, { graph }), onSuccess: () => { setNewSrc(null); refreshSrc(); } });
  const ocrStatus = useQuery({ queryKey: ["docs-ocr", graph], enabled: isAdmin, queryFn: () => get<OcrStatus>("docs/ocr", { graph }) });
  const vision = useMutation({ mutationFn: (on: boolean) => send("PATCH", `brains/${graph}`, { ocr_vision: on }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["docs-ocr", graph] }); void qc.invalidateQueries({ queryKey: ["brains"] }); } });
  const adapters = useQuery({ queryKey: ["wiki-adapters", graph], enabled: isAdmin && instanceAdmin, queryFn: () => get<{ adapters: Adapter[] }>("docs/wiki/adapters", { graph }) });
  const ad = adapters.data?.adapters.find((a) => a.id === wiki?.adapter);
  const srcCols = useQuery({ queryKey: ["wiki-src-cols", graph, editSrc?.s.id], enabled: !!editSrc && editSrc.s.kind === "wiki" && instanceAdmin, retry: false, staleTime: 0,
    queryFn: () => get<{ collections: { id: string; name: string; description: string }[]; selected: string[]; documents: Record<string, number> }>(`docs/sources/${editSrc!.s.id}/wiki/collections`, { graph }) });
  const connect = useMutation({ mutationFn: (w: NonNullable<typeof wiki>) => send<{ collections: { id: string; name: string; description: string }[] }>("POST", "docs/wiki/collections", { adapter: w.adapter, values: w.values }, { graph }),
    onSuccess: (r) => setWiki((w) => (w ? { ...w, cols: r.collections, picked: r.collections.map((c) => c.id) } : w)) });
  const addRepo = useMutation({ mutationFn: (r: Repo) => send("POST", "docs/sources/git", { name: r.name.trim(), url: r.url.trim(), branch: r.branch.trim(), include: lines(r.include),
      username: r.username.trim(), token: r.token.trim(), sync_interval: r.interval === "" ? null : r.interval }, { graph }), onSuccess: () => { setRepo(null); refreshSrc(); } });
  const addWiki = useMutation({ mutationFn: (w: NonNullable<typeof wiki>) => send("POST", "docs/sources/wiki", { adapter: w.adapter, values: w.values, name: w.name, collection_ids: w.picked, sync_interval: w.interval === "" ? null : w.interval }, { graph }),
    onSuccess: () => { setWiki(null); refreshSrc(); } });
  const saveSrc = useMutation({ mutationFn: ({ confirm, ...e }: NonNullable<typeof editSrc> & { confirm?: number }) => send("PATCH", `docs/sources/${e.s.id}`, {
      name: e.name.trim(), ...(e.interval === "" ? { clear_interval: true } : { sync_interval: Number(e.interval) }), ...(e.s.kind === "directory" ? { subpath: e.subpath } : {}),
      ...(e.s.kind === "wiki" && Object.values(e.values).some((v) => v.trim()) ? { values: e.values } : {}), ...(e.s.kind === "wiki" && e.picked ? { collection_ids: e.picked, confirm_removed: confirm } : {}),
      ...(e.s.kind === "git" ? gitChanges(e) : {}) }, { graph }),
    onSuccess: () => { setEditSrc(null); setDropAsk(null); refreshSrc(); } });
  // collections taken out of a wiki source: their documents leave the index when saving, so the count is confirmed first
  const [dropAsk, setDropAsk] = useState<{ e: NonNullable<typeof editSrc>; n: number; names: string[] } | null>(null);
  const save = (e: NonNullable<typeof editSrc>) => {
    const d = srcCols.data;
    const before = d ? (d.selected.length ? d.selected : d.collections.map((c) => c.id)) : [];
    const out = e.picked && d ? before.filter((id) => !e.picked!.includes(id)) : [];
    const n = out.reduce((sum, id) => sum + (d?.documents[id] ?? 0), 0);
    if (n > 0) setDropAsk({ e, n, names: out.map((id) => d?.collections.find((c) => c.id === id)?.name ?? id) });
    else saveSrc.mutate(e);
  };
  // only what changed goes to the server: a Git change is checked against the repository and starts a sync
  function gitChanges(e: NonNullable<typeof editSrc>) {
    const c = e.s.config;
    return { ...(e.branch.trim() !== (c.branch ?? "") ? { branch: e.branch.trim() } : {}), ...(lines(e.include).join("\n") !== (c.include ?? []).join("\n") ? { include: lines(e.include) } : {}),
      ...(e.username.trim() !== (c.settings?.username ?? "") ? { username: e.username.trim() } : {}), ...(e.token.trim() ? { token: e.token.trim() } : {}), ...(e.clearToken ? { clear_token: true } : {}) };
  }
  const scanSrc = useMutation({ mutationFn: (id: number) => send("POST", `docs/sources/${id}/scan`, undefined, { graph }), onSuccess: refreshSrc });
  const toggleSrc = useMutation({ mutationFn: (s: Source) => send("PATCH", `docs/sources/${s.id}`, { enabled: !s.enabled }, { graph }), onSuccess: refreshSrc });
  const removeSrc = useMutation({ mutationFn: (s: Source) => send("DELETE", `docs/sources/${s.id}`, undefined, { graph }), onSuccess: () => { setDelSrc(null); refreshSrc(); } });

  const patch = (key: string, p: Partial<Up>) => setUps((u) => u.map((x) => (x.key === key ? { ...x, ...p } : x)));
  const start = async (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      const key = `${f.name}-${f.size}-${Date.now()}-${Math.random()}`;
      if (f.size === 0) { setUps((u) => [...u, { key, name: f.name, size: 0, done: 0, state: "error", msg: t("el fichero está vacío") }]); continue; }
      setUps((u) => [...u, { key, name: f.name, size: f.size, done: 0, state: "subiendo" }]);
      try {
        const r = await uploadFile(graph, f, (done) => patch(key, { done }));
        patch(key, { done: f.size, state: r.duplicate ? "duplicado" : "listo", msg: r.duplicate ? "ya estaba subido" : undefined });
      } catch (e) { patch(key, { state: "error", msg: (e as Error).message }); }
      qc.invalidateQueries({ queryKey: ["docs", graph] }); qc.invalidateQueries({ queryKey: ["docs-sources", graph] });
    }
  };

  const enabled = sources.data?.enabled !== false;
  const ocr = isAdmin ? ocrStatus.data : undefined;
  const dedupeFailed = !!dedupeJob.data && ["failed", "cancelled"].includes(dedupeJob.data.status);
  const docCount = Object.values(docs.data?.status_counts ?? {}).reduce((a, b) => a + b, 0);
  return (
    <Page fill>
      <PageHeader title={t("Conocimiento")} description={<>{t("Documentos del brain: se guardan sus originales, se trocean y se buscan por significado y por texto. Cada pasaje se muestra con su procedencia.")}</>} />
      {!enabled && <Notice tone="warn">{t("El índice documental necesita PostgreSQL con pgvector; esta instancia no lo tiene y no se pueden indexar documentos.")}</Notice>}
        <Tabs value={tab} onChange={(v) => setTab(v)} className="ms-tabs-fill">
          <Tabs.List>
            <Tabs.Tab value="docs">{t("Documentos (")}{docCount})</Tabs.Tab>
            <Tabs.Tab value="src">{t("Fuentes (")}{sources.data?.sources.length ?? 0})</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="docs">
            <ViewBar title={t("Documentos")}
              help={<Stack gap={6}>
                <Text size="sm">{t("Los documentos del brain con su estado de indexación. La búsqueda devuelve los pasajes que mejor responden, por significado o por texto, cada uno con su procedencia.")}</Text>
                {isAdmin && <Text size="sm"><b>{t("Buscar duplicados")}</b>: {t("Los documentos nuevos se comprueban al indexarse. Esto revisa los que ya estaban indexados y saca del índice los que repiten el texto de otro, sin borrar nada del origen.")}</Text>}
                {ocr && <Text size="sm">{!ocr.configured ? t("Los PDF escaneados y las imágenes necesitan el servicio OCR, que no está configurado en esta instancia.")
                  : ocr.missing?.length ? t("Al servicio OCR le faltan idiomas: {{langs}}.", { langs: ocr.missing.join(", ") })
                  : t("Los PDF escaneados y las imágenes se leen con OCR ({{langs}}).", { langs: ocr.languages })}</Text>}
                {ocr && <Text size="sm"><b>{t("Leer con el modelo de visión")}</b>: {t("Las páginas escaneadas y las imágenes de este brain las lee el modelo de visión de un motor LLM en vez de Tesseract; Tesseract lee las que el modelo no pueda. Cada página es una llamada al motor.")}</Text>}
              </Stack>}
              actions={<>
                {isAdmin && <Btn icon="search" loading={dedupe.isPending || (!!dedupe.data && !dedupeDone && !dedupeFailed)} onClick={() => dedupe.mutate()}>{t("Buscar duplicados")}</Btn>}
                {canUpload && <FilePicker label={t("Elegir ficheros")} accept={ACCEPT} multiple disabled={!enabled} onFiles={(fl) => void start(fl)} />}
              </>}>
              <SearchBar mode="submit" value={q} onChange={setQ} placeholder={t("Busca en los documentos por significado o por texto…")} onSubmit={setQuery} onClear={() => { setQ(""); setQuery(""); }} submitted={!!query} loading={hits.isLoading} disabled={!enabled} />
              {!query && <Segments label={t("Estado")} value={f.status || "all"} onChange={(v) => setFilter({ status: v === "all" ? "" : v })}
                data={[{ value: "all", label: t("Todos"), count: docCount }, ...Object.entries(LABEL).filter(([k]) => (docs.data?.status_counts[k] ?? 0) > 0 || f.status === k).map(([k, v]) => ({ value: k, label: v[0].toUpperCase() + v.slice(1), count: docs.data?.status_counts[k] ?? 0 }))]} />}
              {!query && <ClearFilters active={active} onClear={clear} />}
              {ocr && <Toggle label={t("Leer con el modelo de visión")} checked={ocr.vision} disabled={vision.isPending} onChange={(e) => vision.mutate(e.currentTarget.checked)} />}
            </ViewBar>
            {ocr?.configured && ocr.reachable === false && <Notice tone="warn">{t("El servicio OCR no responde: los PDF escaneados y las imágenes darán error hasta que vuelva.")}</Notice>}
            <MutationError error={vision.error} />
            <MutationError error={dedupe.error} />
            {dedupeDone && <Notice tone="success">{dedupeDone.marked ? t("{{n}} duplicados sacados del índice.", { n: dedupeDone.marked }) : t("No hay duplicados entre los documentos indexados.")}</Notice>}
            {dedupeFailed && <Notice tone="danger">{t("La búsqueda de duplicados no ha terminado; mira el detalle en Trabajos.")}</Notice>}
            {query ? (<>
              <MutationError error={hits.error} />
              <FillArea>
                {hits.isLoading ? <Loading label={t("Buscando…")} />
                  : hits.data && hits.data.results.length === 0 ? <EmptyState>{t("Sin resultados para «{{query}}».", { query })}</EmptyState>
                  : <Stack gap="xs">{(hits.data?.results ?? []).map((h) => (
                      <ListCard key={`${h.document_id}-${h.chunk}`} title={h.citation}
                        aside={<><Pill title={t("similitud del embedding (0 si solo coincide por texto)")}>{h.similarity ? `${Math.round(h.similarity * 100)} %` : t("texto")}</Pill>{fmt(h.updated_at)}</>}
                        actions={<>
                          <Btn size="row" icon="info" onClick={() => setCtxOf(h)}>{t("Ver contexto")}</Btn>
                          <Btn size="row" icon="download" component="a" href={`/api/brains/${graph}/docs/${h.document_id}/file`}>{t("Original")}</Btn>
                          {canUpload && <Btn size="row" icon="plus" onClick={() => { promote.reset(); setPromo({ doc: h.document_id, chunk: h.chunk, title: h.citation, text: h.text, name: "" }); }}>{t("Promover a memoria")}</Btn>}</>}>
                        {h.text}
                      </ListCard>))}</Stack>}
              </FillArea>
            </>) : (<>
              {/* the drop zone: a kit-styled area (theme.css `.ms-drop`), the one dashed border of the system (DESIGN.md, Shapes) */}
              {canUpload && (
                <div className="ms-drop" data-over={over ? "" : undefined}
                  onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                  onDrop={(e) => { e.preventDefault(); setOver(false); if (enabled) void start(e.dataTransfer.files); }}>
                  <Text size="sm">{t("Arrastra aquí ficheros para subirlos: .md, .txt, .rst, .html, .pdf, .docx, .pptx, .xlsx, .odt, .png o .jpg.")}</Text>
                </div>)}
              <FillArea>
                {!docs.data ? <DataState query={docs} /> : docs.data.items.length ? (
                <DataTable fz="sm">
                  <DataTable.Thead><DataTable.Tr>
                    <ColHead sort={sortProps("title")} filter={{ kind: "text", value: f.q, onChange: (v) => setFilter({ q: v }), placeholder: t("Título o nombre de fichero…") }}>{t("Documento")}</ColHead>
                    <ColHead filter={{ kind: "select", value: f.source, onChange: (v) => setFilter({ source: v, path: "" }), allLabel: t("Todas las fuentes"), options: (sources.data?.sources ?? []).map((x) => ({ value: String(x.id), label: x.name, count: x.documents })),
                      extra: f.source && sources.data?.sources.find((x) => String(x.id) === f.source)?.kind !== "upload" ? <TextField size="xs" mt={8} label={t("Carpeta")} placeholder={t("p. ej. fix")} value={f.path} onChange={(e) => setFilter({ path: e.currentTarget.value })} /> : undefined }}>{t("Fuente")}</ColHead>
                    <ColHead sort={sortProps("size")}>{t("Tamaño")}</ColHead>
                    <ColHead sort={sortProps("chunks")}>{t("Trozos")}</ColHead>
                    <ColHead>{t("Estado")}</ColHead>
                    <ColHead sort={sortProps("updated")}>{t("Actualizado")}</ColHead>
                    <DataTable.ActionsHead />
                  </DataTable.Tr></DataTable.Thead>
                  <DataTable.Tbody>{docs.data.items.map((d) => (
                    <DataTable.Tr key={d.id}>
                      <DataTable.Td><CellText data sub={d.filename}>{d.title}</CellText></DataTable.Td>
                      <DataTable.Td>{d.source}</DataTable.Td>
                      <DataTable.Td>{human(d.size)}</DataTable.Td>
                      <DataTable.Td>{d.status === "indexing" && d.progress ? `${d.progress.done}/${d.progress.total}` : d.chunks}</DataTable.Td>
                      <DataTable.Td><Pill tone={TONE[d.status] ?? "neutral"} title={d.error || undefined}>{t(LABEL[d.status] ?? d.status)}</Pill></DataTable.Td>
                      <DataTable.Td>{fmt(d.updated_at)}</DataTable.Td>
                      <DataTable.Td><Btn size="row" onClick={() => setOpen(d.id)}>{t("Ver")}</Btn></DataTable.Td>
                    </DataTable.Tr>))}</DataTable.Tbody>
                </DataTable>) : active
                  ? <EmptyState action={<Btn kind="link" onClick={clear}>{t("Quitar todos los filtros")}</Btn>}>{t("Ningún documento coincide con los filtros.")}</EmptyState>
                  : <EmptyState>{t("Aún no hay documentos.")} {canUpload ? t("Sube el primero arrastrándolo a la zona de arriba.") : t("Un colaborador puede subir ficheros.")}</EmptyState>}
              </FillArea>
              <Pager total={docs.data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} />
            </>)}
            {ups.length > 0 && (
              <Block title={t("Subidas")} count={ups.length} actions={<Btn kind="ghost" size="row" onClick={() => setUps((u) => u.filter((x) => x.state === "subiendo"))}>{t("Limpiar lista")}</Btn>}>
                <DataTable fz="sm" aria-label={t("Subidas")}>
                  <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Fichero")}</DataTable.Th><DataTable.Th>{t("Estado")}</DataTable.Th><DataTable.Th>{t("Progreso")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
                  <DataTable.Tbody>{ups.map((u) => (
                    <DataTable.Tr key={u.key}>
                      <DataTable.Td><CellText sub={u.msg}>{u.name}</CellText></DataTable.Td>
                      <DataTable.Td><Pill tone={u.state === "error" ? "danger" : u.state === "listo" ? "success" : u.state === "subiendo" ? "warn" : "neutral"}>{t(UP_LABEL[u.state])}</Pill></DataTable.Td>
                      <DataTable.Td>{u.state === "subiendo"
                        ? <ProgressBar done={u.done} total={u.size} text={t("{{done}} de {{total}}", { done: human(u.done), total: human(u.size) })} />
                        : <span className="ms-data">{human(u.size)}</span>}</DataTable.Td>
                    </DataTable.Tr>))}</DataTable.Tbody>
                </DataTable>
              </Block>)}
          </Tabs.Panel>
          <Tabs.Panel value="src">
            <ViewBar title={t("Fuentes")}
              help={<>{t("De dónde salen los documentos. Las carpetas se referencian sin copiar los originales, las wikis se leen por su API y los repositorios Git por commit, todo en solo lectura; se reescanean solos: lo nuevo y lo cambiado se indexa, lo que desaparece se retira. El progreso está en")} <Link to="/trabajos">{t("Trabajos")}</Link>.</>}
              actions={isAdmin && <>
                {instanceAdmin && <Btn icon="repo" disabled={!enabled} onClick={() => { addRepo.reset(); setRepo({ name: "", url: "", branch: "", include: GIT_PATHS.join("\n"), username: "", token: "", interval: 60 }); }}>{t("Añadir repositorio")}</Btn>}
                {instanceAdmin && <Btn icon="docs" disabled={!enabled || !adapters.data?.adapters.length} onClick={() => { connect.reset(); addWiki.reset(); setWiki({ adapter: adapters.data?.adapters[0]?.id ?? "outline", name: "", values: {}, cols: null, picked: [], interval: 60 }); }}>{t("Añadir wiki")}</Btn>}
                <Btn kind="primary" icon="folder" disabled={!enabled || !roots.data?.roots.length} onClick={() => setNewSrc({ name: "", root: roots.data?.roots[0]?.name ?? "", subpath: "", interval: 60 })}>{t("Añadir carpeta")}</Btn>
              </>}>
              <ClearFilters active={sv.active} onClear={sv.clear} shown={sv.rows.length} total={sv.total} />
            </ViewBar>
            {isAdmin && roots.data && roots.data.roots.length === 0 && <Notice tone="info" title={t("Sin carpetas autorizadas")}>{t("No hay carpetas autorizadas. El administrador de la instancia las registra en Administración → Carpetas.")}</Notice>}
            <MutationError error={scanSrc.error ?? toggleSrc.error} />
            {!sources.data ? <DataState query={sources} /> : sv.rows.length ? (
            <DataTable fz="sm">
              <DataTable.Thead><DataTable.Tr>
                <ColHead sort={sv.sortProps("name")} filter={sv.text("name")}>{t("Fuente")}</ColHead>
                <ColHead filter={sv.select("kind")}>{t("Tipo")}</ColHead>
                <ColHead sort={sv.sortProps("docs")}>{t("Documentos")}</ColHead>
                <ColHead filter={sv.select("state")}>{t("Estado")}</ColHead>
                <ColHead sort={sv.sortProps("last")}>{t("Último escaneo")}</ColHead>
                <DataTable.ActionsHead />
              </DataTable.Tr></DataTable.Thead>
              <DataTable.Tbody>{sv.rows.map((s) => (
                <DataTable.Tr key={s.id}>
                  <DataTable.Td><CellText data sub={s.kind === "upload" ? undefined : <>{s.kind === "git" ? `${s.config.web ?? s.config.url} · ${s.config.branch || t("rama principal")}${s.config.commit ? ` · ${s.config.commit.slice(0, 7)}` : ""}` : s.kind === "wiki" ? `${adapters.data?.adapters.find((a) => a.id === s.config.adapter)?.label ?? s.config.adapter} · ${s.config.settings?.base_url ?? s.config.settings?.site ?? ""} · ${s.config.collection_ids?.length ? `${s.config.collection_ids.length} ${(adapters.data?.adapters.find((a) => a.id === s.config.adapter)?.collection_label ?? t("colecciones")).toLowerCase()}` : t("todo")}` : `${s.config.root}/${s.config.subpath}`}{s.sync_interval ? t(" · cada {{sync_interval}} min", { sync_interval: s.sync_interval }) : t(" · solo manual")}</>}>{s.name}</CellText></DataTable.Td>
                  <DataTable.Td><Pill>{t(KIND[s.kind] ?? s.kind)}</Pill></DataTable.Td>
                  <DataTable.Td>{s.documents}</DataTable.Td>
                  <DataTable.Td>
                    <CellText sub={s.status === "error" ? translateServer(s.last_error) : s.status === "idle" && noFiles(s) ? t("Ninguna ruta incluida coincide con un fichero del repositorio. Revisa las rutas en «Editar».") : undefined}>
                      {s.status === "scanning" ? <Pill tone="warn">{t("escaneando")}</Pill>
                        : s.status === "error" ? <Pill tone="danger" title={translateServer(s.last_error)}>{t("error")}</Pill>
                        : !s.enabled ? <Pill>{t("pausada")}</Pill>
                        : noFiles(s) ? <Pill tone="warn">{t("sin ficheros")}</Pill>
                        : <Group gap={4}>{Object.entries(s.by_status).map(([k, v]) => <Pill key={k} tone={TONE[k] ?? "neutral"}>{`${v} ${t(LABEL[k] ?? k)}`}</Pill>)}</Group>}
                    </CellText>
                  </DataTable.Td>
                  <DataTable.Td>{s.kind !== "upload" ? fmt(s.last_sync_at) : "—"}</DataTable.Td>
                  <DataTable.Td>{isAdmin && s.kind !== "upload" && (
                    <Group gap={6} wrap="nowrap">
                      <Btn size="row" icon="refresh" loading={scanSrc.isPending && scanSrc.variables === s.id} disabled={s.status === "scanning"} onClick={() => scanSrc.mutate(s.id)}>{t("Escanear")}</Btn>
                      <Btn size="row" icon="edit" onClick={() => { saveSrc.reset(); setEditSrc({ s, name: s.name, interval: s.sync_interval ?? "", subpath: s.config.subpath ?? "", values: {}, picked: null,
                        branch: s.config.branch ?? "", include: (s.config.include ?? []).join("\n"), username: s.config.settings?.username ?? "", token: "", clearToken: false }); }}>{t("Editar")}</Btn>
                      <Btn size="row" icon={s.enabled ? "pause" : "play"} onClick={() => toggleSrc.mutate(s)}>{s.enabled ? t("Pausar") : t("Reanudar")}</Btn>
                      <Btn kind="danger" size="row" icon="trash" onClick={() => setDelSrc(s)}>{t("Quitar")}</Btn>
                    </Group>)}</DataTable.Td>
                </DataTable.Tr>))}</DataTable.Tbody>
            </DataTable>) : sv.active
              ? <EmptyState action={<Btn kind="link" onClick={sv.clear}>{t("Quitar todos los filtros")}</Btn>}>{t("Ninguna fuente coincide con los filtros.")}</EmptyState>
              : <EmptyState>{t("Aún no hay fuentes.")}</EmptyState>}
          </Tabs.Panel>
        </Tabs>

      <SidePanel opened={open !== null} onClose={() => setOpen(null)} title={detail.data?.title}>
        {!detail.data ? <DataState query={detail} /> : (
          <Stack>
            <Sheet label={t("Ficha del documento")}>
              <SheetRow term={t("Estado")}><Pill tone={TONE[detail.data.status] ?? "neutral"}>{t(LABEL[detail.data.status] ?? detail.data.status)}</Pill></SheetRow>
              <SheetRow term={t("Tamaño")}><span className="ms-data">{human(detail.data.size)}</span></SheetRow>
              <SheetRow term={t("Trozos")}><span className="ms-data">{detail.data.chunks}</span></SheetRow>
              <SheetRow term={t("Subido")}><span className="ms-data">{fmt(detail.data.created_at)}</span></SheetRow>
              <SheetRow term={t("Fichero")} wide><span className="ms-data">{detail.data.filename}</span></SheetRow>
              <SheetRow term="SHA-256" wide><span className="ms-data">{detail.data.sha256.slice(0, 12)}…</span></SheetRow>
            </Sheet>
            {detail.data.error && <Notice tone="danger">{detail.data.error}</Notice>}
            <OcrNotice ocr={detail.data.ocr} />
            <SecretsNotice found={detail.data.secrets} original />
            {detail.data.status === "duplicate" && detail.data.duplicate_of && <Notice title={t("Duplicado")}>
              <Stack gap={4}>
                <Text size="sm">{t("Tiene el mismo texto que otro documento del brain, así que no se trocea ni se calculan sus embeddings: el recall usa el original. Si el original desaparece, este pasa a indexarse.")}</Text>
                <Group><Btn size="row" onClick={() => setOpen(detail.data!.duplicate_of!)}>{t("Ver el original")}</Btn></Group>
              </Stack>
            </Notice>}
            <Group gap={6}>
              <Btn size="row" icon="download" component="a" href={`/api/brains/${graph}/docs/${detail.data.id}/file`}>{t("Descargar original")}</Btn>
              <Btn size="row" icon="knowledge" onClick={() => setFullText(detail.data!.id)}>{t("Ver texto completo")}</Btn>
              {detail.data.url && (sources.data?.sources.find((x) => x.name === detail.data!.source)?.kind === "git"
                ? <Btn size="row" icon="repo" component="a" href={detail.data.url} target="_blank" rel="noreferrer">{t("Abrir en el repositorio")}</Btn>
                : <Btn size="row" icon="docs" component="a" href={detail.data.url} target="_blank" rel="noreferrer">{t("Abrir en la wiki")}</Btn>)}
              {isAdmin && <Btn size="row" icon="refresh" loading={reindex.isPending} onClick={() => reindex.mutate(detail.data!.id)}>{t("Reindexar")}</Btn>}
              {(isAdmin || canUpload) && detail.data.source !== undefined && !sources.data?.sources.some((x) => x.name === detail.data!.source && x.kind === "directory") && <Btn kind="danger" size="row" icon="trash" onClick={() => setDel(detail.data!)}>{t("Borrar")}</Btn>}
            </Group>
            <MutationError error={reindex.error} />
            <Block title={t("Entidades mencionadas")} count={entities.data?.entities.length}>
              {entities.isLoading ? <Loading label={t("Buscando en el grafo…")} />
                : (entities.data?.entities.length ?? 0) === 0 ? <EmptyState>{t("No menciona ninguna entidad conocida del grafo.")}</EmptyState>
                : <Group gap={6}>{entities.data!.entities.map((e) => (
                    <Link key={e.uuid} to={`/grafo?nodo=${e.uuid}`} className="ms-nolink"><Pill title={`${e.type || t("entidad")} · ${e.count} ${e.count === 1 ? t("mención") : t("menciones")}`}>{e.name}{e.count > 1 ? ` ×${e.count}` : ""}</Pill></Link>))}</Group>}
            </Block>
            {((entities.data?.relations.length ?? 0) > 0 || (entities.data?.expired_count ?? 0) > 0) && (
              <Block title={t("Relaciones")} count={entities.data!.total} help={t("Hechos del grafo que unen a las entidades de este documento.")}
                actions={(entities.data?.expired_count ?? 0) > 0 && <Check label={t("Incluir hechos que dejaron de ser ciertos")} checked={relExpired} onChange={(e) => { setRelExpired(e.currentTarget.checked); setRelMax(30); }} />}>
                {entities.data!.relations.map((r) => (
                  <ListCard key={r.uuid} invalid={r.status === "invalidated"}
                    tags={<>
                      <Link to={`/grafo?nodo=${r.source_uuid}`} className="ms-nolink"><Pill>{r.source}</Pill></Link>
                      <span className="ms-data">{r.name} →</span>
                      <Link to={`/grafo?nodo=${r.target_uuid}`} className="ms-nolink"><Pill>{r.target}</Pill></Link>
                      {r.status === "invalidated" && <Pill tone="warn">{t("ya no es cierto")}</Pill>}</>}
                    meta={`${t("desde")} ${fmt(r.valid_at)}${r.invalid_at ? ` → ${fmt(r.invalid_at)}` : ""}`}>{r.fact}</ListCard>))}
                {(entities.data?.total ?? 0) > (entities.data?.relations.length ?? 0) && <Group><Btn size="row" onClick={() => setRelMax((n) => n + 30)}>{t("Mostrar más")} ({entities.data!.total - entities.data!.relations.length})</Btn></Group>}
              </Block>)}
            <Block title={t("Trozos")} count={detail.data.chunk_list.length}>
              {detail.data.chunk_list.map((c) => (
                <ListCard key={c.chunk_idx} title={`#${c.chunk_idx}${c.heading_path ? ` · ${c.heading_path}` : ""}${c.page ? ` · p. ${c.page}` : ""}`}
                  actions={<>{c.text.length > 400 && <Btn size="row" onClick={() => setOpenChunks((o) => { const n = new Set(o); n.has(c.chunk_idx) ? n.delete(c.chunk_idx) : n.add(c.chunk_idx); return n; })}>{openChunks.has(c.chunk_idx) ? t("Mostrar menos") : t("Mostrar más")}</Btn>}
                    {canUpload && <Btn size="row" icon="plus" onClick={() => { promote.reset(); setPromo({ doc: detail.data!.id, chunk: c.chunk_idx, title: `${detail.data!.title}${c.heading_path ? ` › ${c.heading_path}` : ""}`, text: c.text, name: "" }); }}>{t("Promover a memoria")}</Btn>}</>}>
                  <Text className="ms-prose" lineClamp={openChunks.has(c.chunk_idx) ? undefined : 6}>{c.text}</Text>
                </ListCard>))}
            </Block>
          </Stack>)}
      </SidePanel>
      <SidePanel opened={fullText !== null} onClose={() => setFullText(null)} title={full.data?.title ?? t("Texto completo")}>
        <DataState query={full}>{(d) => (
          <Stack>{d.truncated && <Notice tone="warn">{t("El documento tiene {{chars}} caracteres: se muestra el primer megabyte. Descarga el original para verlo entero.", { chars: d.chars.toLocaleString(locale()) })}</Notice>}
            <Text className="ms-prose">{d.text.split("\f").join("\n\n")}</Text></Stack>)}</DataState>
      </SidePanel>
      <SidePanel opened={!!ctxOf} onClose={() => setCtxOf(null)} title={ctxOf?.citation}>
        <DataState query={context}>{(d) => (
          <Stack><Text size="sm">{t("Trozos {{from}}–{{to}} de «{{title}}»", { from: d.from_chunk, to: d.to_chunk, title: d.title })}</Text><Text className="ms-prose">{d.text}</Text></Stack>)}</DataState>
      </SidePanel>
      <Modal opened={!!newSrc} onClose={() => setNewSrc(null)} title={t("Añadir carpeta")}>
        {newSrc && (
          <Stack gap="sm">
            <TextField label={t("Nombre")} value={newSrc.name} onChange={(e) => setNewSrc({ ...newSrc, name: e.currentTarget.value })} />
            <SelectField label={t("Raíz autorizada")} value={newSrc.root} onChange={(v) => v && setNewSrc({ ...newSrc, root: v })} allowDeselect={false}
              data={(roots.data?.roots ?? []).map((r) => ({ value: r.name, label: r.available ? r.name : t("{{name}} (no disponible)", { name: r.name }) }))} />
            <TextField label={t("Subcarpeta (opcional)")} description={t("Relativa a la raíz. Se recorre entera, subcarpetas incluidas; se ignoran los ocultos.")} value={newSrc.subpath} onChange={(e) => setNewSrc({ ...newSrc, subpath: e.currentTarget.value })} />
            <NumberField label={t("Reescanear cada (minutos)")} description={t("Vacío = solo cuando pulses «Escanear».")} min={5} value={newSrc.interval} onChange={(v) => setNewSrc({ ...newSrc, interval: v === "" ? "" : Number(v) })} />
            <MutationError error={addSrc.error} />
            <DialogActions><Btn kind="ghost" onClick={() => setNewSrc(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="plus" loading={addSrc.isPending} disabled={!newSrc.name.trim() || !newSrc.root} onClick={() => addSrc.mutate(newSrc)}>{t("Añadir y escanear")}</Btn></DialogActions>
          </Stack>)}
      </Modal>
      <Modal opened={!!editSrc} onClose={() => setEditSrc(null)} title={t("Editar fuente")}>
        {editSrc && (
          <Stack gap="sm">
            <TextField label={t("Nombre")} value={editSrc.name} onChange={(e) => setEditSrc({ ...editSrc, name: e.currentTarget.value })} />
            <NumberField label={t("Reescanear cada (minutos)")} description={t("Vacío = solo cuando pulses «Escanear». Mínimo 5.")} min={5} value={editSrc.interval} onChange={(v) => setEditSrc({ ...editSrc, interval: v === "" ? "" : Number(v) })} />
            {editSrc.s.kind === "directory" && <TextField label={t("Subcarpeta")} description={t("Dentro de la raíz «{{root}}». Cambiarla reindexa lo que quede fuera o dentro en el próximo escaneo.", { root: editSrc.s.config.root })} value={editSrc.subpath} onChange={(e) => setEditSrc({ ...editSrc, subpath: e.currentTarget.value })} />}
            {editSrc.s.kind === "git" && instanceAdmin && <>
              <TextField label={t("Rama")} description={t("Vacío = la rama principal del repositorio.")} value={editSrc.branch} onChange={(e) => setEditSrc({ ...editSrc, branch: e.currentTarget.value })} />
              <TextArea label={t("Rutas incluidas")} autosize minRows={3}
                description={<>{t("Una por línea. Una carpeta por su nombre entra entera. Al guardar un cambio se vuelve a leer el repositorio: lo que quede fuera sale del índice.")}
                  {editSrc.s.config.matched && Object.keys(editSrc.s.config.matched).length > 0 && <> {t("Ficheros por ruta en la última lectura:")} <span className="ms-data">{Object.entries(editSrc.s.config.matched).map(([p, n]) => `${p} ${n}`).join(" · ")}</span></>}</>}
                value={editSrc.include} onChange={(e) => setEditSrc({ ...editSrc, include: e.currentTarget.value })} />
              <TextField label={t("Usuario (opcional)")} value={editSrc.username} onChange={(e) => setEditSrc({ ...editSrc, username: e.currentTarget.value })} />
              <PasswordField label={t("Token de solo lectura (opcional)")} description={t("Vacío = conservar el guardado. Si escribes uno nuevo se comprueba la conexión antes de guardar.")} value={editSrc.token}
                disabled={editSrc.clearToken} onChange={(e) => setEditSrc({ ...editSrc, token: e.currentTarget.value })} />
              {editSrc.s.config.secrets_set?.includes("token") && <Check label={t("Quitar el token guardado")} checked={editSrc.clearToken} onChange={(e) => setEditSrc({ ...editSrc, clearToken: e.currentTarget.checked, token: "" })} />}
            </>}
            {editSrc.s.kind === "wiki" && instanceAdmin && (adapters.data?.adapters.find((a) => a.id === editSrc.s.config.adapter)?.fields ?? []).filter((f) => f.secret).map((f) => (
              <PasswordField key={f.name} label={t("{{label}} (opcional)", { label: f.label })} description={t("Vacío = conservar la guardada. Si escribes una nueva se comprueba la conexión antes de guardar.")} value={editSrc.values[f.name] ?? ""} onChange={(e) => setEditSrc({ ...editSrc, values: { ...editSrc.values, [f.name]: e.currentTarget.value } })} />))}
            {editSrc.s.kind === "wiki" && instanceAdmin && (() => {
              const label = adapters.data?.adapters.find((a) => a.id === editSrc.s.config.adapter)?.collection_label ?? t("Colecciones");
              const all = srcCols.data?.collections.map((c) => c.id) ?? [];
              const current = editSrc.picked ?? (srcCols.data?.selected.length ? srcCols.data.selected : all);
              return (
                <Block title={label} help={t("Cuáles se indexan. Una que añadas se escanea al guardar; las que quites salen del índice con sus documentos al guardar, después de confirmarlo. Las páginas de la wiki no se tocan.")}>
                  {srcCols.isLoading && <Loading label={t("Conectando con la wiki…")} />}
                  {srcCols.error && <Notice tone="warn">{(srcCols.error as Error).message}</Notice>}
                  {srcCols.data?.collections.map((c) => (
                    <Check key={c.id} label={c.name} checked={current.includes(c.id)}
                      description={[c.description, srcCols.data?.documents[c.id] ? t("{{count}} documentos indexados", { count: srcCols.data.documents[c.id] }) : ""].filter(Boolean).join(" · ") || undefined}
                      onChange={(e) => setEditSrc({ ...editSrc, picked: e.currentTarget.checked ? [...current, c.id] : current.filter((x) => x !== c.id) })} />))}
                  {editSrc.picked && editSrc.picked.length === 0 && <Notice tone="warn">{t("Elige al menos una.")}</Notice>}
                </Block>);
            })()}
            <MutationError error={saveSrc.error} />
            <DialogActions><Btn kind="ghost" onClick={() => setEditSrc(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" loading={saveSrc.isPending} disabled={!editSrc.name.trim() || (editSrc.interval !== "" && Number(editSrc.interval) < 5) || (!!editSrc.picked && editSrc.picked.length === 0) || (editSrc.s.kind === "git" && !lines(editSrc.include).length)} onClick={() => save(editSrc)}>{t("Guardar")}</Btn></DialogActions>
          </Stack>)}
      </Modal>
      <Modal opened={!!repo} onClose={() => setRepo(null)} title={t("Añadir repositorio")}>
        {repo && (
          <Stack gap="sm">
            <TextField label={t("Nombre de la fuente")} value={repo.name} onChange={(e) => setRepo({ ...repo, name: e.currentTarget.value })} />
            <TextField label={t("Dirección del repositorio")} placeholder={t("https://github.com/equipo/proyecto.git")} description={t("La dirección para clonar por https. Sin usuario ni contraseña: para un repositorio privado, usa el token.")}
              value={repo.url} onChange={(e) => setRepo({ ...repo, url: e.currentTarget.value })} />
            <TextField label={t("Rama (opcional)")} description={t("Vacío = la rama principal del repositorio.")} value={repo.branch} onChange={(e) => setRepo({ ...repo, branch: e.currentTarget.value })} />
            <TextArea label={t("Rutas incluidas")} autosize minRows={4} value={repo.include} onChange={(e) => setRepo({ ...repo, include: e.currentTarget.value })}
              description={t("Una por línea, desde la raíz. Una carpeta por su nombre (docs o docs/) entra entera; «*» no cruza carpetas y «**» sí. Solo entran documentos (Markdown, texto, HTML, PDF y ofimática). Nunca entran ficheros ocultos ni de claves (.env, *.pem, *.key, id_rsa…), y todo pasa por el detector de secretos.")} />
            <TextField label={t("Usuario (opcional)")} description={t("Solo si tu forja lo pide junto al token (Bitbucket, Gitea). Si no, se deja vacío.")} value={repo.username} onChange={(e) => setRepo({ ...repo, username: e.currentTarget.value })} />
            <PasswordField label={t("Token de solo lectura (opcional)")} description={t("Para un repositorio privado. Se guarda cifrado, no se vuelve a mostrar y solo se envía por https.")} value={repo.token}
              onChange={(e) => setRepo({ ...repo, token: e.currentTarget.value })} />
            <NumberField label={t("Reescanear cada (minutos)")} description={t("Vacío = solo cuando pulses «Escanear». Sin commits nuevos no se lee nada.")} min={5} value={repo.interval}
              onChange={(v) => setRepo({ ...repo, interval: v === "" ? "" : Number(v) })} />
            <MutationError error={addRepo.error} />
            <DialogActions><Btn kind="ghost" onClick={() => setRepo(null)}>{t("Cancelar")}</Btn>
              <Btn kind="primary" icon="plus" loading={addRepo.isPending} disabled={!repo.name.trim() || !repo.url.trim() || !lines(repo.include).length} onClick={() => addRepo.mutate(repo)}>{t("Conectar y escanear")}</Btn></DialogActions>
          </Stack>)}
      </Modal>
      <Modal opened={!!wiki} onClose={() => setWiki(null)} title={t("Añadir wiki")}>
        {wiki && ad && (
          <Stack gap="sm">
            {(adapters.data?.adapters.length ?? 0) > 1 && <SelectField label={t("Tipo de wiki")} allowDeselect={false} value={wiki.adapter} disabled={!!wiki.cols} onChange={(v) => v && setWiki({ ...wiki, adapter: v, values: {} })} data={adapters.data!.adapters.map((a) => ({ value: a.id, label: a.label }))} />}
            <TextField label={t("Nombre de la fuente")} value={wiki.name} onChange={(e) => setWiki({ ...wiki, name: e.currentTarget.value })} />
            {ad.fields.map((f) => {
              const P = f.secret ? PasswordField : TextField;
              return <P key={f.name} label={f.label} placeholder={f.placeholder} description={f.help ? `${f.help}${f.secret ? t(" Se guarda cifrada y no se vuelve a mostrar.") : ""}` : f.secret ? t("Se guarda cifrada y no se vuelve a mostrar.") : undefined}
                value={wiki.values[f.name] ?? ""} disabled={!!wiki.cols} onChange={(e) => setWiki({ ...wiki, values: { ...wiki.values, [f.name]: e.currentTarget.value } })} />;
            })}
            {!wiki.cols
              ? <><MutationError error={connect.error} />
                  <DialogActions><Btn kind="ghost" onClick={() => setWiki(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" loading={connect.isPending} disabled={ad.fields.some((f) => f.required && !(wiki.values[f.name] ?? "").trim())} onClick={() => connect.mutate(wiki)}>{t("Conectar")}</Btn></DialogActions></>
              : <>
                  <Block title={`${ad.collection_label} ${t("a indexar")}`}>
                    {wiki.cols.map((c) => (
                      <Check key={c.id} label={c.name} description={c.description || undefined} checked={wiki.picked.includes(c.id)}
                        onChange={(e) => setWiki({ ...wiki, picked: e.currentTarget.checked ? [...wiki.picked, c.id] : wiki.picked.filter((x) => x !== c.id) })} />))}
                  </Block>
                  <NumberField label={t("Resincronizar cada (minutos)")} description={t("Vacío = solo cuando pulses «Escanear».")} min={5} value={wiki.interval} onChange={(v) => setWiki({ ...wiki, interval: v === "" ? "" : Number(v) })} />
                  <MutationError error={addWiki.error} />
                  <DialogActions><Btn kind="ghost" onClick={() => setWiki(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="plus" loading={addWiki.isPending} disabled={!wiki.name.trim() || wiki.picked.length === 0} onClick={() => addWiki.mutate(wiki)}>{t("Añadir y sincronizar")}</Btn></DialogActions>
                </>}
          </Stack>)}
      </Modal>
      <Modal opened={!!promo} onClose={() => setPromo(null)} title={t("Promover a memoria")} size="lg">
        {promo && (
          <Stack gap="sm">
            <Text size="sm">{t("El pasaje se envía como propuesta con su procedencia (documento y sección).")} {canUpload && ["curator", "admin", "owner"].includes(role) ? t("Como curador, se aprueba directamente y se extraen los hechos al grafo.") : t("Entra en cuarentena hasta que un curador la apruebe.")} {t("El documento no cambia.")}</Text>
            <Text size="sm">«{promo.title}»</Text>
            <TextArea label={t("Texto a recordar")} description={t("Puedes recortarlo o reescribirlo: conviene que sea una afirmación autocontenida.")} autosize minRows={5} maxRows={14} value={promo.text} onChange={(e) => setPromo({ ...promo, text: e.currentTarget.value })} />
            <TextField label={t("Título de la propuesta (opcional)")} value={promo.name} onChange={(e) => setPromo({ ...promo, name: e.currentTarget.value })} />
            <MutationError error={promote.error} />
            {promote.data && <Notice tone="success">{t("Propuesta #{{id}} creada ({{state}}).", { id: promote.data.id, state: promote.data.status === "pending" ? t("en cuarentena") : t("aprobada; la ingesta está en Trabajos") })} <Btn kind="link" component={Link} to="/propuestas">{t("Ver propuestas")}</Btn></Notice>}
            <DialogActions><Btn kind="ghost" onClick={() => setPromo(null)}>{promote.data ? t("Cerrar") : t("Cancelar")}</Btn>
              {!promote.data && <Btn kind="primary" icon="plus" loading={promote.isPending} disabled={!promo.text.trim()} onClick={() => promote.mutate(promo)}>{t("Enviar propuesta")}</Btn>}</DialogActions>
          </Stack>)}
      </Modal>
      <ConfirmDialog opened={!!dropAsk} onClose={() => setDropAsk(null)} title={t("Quitar colecciones")} action={t("Quitar y guardar")} subject={dropAsk?.names.join(", ")}
        warning={t("Se retiran del índice {{count}} documentos de estas colecciones. Las páginas de la wiki no se tocan, y volver a marcarlas las indexa de nuevo.", { count: dropAsk?.n })}
        onConfirm={() => saveSrc.mutateAsync({ ...dropAsk!.e, confirm: dropAsk!.n })} />
      <ConfirmDialog opened={!!delSrc} onClose={() => setDelSrc(null)} title={t("Quitar fuente")} action={t("Quitar fuente")} subject={delSrc?.name}
        warning={t("Se quitan la fuente y sus {{documents}} documentos del índice. Los ficheros de la carpeta o las páginas de la wiki no se tocan.", { documents: delSrc?.documents })}
        onConfirm={() => removeSrc.mutateAsync(delSrc!)} />
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar documento")} action={t("Borrar documento")} subject={del?.title}
        warning={t("Se eliminan el original, el texto extraído y todos sus trozos del índice. No se puede deshacer.")}
        onConfirm={() => remove.mutateAsync(del!)} />
    </Page>
  );
}
