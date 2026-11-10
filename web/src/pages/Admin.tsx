import { locale, T, translateServer } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { Btn, CellText, Check, ClearFilters, ColHead, ComboField, DataState, DataTable, DialogActions, Loading, Modal, Notice, NumberField, PasswordField, Pill, SelectField, TextArea, TextField, Toggle, useTableView, MutationError, ConfirmDialog, EmptyState, Page, PageHeader, useTabParam, Tone, SettingsBody, SettingsGroup, SettingsLayout, SettingsRow, SubNav, ViewBar } from "../ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Brain, fmt, get, Me, send } from "../api";
import AdminFolders from "./AdminFolders";
import AdminSettings from "./AdminSettings";
import AdminUsers from "./AdminUsers";
import TokensPanel from "./TokensPanel";
import ConnectAgent from "./ConnectAgent";
import Federation from "./Federation";
import Secrets from "./Secrets";
import BrainExport from "./BrainExport";
import BrainImport from "./BrainImport";
import BrainRetention from "./BrainRetention";
import BrainWebhooks from "./BrainWebhooks";
import { BrainAiUsage, InstanceAiUsage } from "./AiUsage";
import { ReindexPanel, StartReindex } from "./AdminReindex";
import AdminNotifications from "./AdminNotifications";
import AdminMetrics from "./AdminMetrics";
import AdminGraph from "./AdminGraph";
import SealedNotice from "./SealedNotice";

type AuditRow = { ts: string; action: string; detail: unknown };
const AUDIT_COLS = { ts: { get: (a: AuditRow) => a.ts }, action: { get: (a: AuditRow) => a.action, exact: true }, detail: { get: (a: AuditRow) => JSON.stringify(a.detail ?? "") } };
function AuditTable({ rows }: { rows: AuditRow[] }) {
  const { t } = useTranslation();
  const v = useTableView(rows, AUDIT_COLS);
  return (<>
    <ViewBar title={t("Auditoría")}>{v.active && <ClearFilters active onClear={v.clear} shown={v.rows.length} total={v.total} />}</ViewBar>
    {v.rows.length === 0 ? <EmptyState>{t("Sin resultados")}</EmptyState> : <DataTable fz="xs">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("ts")}>{t("Fecha")}</ColHead>
          <ColHead sort={v.sortProps("action")} filter={v.select("action")}>{t("Acción")}</ColHead>
          <ColHead filter={v.text("detail", t("Buscar en el detalle…"))}>{t("Detalle")}</ColHead>
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((a, i) => <DataTable.Tr key={i}><DataTable.Td className="ms-data">{fmt(a.ts)}</DataTable.Td><DataTable.Td>{a.action}</DataTable.Td><DataTable.Td>{JSON.stringify(a.detail)}</DataTable.Td></DataTable.Tr>)}</DataTable.Tbody>
      </DataTable>}
  </>);
}

const ROLES = [
  { value: "reader", label: T("Lector") }, { value: "contributor", label: T("Colaborador") }, { value: "curator", label: T("Curador") },
  { value: "admin", label: T("Administrador") }, { value: "owner", label: T("Propietario") },
];
type Member = { user_id: number; email: string | null; name: string; role: string; implicit?: boolean };

function Members({ brain }: { brain: Brain }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["members", brain.slug], queryFn: () => get<Member[]>(`brains/${brain.slug}/members`), retry: false });
  const [email, setEmail] = useState(""); const [role, setRole] = useState("reader");
  const refresh = () => qc.invalidateQueries({ queryKey: ["members", brain.slug] });
  const add = useMutation({ mutationFn: (b: { email: string; role: string }) => send("PUT", `brains/${brain.slug}/members`, b), onSuccess: () => { setEmail(""); refresh(); } });
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `brains/${brain.slug}/members/${id}`), onSuccess: refresh });
  const [ask, setAsk] = useState<Member | null>(null);
  const mv = useTableView(data ?? [], { user: { get: (m: Member) => m.email ?? m.name }, role: { get: (m: Member) => (m.implicit ? "owner" : m.role), label: (r: string) => ROLES.find((x) => x.value === r)?.label ?? r, exact: true } });
  if (error) return <EmptyState>{t("Solo los administradores del brain gestionan sus miembros.")}</EmptyState>;
  if (!data) return <Loading />;
  const roles = ROLES.map((r) => ({ ...r, label: t(r.label) }));
  // The add form is the view's bar: who and with which role, then «Add»; the table's filters are cleared from the same bar.
  return (<>
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title={t("Quitar miembro")} action={t("Quitar miembro")} subject={ask?.email ?? ask?.name}
        warning={t("Pierde el acceso a este brain. Sus tokens de API siguen existiendo hasta que se revoquen.")} onConfirm={() => del.mutateAsync(ask!.user_id)} />
      <ViewBar title={t("Miembros")} actions={<Btn kind="primary" disabled={!email} onClick={() => add.mutate({ email, role })} icon="plus">{t("Añadir")}</Btn>}>
        <TextField label={t("Añadir por email")} placeholder={t("persona@dominio.com")} value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
        <SelectField label={t("Rol")} data={roles} value={role} onChange={(v) => setRole(v ?? "reader")} allowDeselect={false} />
        <ClearFilters active={mv.active} onClear={mv.clear} shown={mv.rows.length} total={mv.total} />
      </ViewBar>
      <MutationError error={add.error} />
      {mv.rows.length === 0 ? <EmptyState>{t("Sin resultados")}</EmptyState> : <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead sort={mv.sortProps("user")} filter={mv.text("user")}>{t("Usuario")}</ColHead><ColHead sort={mv.sortProps("role")} filter={mv.select("role")}>{t("Rol")}</ColHead><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{mv.rows.map((m) => (
          <DataTable.Tr key={m.user_id}>
            <DataTable.Td>{m.email ?? m.name}</DataTable.Td>
            <DataTable.Td>{m.implicit
              ? <CellText sub={t("administrador de la instancia")}><Pill>{t("Propietario")}</Pill></CellText>
              : <SelectField aria-label={t("Rol")} data={roles} value={m.role} allowDeselect={false} onChange={(v) => v && m.email && add.mutate({ email: m.email, role: v })} />}</DataTable.Td>
            <DataTable.Td>{!m.implicit && <Btn kind="danger" size="row" onClick={() => setAsk(m)} icon="trash">{t("Quitar")}</Btn>}</DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>}
  </>);
}

function Tokens({ brain }: { brain: Brain }) {
  return (
    <TokensPanel brain={brain.slug} brains={[brain]} />
  );
}

// The last full check of an LLM or a decider (issue 424): the structured output ingestion needs, or the letter with logprobs.
type Fitness = { at: string; ok: boolean; fit: boolean | null; text: string; warning?: string; current: boolean };
type Engine = { threshold?: number; dim?: number; id: number; name: string; base_url: string; model: string; small_model: string; has_key: boolean; enabled: boolean; is_default: boolean; fitness?: Fitness | null };
type EngineForm = { threshold?: number; id?: number; name: string; base_url: string; model: string; small_model: string; api_key: string; enabled: boolean };
const EMPTY: EngineForm = { name: "", base_url: "", model: "", small_model: "", api_key: "", enabled: true };

function Engines({ kind, title, description, help }: { kind: "llm" | "embedding" | "decision"; title: string; description: string; help: ReactNode }) {
  const { t } = useTranslation();
  const emb = kind === "embedding"; const dec = kind === "decision"; const path = emb ? "embedding-engines" : dec ? "decision-engines" : "llm-engines";
  const qc = useQueryClient();
  const list = useQuery({ queryKey: [path], queryFn: () => get<Engine[]>(path) });
  const [form, setForm] = useState<EngineForm | null>(null);
  const [tests, setTests] = useState<Record<number, { text: string; warning?: string; ok: boolean }>>({});
  const refresh = () => { qc.invalidateQueries({ queryKey: [path] }); qc.invalidateQueries({ queryKey: ["ai-status"] }); };
  // An LLM or a decider is tested as soon as it is saved (issue 420): it is kept even when it fails, with the reason in sight.
  const save = useMutation({ mutationFn: (f: EngineForm) => f.id ? send<Engine>("PATCH", `${path}/${f.id}`, f) : send<Engine>("POST", path, f),
    onSuccess: (e) => { setForm(null); refresh(); if (!emb && e?.id) test.mutate(e.id); } });
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `${path}/${id}`), onSuccess: refresh });
  const [ask, setAsk] = useState<Engine | null>(null);
  const mk = useMutation({ mutationFn: (id: number) => send("POST", `${path}/${id}/default`), onSuccess: refresh });
  const [reindex, setReindex] = useState<Engine | null>(null);
  const def = (list.data ?? []).find((e) => e.is_default);
  const otherModel = (e: Engine) => emb && e.enabled && !e.is_default && (!def || def.model !== e.model || def.dim !== e.dim);
  const test = useMutation({ mutationFn: (id: number) => send<{ ok: boolean; ms: number; error?: string; reply?: string; warning?: string }>("POST", `${path}/${id}/test`),
    onSuccess: (r, id) => { qc.invalidateQueries({ queryKey: [path] }); setTests((prev) => ({ ...prev, [id]: r.ok
      ? { ok: true, text: `OK · ${r.ms} ms · ${emb ? `«${r.reply}»` : translateServer(r.reply ?? "")}`, warning: r.warning ? translateServer(r.warning) : undefined }
      : { ok: false, text: t("Error: {{error}}", { error: translateServer(r.error ?? "") }) } })); },
    onError: (err, id) => setTests((prev) => ({ ...prev, [id]: { ok: false, text: t("Error: {{error}}", { error: (err as Error).message }) } })) });
  const [models, setModels] = useState<string[]>([]); const [mErr, setMErr] = useState("");
  const loadModels = useMutation({ mutationFn: (f: EngineForm) => send<{ models: string[]; error: string | null }>("POST", "llm-engines/models", { base_url: f.base_url, api_key: f.api_key || undefined, engine_id: f.id }),
    onSuccess: (r) => { setModels(r.models); setMErr(r.error ?? ""); } });
  const ev = useTableView(list.data ?? [], { name: { get: (e: Engine) => e.name }, url: { get: (e: Engine) => e.base_url }, model: { get: (e: Engine) => e.model },
    state: { get: (e: Engine) => (e.is_default ? t("por defecto") : !e.enabled ? "desactivado" : !e.has_key ? t("sin clave") : "activo"), exact: true } });
  const open = (f: EngineForm | null) => { setForm(f); setModels([]); setMErr(""); if (f?.id) loadModels.mutate(f); };
  const set = (k: keyof EngineForm, v: string | boolean) => setForm((f) => f && { ...f, [k]: v });
  return (
    <SettingsGroup title={title} description={description} help={help} action={<Btn kind="primary" onClick={() => open({ ...EMPTY })} icon="plus">{t("Añadir motor")}</Btn>}>
    <SettingsBody>
      <AiStatus kind={kind} title={title}><ClearFilters active={ev.active} onClear={ev.clear} shown={ev.rows.length} total={ev.total} /></AiStatus>
      {emb && <ReindexPanel onDone={refresh} />}
      <MutationError error={mk.error} />
      {!list.data ? <DataState query={list} />
        : list.data.length === 0 ? <EmptyState>{dec ? t("Sin decisores: toda propuesta de un colaborador espera a un curador.") : emb ? t("Sin motores: se usan las variables MIMIRSYNTH_EMBEDDING_*. Añade el que ya usas (mismo modelo) para gestionarlo desde aquí.") : t("Sin motores. Mientras no haya ninguno se usan las variables MIMIRSYNTH_LLM_* si existen; si tampoco, la ingesta queda desactivada.")}</EmptyState>
        : ev.rows.length === 0 ? <EmptyState>{t("Sin resultados")}</EmptyState> : <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead sort={ev.sortProps("name")} filter={ev.text("name")}>{t("Nombre")}</ColHead><ColHead filter={ev.text("url")}>{t("Endpoint")}</ColHead><ColHead sort={ev.sortProps("model")} filter={ev.text("model")}>{t("Modelo")}</ColHead><ColHead filter={ev.select("state")}>{t("Estado")}</ColHead><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>
          {ev.rows.map((e) => (
            <DataTable.Tr key={e.id}>
              <DataTable.Td>{e.name}</DataTable.Td><DataTable.Td><Text size="xs" className="ms-breakall">{e.base_url}</Text></DataTable.Td><DataTable.Td>{e.model}{emb && e.dim ? ` · ${e.dim}d` : ""}{dec && e.threshold ? t(" · umbral {{threshold}}", { threshold: e.threshold }) : ""}</DataTable.Td>
              <DataTable.Td><CellText sub={!emb && <FitnessLine fitness={e.fitness} decider={dec} />}>
                <Group gap={4}>{e.is_default && <Pill tone="success">{t("por defecto")}</Pill>}{!e.enabled && <Pill>{t("desactivado")}</Pill>}{!e.has_key && <Pill tone="warn">{t("sin clave")}</Pill>}</Group>
                {tests[e.id] && <Text size="xs" className={tests[e.id].ok ? "ms-text-ok" : "ms-text-danger"}>{tests[e.id].text}</Text>}
                {tests[e.id]?.warning && <Group gap={4} wrap="nowrap" align="flex-start"><Pill tone="warn">{t("Aviso")}</Pill><Text size="xs">{tests[e.id].warning}</Text></Group>}
              </CellText></DataTable.Td>
              <DataTable.Td><Group gap={4} wrap="nowrap">
                <Btn size="row" loading={test.isPending && test.variables === e.id} onClick={() => test.mutate(e.id)} icon="test">{t("Probar")}</Btn>
                {!e.is_default && e.enabled && (!otherModel(e) || !def) && <Btn size="row" onClick={() => mk.mutate(e.id)}>{t("Por defecto")}</Btn>}
                {otherModel(e) && <Btn size="row" icon="refresh" onClick={() => setReindex(e)}>{t("Reindexar")}</Btn>}
                <Btn size="row" onClick={() => open({ ...e, api_key: "" })} icon="edit">{t("Editar")}</Btn>
                <Btn kind="danger" size="row" onClick={() => setAsk(e)} icon="trash">{t("Borrar")}</Btn></Group></DataTable.Td>
            </DataTable.Tr>))}
        </DataTable.Tbody>
      </DataTable>}
      {emb && <StartReindex engine={reindex} onClose={() => setReindex(null)} />}
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title={t("Borrar motor")} action={t("Borrar motor")} subject={ask?.name}
        warning={t("Los brains que lo usen pasan al motor por defecto, o a las variables de entorno si no hay otro.")} onConfirm={() => del.mutateAsync(ask!.id)} />
      <Modal opened={!!form} onClose={() => setForm(null)} title={(form?.id ? t("Editar ") : t("Añadir ")) + (emb ? t("motor de embeddings") : dec ? t("decisor") : t("motor LLM"))}>
        {form && <Stack gap="sm">
          <TextField label={t("Endpoint (base URL)")} placeholder={t("http://gateway:4000/v1")} value={form.base_url} onChange={(e) => set("base_url", e.currentTarget.value)} />
          <PasswordField label={t("Clave de API")} description={form.id ? t("Vacío = conservar la actual") : undefined} value={form.api_key} onChange={(e) => set("api_key", e.currentTarget.value)}
            onBlur={() => form.base_url && (form.api_key || form.id) && loadModels.mutate(form)} />
          <Group><Btn disabled={!form.base_url} loading={loadModels.isPending} onClick={() => loadModels.mutate(form)} icon="models">{t("Cargar modelos")}</Btn></Group>
          {mErr && <Notice tone="warn">{mErr}</Notice>}
          <ComboField label={t("Modelo")} description={models.length ? t("{{length}} modelos disponibles", { length: models.length }) : t("Rellena endpoint y clave para listar los modelos del proveedor")} disabled={emb && !!form.id} data={models} limit={50} value={form.model} onChange={(v) => set("model", v)} placeholder={t("Elige uno o escribe el nombre")} />
          {!emb && !dec && <ComboField label={t("Modelo pequeño (opcional)")} description={t("Para tareas ligeras; por defecto el mismo modelo")} data={models} limit={50} value={form.small_model} onChange={(v) => set("small_model", v)} />}
          {dec && <NumberField label={t("Umbral de confianza")} description={t("Por debajo, la propuesta va a revisión humana")} min={0.5} max={0.99} step={0.05} decimalScale={2} value={form.threshold ?? 0.8} onChange={(v) => set("threshold", Number(v) as unknown as string)} />}
          <TextField label={t("Nombre")} value={form.name} onChange={(e) => set("name", e.currentTarget.value)} />
          <Toggle label={t("Activado")} checked={form.enabled} onChange={(e) => set("enabled", e.currentTarget.checked)} />
          <MutationError error={save.error} />
          <DialogActions><Btn kind="ghost" onClick={() => setForm(null)}>{t("Cancelar")}</Btn>
            <Btn kind="primary" disabled={!form.name || !form.base_url || !form.model} loading={save.isPending} onClick={() => save.mutate(form)} icon="save">{t("Guardar")}</Btn></DialogActions>
        </Stack>}
      </Modal>
    </SettingsBody>
    </SettingsGroup>
  );
}

// «Structured output: checked 09/11 08:00 ✅»: kept on the engine, so it is there on every visit and after a change of engine (issue 424).
// It is the second line of the engine's state cell (CellText sub), so it is already in the muted style.
function FitnessLine({ fitness: f, decider }: { fitness?: Fitness | null; decider: boolean }) {
  const { t } = useTranslation();
  if (!f) return <>{decider ? t("Letra y logprobs: sin comprobar todavía") : t("Salida estructurada: sin comprobar todavía")}</>;
  const at = new Date(f.at).toLocaleString(locale(), { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const mark = f.fit === null ? "⚠️" : f.ok && !f.warning ? "✅" : f.ok ? "⚠️" : "❌";  // i18n-ok: symbols
  const why = f.fit === null ? t("no respondió; se repite en una hora") : !f.ok || f.warning ? translateServer(f.warning ?? f.text) : "";
  return (<>
    {decider ? t("Letra y logprobs: comprobados el {{at}}", { at }) : t("Salida estructurada: comprobada el {{at}}", { at })} {mark}
    {!f.current && <>{" "}{t("(antes del último cambio de modelo o endpoint)")}</>}
    {why && <span className={f.ok ? undefined : "ms-text-danger"}>{" · "}{why}</span>}
  </>);
}

type AiSt = { configured: boolean; source: string | null; name: string | null; healthy?: boolean; error?: string; model?: string; ms?: number };
/** The bar of an engine section: the state of the engine in force and its last check (`meta`), «Check» on the right, and the table's
 *  filters (`children`). When the engine comes from the .env, a titled notice says so. */
function AiStatus({ kind, title, children }: { kind: "llm" | "embedding" | "decision"; title: string; children?: ReactNode }) {
  const { t } = useTranslation();
  const st = useQuery({ queryKey: ["ai-status", "check"], queryFn: () => get<Record<string, AiSt>>("ai-status", { check: true }), refetchOnWindowFocus: false });
  const k = kind === "decision" ? "decider" : kind;
  const e = st.data?.[k];
  const env = e?.source === "env";
  const tone: Tone = !e ? "neutral" : !e.configured ? "neutral" : e.healthy === undefined ? (k === "embedding" ? "neutral" : "warn") : e.healthy ? "success" : "danger";
  const text = !e ? t("comprobando…") : !e.configured ? t("sin configurar") : e.healthy === undefined ? (env ? t("por variables de entorno") : t("configurado")) : `${e.healthy ? "OK" : t("caído")} · ${env ? t("variables de entorno") : e.name}`;
  const at = new Date(st.dataUpdatedAt).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  // El resultado se queda a la vista hasta la siguiente comprobación: un aviso efímero no da tiempo a leerlo (#78).
  const result = st.isFetching ? t("Comprobando la conexión con el proveedor…")
    : e?.healthy !== undefined && <><span className={e.healthy ? "ms-text-ok" : "ms-text-danger"}>{e.healthy ? t("Responde · {{model}} · {{ms}} ms", { model: e.model, ms: e.ms }) : t("Error con {{model}}: {{error}}", { model: e.model, error: translateServer(e.error ?? "") })}</span>
      {" · "}{t("comprobado a las {{at}}", { at })}</>;
  const envHelp = k === "llm" ? t("Se usan las variables MIMIRSYNTH_LLM_* del .env (cambiarlas exige reiniciar la API). Si añades un motor aquí, tiene prioridad sobre ellas.")
    : t("Se usan las variables MIMIRSYNTH_EMBEDDING_* del .env (cambiarlas exige reiniciar la API). Si añades un motor aquí, tiene prioridad sobre ellas.");
  return (<>
    <ViewBar title={title} meta={<><Pill tone={tone}>{t("Estado")}: {text}</Pill>{result && <>{" "}{result}</>}</>}
      actions={<Btn loading={st.isFetching} onClick={() => st.refetch()} icon="refresh">{t("Comprobar")}</Btn>}>{children}</ViewBar>
    {env && <Notice tone="info" title={t("Viene de las variables de entorno")}>{envHelp}</Notice>}
    <MutationError error={st.error} />
  </>);
}

export default function Admin({ me, brain, setBrain }: { me: Me; brain: string; setBrain: (s: string) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const navigate = useNavigate();
  const wizard = useMutation({ mutationFn: () => send("POST", "setup/reopen"), onSuccess: () => { qc.invalidateQueries({ queryKey: ["me"] }); qc.invalidateQueries({ queryKey: ["setup"] }); navigate("/configuracion"); } });
  // «Crea tu primer brain» (Primeros pasos) llega con ?crear=brain: abre el diálogo y quita el parámetro para que una recarga no lo reabra.
  const [sp, setSp] = useSearchParams();
  const [open, setOpen] = useState(() => me.is_admin && sp.get("crear") === "brain"); const [editing, setEditing] = useState(false);
  useEffect(() => { if (sp.has("crear")) { const p = new URLSearchParams(sp); p.delete("crear"); setSp(p, { replace: true }); } }, [sp, setSp]);
  const [slug, setSlug] = useState(""); const [name, setName] = useState(""); const [graph, setGraph] = useState(""); const [desc, setDesc] = useState("");
  const [del, setDel] = useState(false); const [delGraph, setDelGraph] = useState(false);
  const remove = useMutation({ mutationFn: () => send<{ deleted: string; graph: string; graph_deleted: boolean }>("POST", `brains/${brain}/delete`, { confirm: cur?.slug, delete_graph: delGraph }),
    onSuccess: async (r) => { setDel(false); setDelGraph(false); const left = (await qc.fetchQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains"), staleTime: 0 })).filter((b) => b.slug !== r.deleted); qc.setQueryData(["brains"], left); setBrain(left[0]?.slug ?? ""); } });
  const [newName, setNewName] = useState(""); const [newSlug, setNewSlug] = useState(""); const [newGraph, setNewGraph] = useState(""); const [newDesc, setNewDesc] = useState("");
  const create = useMutation({ mutationFn: () => send<Brain>("POST", "brains", { slug, name, description: desc, graph_name: graph || undefined }),
    onSuccess: (b) => { setSlug(""); setName(""); setGraph(""); setDesc(""); setOpen(false); qc.invalidateQueries({ queryKey: ["brains"] }); setBrain(b.slug); } });
  const rename = useMutation({
    mutationFn: () => send<Brain & { old_graph_kept?: string }>("PATCH", `brains/${brain}`, { name: newName, description: newDesc, slug: newSlug, graph_name: newGraph }),
    onSuccess: (r) => { setEditing(false); setDone(r.old_graph_kept ?? ""); if (r.slug !== brain) setBrain(r.slug); qc.invalidateQueries(); } });
  const [done, setDone] = useState("");
  const users = useQuery({ queryKey: ["users"], enabled: me.is_admin, queryFn: () => get<any[]>("users") });
  const audit = useQuery({ queryKey: ["audit"], enabled: me.is_admin, queryFn: () => get<any[]>("audit") });
  const cur = (brains.data ?? []).find((b) => b.slug === brain);
  const [sectionParam, setSection] = useTabParam("brains", "seccion");
  const canAdmin = cur && ["admin", "owner"].includes(cur.role);
  // The active brain, one entry per topic, each with the same role rules as the card it holds; «brains» is the old single page.
  const brainNav = [{ value: "brains", label: t("Brain activo") }, ...(cur ? [
    { value: "connect", label: t("Conectar un agente") }, { value: "members", label: t("Miembros") }, { value: "tokens", label: t("Tokens de API") }, { value: "federation", label: t("Federación") },
    ...(canAdmin ? [{ value: "secrets", label: t("Secretos") }, { value: "webhooks", label: t("Webhooks de entrada") }, { value: "brain-usage", label: t("Consumo de IA") }] : []),
    ...(cur.role === "owner" ? [{ value: "retention", label: t("Retención") }] : []),
    ...(canAdmin ? [{ value: "export", label: t("Exportar") }] : []),
  ] : [])];
  const nav: ({ value: string; label: string } | { heading: string })[] = [
    { heading: t("Brain") }, ...brainNav,
    ...(me.is_admin ? [
      { heading: t("Cuentas") }, { value: "users", label: t("Usuarios") }, { value: "security", label: t("Seguridad") }, { value: "identity", label: t("Identidad") }, { value: "mail", label: t("Correo (SMTP)") },
      { heading: t("Modelos de IA") }, { value: "llm", label: t("Modelo LLM") }, { value: "embedding", label: t("Embeddings") }, { value: "decision", label: t("Decisor") }, { value: "usage", label: t("Consumo") },
      { heading: t("Documentos") }, { value: "folders", label: t("Carpetas") }, { value: "docs", label: t("Límites") },
      { heading: t("Sistema") }, { value: "general", label: t("General") }, { value: "graph", label: t("Base de datos del grafo") }, { value: "recall", label: t("Recuerdo (recall)") }, { value: "ingest", label: t("Ingesta y trabajos") }, { value: "notifications", label: t("Notificaciones") }, { value: "metrics", label: t("Métricas") }, { value: "audit", label: t("Auditoría") },
    ] : []),
  ];
  // a link to a section this person cannot see (or to one that no longer exists) opens the first one
  const section = nav.some((i) => "value" in i && i.value === sectionParam) ? sectionParam : "brains";
  return (
    <Page>
      <PageHeader title={t("Administración")} description={t("Acceso a cada brain y, para el administrador de la instancia, usuarios, seguridad, modelos de IA, documentos y el resto de ajustes.")}
        actions={me.is_admin && <Btn icon="play" loading={wizard.isPending} onClick={() => wizard.mutate()}>{t("Asistente de configuración")}</Btn>} />
      {me.is_admin && <SealedNotice />}
      {me.auth_mode === "off" && <Notice tone="warn" title={t("Modo prototipo")}>{t("Sin autenticación: todos son administradores.")}</Notice>}
      <Modal opened={open} onClose={() => setOpen(false)} title={t("Crear brain")}>
        <Stack gap="sm">
          <TextField label={t("Slug")} description={t("Identificador permanente (minúsculas, números y guiones)")} placeholder={t("familia")} value={slug} onChange={(e) => setSlug(e.currentTarget.value)} />
          <TextField label={t("Nombre")} placeholder={t("Familia")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <TextArea label={t("Descripción")} description={t("De qué trata este brain. El decisor la usa para juzgar si una propuesta encaja en él.")} autosize minRows={2} value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
          <TextField label={t("Grafo existente (opcional)")} description={t("Vacío = grafo nuevo con el nombre del slug")} value={graph} onChange={(e) => setGraph(e.currentTarget.value)} />
          <MutationError error={create.error} />
          <DialogActions><Btn kind="ghost" onClick={() => setOpen(false)}>{t("Cancelar")}</Btn><Btn kind="primary" disabled={!slug || !name} loading={create.isPending} onClick={() => create.mutate()} icon="plus">{t("Crear")}</Btn></DialogActions>
        </Stack>
      </Modal>
      <Modal opened={editing} onClose={() => setEditing(false)} title={t("Editar brain")}>
        <Stack gap="sm">
          <TextField label={t("Nombre")} value={newName} onChange={(e) => setNewName(e.currentTarget.value)} data-autofocus />
          <TextArea label={t("Descripción")} description={t("De qué trata este brain. El decisor la usa para juzgar si una propuesta encaja en él.")} autosize minRows={2} value={newDesc} onChange={(e) => setNewDesc(e.currentTarget.value)} />
          <TextField label={t("Slug")} description={t("Va en las URLs de la API. Los tokens siguen funcionando; actualiza la URL de tus hooks y plugins.")} value={newSlug} onChange={(e) => setNewSlug(e.currentTarget.value)} />
          <TextField label={t("Grafo")} disabled={!me.is_admin} value={newGraph} onChange={(e) => setNewGraph(e.currentTarget.value)}
            description={me.is_admin ? t("Cambiarlo copia el grafo con el nuevo nombre, reescribe el group_id de cada nodo y arista, y verifica los conteos. El original se conserva.") : t("Solo el administrador de la instancia puede cambiar el grafo.")} />
          {newGraph !== cur?.graph_name && <Notice tone="warn">{t("Los agentes que escriban en Graphiti con group_id «")}{cur?.graph_name}{t("» seguirán escribiendo en el grafo antiguo; deberás repuntarlos a «")}{newGraph}».</Notice>}
          <MutationError error={rename.error} />
          <DialogActions><Btn kind="ghost" onClick={() => setEditing(false)}>{t("Cancelar")}</Btn><Btn kind="primary" disabled={!newName.trim() || !newSlug || !newGraph} loading={rename.isPending} onClick={() => rename.mutate()} icon="save">{t("Guardar")}</Btn></DialogActions>
        </Stack>
      </Modal>
      {/* An acknowledgement, not a choice: its one button closes it, so it has no «Cancel». */}
      <Modal opened={!!done} onClose={() => setDone("")} title={t("Grafo migrado")}>
        <Stack gap="sm"><Text size="sm">{t("El brain usa ya el grafo nuevo. El grafo original «")}{done}{t("» se ha conservado como copia de seguridad; bórralo cuando hayas comprobado que todo está bien (y repuntado los agentes).")}</Text>
          <DialogActions><Btn kind="primary" onClick={() => setDone("")}>{t("Entendido")}</Btn></DialogActions></Stack>
      </Modal>
      <ConfirmDialog opened={del} onClose={() => setDel(false)} title={t("Borrar brain")} action={delGraph ? t("Borrar brain y grafo") : t("Borrar brain")} requireText={cur?.slug}
        warning={t("Vas a borrar «{{name}}». Se eliminan sus miembros, tokens de API, propuestas, ontología, correcciones de tipos y el índice de texto. No se puede deshacer.", { name: cur?.name })}
        onConfirm={() => remove.mutateAsync()}>
        <Check checked={delGraph} onChange={(e) => setDelGraph(e.currentTarget.checked)} label={t("Borrar también el grafo «{{graph_name}}» de FalkorDB (episodios, entidades y hechos)", { graph_name: cur?.graph_name })} description={t("Si no lo marcas, el grafo se conserva sin brain asociado y puede volver a asociarse creando un brain con ese grafo.")} />
      </ConfirmDialog>
      <SettingsLayout nav={<SubNav label={t("Secciones de administración")} value={section} onChange={setSection} items={nav} />}>
        {section === "brains" && <>
          {/* The active brain is one row: its name with its slug and graph under it, then its role and its actions on the right. */}
          <SettingsGroup title={t("Brain activo")} description={t("Cámbialo con el selector de la barra lateral.")}
            action={me.is_admin && <Btn kind="primary" icon="plus" onClick={() => setOpen(true)}>{t("Crear brain")}</Btn>}>
            {cur ? (
              <SettingsRow label={cur.name} help={<span className="ms-data">{cur.slug} {t("· grafo")} {cur.graph_name}</span>}>
                <Group gap={6}>
                  <Pill>{t(ROLES.find((r) => r.value === cur.role)?.label ?? cur.role)}</Pill>{cur.read_only && <Pill tone="warn">{t("solo lectura")}</Pill>}
                  {canAdmin && <Btn size="row" icon="edit" onClick={() => { setNewName(cur.name); setNewSlug(cur.slug); setNewGraph(cur.graph_name); setNewDesc(cur.description); rename.reset(); setEditing(true); }}>{t("Editar")}</Btn>}
                  {cur.role === "owner" && <Btn kind="danger" size="row" icon="trash" onClick={() => { setDelGraph(false); setDel(true); }}>{t("Borrar")}</Btn>}
                </Group>
              </SettingsRow>) : <SettingsBody><EmptyState>{t("No hay ningún brain seleccionado.")}</EmptyState></SettingsBody>}
          </SettingsGroup>
          {me.is_admin && <BrainImport onOpen={(s) => { qc.invalidateQueries({ queryKey: ["brains"] }); setBrain(s); }} />}
        </>}
        {cur && <>
          {section === "connect" && <SettingsGroup title={t("Conectar un agente")} description={t("Elige tu agente y copia lo que necesita, ya con este servidor, este brain y un token.")}
            help={t("Se pone en verde en cuanto el agente hace su primera llamada.")}><SettingsBody><ConnectAgent brain={cur} /></SettingsBody></SettingsGroup>}
          {section === "members" && <SettingsGroup title={t("Miembros")} description={t("Quién tiene acceso a este brain y con qué rol.")}><SettingsBody><Members brain={cur} /></SettingsBody></SettingsGroup>}
          {section === "tokens" && <SettingsGroup title={t("Tokens de API")} description={t("Para plugins y MCP.")}
            help={t("Acotados a este brain; el rol de un token nunca supera el tuyo y no puede ser administrador.")}><SettingsBody><Tokens brain={cur} /></SettingsBody></SettingsGroup>}
          {section === "federation" && <SettingsGroup title={t("Federación")} description={t("Prestar la lectura de este brain a otros, o ver de quién recibe.")}
            help={t("Solo lectura y revocable.")}><SettingsBody><Federation brain={cur} canAdmin={!!canAdmin} /></SettingsBody></SettingsGroup>}
          {section === "secrets" && <Secrets brain={cur} />}
          {section === "webhooks" && <BrainWebhooks brain={cur} />}
          {section === "brain-usage" && <BrainAiUsage brain={cur} />}
          {section === "retention" && <BrainRetention brain={cur} />}
          {section === "export" && <BrainExport brain={cur} />}
        </>}
        {section === "users" && <AdminUsers me={me.id} />}
        {section === "llm" && <Engines kind="llm" title={t("Modelo LLM")} description={t("Motores que extraen hechos al ingerir propuestas.")}
          help={t("Cualquier endpoint compatible con OpenAI; se usa el motor por defecto y las claves se guardan cifradas.")} />}
        {section === "embedding" && <Engines kind="embedding" title={t("Embeddings")} description={t("Motores de embeddings (recall, índice de texto e ingesta).")}
          help={t("Los vectores guardados dependen del modelo: para pasar a un motor con otro modelo usa «Reindexar», que los calcula todos en sombra antes de cambiar.")} />}
        {section === "usage" && <InstanceAiUsage />}
        {section === "decision" && <Engines kind="decision" title={t("Decisor")} description={t("Modelos de decisión cerrada para el triaje de propuestas y el corrector de tipos.")}
          help={t("Solo aprueban lo factual con confianza suficiente; lo dudoso va a un curador.")} />}
        {section === "folders" && <AdminFolders />}
        {section === "audit" && <SettingsGroup title={t("Auditoría")} description={t("Registro de las acciones de administración y de acceso.")}>
          <SettingsBody>{audit.data ? <AuditTable rows={audit.data} /> : <DataState query={audit} />}</SettingsBody></SettingsGroup>}
        {section === "graph" && <AdminGraph />}
        {section === "notifications" && <AdminNotifications />}
        {section === "metrics" && <AdminMetrics />}
        {["general", "security", "mail", "identity", "docs", "recall", "ingest"].includes(section) && <AdminSettings group={section} />}
      </SettingsLayout>
    </Page>
  );
}
