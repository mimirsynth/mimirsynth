import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, Check, ClearFilters, ColHead, ComboField, CopyBtn, DataTable, Modal, Notice, NumberField, Panel, PasswordField, Pill, SelectField, Tabs, TextField, Toggle, useTableView, MutationError, ConfirmDialog, EmptyState, Page, PageHeader, FillArea, useTabParam, Tone, SettingsBody, SettingsGroup, SettingsLayout, SubNav } from "../ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Brain, fmt, get, Me, send } from "../api";
import AdminFolders from "./AdminFolders";
import AdminSettings from "./AdminSettings";
import AdminUsers from "./AdminUsers";
import TokensPanel from "./TokensPanel";

type AuditRow = { ts: string; action: string; detail: unknown };
const AUDIT_COLS = { ts: { get: (a: AuditRow) => a.ts }, action: { get: (a: AuditRow) => a.action, exact: true }, detail: { get: (a: AuditRow) => JSON.stringify(a.detail ?? "") } };
function AuditTable({ rows }: { rows: AuditRow[] }) {
  const v = useTableView(rows, AUDIT_COLS);
  return (
    <Stack gap="xs">
      {v.active && <Group><Btn size="row" onClick={v.clear}>Quitar todos los filtros ({v.rows.length} de {v.total})</Btn></Group>}
      <DataTable fz="xs">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("ts")}>Fecha</ColHead>
          <ColHead sort={v.sortProps("action")} filter={v.select("action")}>Acción</ColHead>
          <ColHead filter={v.text("detail", "Buscar en el detalle…")}>Detalle</ColHead>
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((a, i) => <DataTable.Tr key={i}><DataTable.Td>{fmt(a.ts)}</DataTable.Td><DataTable.Td>{a.action}</DataTable.Td><DataTable.Td>{JSON.stringify(a.detail)}</DataTable.Td></DataTable.Tr>)}</DataTable.Tbody>
      </DataTable>
    </Stack>
  );
}

const ROLES = [
  { value: "reader", label: "Lector" }, { value: "contributor", label: "Colaborador" }, { value: "curator", label: "Curador" },
  { value: "admin", label: "Administrador" }, { value: "owner", label: "Propietario" },
];
type Member = { user_id: number; email: string | null; name: string; role: string; implicit?: boolean };

function Members({ brain }: { brain: Brain }) {
  const qc = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["members", brain.slug], queryFn: () => get<Member[]>(`brains/${brain.slug}/members`), retry: false });
  const [email, setEmail] = useState(""); const [role, setRole] = useState("reader");
  const refresh = () => qc.invalidateQueries({ queryKey: ["members", brain.slug] });
  const add = useMutation({ mutationFn: (b: { email: string; role: string }) => send("PUT", `brains/${brain.slug}/members`, b), onSuccess: () => { setEmail(""); refresh(); } });
  const del = useMutation({ mutationFn: (id: number) => send("DELETE", `brains/${brain.slug}/members/${id}`), onSuccess: refresh });
  const [ask, setAsk] = useState<Member | null>(null);
  const mv = useTableView(data ?? [], { user: { get: (m: Member) => m.email ?? m.name }, role: { get: (m: Member) => (m.implicit ? "owner" : m.role), label: (r: string) => ROLES.find((x) => x.value === r)?.label ?? r, exact: true } });
  if (error) return <Text c="dimmed" size="sm">Solo los administradores del brain gestionan sus miembros.</Text>;
  return (
    <Stack gap="xs">
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title="Quitar miembro" action="Quitar miembro" subject={ask?.email ?? ask?.name}
        warning="Pierde el acceso a este brain. Sus tokens de API siguen existiendo hasta que se revoquen." onConfirm={() => del.mutateAsync(ask!.user_id)} />
      <ClearFilters active={mv.active} onClear={mv.clear} shown={mv.rows.length} total={mv.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead sort={mv.sortProps("user")} filter={mv.text("user")}>Usuario</ColHead><ColHead sort={mv.sortProps("role")} filter={mv.select("role")}>Rol</ColHead><DataTable.Th /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{mv.rows.map((m) => (
          <DataTable.Tr key={m.user_id}>
            <DataTable.Td>{m.email ?? m.name}</DataTable.Td>
            <DataTable.Td>{m.implicit
              ? <Group gap={6}><Pill>Propietario</Pill><Text size="xs" c="dimmed">administrador de la instancia</Text></Group>
              : <SelectField size="xs" w={150} data={ROLES} value={m.role} allowDeselect={false} onChange={(v) => v && m.email && add.mutate({ email: m.email, role: v })} />}</DataTable.Td>
            <DataTable.Td>{!m.implicit && <Btn kind="danger" size="row" onClick={() => setAsk(m)} icon="trash">Quitar</Btn>}</DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
      <Group align="flex-end" gap="xs">
        <TextField size="xs" label="Añadir por email" placeholder="persona@dominio.com" value={email} onChange={(e) => setEmail(e.currentTarget.value)} w={260} />
        <SelectField size="xs" label="Rol" data={ROLES} value={role} onChange={(v) => setRole(v ?? "reader")} allowDeselect={false} w={150} />
        <Btn kind="primary" disabled={!email} onClick={() => add.mutate({ email, role })} icon="plus">Añadir</Btn>
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

function Engines({ kind }: { kind: "llm" | "embedding" | "decision" }) {
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
  const test = useMutation({ mutationFn: (id: number) => send<{ ok: boolean; ms: number; error?: string; reply?: string }>("POST", `${path}/${id}/test`),
    onSuccess: (r, id) => setTests((t) => ({ ...t, [id]: r.ok ? `OK · ${r.ms} ms · «${r.reply}»` : `Error: ${r.error}` })) });
  const [models, setModels] = useState<string[]>([]); const [mErr, setMErr] = useState("");
  const loadModels = useMutation({ mutationFn: (f: EngineForm) => send<{ models: string[]; error: string | null }>("POST", "llm-engines/models", { base_url: f.base_url, api_key: f.api_key || undefined, engine_id: f.id }),
    onSuccess: (r) => { setModels(r.models); setMErr(r.error ?? ""); } });
  const ev = useTableView(list.data ?? [], { name: { get: (e: Engine) => e.name }, url: { get: (e: Engine) => e.base_url }, model: { get: (e: Engine) => e.model },
    state: { get: (e: Engine) => (e.is_default ? "por defecto" : !e.enabled ? "desactivado" : !e.has_key ? "sin clave" : "activo"), exact: true } });
  const open = (f: EngineForm | null) => { setForm(f); setModels([]); setMErr(""); if (f?.id) loadModels.mutate(f); };
  const set = (k: keyof EngineForm, v: string | boolean) => setForm((f) => f && { ...f, [k]: v });
  return (
    <Stack gap="xs">
      <Group justify="flex-end">
        <Btn kind="primary" onClick={() => open({ ...EMPTY })} icon="plus">Añadir motor</Btn></Group>
      <ClearFilters active={ev.active} onClear={ev.clear} shown={ev.rows.length} total={ev.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead sort={ev.sortProps("name")} filter={ev.text("name")}>Nombre</ColHead><ColHead filter={ev.text("url")}>Endpoint</ColHead><ColHead sort={ev.sortProps("model")} filter={ev.text("model")}>Modelo</ColHead><ColHead filter={ev.select("state")}>Estado</ColHead><DataTable.Th /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>
          {ev.rows.map((e) => (
            <DataTable.Tr key={e.id}>
              <DataTable.Td>{e.name}</DataTable.Td><DataTable.Td><Text size="xs" className="ms-breakall">{e.base_url}</Text></DataTable.Td><DataTable.Td>{e.model}{emb && e.dim ? ` · ${e.dim}d` : ""}{dec && e.threshold ? ` · umbral ${e.threshold}` : ""}</DataTable.Td>
              <DataTable.Td><Group gap={4}>{e.is_default && <Pill size="sm" tone="success">por defecto</Pill>}{!e.enabled && <Pill size="sm">desactivado</Pill>}{!e.has_key && <Pill size="sm" tone="warn">sin clave</Pill>}</Group>
                {tests[e.id] && <Text size="xs" className={tests[e.id].startsWith("OK") ? "ms-text-ok" : "ms-text-danger"}>{tests[e.id]}</Text>}</DataTable.Td>
              <DataTable.Td><Group gap={4} wrap="nowrap">
                <Btn size="row" loading={test.isPending && test.variables === e.id} onClick={() => test.mutate(e.id)} icon="test">Probar</Btn>
                {!e.is_default && e.enabled && <Btn size="row" onClick={() => mk.mutate(e.id)}>Por defecto</Btn>}
                <Btn size="row" onClick={() => open({ ...e, api_key: "" })} icon="edit">Editar</Btn>
                <Btn kind="danger" size="row" onClick={() => setAsk(e)} icon="trash">Borrar</Btn></Group></DataTable.Td>
            </DataTable.Tr>))}
          {list.data?.length === 0 && <DataTable.Tr><DataTable.Td colSpan={5}><Text c="dimmed" size="sm">{dec ? "Sin decisores: toda propuesta de un colaborador espera a un curador." : emb ? "Sin motores: se usan las variables MIMIRSYNTH_EMBEDDING_*. Añade el que ya usas (mismo modelo) para gestionarlo desde aquí." : "Sin motores. Mientras no haya ninguno se usan las variables MIMIRSYNTH_LLM_* si existen; si tampoco, la ingesta queda desactivada."}</Text></DataTable.Td></DataTable.Tr>}
        </DataTable.Tbody>
      </DataTable>
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title="Borrar motor" action="Borrar motor" subject={ask?.name}
        warning="Los brains que lo usen pasan al motor por defecto, o a las variables de entorno si no hay otro." onConfirm={() => del.mutateAsync(ask!.id)} />
      <Modal opened={!!form} onClose={() => setForm(null)} title={(form?.id ? "Editar " : "Añadir ") + (emb ? "motor de embeddings" : dec ? "decisor" : "motor LLM")} centered>
        {form && <Stack gap="xs">
          <TextField label="Endpoint (base URL)" placeholder="http://gateway:4000/v1" value={form.base_url} onChange={(e) => set("base_url", e.currentTarget.value)} />
          <PasswordField label="Clave de API" description={form.id ? "Vacío = conservar la actual" : undefined} value={form.api_key} onChange={(e) => set("api_key", e.currentTarget.value)}
            onBlur={() => form.base_url && (form.api_key || form.id) && loadModels.mutate(form)} />
          <Group gap="xs"><Btn size="row" disabled={!form.base_url} loading={loadModels.isPending} onClick={() => loadModels.mutate(form)} icon="models">Cargar modelos</Btn>
            <Text size="xs" c={mErr ? "orange" : "dimmed"}>{mErr || (models.length ? `${models.length} modelos disponibles` : "Rellena endpoint y clave para listar los modelos del proveedor")}</Text></Group>
          <ComboField label="Modelo" disabled={emb && !!form.id} data={models} limit={50} value={form.model} onChange={(v) => set("model", v)} placeholder="Elige uno o escribe el nombre" />
          {!emb && !dec && <ComboField label="Modelo pequeño (opcional)" description="Para tareas ligeras; por defecto el mismo modelo" data={models} limit={50} value={form.small_model} onChange={(v) => set("small_model", v)} />}
          {dec && <NumberField label="Umbral de confianza" description="Por debajo, la propuesta va a revisión humana" min={0.5} max={0.99} step={0.05} decimalScale={2} value={form.threshold ?? 0.8} onChange={(v) => set("threshold", Number(v) as unknown as string)} />}
          <TextField label="Nombre" value={form.name} onChange={(e) => set("name", e.currentTarget.value)} />
          <Toggle label="Activado" checked={form.enabled} onChange={(e) => set("enabled", e.currentTarget.checked)} />
          <MutationError error={save.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setForm(null)}>Cancelar</Btn>
            <Btn kind="primary" disabled={!form.name || !form.base_url || !form.model} loading={save.isPending} onClick={() => save.mutate(form)} icon="save">Guardar</Btn></Group>
        </Stack>}
      </Modal>
    </Stack>
  );
}

type AiSt = { configured: boolean; source: string | null; name: string | null; healthy?: boolean; error?: string };
function AiStatus() {
  const st = useQuery({ queryKey: ["ai-status", "check"], queryFn: () => get<Record<string, AiSt>>("ai-status", { check: true }), refetchOnWindowFocus: false });
  const items: [string, string][] = [["llm", "LLM"], ["embedding", "Embeddings"], ["decider", "Decisor"]];
  return (
    <Group gap="xs" mb="sm">
      {items.map(([k, label]) => {
        const e = st.data?.[k];
        const tone: Tone = !e ? "neutral" : !e.configured ? "neutral" : e.healthy === undefined ? (k === "embedding" ? "neutral" : "warn") : e.healthy ? "success" : "danger";
        const text = !e ? "comprobando…" : !e.configured ? "sin configurar" : e.healthy === undefined ? (e.source === "env" ? "por variables de entorno" : "configurado") : e.healthy ? `OK · ${e.name ?? e.source}` : `caído · ${e.error ?? ""}`;
        return <Pill key={k} tone={tone} size="md">{label}: {text}</Pill>;
      })}
      <Btn size="row" loading={st.isFetching} onClick={() => st.refetch()} icon="refresh">Comprobar</Btn>
    </Group>
  );
}

export default function Admin({ me, brain, setBrain }: { me: Me; brain: string; setBrain: (s: string) => void }) {
  const qc = useQueryClient();
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const [open, setOpen] = useState(false); const [editing, setEditing] = useState(false);
  const [slug, setSlug] = useState(""); const [name, setName] = useState(""); const [graph, setGraph] = useState("");
  const [del, setDel] = useState(false); const [delGraph, setDelGraph] = useState(false);
  const remove = useMutation({ mutationFn: () => send<{ deleted: string; graph: string; graph_deleted: boolean }>("POST", `brains/${brain}/delete`, { confirm: cur?.slug, delete_graph: delGraph }),
    onSuccess: async (r) => { setDel(false); setDelGraph(false); const left = (await qc.fetchQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains"), staleTime: 0 })).filter((b) => b.slug !== r.deleted); qc.setQueryData(["brains"], left); setBrain(left[0]?.slug ?? ""); } });
  const [newName, setNewName] = useState(""); const [newSlug, setNewSlug] = useState(""); const [newGraph, setNewGraph] = useState("");
  const create = useMutation({ mutationFn: () => send<Brain>("POST", "brains", { slug, name, graph_name: graph || undefined }),
    onSuccess: (b) => { setSlug(""); setName(""); setGraph(""); setOpen(false); qc.invalidateQueries({ queryKey: ["brains"] }); setBrain(b.slug); } });
  const rename = useMutation({
    mutationFn: () => send<Brain & { old_graph_kept?: string }>("PATCH", `brains/${brain}`, { name: newName, slug: newSlug, graph_name: newGraph }),
    onSuccess: (r) => { setEditing(false); setDone(r.old_graph_kept ?? ""); if (r.slug !== brain) setBrain(r.slug); qc.invalidateQueries(); } });
  const [done, setDone] = useState("");
  const users = useQuery({ queryKey: ["users"], enabled: me.is_admin, queryFn: () => get<any[]>("users") });
  const audit = useQuery({ queryKey: ["audit"], enabled: me.is_admin, queryFn: () => get<any[]>("audit") });
  const cur = (brains.data ?? []).find((b) => b.slug === brain);
  const [sectionParam, setSection] = useTabParam("brains", "seccion");
  const section = me.is_admin ? sectionParam : "brains";  // el resto de secciones son solo del administrador de la instancia
  const nav: ({ value: string; label: string } | { heading: string })[] = [
    { heading: "Brain" }, { value: "brains", label: "Acceso al brain" },
    ...(me.is_admin ? [
      { heading: "Cuentas" }, { value: "users", label: "Usuarios" }, { value: "security", label: "Seguridad" }, { value: "identity", label: "Identidad (OIDC)" }, { value: "mail", label: "Correo (SMTP)" },
      { heading: "Modelos de IA" }, { value: "llm", label: "Modelo LLM" }, { value: "embedding", label: "Embeddings" }, { value: "decision", label: "Decisor" },
      { heading: "Documentos" }, { value: "folders", label: "Carpetas" }, { value: "docs", label: "Límites" },
      { heading: "Sistema" }, { value: "recall", label: "Recuerdo (recall)" }, { value: "ingest", label: "Ingesta y trabajos" }, { value: "audit", label: "Auditoría" },
    ] : []),
  ];
  const canAdmin = cur && ["admin", "owner"].includes(cur.role);
  return (
    <Page>
      <PageHeader title="Administración" description="Acceso a cada brain y, para el administrador de la instancia, usuarios, seguridad, modelos de IA, documentos y el resto de ajustes." />
      {me.auth_mode === "off" && <Pill tone="warn" size="md">Modo prototipo: sin autenticación (todos son administradores)</Pill>}
      <Modal opened={open} onClose={() => setOpen(false)} title="Crear brain" centered>
        <Stack gap="xs">
          <TextField label="Slug" description="Identificador permanente (minúsculas, números y guiones)" placeholder="familia" value={slug} onChange={(e) => setSlug(e.currentTarget.value)} />
          <TextField label="Nombre" placeholder="Familia" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <TextField label="Grafo existente (opcional)" description="Vacío = grafo nuevo con el nombre del slug" value={graph} onChange={(e) => setGraph(e.currentTarget.value)} />
          <MutationError error={create.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setOpen(false)}>Cancelar</Btn><Btn kind="primary" disabled={!slug || !name} loading={create.isPending} onClick={() => create.mutate()} icon="plus">Crear</Btn></Group>
        </Stack>
      </Modal>
      <Modal opened={editing} onClose={() => setEditing(false)} title="Editar brain" centered>
        <Stack gap="xs">
          <TextField label="Nombre" value={newName} onChange={(e) => setNewName(e.currentTarget.value)} data-autofocus />
          <TextField label="Slug" description="Va en las URLs de la API. Los tokens siguen funcionando; actualiza la URL de tus hooks y plugins." value={newSlug} onChange={(e) => setNewSlug(e.currentTarget.value)} />
          <TextField label="Grafo" disabled={!me.is_admin} value={newGraph} onChange={(e) => setNewGraph(e.currentTarget.value)}
            description={me.is_admin ? "Cambiarlo copia el grafo con el nuevo nombre, reescribe el group_id de cada nodo y arista, y verifica los conteos. El original se conserva." : "Solo el administrador de la instancia puede cambiar el grafo."} />
          {newGraph !== cur?.graph_name && <Notice tone="warn">Los agentes que escriban en Graphiti con group_id «{cur?.graph_name}» seguirán escribiendo en el grafo antiguo; deberás repuntarlos a «{newGraph}».</Notice>}
          <MutationError error={rename.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setEditing(false)}>Cancelar</Btn><Btn kind="primary" disabled={!newName.trim() || !newSlug || !newGraph} loading={rename.isPending} onClick={() => rename.mutate()} icon="save">Guardar</Btn></Group>
        </Stack>
      </Modal>
      <Modal opened={!!done} onClose={() => setDone("")} title="Grafo migrado" centered>
        <Stack><Text size="sm">El brain usa ya el grafo nuevo. El grafo original «{done}» se ha conservado como copia de seguridad; bórralo cuando hayas comprobado que todo está bien (y repuntado los agentes).</Text><Btn kind="primary" onClick={() => setDone("")}>Entendido</Btn></Stack>
      </Modal>
      <ConfirmDialog opened={del} onClose={() => setDel(false)} title="Borrar brain" action={delGraph ? "Borrar brain y grafo" : "Borrar brain"} requireText={cur?.slug}
        warning={`Vas a borrar «${cur?.name}». Se eliminan sus miembros, tokens de API, propuestas, ontología, correcciones de tipos y el índice de texto. No se puede deshacer.`}
        onConfirm={() => remove.mutateAsync()}>
        <Check checked={delGraph} onChange={(e) => setDelGraph(e.currentTarget.checked)} label={`Borrar también el grafo «${cur?.graph_name}» de FalkorDB (episodios, entidades y hechos)`} description="Si no lo marcas, el grafo se conserva sin brain asociado y puede volver a asociarse creando un brain con ese grafo." />
      </ConfirmDialog>
      <FillArea>
        <SettingsLayout nav={<SubNav label="Secciones de administración" value={section} onChange={setSection} items={nav} />}>
          {section === "brains" && <>
            <SettingsGroup title="Brain activo" description="Cámbialo con el selector de la barra lateral."
              action={me.is_admin && <Btn kind="primary" icon="plus" onClick={() => setOpen(true)}>Crear brain</Btn>}>
              <SettingsBody>
                {cur ? (
                  <Group justify="space-between" wrap="nowrap">
                    <Stack gap={2}>
                      <Group gap="xs"><Title order={4}>{cur.name}</Title><Pill size="xs">{ROLES.find((r) => r.value === cur.role)?.label ?? cur.role}</Pill></Group>
                      <Text size="xs" c="dimmed" className="ms-data">{cur.slug} · grafo {cur.graph_name}</Text>
                    </Stack>
                    <Group gap={6}>
                      {canAdmin && <Btn size="row" icon="edit" onClick={() => { setNewName(cur.name); setNewSlug(cur.slug); setNewGraph(cur.graph_name); rename.reset(); setEditing(true); }}>Editar</Btn>}
                      {cur.role === "owner" && <Btn kind="danger" size="row" icon="trash" onClick={() => { setDelGraph(false); setDel(true); }}>Borrar</Btn>}
                    </Group>
                  </Group>) : <EmptyState>No hay ningún brain seleccionado.</EmptyState>}
              </SettingsBody>
            </SettingsGroup>
            {cur && <>
              <SettingsGroup title="Miembros" description="Quién tiene acceso a este brain y con qué rol."><SettingsBody><Members brain={cur} /></SettingsBody></SettingsGroup>
              <SettingsGroup title="Tokens de API" description="Para plugins y MCP. Acotados a este brain; el rol de un token nunca supera el tuyo y no puede ser administrador."><SettingsBody><Tokens brain={cur} /></SettingsBody></SettingsGroup>
            </>}
          </>}
          {section === "users" && <SettingsGroup title="Usuarios" description="Cuentas de la instancia: altas por invitación, roles, acceso a brains y estado."><SettingsBody><AdminUsers me={me.id} /></SettingsBody></SettingsGroup>}
          {section === "llm" && <SettingsGroup title="Modelo LLM" description="Motores que extraen hechos al ingerir propuestas. Cualquier endpoint compatible con OpenAI; se usa el motor por defecto y las claves se guardan cifradas."><SettingsBody><AiStatus /><Engines kind="llm" /></SettingsBody></SettingsGroup>}
          {section === "embedding" && <SettingsGroup title="Embeddings" description="Motores de embeddings (recall, índice de texto e ingesta). Modelo y dimensión no se pueden cambiar una vez creado: los vectores guardados dependen de él."><SettingsBody><AiStatus /><Engines kind="embedding" /></SettingsBody></SettingsGroup>}
          {section === "decision" && <SettingsGroup title="Decisor" description="Modelos de decisión cerrada para el triaje de propuestas y el corrector de tipos: solo aprueban lo factual con confianza suficiente; lo dudoso va a un curador."><SettingsBody><AiStatus /><Engines kind="decision" /></SettingsBody></SettingsGroup>}
          {section === "folders" && <SettingsGroup title="Carpetas" description="Carpetas del servidor que los administradores de un brain pueden usar como fuente de documentos."><SettingsBody><AdminFolders /></SettingsBody></SettingsGroup>}
          {section === "audit" && <SettingsGroup title="Auditoría" description="Registro de las acciones de administración y de acceso."><SettingsBody><AuditTable rows={audit.data ?? []} /></SettingsBody></SettingsGroup>}
          {["security", "mail", "identity", "docs", "recall", "ingest"].includes(section) && <AdminSettings group={section} />}
        </SettingsLayout>
      </FillArea>
    </Page>
  );
}
