import { locale, T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, Check, ClearFilters, ColHead, ComboField, CopyBtn, DataTable, Modal, Notice, NumberField, Panel, PasswordField, Pill, SelectField, Tabs, TextArea, TextField, Toggle, useTableView, MutationError, ConfirmDialog, EmptyState, Page, PageHeader, FillArea, useTabParam, Tone, SettingsBody, SettingsGroup, SettingsLayout, SubNav } from "../ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Brain, fmt, get, Me, send } from "../api";
import AdminFolders from "./AdminFolders";
import AdminSettings from "./AdminSettings";
import AdminUsers from "./AdminUsers";
import TokensPanel from "./TokensPanel";
import Federation from "./Federation";
import Secrets from "./Secrets";
import BrainExport from "./BrainExport";
import BrainImport from "./BrainImport";
import { ReindexPanel, StartReindex } from "./AdminReindex";
import AdminNotifications from "./AdminNotifications";

type AuditRow = { ts: string; action: string; detail: unknown };
const AUDIT_COLS = { ts: { get: (a: AuditRow) => a.ts }, action: { get: (a: AuditRow) => a.action, exact: true }, detail: { get: (a: AuditRow) => JSON.stringify(a.detail ?? "") } };
function AuditTable({ rows }: { rows: AuditRow[] }) {
  const { t } = useTranslation();
  const v = useTableView(rows, AUDIT_COLS);
  return (
    <Stack gap="xs">
      {v.active && <Group><Btn size="row" onClick={v.clear}>{t("Quitar todos los filtros (")}{v.rows.length} {t("de")} {v.total})</Btn></Group>}
      <DataTable fz="xs">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("ts")}>{t("Fecha")}</ColHead>
          <ColHead sort={v.sortProps("action")} filter={v.select("action")}>{t("Acción")}</ColHead>
          <ColHead filter={v.text("detail", t("Buscar en el detalle…"))}>{t("Detalle")}</ColHead>
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((a, i) => <DataTable.Tr key={i}><DataTable.Td>{fmt(a.ts)}</DataTable.Td><DataTable.Td>{a.action}</DataTable.Td><DataTable.Td>{JSON.stringify(a.detail)}</DataTable.Td></DataTable.Tr>)}</DataTable.Tbody>
      </DataTable>
    </Stack>
  );
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
  if (error) return <Text c="dimmed" size="sm">{t("Solo los administradores del brain gestionan sus miembros.")}</Text>;
  return (
    <Stack gap="xs">
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title={t("Quitar miembro")} action={t("Quitar miembro")} subject={ask?.email ?? ask?.name}
        warning={t("Pierde el acceso a este brain. Sus tokens de API siguen existiendo hasta que se revoquen.")} onConfirm={() => del.mutateAsync(ask!.user_id)} />
      <ClearFilters active={mv.active} onClear={mv.clear} shown={mv.rows.length} total={mv.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead sort={mv.sortProps("user")} filter={mv.text("user")}>{t("Usuario")}</ColHead><ColHead sort={mv.sortProps("role")} filter={mv.select("role")}>{t("Rol")}</ColHead><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{mv.rows.map((m) => (
          <DataTable.Tr key={m.user_id}>
            <DataTable.Td>{m.email ?? m.name}</DataTable.Td>
            <DataTable.Td>{m.implicit
              ? <Group gap={6}><Pill>{t("Propietario")}</Pill><Text size="xs" c="dimmed">{t("administrador de la instancia")}</Text></Group>
              : <SelectField size="xs" w={150} data={ROLES.map((r) => ({ ...r, label: t(r.label) }))} value={m.role} allowDeselect={false} onChange={(v) => v && m.email && add.mutate({ email: m.email, role: v })} />}</DataTable.Td>
            <DataTable.Td>{!m.implicit && <Btn kind="danger" size="row" onClick={() => setAsk(m)} icon="trash">{t("Quitar")}</Btn>}</DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
      <Group align="flex-end" gap="xs">
        <TextField size="xs" label={t("Añadir por email")} placeholder={t("persona@dominio.com")} value={email} onChange={(e) => setEmail(e.currentTarget.value)} w={260} />
        <SelectField size="xs" label={t("Rol")} data={ROLES.map((r) => ({ ...r, label: t(r.label) }))} value={role} onChange={(v) => setRole(v ?? "reader")} allowDeselect={false} w={150} />
        <Btn kind="primary" disabled={!email} onClick={() => add.mutate({ email, role })} icon="plus">{t("Añadir")}</Btn>
      </Group>
      <MutationError error={add.error} />
    </Stack>
  );
}

function Tokens({ brain }: { brain: Brain }) {
  return (
    <TokensPanel brain={brain.slug} brains={[brain]} />
  );
}

type Engine = { threshold?: number; dim?: number; id: number; name: string; base_url: string; model: string; small_model: string; has_key: boolean; enabled: boolean; is_default: boolean };
type EngineForm = { threshold?: number; id?: number; name: string; base_url: string; model: string; small_model: string; api_key: string; enabled: boolean };
const EMPTY: EngineForm = { name: "", base_url: "", model: "", small_model: "", api_key: "", enabled: true };

function Engines({ kind, title, description }: { kind: "llm" | "embedding" | "decision"; title: string; description: string }) {
  const { t } = useTranslation();
  const emb = kind === "embedding"; const dec = kind === "decision"; const path = emb ? "embedding-engines" : dec ? "decision-engines" : "llm-engines";
  const qc = useQueryClient();
  const list = useQuery({ queryKey: [path], queryFn: () => get<Engine[]>(path) });
  const [form, setForm] = useState<EngineForm | null>(null);
  const [tests, setTests] = useState<Record<number, string>>({});
  const refresh = () => { qc.invalidateQueries({ queryKey: [path] }); qc.invalidateQueries({ queryKey: ["ai-status"] }); };
  const save = useMutation({ mutationFn: (f: EngineForm) => f.id ? send("PATCH", `${path}/${f.id}`, f) : send("POST", path, f), onSuccess: () => { setForm(null); refresh(); } });
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `${path}/${id}`), onSuccess: refresh });
  const [ask, setAsk] = useState<Engine | null>(null);
  const mk = useMutation({ mutationFn: (id: number) => send("POST", `${path}/${id}/default`), onSuccess: refresh });
  const [reindex, setReindex] = useState<Engine | null>(null);
  const def = (list.data ?? []).find((e) => e.is_default);
  const otherModel = (e: Engine) => emb && e.enabled && !e.is_default && (!def || def.model !== e.model || def.dim !== e.dim);
  const test = useMutation({ mutationFn: (id: number) => send<{ ok: boolean; ms: number; error?: string; reply?: string }>("POST", `${path}/${id}/test`),
    onSuccess: (r, id) => setTests((prev) => ({ ...prev, [id]: r.ok ? `OK · ${r.ms} ms · «${r.reply}»` : t("Error: {{error}}", { error: r.error }) })) });
  const [models, setModels] = useState<string[]>([]); const [mErr, setMErr] = useState("");
  const loadModels = useMutation({ mutationFn: (f: EngineForm) => send<{ models: string[]; error: string | null }>("POST", "llm-engines/models", { base_url: f.base_url, api_key: f.api_key || undefined, engine_id: f.id }),
    onSuccess: (r) => { setModels(r.models); setMErr(r.error ?? ""); } });
  const ev = useTableView(list.data ?? [], { name: { get: (e: Engine) => e.name }, url: { get: (e: Engine) => e.base_url }, model: { get: (e: Engine) => e.model },
    state: { get: (e: Engine) => (e.is_default ? t("por defecto") : !e.enabled ? "desactivado" : !e.has_key ? t("sin clave") : "activo"), exact: true } });
  const open = (f: EngineForm | null) => { setForm(f); setModels([]); setMErr(""); if (f?.id) loadModels.mutate(f); };
  const set = (k: keyof EngineForm, v: string | boolean) => setForm((f) => f && { ...f, [k]: v });
  return (
    <SettingsGroup title={title} description={description} action={<Btn kind="primary" onClick={() => open({ ...EMPTY })} icon="plus">{t("Añadir motor")}</Btn>}>
    <SettingsBody><Stack gap="xs">
      <AiStatus kind={kind} />
      {emb && <ReindexPanel onDone={refresh} />}
      <MutationError error={mk.error} />
      <ClearFilters active={ev.active} onClear={ev.clear} shown={ev.rows.length} total={ev.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead sort={ev.sortProps("name")} filter={ev.text("name")}>{t("Nombre")}</ColHead><ColHead filter={ev.text("url")}>{t("Endpoint")}</ColHead><ColHead sort={ev.sortProps("model")} filter={ev.text("model")}>{t("Modelo")}</ColHead><ColHead filter={ev.select("state")}>{t("Estado")}</ColHead><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>
          {ev.rows.map((e) => (
            <DataTable.Tr key={e.id}>
              <DataTable.Td>{e.name}</DataTable.Td><DataTable.Td><Text size="xs" className="ms-breakall">{e.base_url}</Text></DataTable.Td><DataTable.Td>{e.model}{emb && e.dim ? ` · ${e.dim}d` : ""}{dec && e.threshold ? t(" · umbral {{threshold}}", { threshold: e.threshold }) : ""}</DataTable.Td>
              <DataTable.Td><Group gap={4}>{e.is_default && <Pill size="sm" tone="success">{t("por defecto")}</Pill>}{!e.enabled && <Pill size="sm">{t("desactivado")}</Pill>}{!e.has_key && <Pill size="sm" tone="warn">{t("sin clave")}</Pill>}</Group>
                {tests[e.id] && <Text size="xs" className={tests[e.id].startsWith("OK") ? "ms-text-ok" : "ms-text-danger"}>{tests[e.id]}</Text>}</DataTable.Td>
              <DataTable.Td><Group gap={4} wrap="nowrap">
                <Btn size="row" loading={test.isPending && test.variables === e.id} onClick={() => test.mutate(e.id)} icon="test">{t("Probar")}</Btn>
                {!e.is_default && e.enabled && (!otherModel(e) || !def) && <Btn size="row" onClick={() => mk.mutate(e.id)}>{t("Por defecto")}</Btn>}
                {otherModel(e) && <Btn size="row" icon="refresh" onClick={() => setReindex(e)}>{t("Reindexar")}</Btn>}
                <Btn size="row" onClick={() => open({ ...e, api_key: "" })} icon="edit">{t("Editar")}</Btn>
                <Btn kind="danger" size="row" onClick={() => setAsk(e)} icon="trash">{t("Borrar")}</Btn></Group></DataTable.Td>
            </DataTable.Tr>))}
          {list.data?.length === 0 && <DataTable.Tr><DataTable.Td colSpan={5}><Text c="dimmed" size="sm">{dec ? t("Sin decisores: toda propuesta de un colaborador espera a un curador.") : emb ? t("Sin motores: se usan las variables MIMIRSYNTH_EMBEDDING_*. Añade el que ya usas (mismo modelo) para gestionarlo desde aquí.") : t("Sin motores. Mientras no haya ninguno se usan las variables MIMIRSYNTH_LLM_* si existen; si tampoco, la ingesta queda desactivada.")}</Text></DataTable.Td></DataTable.Tr>}
        </DataTable.Tbody>
      </DataTable>
      {emb && <StartReindex engine={reindex} onClose={() => setReindex(null)} />}
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title={t("Borrar motor")} action={t("Borrar motor")} subject={ask?.name}
        warning={t("Los brains que lo usen pasan al motor por defecto, o a las variables de entorno si no hay otro.")} onConfirm={() => del.mutateAsync(ask!.id)} />
      <Modal opened={!!form} onClose={() => setForm(null)} title={(form?.id ? t("Editar ") : t("Añadir ")) + (emb ? t("motor de embeddings") : dec ? "decisor" : "motor LLM")} centered>
        {form && <Stack gap="xs">
          <TextField label={t("Endpoint (base URL)")} placeholder={t("http://gateway:4000/v1")} value={form.base_url} onChange={(e) => set("base_url", e.currentTarget.value)} />
          <PasswordField label={t("Clave de API")} description={form.id ? t("Vacío = conservar la actual") : undefined} value={form.api_key} onChange={(e) => set("api_key", e.currentTarget.value)}
            onBlur={() => form.base_url && (form.api_key || form.id) && loadModels.mutate(form)} />
          <Group gap="xs"><Btn size="row" disabled={!form.base_url} loading={loadModels.isPending} onClick={() => loadModels.mutate(form)} icon="models">{t("Cargar modelos")}</Btn>
            <Text size="xs" c={mErr ? "orange" : "dimmed"}>{mErr || (models.length ? t("{{length}} modelos disponibles", { length: models.length }) : t("Rellena endpoint y clave para listar los modelos del proveedor"))}</Text></Group>
          <ComboField label={t("Modelo")} disabled={emb && !!form.id} data={models} limit={50} value={form.model} onChange={(v) => set("model", v)} placeholder={t("Elige uno o escribe el nombre")} />
          {!emb && !dec && <ComboField label={t("Modelo pequeño (opcional)")} description={t("Para tareas ligeras; por defecto el mismo modelo")} data={models} limit={50} value={form.small_model} onChange={(v) => set("small_model", v)} />}
          {dec && <NumberField label={t("Umbral de confianza")} description={t("Por debajo, la propuesta va a revisión humana")} min={0.5} max={0.99} step={0.05} decimalScale={2} value={form.threshold ?? 0.8} onChange={(v) => set("threshold", Number(v) as unknown as string)} />}
          <TextField label={t("Nombre")} value={form.name} onChange={(e) => set("name", e.currentTarget.value)} />
          <Toggle label={t("Activado")} checked={form.enabled} onChange={(e) => set("enabled", e.currentTarget.checked)} />
          <MutationError error={save.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setForm(null)}>{t("Cancelar")}</Btn>
            <Btn kind="primary" disabled={!form.name || !form.base_url || !form.model} loading={save.isPending} onClick={() => save.mutate(form)} icon="save">{t("Guardar")}</Btn></Group>
        </Stack>}
      </Modal>
    </Stack></SettingsBody>
    </SettingsGroup>
  );
}

type AiSt = { configured: boolean; source: string | null; name: string | null; healthy?: boolean; error?: string; model?: string; ms?: number };
function AiStatus({ kind }: { kind: "llm" | "embedding" | "decision" }) {
  const { t } = useTranslation();
  const st = useQuery({ queryKey: ["ai-status", "check"], queryFn: () => get<Record<string, AiSt>>("ai-status", { check: true }), refetchOnWindowFocus: false });
  const k = kind === "decision" ? "decider" : kind;
  const e = st.data?.[k];
  const env = e?.source === "env";
  const tone: Tone = !e ? "neutral" : !e.configured ? "neutral" : e.healthy === undefined ? (k === "embedding" ? "neutral" : "warn") : e.healthy ? "success" : "danger";
  const text = !e ? t("comprobando…") : !e.configured ? t("sin configurar") : e.healthy === undefined ? (env ? t("por variables de entorno") : t("configurado")) : `${e.healthy ? "OK" : t("caído")} · ${env ? t("variables de entorno") : e.name}`;
  const at = new Date(st.dataUpdatedAt).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  // El resultado se queda a la vista hasta la siguiente comprobación: un aviso efímero no da tiempo a leerlo (#78).
  const result = st.isFetching ? <Text size="xs" c="dimmed">{t("Comprobando la conexión con el proveedor…")}</Text>
    : e?.healthy !== undefined && <Text size="xs"><Text span className={e.healthy ? "ms-text-ok" : "ms-text-danger"}>{e.healthy ? t("Responde · {{model}} · {{ms}} ms", { model: e.model, ms: e.ms }) : t("Error con {{model}}: {{error}}", { model: e.model, error: e.error })}</Text>
      <Text span c="dimmed">{" · "}{t("comprobado a las {{at}}", { at })}</Text></Text>;
  const envHelp = k === "llm" ? t("Se usan las variables MIMIRSYNTH_LLM_* del .env (cambiarlas exige reiniciar la API). Si añades un motor aquí, tiene prioridad sobre ellas.")
    : t("Se usan las variables MIMIRSYNTH_EMBEDDING_* del .env (cambiarlas exige reiniciar la API). Si añades un motor aquí, tiene prioridad sobre ellas.");
  return (
    <Stack gap={4}>
      <Group gap="xs">
        <Pill tone={tone} size="md">{t("Estado")}: {text}</Pill>
        <Btn size="row" loading={st.isFetching} onClick={() => st.refetch()} icon="refresh">{t("Comprobar")}</Btn>
        {result}
      </Group>
      {env && <Text size="xs" c="dimmed">{envHelp}</Text>}
      <MutationError error={st.error} />
    </Stack>
  );
}

export default function Admin({ me, brain, setBrain }: { me: Me; brain: string; setBrain: (s: string) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
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
  const section = me.is_admin ? sectionParam : "brains";  // el resto de secciones son solo del administrador de la instancia
  const nav: ({ value: string; label: string } | { heading: string })[] = [
    { heading: t("Brain") }, { value: "brains", label: t("Acceso al brain") },
    ...(me.is_admin ? [
      { heading: t("Cuentas") }, { value: "users", label: t("Usuarios") }, { value: "security", label: t("Seguridad") }, { value: "identity", label: t("Identidad") }, { value: "mail", label: t("Correo (SMTP)") },
      { heading: t("Modelos de IA") }, { value: "llm", label: t("Modelo LLM") }, { value: "embedding", label: t("Embeddings") }, { value: "decision", label: t("Decisor") },
      { heading: t("Documentos") }, { value: "folders", label: t("Carpetas") }, { value: "docs", label: t("Límites") },
      { heading: t("Sistema") }, { value: "general", label: t("General") }, { value: "recall", label: t("Recuerdo (recall)") }, { value: "ingest", label: t("Ingesta y trabajos") }, { value: "notifications", label: t("Notificaciones") }, { value: "audit", label: t("Auditoría") },
    ] : []),
  ];
  const canAdmin = cur && ["admin", "owner"].includes(cur.role);
  return (
    <Page>
      <PageHeader title={t("Administración")} description={t("Acceso a cada brain y, para el administrador de la instancia, usuarios, seguridad, modelos de IA, documentos y el resto de ajustes.")} />
      {me.auth_mode === "off" && <Pill tone="warn" size="md">{t("Modo prototipo: sin autenticación (todos son administradores)")}</Pill>}
      <Modal opened={open} onClose={() => setOpen(false)} title={t("Crear brain")} centered>
        <Stack gap="xs">
          <TextField label={t("Slug")} description={t("Identificador permanente (minúsculas, números y guiones)")} placeholder={t("familia")} value={slug} onChange={(e) => setSlug(e.currentTarget.value)} />
          <TextField label={t("Nombre")} placeholder={t("Familia")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <TextArea label={t("Descripción")} description={t("De qué trata este brain. El decisor la usa para juzgar si una propuesta encaja en él.")} autosize minRows={2} value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
          <TextField label={t("Grafo existente (opcional)")} description={t("Vacío = grafo nuevo con el nombre del slug")} value={graph} onChange={(e) => setGraph(e.currentTarget.value)} />
          <MutationError error={create.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setOpen(false)}>{t("Cancelar")}</Btn><Btn kind="primary" disabled={!slug || !name} loading={create.isPending} onClick={() => create.mutate()} icon="plus">{t("Crear")}</Btn></Group>
        </Stack>
      </Modal>
      <Modal opened={editing} onClose={() => setEditing(false)} title={t("Editar brain")} centered>
        <Stack gap="xs">
          <TextField label={t("Nombre")} value={newName} onChange={(e) => setNewName(e.currentTarget.value)} data-autofocus />
          <TextArea label={t("Descripción")} description={t("De qué trata este brain. El decisor la usa para juzgar si una propuesta encaja en él.")} autosize minRows={2} value={newDesc} onChange={(e) => setNewDesc(e.currentTarget.value)} />
          <TextField label={t("Slug")} description={t("Va en las URLs de la API. Los tokens siguen funcionando; actualiza la URL de tus hooks y plugins.")} value={newSlug} onChange={(e) => setNewSlug(e.currentTarget.value)} />
          <TextField label={t("Grafo")} disabled={!me.is_admin} value={newGraph} onChange={(e) => setNewGraph(e.currentTarget.value)}
            description={me.is_admin ? t("Cambiarlo copia el grafo con el nuevo nombre, reescribe el group_id de cada nodo y arista, y verifica los conteos. El original se conserva.") : t("Solo el administrador de la instancia puede cambiar el grafo.")} />
          {newGraph !== cur?.graph_name && <Notice tone="warn">{t("Los agentes que escriban en Graphiti con group_id «")}{cur?.graph_name}{t("» seguirán escribiendo en el grafo antiguo; deberás repuntarlos a «")}{newGraph}».</Notice>}
          <MutationError error={rename.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setEditing(false)}>{t("Cancelar")}</Btn><Btn kind="primary" disabled={!newName.trim() || !newSlug || !newGraph} loading={rename.isPending} onClick={() => rename.mutate()} icon="save">{t("Guardar")}</Btn></Group>
        </Stack>
      </Modal>
      <Modal opened={!!done} onClose={() => setDone("")} title={t("Grafo migrado")} centered>
        <Stack><Text size="sm">{t("El brain usa ya el grafo nuevo. El grafo original «")}{done}{t("» se ha conservado como copia de seguridad; bórralo cuando hayas comprobado que todo está bien (y repuntado los agentes).")}</Text><Btn kind="primary" onClick={() => setDone("")}>{t("Entendido")}</Btn></Stack>
      </Modal>
      <ConfirmDialog opened={del} onClose={() => setDel(false)} title={t(t("Borrar brain"))} action={delGraph ? t("Borrar brain y grafo") : t("Borrar brain")} requireText={cur?.slug}
        warning={t("Vas a borrar «{{name}}». Se eliminan sus miembros, tokens de API, propuestas, ontología, correcciones de tipos y el índice de texto. No se puede deshacer.", { name: cur?.name })}
        onConfirm={() => remove.mutateAsync()}>
        <Check checked={delGraph} onChange={(e) => setDelGraph(e.currentTarget.checked)} label={t("Borrar también el grafo «{{graph_name}}» de FalkorDB (episodios, entidades y hechos)", { graph_name: cur?.graph_name })} description={t("Si no lo marcas, el grafo se conserva sin brain asociado y puede volver a asociarse creando un brain con ese grafo.")} />
      </ConfirmDialog>
      <FillArea>
        <SettingsLayout nav={<SubNav label={t("Secciones de administración")} value={section} onChange={setSection} items={nav} />}>
          {section === "brains" && <>
            <SettingsGroup title={t("Brain activo")} description={t("Cámbialo con el selector de la barra lateral.")}
              action={me.is_admin && <Btn kind="primary" icon="plus" onClick={() => setOpen(true)}>{t("Crear brain")}</Btn>}>
              <SettingsBody>
                {cur ? (
                  <Group justify="space-between" wrap="nowrap">
                    <Stack gap={2}>
                      <Group gap="xs"><Title order={3}>{cur.name}</Title><Pill size="xs">{t(ROLES.find((r) => r.value === cur.role)?.label ?? cur.role)}</Pill></Group>
                      <Text size="xs" c="dimmed" className="ms-data">{cur.slug} {t("· grafo")} {cur.graph_name}</Text>
                    </Stack>
                    <Group gap={6}>
                      {canAdmin && <Btn size="row" icon="edit" onClick={() => { setNewName(cur.name); setNewSlug(cur.slug); setNewGraph(cur.graph_name); setNewDesc(cur.description); rename.reset(); setEditing(true); }}>{t("Editar")}</Btn>}
                      {cur.role === "owner" && <Btn kind="danger" size="row" icon="trash" onClick={() => { setDelGraph(false); setDel(true); }}>{t("Borrar")}</Btn>}
                    </Group>
                  </Group>) : <EmptyState>{t("No hay ningún brain seleccionado.")}</EmptyState>}
              </SettingsBody>
            </SettingsGroup>
            {cur && <>
              <SettingsGroup title={t("Miembros")} description={t("Quién tiene acceso a este brain y con qué rol.")}><SettingsBody><Members brain={cur} /></SettingsBody></SettingsGroup>
              <SettingsGroup title={t("Federación")} description={t("Prestar la lectura de este brain a otros, o ver de quién recibe. Solo lectura y revocable.")}><SettingsBody><Federation brain={cur} canAdmin={!!canAdmin} /></SettingsBody></SettingsGroup>
              {canAdmin && <SettingsGroup title={t("Secretos")} description={t("Qué hacer cuando una propuesta o un documento lleva una contraseña, un token o una clave.")}><SettingsBody><Secrets brain={cur} /></SettingsBody></SettingsGroup>}
              {canAdmin && <SettingsGroup title={t("Exportar")} description={t("Una copia de este brain en un paquete, para guardarla aparte o llevarla a otra instancia.")}><SettingsBody><BrainExport brain={cur} /></SettingsBody></SettingsGroup>}
              <SettingsGroup title={t("Tokens de API")} description={t("Para plugins y MCP. Acotados a este brain; el rol de un token nunca supera el tuyo y no puede ser administrador.")}><SettingsBody><Tokens brain={cur} /></SettingsBody></SettingsGroup>
            </>}
            {me.is_admin && <SettingsGroup title={t("Importar un brain")} description={t("Un brain nuevo a partir de un paquete exportado.")}>
              <SettingsBody><BrainImport onOpen={(s) => { qc.invalidateQueries({ queryKey: ["brains"] }); setBrain(s); }} /></SettingsBody></SettingsGroup>}
          </>}
          {section === "users" && <SettingsGroup title={t("Usuarios")} description={t("Cuentas de la instancia: altas por invitación, roles, acceso a brains y estado.")}><SettingsBody><AdminUsers me={me.id} /></SettingsBody></SettingsGroup>}
          {section === "llm" && <Engines kind="llm" title={t("Modelo LLM")} description={t("Motores que extraen hechos al ingerir propuestas. Cualquier endpoint compatible con OpenAI; se usa el motor por defecto y las claves se guardan cifradas.")} />}
          {section === "embedding" && <Engines kind="embedding" title={t("Embeddings")} description={t("Motores de embeddings (recall, índice de texto e ingesta). Los vectores guardados dependen del modelo: para pasar a un motor con otro modelo usa «Reindexar», que los calcula todos en sombra antes de cambiar.")} />}
          {section === "decision" && <Engines kind="decision" title={t("Decisor")} description={t("Modelos de decisión cerrada para el triaje de propuestas y el corrector de tipos: solo aprueban lo factual con confianza suficiente; lo dudoso va a un curador.")} />}
          {section === "folders" && <SettingsGroup title={t("Carpetas")} description={t("Carpetas del servidor que los administradores de un brain pueden usar como fuente de documentos.")}><SettingsBody><AdminFolders /></SettingsBody></SettingsGroup>}
          {section === "audit" && <SettingsGroup title={t("Auditoría")} description={t("Registro de las acciones de administración y de acceso.")}><SettingsBody><AuditTable rows={audit.data ?? []} /></SettingsBody></SettingsGroup>}
          {section === "notifications" && <AdminNotifications />}
          {["general", "security", "mail", "identity", "docs", "recall", "ingest"].includes(section) && <AdminSettings group={section} />}
        </SettingsLayout>
      </FillArea>
    </Page>
  );
}
