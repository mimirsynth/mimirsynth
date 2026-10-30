import { T, locale } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { fmt, get, langHeaders, send } from "../api";
import { Btn, Check, ClearFilters, ColHead, DataTable, FillArea, Modal, Notice, NumberField, Page, Pager, Panel, PasswordField, Pill, ProgressBar, SelectField, SidePanel, Tabs, TextArea, TextField, useTableView, type ColSort, type SortDir, type Tone, MutationError, ConfirmDialog, EmptyState, PageHeader, Segments, SearchBar, useServerTableView, useTabParam, ListCard, FilePicker } from "../ui";
import { SecretsNotice, type SecretFinding } from "./Secrets";
import { Link, useSearchParams } from "react-router-dom";

type Doc = {
  url?: string; id: number; source: string; title: string; filename: string; size: number; status: string; error: string; chunks: number;
  progress: { done: number; total: number } | null; created_at: string; updated_at: string; sha256: string; secrets?: SecretFinding[]; duplicate_of?: number | null;
};
type Chunk = { chunk_idx: number; heading_path: string; page: number | null; text: string };
type Hit = { document_id: number; chunk: number; title: string; citation: string; text: string; similarity: number; updated_at: string };
type Source = { id: number; kind: string; name: string; documents: number; by_status: Record<string, number>; last_sync_at: string | null; last_error: string; status: string; enabled: boolean;
  sync_interval: number | null; config: { root?: string; subpath?: string; adapter?: string; settings?: Record<string, string>; collection_ids?: string[]; secrets_set?: string[] } };
type Adapter = { id: string; label: string; collection_label: string; fields: { name: string; label: string; secret: boolean; required: boolean; placeholder: string; help: string }[] };
type Up = { key: string; name: string; size: number; done: number; state: "subiendo" | "listo" | "duplicado" | "error"; msg?: string };

const TONE: Record<string, Tone> = { active: "success", indexing: "warn", pending: "warn", error: "danger", duplicate: "neutral" };
const LABEL: Record<string, string> = { active: "indexado", indexing: "indexando", pending: T("en cola"), error: "error", duplicate: T("duplicado") };
const human = (n: number) => (n >= 1 << 30 ? `${(n / (1 << 30)).toFixed(1)} GB` : n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);
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
  const [wiki, setWiki] = useState<{ adapter: string; name: string; values: Record<string, string>; cols: { id: string; name: string; description: string }[] | null; picked: string[]; interval: number | "" } | null>(null);

  const { f, sent, setFilter, sortProps, sort, page, setPage, active, clear } = useServerTableView({ q: "", status: "", source: "", path: "" }, { debounced: ["q", "path"], firstDir: { title: "asc" } });
  const docs = useQuery({ queryKey: ["docs", graph, sent.q, sent.status, sent.source, sent.path, sort?.key ?? "updated", sort?.dir ?? "desc", page.offset, page.limit], placeholderData: keepPreviousData,
    queryFn: () => get<{ total: number; status_counts: Record<string, number>; items: Doc[] }>("docs", { graph, q: sent.q, status: sent.status, source_id: sent.source ? Number(sent.source) : undefined, path: sent.path, sort: sort?.key ?? "updated", order: sort?.dir ?? "desc", limit: page.limit, offset: page.offset }),
    refetchInterval: (qr) => (qr.state.data?.items.some((d) => d.status === "indexing" || d.status === "pending") ? 2000 : false) });
  const sources = useQuery({ queryKey: ["docs-sources", graph], queryFn: () => get<{ enabled: boolean; sources: Source[] }>("docs/sources", { graph }),
    refetchInterval: (qr) => (qr.state.data?.sources.some((x) => x.status === "scanning") ? 3000 : false) });
  const sv = useTableView(sources.data?.sources ?? [], {
    name: { get: (x: Source) => x.name }, kind: { get: (x: Source) => (x.kind === "upload" ? "subidas" : x.kind === "wiki" ? "wiki" : "carpeta"), exact: true }, docs: { get: (x: Source) => x.documents },
    state: { get: (x: Source) => (x.status === "scanning" ? "escaneando" : x.status === "error" ? t("con error") : !x.enabled ? "pausada" : t("al día")), exact: true }, last: { get: (x: Source) => x.last_sync_at ?? "" } });
  const [editSrc, setEditSrc] = useState<{ s: Source; name: string; interval: number | ""; subpath: string; values: Record<string, string>; picked: string[] | null } | null>(null);
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
  const dedupe = useMutation({ mutationFn: () => send<{ hashed: number; marked: number }>("POST", "docs/duplicates", undefined, { graph }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["docs", graph] }); qc.invalidateQueries({ queryKey: ["docs-sources", graph] }); } });
  const reindex = useMutation({ mutationFn: (id: number) => send("POST", `docs/${id}/reindex`, undefined, { graph }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["docs", graph] }); qc.invalidateQueries({ queryKey: ["doc", graph] }); } });

  const roots = useQuery({ queryKey: ["docs-roots", graph], enabled: isAdmin, queryFn: () => get<{ roots: { name: string; available: boolean }[] }>("docs/roots", { graph }) });
  const refreshSrc = () => { for (const k of ["docs", "docs-sources", "jobs", "jobs-summary"]) qc.invalidateQueries({ queryKey: [k, graph] }); };
  const addSrc = useMutation({ mutationFn: (b: NonNullable<typeof newSrc>) => send("POST", "docs/sources", { name: b.name, root: b.root, subpath: b.subpath, sync_interval: b.interval === "" ? null : b.interval }, { graph }), onSuccess: () => { setNewSrc(null); refreshSrc(); } });
  const adapters = useQuery({ queryKey: ["wiki-adapters", graph], enabled: isAdmin && instanceAdmin, queryFn: () => get<{ adapters: Adapter[] }>("docs/wiki/adapters", { graph }) });
  const ad = adapters.data?.adapters.find((a) => a.id === wiki?.adapter);
  const srcCols = useQuery({ queryKey: ["wiki-src-cols", graph, editSrc?.s.id], enabled: !!editSrc && editSrc.s.kind === "wiki" && instanceAdmin, retry: false, staleTime: 0,
    queryFn: () => get<{ collections: { id: string; name: string; description: string }[]; selected: string[] }>(`docs/sources/${editSrc!.s.id}/wiki/collections`, { graph }) });
  const connect = useMutation({ mutationFn: (w: NonNullable<typeof wiki>) => send<{ collections: { id: string; name: string; description: string }[] }>("POST", "docs/wiki/collections", { adapter: w.adapter, values: w.values }, { graph }),
    onSuccess: (r) => setWiki((w) => (w ? { ...w, cols: r.collections, picked: r.collections.map((c) => c.id) } : w)) });
  const addWiki = useMutation({ mutationFn: (w: NonNullable<typeof wiki>) => send("POST", "docs/sources/wiki", { adapter: w.adapter, values: w.values, name: w.name, collection_ids: w.picked, sync_interval: w.interval === "" ? null : w.interval }, { graph }),
    onSuccess: () => { setWiki(null); refreshSrc(); } });
  const saveSrc = useMutation({ mutationFn: (e: NonNullable<typeof editSrc>) => send("PATCH", `docs/sources/${e.s.id}`, {
      name: e.name.trim(), ...(e.interval === "" ? { clear_interval: true } : { sync_interval: Number(e.interval) }), ...(e.s.kind === "directory" ? { subpath: e.subpath } : {}),
      ...(e.s.kind === "wiki" && Object.values(e.values).some((v) => v.trim()) ? { values: e.values } : {}), ...(e.s.kind === "wiki" && e.picked ? { collection_ids: e.picked } : {}) }, { graph }),
    onSuccess: () => { setEditSrc(null); refreshSrc(); } });
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
  return (
    <Page>
      <PageHeader title={t("Conocimiento")} description={<>{t("Documentos del brain: se guardan sus originales, se trocean y se buscan por significado y por texto. Cada pasaje se muestra con su procedencia.")}</>} />
      {!enabled && <Notice tone="warn">{t("El índice documental necesita PostgreSQL con pgvector; esta instancia no lo tiene y no se pueden indexar documentos.")}</Notice>}
        <Tabs value={tab} onChange={(v) => setTab(v)} className="ms-tabs-fill">
          <Tabs.List>
            <Tabs.Tab value="docs">{t("Documentos (")}{Object.values(docs.data?.status_counts ?? {}).reduce((a, b) => a + b, 0)})</Tabs.Tab>
            <Tabs.Tab value="src">{t("Fuentes (")}{sources.data?.sources.length ?? 0})</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="docs" pt="sm">
            <Stack gap="sm">
              <SearchBar mode="submit" value={q} onChange={setQ} placeholder={t("Busca en los documentos por significado o por texto…")} onSubmit={setQuery} onClear={() => { setQ(""); setQuery(""); }} submitted={!!query} loading={hits.isLoading} disabled={!enabled} />
              {query ? (
                  <FillArea><Stack gap="xs">
                    {hits.isLoading && <EmptyState>{t("Buscando…")}</EmptyState>}
                    <MutationError error={hits.error} />
                    {hits.data && hits.data.results.length === 0 && <EmptyState>{t("Sin resultados para «{{query}}».", { query })}</EmptyState>}
                    {(hits.data?.results ?? []).map((h) => (
                      <ListCard key={`${h.document_id}-${h.chunk}`} title={h.citation}
                        aside={<><Pill size="xs" title={t("similitud del embedding (0 si solo coincide por texto)")}>{h.similarity ? `${Math.round(h.similarity * 100)} %` : "texto"}</Pill>{fmt(h.updated_at)}</>}
                        actions={<>
                          <Btn size="row" icon="info" onClick={() => setCtxOf(h)}>{t("Ver contexto")}</Btn>
                          <Btn size="row" icon="download" component="a" href={`/api/brains/${graph}/docs/${h.document_id}/file`}>{t("Original")}</Btn>
                          {canUpload && <Btn size="row" icon="plus" onClick={() => { promote.reset(); setPromo({ doc: h.document_id, chunk: h.chunk, title: h.citation, text: h.text, name: "" }); }}>{t("Promover a memoria")}</Btn>}</>}>
                        {h.text}
                      </ListCard>))}
                  </Stack></FillArea>
              ) : (<>
              {canUpload && (
                <div className="ms-drop" data-over={over ? "" : undefined}
                  onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                  onDrop={(e) => { e.preventDefault(); setOver(false); if (enabled) void start(e.dataTransfer.files); }}>
                  <Group justify="center" gap="md">
                    <Text size="sm">{t("Arrastra aquí ficheros (.md, .txt, .rst, .html, .pdf) o")}</Text>
                    <FilePicker label={t("Elegir ficheros")} accept=".md,.markdown,.txt,.rst,.log,.html,.htm,.pdf" multiple disabled={!enabled} onFiles={(fl) => void start(fl)} />
                  </Group>
                </div>)}
              {ups.length > 0 && (
                <Stack gap={6}>
                  {ups.map((u) => u.state === "subiendo"
                    ? <ProgressBar key={u.key} done={u.done} total={u.size} text={`${u.name} · ${human(u.done)} de ${human(u.size)}`} />
                    : <Group key={u.key} gap={6}><Pill size="xs" tone={u.state === "error" ? "danger" : u.state === "listo" ? "success" : "neutral"}>{u.state}</Pill><Text size="sm">{u.name}</Text>{u.msg && <Text size="xs" c="dimmed">{u.msg}</Text>}</Group>)}
                  <Group><Btn size="row" onClick={() => setUps((u) => u.filter((x) => x.state === "subiendo"))}>{t("Limpiar lista")}</Btn></Group>
                </Stack>)}
              <Segments label={t("Estado")} value={f.status || "all"} onChange={(v) => setFilter({ status: v === "all" ? "" : v })}
                data={[{ value: "all", label: t("Todos"), count: Object.values(docs.data?.status_counts ?? {}).reduce((a, b) => a + b, 0) }, ...Object.entries(LABEL).filter(([k]) => (docs.data?.status_counts[k] ?? 0) > 0 || f.status === k).map(([k, v]) => ({ value: k, label: v[0].toUpperCase() + v.slice(1), count: docs.data?.status_counts[k] ?? 0 }))]} />
              <Group gap="xs" justify="space-between">
                <ClearFilters active={active} onClear={clear} />
                {isAdmin && <Group gap="xs" ml="auto">
                  {dedupe.data && <Text size="xs" c="dimmed">{dedupe.data.marked ? t("{{n}} duplicados sacados del índice.", { n: dedupe.data.marked }) : t("No hay duplicados entre los documentos indexados.")}</Text>}
                  <Btn size="row" icon="search" loading={dedupe.isPending} onClick={() => dedupe.mutate()}
                    title={t("Los documentos nuevos se comprueban al indexarse. Esto revisa los que ya estaban indexados y saca del índice los que repiten el texto de otro, sin borrar nada del origen.")}>{t("Buscar duplicados")}</Btn>
                </Group>}
              </Group>
              <MutationError error={dedupe.error} />
              <FillArea>
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
                  <DataTable.Tbody>{(docs.data?.items ?? []).map((d) => (
                    <DataTable.Tr key={d.id}>
                      <DataTable.Td><Text fw={500} size="sm">{d.title}</Text><Text size="xs" c="dimmed">{d.filename}</Text></DataTable.Td>
                      <DataTable.Td>{d.source}</DataTable.Td>
                      <DataTable.Td>{human(d.size)}</DataTable.Td>
                      <DataTable.Td>{d.status === "indexing" && d.progress ? `${d.progress.done}/${d.progress.total}` : d.chunks}</DataTable.Td>
                      <DataTable.Td><Pill size="xs" tone={TONE[d.status] ?? "neutral"} title={d.error || undefined}>{t(LABEL[d.status] ?? d.status)}</Pill></DataTable.Td>
                      <DataTable.Td>{fmt(d.updated_at)}</DataTable.Td>
                      <DataTable.Td><Btn size="row" onClick={() => setOpen(d.id)}>{t("Ver")}</Btn></DataTable.Td>
                    </DataTable.Tr>))}</DataTable.Tbody>
                </DataTable>
                {docs.data?.items.length === 0 && (active
                  ? <Text c="dimmed" mt="sm">{t("Ningún documento coincide con los filtros.")}</Text>
                  : <EmptyState>{t("Aún no hay documentos.")} {canUpload ? t("Sube el primero arrastrándolo a la zona de arriba.") : t("Un colaborador puede subir ficheros.")}</EmptyState>)}
              </FillArea>
              <Pager total={docs.data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} />
              </>)}
            </Stack>
          </Tabs.Panel>
          <Tabs.Panel value="src" pt="sm">
            <Stack gap="sm">
              <Group justify="space-between">
                <Text size="sm" c="dimmed">{t("De dónde salen los documentos. Las carpetas se referencian sin copiar los originales y las wikis se leen por su API (solo lectura); ambas se reescanean solas: lo nuevo y lo cambiado se indexa, lo que desaparece se retira. El progreso está en")} <Link to="/trabajos">{t("Trabajos")}</Link>.</Text>
                {isAdmin && (
                  <Group gap={6} wrap="nowrap">
                    {instanceAdmin && <Btn icon="docs" disabled={!enabled || !adapters.data?.adapters.length} onClick={() => { connect.reset(); addWiki.reset(); setWiki({ adapter: adapters.data?.adapters[0]?.id ?? "outline", name: "", values: {}, cols: null, picked: [], interval: 60 }); }}>{t("Añadir wiki")}</Btn>}
                    <Btn kind="primary" icon="folder" disabled={!enabled || !roots.data?.roots.length} onClick={() => setNewSrc({ name: "", root: roots.data?.roots[0]?.name ?? "", subpath: "", interval: 60 })}>{t("Añadir carpeta")}</Btn>
                  </Group>)}
              </Group>
              {isAdmin && roots.data && roots.data.roots.length === 0 && <Notice tone="info">{t("No hay carpetas autorizadas. El administrador de la instancia las registra en Administración → Carpetas.")}</Notice>}
              <ClearFilters active={sv.active} onClear={sv.clear} shown={sv.rows.length} total={sv.total} />
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
                    <DataTable.Td><Text size="sm" fw={500}>{s.name}</Text>{s.kind !== "upload" && <Text size="xs" c="dimmed" className="ms-data">{s.kind === "wiki" ? `${adapters.data?.adapters.find((a) => a.id === s.config.adapter)?.label ?? s.config.adapter} · ${s.config.settings?.base_url ?? s.config.settings?.site ?? ""} · ${s.config.collection_ids?.length ? `${s.config.collection_ids.length} ${(adapters.data?.adapters.find((a) => a.id === s.config.adapter)?.collection_label ?? "colecciones").toLowerCase()}` : "todo"}` : `${s.config.root}/${s.config.subpath}`}{s.sync_interval ? t(" · cada {{sync_interval}} min", { sync_interval: s.sync_interval }) : t(" · solo manual")}</Text>}</DataTable.Td>
                    <DataTable.Td><Pill size="xs">{s.kind === "upload" ? "subidas" : s.kind === "wiki" ? "wiki" : "carpeta"}</Pill></DataTable.Td>
                    <DataTable.Td>{s.documents}</DataTable.Td>
                    <DataTable.Td>
                      {s.status === "scanning" ? <Pill size="xs" tone="warn">{t("escaneando")}</Pill>
                        : s.status === "error" ? <Pill size="xs" tone="danger" title={s.last_error}>{t("error")}</Pill>
                        : !s.enabled ? <Pill size="xs">{t("pausada")}</Pill>
                        : Object.entries(s.by_status).map(([k, v]) => <Pill key={k} size="xs" tone={TONE[k] ?? "neutral"}>{`${v} ${t(LABEL[k] ?? k)}`}</Pill>)}
                      {s.status === "error" && <Text size="xs" className="ms-text-danger" lineClamp={2}>{s.last_error}</Text>}
                    </DataTable.Td>
                    <DataTable.Td>{s.kind !== "upload" ? fmt(s.last_sync_at) : "—"}</DataTable.Td>
                    <DataTable.Td>{isAdmin && s.kind !== "upload" && (
                      <Group gap={6} wrap="nowrap">
                        <Btn size="row" icon="refresh" loading={scanSrc.isPending && scanSrc.variables === s.id} disabled={s.status === "scanning"} onClick={() => scanSrc.mutate(s.id)}>{t("Escanear")}</Btn>
                        <Btn size="row" icon="edit" onClick={() => { saveSrc.reset(); setEditSrc({ s, name: s.name, interval: s.sync_interval ?? "", subpath: s.config.subpath ?? "", values: {}, picked: null }); }}>{t("Editar")}</Btn>
                        <Btn size="row" icon={s.enabled ? "pause" : "play"} onClick={() => toggleSrc.mutate(s)}>{s.enabled ? t("Pausar") : t("Reanudar")}</Btn>
                        <Btn kind="danger" size="row" icon="trash" onClick={() => setDelSrc(s)}>{t("Quitar")}</Btn>
                      </Group>)}</DataTable.Td>
                  </DataTable.Tr>))}</DataTable.Tbody>
              </DataTable>
              {(scanSrc.error || toggleSrc.error) && <Notice tone="danger">{((scanSrc.error || toggleSrc.error) as Error).message}</Notice>}
            </Stack>
          </Tabs.Panel>
        </Tabs>

      <SidePanel opened={open !== null} onClose={() => setOpen(null)} title={detail.data?.title}>
        {detail.data && (
          <Stack>
            <Group gap={6}><Pill size="xs" tone={TONE[detail.data.status] ?? "neutral"}>{t(LABEL[detail.data.status] ?? detail.data.status)}</Pill><Pill size="xs">{human(detail.data.size)}</Pill><Pill size="xs">{detail.data.chunks} {t("trozos")}</Pill></Group>
            <Text size="xs" c="dimmed" className="ms-data">{t("{{filename}} · sha256 {{hash}}… · subido {{date}}", { filename: detail.data.filename, hash: detail.data.sha256.slice(0, 12), date: fmt(detail.data.created_at) })}</Text>
            {detail.data.error && <Notice tone="danger">{detail.data.error}</Notice>}
            <SecretsNotice found={detail.data.secrets} original />
            {detail.data.status === "duplicate" && detail.data.duplicate_of && <Notice title={t("Duplicado")}>
              <Stack gap={4}>
                <Text size="xs">{t("Tiene el mismo texto que otro documento del brain, así que no se trocea ni se calculan sus embeddings: el recall usa el original. Si el original desaparece, este pasa a indexarse.")}</Text>
                <Group><Btn size="row" onClick={() => setOpen(detail.data!.duplicate_of!)}>{t("Ver el original")}</Btn></Group>
              </Stack>
            </Notice>}
            <Group gap={6}>
              <Btn size="row" icon="download" component="a" href={`/api/brains/${graph}/docs/${detail.data.id}/file`}>{t("Descargar original")}</Btn>
              <Btn size="row" icon="knowledge" onClick={() => setFullText(detail.data!.id)}>{t("Ver texto completo")}</Btn>
              {detail.data.url && <Btn size="row" icon="docs" component="a" href={detail.data.url} target="_blank" rel="noreferrer">{t("Abrir en la wiki")}</Btn>}
              {isAdmin && <Btn size="row" icon="refresh" loading={reindex.isPending} onClick={() => reindex.mutate(detail.data!.id)}>{t("Reindexar")}</Btn>}
              {(isAdmin || canUpload) && detail.data.source !== undefined && !sources.data?.sources.some((x) => x.name === detail.data!.source && x.kind === "directory") && <Btn kind="danger" size="row" icon="trash" onClick={() => setDel(detail.data!)}>{t("Borrar")}</Btn>}
            </Group>
            <MutationError error={reindex.error} />
            <Title order={5}>{t("Entidades mencionadas")}</Title>
            {entities.isLoading ? <EmptyState>{t("Buscando en el grafo…")}</EmptyState>
              : (entities.data?.entities.length ?? 0) === 0 ? <EmptyState>{t("No menciona ninguna entidad conocida del grafo.")}</EmptyState>
              : <Group gap={6}>{entities.data!.entities.map((e) => (
                  <Link key={e.uuid} to={`/grafo?nodo=${e.uuid}`} className="ms-nolink"><Pill size="xs" title={`${e.type || "entidad"} · ${e.count} ${e.count === 1 ? t("mención") : "menciones"}`}>{e.name}{e.count > 1 ? ` ×${e.count}` : ""}</Pill></Link>))}</Group>}
            {((entities.data?.relations.length ?? 0) > 0 || (entities.data?.expired_count ?? 0) > 0) && <>
              <Title order={5}>{t("Relaciones")}</Title>
              <Text size="xs" c="dimmed">{t("Hechos del grafo que unen a las entidades de este documento.")}</Text>
              {(entities.data?.expired_count ?? 0) > 0 && <Check label={t("Incluir hechos que dejaron de ser ciertos")} checked={relExpired} onChange={(e) => { setRelExpired(e.currentTarget.checked); setRelMax(30); }} />}
              {entities.data!.relations.map((r) => (
                <ListCard key={r.uuid} invalid={r.status === "invalidated"}
                  tags={<>
                    <Link to={`/grafo?nodo=${r.source_uuid}`} className="ms-nolink"><Pill size="xs">{r.source}</Pill></Link>
                    <Text size="xs" className="ms-data">{r.name} →</Text>
                    <Link to={`/grafo?nodo=${r.target_uuid}`} className="ms-nolink"><Pill size="xs">{r.target}</Pill></Link>
                    {r.status === "invalidated" && <Pill size="xs" tone="warn">{t("ya no es cierto")}</Pill>}</>}
                  meta={`${t("desde")} ${fmt(r.valid_at)}${r.invalid_at ? ` → ${fmt(r.invalid_at)}` : ""}`}>{r.fact}</ListCard>))}
              {(entities.data?.total ?? 0) > (entities.data?.relations.length ?? 0) && <Group><Btn size="row" onClick={() => setRelMax((n) => n + 30)}>{t("Mostrar más")} ({entities.data!.total - entities.data!.relations.length})</Btn></Group>}
            </>}
            <Title order={5}>{t("Trozos")}</Title>
            {detail.data.chunk_list.map((c) => (
              <ListCard key={c.chunk_idx} title={`#${c.chunk_idx}${c.heading_path ? ` · ${c.heading_path}` : ""}${c.page ? ` · p. ${c.page}` : ""}`}
                actions={<>{c.text.length > 400 && <Btn size="row" onClick={() => setOpenChunks((o) => { const n = new Set(o); n.has(c.chunk_idx) ? n.delete(c.chunk_idx) : n.add(c.chunk_idx); return n; })}>{openChunks.has(c.chunk_idx) ? t("Mostrar menos") : t("Mostrar más")}</Btn>}
                  {canUpload && <Btn size="row" icon="plus" onClick={() => { promote.reset(); setPromo({ doc: detail.data!.id, chunk: c.chunk_idx, title: `${detail.data!.title}${c.heading_path ? ` › ${c.heading_path}` : ""}`, text: c.text, name: "" }); }}>{t("Promover a memoria")}</Btn>}</>}>
                <Text className="ms-prose" lineClamp={openChunks.has(c.chunk_idx) ? undefined : 6}>{c.text}</Text>
              </ListCard>))}
          </Stack>)}
      </SidePanel>
      <SidePanel opened={fullText !== null} onClose={() => setFullText(null)} title={full.data?.title ?? t("Texto completo")}>
        {full.isLoading && <EmptyState>{t("Cargando…")}</EmptyState>}
        <MutationError error={full.error} />
        {full.data && <Stack>{full.data.truncated && <Notice tone="warn">{t("El documento tiene {{chars}} caracteres: se muestra el primer megabyte. Descarga el original para verlo entero.", { chars: full.data.chars.toLocaleString(locale()) })}</Notice>}
          <Text className="ms-prose">{full.data.text}</Text></Stack>}
      </SidePanel>
      <SidePanel opened={!!ctxOf} onClose={() => setCtxOf(null)} title={ctxOf?.citation}>
        {context.isLoading && <EmptyState>{t("Cargando…")}</EmptyState>}
        {context.data && <Stack><Text size="xs" c="dimmed">{t("Trozos {{from}}–{{to}} de «{{title}}»", { from: context.data.from_chunk, to: context.data.to_chunk, title: context.data.title })}</Text><Text className="ms-prose">{context.data.text}</Text></Stack>}
      </SidePanel>
      <Modal opened={!!newSrc} onClose={() => setNewSrc(null)} title={t("Añadir carpeta")}>
        {newSrc && (
          <Stack>
            <TextField label={t("Nombre")} value={newSrc.name} onChange={(e) => setNewSrc({ ...newSrc, name: e.currentTarget.value })} />
            <SelectField label={t("Raíz autorizada")} value={newSrc.root} onChange={(v) => v && setNewSrc({ ...newSrc, root: v })} allowDeselect={false}
              data={(roots.data?.roots ?? []).map((r) => ({ value: r.name, label: r.available ? r.name : t("{{name}} (no disponible)", { name: r.name }) }))} />
            <TextField label={t("Subcarpeta (opcional)")} description={t("Relativa a la raíz. Se recorre entera, subcarpetas incluidas; se ignoran los ocultos.")} value={newSrc.subpath} onChange={(e) => setNewSrc({ ...newSrc, subpath: e.currentTarget.value })} />
            <NumberField label={t("Reescanear cada (minutos)")} description={t("Vacío = solo cuando pulses «Escanear».")} min={5} value={newSrc.interval} onChange={(v) => setNewSrc({ ...newSrc, interval: v === "" ? "" : Number(v) })} />
            <MutationError error={addSrc.error} />
            <Group justify="flex-end"><Btn kind="ghost" onClick={() => setNewSrc(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="plus" loading={addSrc.isPending} disabled={!newSrc.name.trim() || !newSrc.root} onClick={() => addSrc.mutate(newSrc)}>{t("Añadir y escanear")}</Btn></Group>
          </Stack>)}
      </Modal>
      <Modal opened={!!editSrc} onClose={() => setEditSrc(null)} title={t("Editar fuente")}>
        {editSrc && (
          <Stack>
            <TextField label={t("Nombre")} value={editSrc.name} onChange={(e) => setEditSrc({ ...editSrc, name: e.currentTarget.value })} />
            <NumberField label={t("Reescanear cada (minutos)")} description={t("Vacío = solo cuando pulses «Escanear». Mínimo 5.")} min={5} value={editSrc.interval} onChange={(v) => setEditSrc({ ...editSrc, interval: v === "" ? "" : Number(v) })} />
            {editSrc.s.kind === "directory" && <TextField label={t("Subcarpeta")} description={t("Dentro de la raíz «{{root}}». Cambiarla reindexa lo que quede fuera o dentro en el próximo escaneo.", { root: editSrc.s.config.root })} value={editSrc.subpath} onChange={(e) => setEditSrc({ ...editSrc, subpath: e.currentTarget.value })} />}
            {editSrc.s.kind === "wiki" && instanceAdmin && (adapters.data?.adapters.find((a) => a.id === editSrc.s.config.adapter)?.fields ?? []).filter((f) => f.secret).map((f) => (
              <PasswordField key={f.name} label={t("{{label}} (opcional)", { label: f.label })} description={t("Vacío = conservar la guardada. Si escribes una nueva se comprueba la conexión antes de guardar.")} value={editSrc.values[f.name] ?? ""} onChange={(e) => setEditSrc({ ...editSrc, values: { ...editSrc.values, [f.name]: e.currentTarget.value } })} />))}
            {editSrc.s.kind === "wiki" && instanceAdmin && (() => {
              const label = adapters.data?.adapters.find((a) => a.id === editSrc.s.config.adapter)?.collection_label ?? t("Colecciones");
              const all = srcCols.data?.collections.map((c) => c.id) ?? [];
              const current = editSrc.picked ?? (srcCols.data?.selected.length ? srcCols.data.selected : all);
              return (
                <Stack gap={4}>
                  <Text size="sm" fw={600}>{label}</Text>
                  <Text size="xs" c="dimmed">{t("Cuáles se indexan. Las que quites dejan de indexarse y sus páginas se retiran en el próximo escaneo.")}</Text>
                  {srcCols.isLoading && <Text size="xs" c="dimmed">{t("Conectando con la wiki…")}</Text>}
                  {srcCols.error && <Notice tone="warn">{(srcCols.error as Error).message}</Notice>}
                  {srcCols.data?.collections.map((c) => (
                    <Check key={c.id} label={c.name} description={c.description || undefined} checked={current.includes(c.id)}
                      onChange={(e) => setEditSrc({ ...editSrc, picked: e.currentTarget.checked ? [...current, c.id] : current.filter((x) => x !== c.id) })} />))}
                  {editSrc.picked && editSrc.picked.length === 0 && <Notice tone="warn">{t("Elige al menos una.")}</Notice>}
                </Stack>);
            })()}
            <MutationError error={saveSrc.error} />
            <Group justify="flex-end"><Btn kind="ghost" onClick={() => setEditSrc(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" loading={saveSrc.isPending} disabled={!editSrc.name.trim() || (editSrc.interval !== "" && Number(editSrc.interval) < 5) || (!!editSrc.picked && editSrc.picked.length === 0)} onClick={() => saveSrc.mutate(editSrc)}>{t("Guardar")}</Btn></Group>
          </Stack>)}
      </Modal>
      <Modal opened={!!wiki} onClose={() => setWiki(null)} title={t("Añadir wiki")}>
        {wiki && ad && (
          <Stack>
            {(adapters.data?.adapters.length ?? 0) > 1 && <SelectField label={t("Tipo de wiki")} allowDeselect={false} value={wiki.adapter} disabled={!!wiki.cols} onChange={(v) => v && setWiki({ ...wiki, adapter: v, values: {} })} data={adapters.data!.adapters.map((a) => ({ value: a.id, label: a.label }))} />}
            <TextField label={t("Nombre de la fuente")} value={wiki.name} onChange={(e) => setWiki({ ...wiki, name: e.currentTarget.value })} />
            {ad.fields.map((f) => {
              const P = f.secret ? PasswordField : TextField;
              return <P key={f.name} label={f.label} placeholder={f.placeholder} description={f.help ? `${f.help}${f.secret ? t(" Se guarda cifrada y no se vuelve a mostrar.") : ""}` : f.secret ? t("Se guarda cifrada y no se vuelve a mostrar.") : undefined}
                value={wiki.values[f.name] ?? ""} disabled={!!wiki.cols} onChange={(e) => setWiki({ ...wiki, values: { ...wiki.values, [f.name]: e.currentTarget.value } })} />;
            })}
            {!wiki.cols
              ? <><MutationError error={connect.error} />
                  <Group justify="flex-end"><Btn kind="ghost" onClick={() => setWiki(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" loading={connect.isPending} disabled={ad.fields.some((f) => f.required && !(wiki.values[f.name] ?? "").trim())} onClick={() => connect.mutate(wiki)}>{t("Conectar")}</Btn></Group></>
              : <>
                  <Text size="sm" fw={500}>{ad.collection_label} {t("a indexar")}</Text>
                  <Stack gap={4}>{wiki.cols.map((c) => (
                    <Check key={c.id} label={c.name} description={c.description || undefined} checked={wiki.picked.includes(c.id)}
                      onChange={(e) => setWiki({ ...wiki, picked: e.currentTarget.checked ? [...wiki.picked, c.id] : wiki.picked.filter((x) => x !== c.id) })} />))}</Stack>
                  <NumberField label={t("Resincronizar cada (minutos)")} description={t("Vacío = solo cuando pulses «Escanear».")} min={5} value={wiki.interval} onChange={(v) => setWiki({ ...wiki, interval: v === "" ? "" : Number(v) })} />
                  <MutationError error={addWiki.error} />
                  <Group justify="flex-end"><Btn kind="ghost" onClick={() => setWiki(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="plus" loading={addWiki.isPending} disabled={!wiki.name.trim() || wiki.picked.length === 0} onClick={() => addWiki.mutate(wiki)}>{t("Añadir y sincronizar")}</Btn></Group>
                </>}
          </Stack>)}
      </Modal>
      <Modal opened={!!promo} onClose={() => setPromo(null)} title={t("Promover a memoria")} size="lg">
        {promo && (
          <Stack>
            <Text size="sm" c="dimmed">{t("El pasaje se envía como propuesta con su procedencia (documento y sección).")} {canUpload && ["curator", "admin", "owner"].includes(role) ? t("Como curador, se aprueba directamente y se extraen los hechos al grafo.") : t("Entra en cuarentena hasta que un curador la apruebe.")} {t("El documento no cambia.")}</Text>
            <Text size="xs" fw={500}>{promo.title}</Text>
            <TextArea label={t("Texto a recordar")} description={t("Puedes recortarlo o reescribirlo: conviene que sea una afirmación autocontenida.")} autosize minRows={5} maxRows={14} value={promo.text} onChange={(e) => setPromo({ ...promo, text: e.currentTarget.value })} />
            <TextField label={t("Título de la propuesta (opcional)")} value={promo.name} onChange={(e) => setPromo({ ...promo, name: e.currentTarget.value })} />
            <MutationError error={promote.error} />
            {promote.data && <Notice tone="info">{t("Propuesta #{{id}} creada ({{state}}).", { id: promote.data.id, state: promote.data.status === "pending" ? t("en cuarentena") : t("aprobada; la ingesta está en Trabajos") })} <Link to="/propuestas">{t("Ver propuestas")}</Link></Notice>}
            <Group justify="flex-end"><Btn kind="ghost" onClick={() => setPromo(null)}>{promote.data ? t("Cerrar") : t("Cancelar")}</Btn>
              {!promote.data && <Btn kind="primary" icon="plus" loading={promote.isPending} disabled={!promo.text.trim()} onClick={() => promote.mutate(promo)}>{t("Enviar propuesta")}</Btn>}</Group>
          </Stack>)}
      </Modal>
      <ConfirmDialog opened={!!delSrc} onClose={() => setDelSrc(null)} title={t("Quitar fuente")} action={t("Quitar fuente")} subject={delSrc?.name}
        warning={t("Se quitan la fuente y sus {{documents}} documentos del índice. Los ficheros de la carpeta o las páginas de la wiki no se tocan.", { documents: delSrc?.documents })}
        onConfirm={() => removeSrc.mutateAsync(delSrc!)} />
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar documento")} action={t("Borrar documento")} subject={del?.title}
        warning={t("Se eliminan el original, el texto extraído y todos sus trozos del índice. No se puede deshacer.")}
        onConfirm={() => remove.mutateAsync(del!)} />
    </Page>
  );
}
