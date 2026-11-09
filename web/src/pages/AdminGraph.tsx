import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, fmtNum, get, send } from "../api";
import ExistingGraphs from "./AdminGraphAdopt";
import { Btn, DataState, DataTable, Modal, MutationError, Notice, NumberField, PasswordField, Pill, Radio, RadioGroup, SettingsBody, SettingsGroup, Sheet, SheetRow, Step, Steps, TextField, Toggle, type Tone } from "../ui";

type Backend = "falkordb" | "neo4j";
type Conn = {
  source: "env" | "db" | "default"; editable: boolean; backend: Backend; label: string; host: string; port: number; user: string; tls: boolean;
  database: string; address: string; has_password: boolean; bundled_host: string; updated_at: string | null;
};
type TestResult = {
  ok: boolean; label: string; address: string; steps: { step: string; ok: boolean; ms: number }[];
  server: { server: string; version: string | null; edition?: string; database?: string; home?: boolean } | null;
  graphs: { name: string; nodes: number; brain: string | null }[]; truncated: boolean; error: { step: string; code: string; message: string } | null;
};
type Saved = Conn & { changed: boolean; test: TestResult };
type Kind = "bundled" | Backend;
type Form = { kind: Kind; host: string; port: number | ""; user: string; password: string; tls: boolean; database: string };

const PORT: Record<Backend, number> = { falkordb: 6379, neo4j: 7687 };
const STEP: Record<string, string> = {
  reach: T("Dirección"), auth: T("Credenciales"), version: T("Versión"), write: T("Permiso de escritura"), list: T("Contenido"),
};
const SOURCE: Record<Conn["source"], string> = { env: T("variables de entorno"), db: T("guardada aquí"), default: T("FalkorDB incluido") };

/** The request body for a form: the bundled FalkorDB is FalkorDB at its own host. An empty password means «the saved one» (the server
 *  only reuses it for the same server). */
function body(f: Form, bundledHost: string) {
  if (f.kind === "bundled") return { backend: "falkordb", host: bundledHost, port: PORT.falkordb, user: "", password: "", tls: false, database: "" };
  return { backend: f.kind, host: f.host.trim(), port: f.port || PORT[f.kind], user: f.user.trim(), password: f.password || null, tls: f.tls,
    database: f.kind === "neo4j" ? f.database.trim() : "" };
}

function formOf(c: Conn): Form {
  const bundled = c.backend === "falkordb" && c.host === c.bundled_host && c.port === PORT.falkordb && !c.user && !c.tls;
  return { kind: bundled ? "bundled" : c.backend, host: bundled ? "" : c.host, port: bundled ? "" : c.port, user: c.user, password: "", tls: c.tls, database: c.database };
}

/** What a test found, step by step, then what the database holds. */
export function GraphTestResult({ r }: { r: TestResult }) {
  const { t } = useTranslation();
  const tone = (ok: boolean): Tone => (ok ? "success" : "danger");
  const v = r.server;
  return (
    <Stack gap="xs" aria-live="polite">
      <Notice tone={r.ok ? "success" : "danger"} title={r.ok ? t("La conexión funciona") : t("La conexión falla")}>
        {r.ok ? t("{{label}} en {{address}} responde, acepta las credenciales y deja escribir.", { label: r.label, address: r.address }) : r.error?.message}
      </Notice>
      <Steps label={t("Prueba de la conexión")}>
        {r.steps.map((s) => (
          <Step key={s.step} title={`${t(STEP[s.step] ?? s.step)} · ${s.ok ? t("pasa") : t("falla")}`} tone={tone(s.ok)}>
            <Text size="xs" c="dimmed">{s.step === "version" && s.ok && v ? `${v.server} ${v.version ?? t("(versión no disponible)")}${v.edition ? ` · ${v.edition}` : ""}${v.database ? ` · ${v.home ? t("base de datos «{{database}}», la predeterminada del usuario", { database: v.database }) : t("base de datos «{{database}}»", { database: v.database })}` : ""} · ` : ""}{t("{{ms}} ms", { ms: s.ms })}</Text>
          </Step>))}
      </Steps>
      {r.ok && (r.graphs.length === 0
        ? <Text size="sm" c="dimmed" className="ms-measure">{t("La base de datos no tiene grafos todavía: cada brain nuevo creará el suyo.")}</Text>
        : <Stack gap={4}>
            <Text size="sm" className="ms-measure">{t("Lo que ya hay en la base de datos. MimirSynth no toca lo que no sea de un brain.")}</Text>
            <DataTable fz="sm">
              <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Grafo")}</DataTable.Th><DataTable.Th>{t("Nodos")}</DataTable.Th><DataTable.Th>{t("Brain")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
              <DataTable.Tbody>{r.graphs.map((g) => (
                <DataTable.Tr key={g.name}><DataTable.Td><Text size="sm" className="ms-data">{g.name}</Text></DataTable.Td><DataTable.Td>{fmtNum(g.nodes)}</DataTable.Td>
                  <DataTable.Td>{g.brain ? <Pill size="sm" tone="success">{g.brain}</Pill> : <Text size="xs" c="dimmed">{t("ninguno")}</Text>}</DataTable.Td></DataTable.Tr>))}
              </DataTable.Tbody>
            </DataTable>
            {r.truncated && <Text size="xs" c="dimmed">{t("Hay más grafos de los que se listan aquí.")}</Text>}
          </Stack>)}
    </Stack>
  );
}

function EditConnection({ cur, onClose, onSaved }: { cur: Conn; onClose: () => void; onSaved: (s: Saved) => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState<Form>(() => formOf(cur));
  const [tested, setTested] = useState<{ key: string; r: TestResult } | null>(null);
  const b = body(f, cur.bundled_host);
  const key = JSON.stringify(b);
  const test = useMutation({ mutationFn: () => send<TestResult>("POST", "admin/graph/test", b), onSuccess: (r) => setTested({ key, r }) });
  const save = useMutation({ mutationFn: () => send<Saved>("PUT", "admin/graph", b), onSuccess: onSaved });
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((p) => ({ ...p, [k]: v }));
  const current = tested?.key === key ? tested.r : null; // a result for other values than the ones in the form is not shown as theirs
  const address = f.kind === "bundled" ? `${cur.bundled_host}:${PORT.falkordb}` : `${f.host.trim()}:${f.port || PORT[f.kind]}`;
  const moves = (f.kind === "bundled" ? "falkordb" : f.kind) !== cur.backend || address !== `${cur.host}:${cur.port}` || (f.kind === "neo4j" && f.database.trim() !== cur.database);
  const sameServer = f.kind !== "bundled" && f.kind === cur.backend && f.host.trim() === cur.host && (f.port || PORT[f.kind]) === cur.port;
  return (
    <Modal opened onClose={onClose} title={t("Cambiar la base de datos del grafo")} centered>
      <Stack gap="sm">
        <RadioGroup label={t("Base de datos")} value={f.kind} onChange={(v) => { set("kind", v as Kind); if (v !== "bundled" && !f.port) set("port", PORT[v as Backend]); if (v === "neo4j" && !f.user) set("user", "neo4j"); }}>
          <Stack gap="xs" mt={4}>
            <Radio value="bundled" label={t("FalkorDB incluido")} description={t("El FalkorDB que se instala junto a MimirSynth, en {{address}}. Necesita el perfil «bundled» de Docker Compose, que el instalador activa cuando eliges una base de datos local.", { address: `${cur.bundled_host}:${PORT.falkordb}` })} />
            <Radio value="falkordb" label={t("FalkorDB existente")} />
            <Radio value="neo4j" label={t("Neo4j existente")} description={t("5.26 o posterior, Community o Enterprise.")} />
          </Stack>
        </RadioGroup>
        {f.kind !== "bundled" && <>
              <TextField label={t("Servidor")} description={t("Nombre o IP, sin protocolo. Desde el contenedor: host.docker.internal es tu equipo.")} placeholder={f.kind === "neo4j" ? t("neo4j.example.com") : t("falkordb.example.com")}
                value={f.host} onChange={(e) => set("host", e.currentTarget.value)} data-autofocus />
              <NumberField label={t("Puerto")} min={1} max={65535} allowDecimal={false} value={f.port} onChange={(v) => set("port", typeof v === "number" ? v : "")} placeholder={String(PORT[f.kind])} />
              <TextField label={f.kind === "neo4j" ? t("Usuario") : t("Usuario (opcional)")} description={f.kind === "falkordb" ? t("Solo si el servidor tiene usuarios (ACL).") : undefined}
                value={f.user} onChange={(e) => set("user", e.currentTarget.value)} autoComplete="off" />
              <PasswordField label={t("Contraseña")} description={sameServer && cur.has_password ? t("Vacío = conservar la guardada") : undefined}
                value={f.password} onChange={(e) => set("password", e.currentTarget.value)} autoComplete="new-password" />
              {f.kind === "neo4j" && <TextField label={t("Base de datos (opcional)")} description={t("Vacío = la base de datos predeterminada del usuario (en Neo4j Aura, la de la instancia); la prueba dice cuál es. Todos los brains viven en ella, cada uno con su group_id.")}
                value={f.database} onChange={(e) => set("database", e.currentTarget.value)} />}
              <Toggle label={t("Conexión cifrada (TLS)")} description={f.kind === "neo4j" ? t("Usa neo4j+s://, con el certificado comprobado, como pide Neo4j Aura.") : t("Con el certificado comprobado.")}
                checked={f.tls} onChange={(e) => set("tls", e.currentTarget.checked)} />
            </>}
        {moves && <Notice tone="warn" title={t("Los datos no se mueven")}>{t("La instancia pasará a usar esta base de datos, pero lo que hay en la actual se queda allí. Un brain cuyo grafo no esté en la nueva se verá vacío hasta que vuelvas a la anterior.")}</Notice>}
        {current && <GraphTestResult r={current} />}
        <MutationError error={test.error ?? save.error} />
        <Text size="xs" c="dimmed" className="ms-measure">{current?.ok ? t("La prueba ha pasado: ya se puede guardar.") : t("Para guardar, la prueba tiene que pasar con estos datos.")}</Text>
        <Group justify="flex-end" gap="xs">
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn icon="test" loading={test.isPending} disabled={f.kind !== "bundled" && !f.host.trim()} onClick={() => test.mutate()}>{t("Probar")}</Btn>
          <Btn kind="primary" icon="save" loading={save.isPending} disabled={!current?.ok} onClick={() => save.mutate()}>{t("Guardar")}</Btn>
        </Group>
      </Stack>
    </Modal>
  );
}

/** Administration → Graph database (issue 358): the connection in force, where it comes from, a test of it and, when it does not come from
 *  the environment, changing it. Saving needs a test that passes, and the instance switches without a restart. */
export default function AdminGraph() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-graph"], queryFn: () => get<Conn>("admin/graph") });
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState<Saved | null>(null);
  const check = useMutation({ mutationFn: () => send<TestResult>("POST", "admin/graph/test") });
  const c = q.data;
  const sourceTone: Tone = c?.source === "env" ? "neutral" : c?.source === "db" ? "success" : "alt";
  return (<>
    <SettingsGroup title={t("Base de datos del grafo")}
      description={t("Dónde guardan los brains sus entidades, hechos y episodios: el FalkorDB incluido, o un FalkorDB o Neo4j que ya tengas.")}
      action={c?.editable && <Btn kind="primary" icon="edit" onClick={() => { setSaved(null); setEditing(true); }}>{t("Cambiar")}</Btn>}>
      <SettingsBody>
        {!c ? <DataState query={q} /> : <Stack gap="sm">
          <Sheet label={t("Conexión en uso")}>
            <SheetRow term={t("Base de datos")}><Group gap={6}><Text size="sm">{c.label}</Text><Pill size="sm" tone={sourceTone}>{t(SOURCE[c.source])}</Pill></Group></SheetRow>
            <SheetRow term={t("Dirección")}><Text size="sm" className="ms-data ms-breakall">{c.address}</Text></SheetRow>
            {c.user && <SheetRow term={t("Usuario")}><Text size="sm" className="ms-data">{c.user}</Text></SheetRow>}
            <SheetRow term={t("Contraseña")}><Text size="sm">{c.has_password ? t("guardada") : t("sin contraseña")}</Text></SheetRow>
            <SheetRow term={t("TLS")}><Text size="sm">{c.tls ? t("sí") : t("no")}</Text></SheetRow>
            {c.backend === "neo4j" && <SheetRow term={t("Base de datos de Neo4j")}>{c.database ? <Text size="sm" className="ms-data">{c.database}</Text> : <Text size="sm">{t("la predeterminada del usuario")}</Text>}</SheetRow>}
            {c.updated_at && <SheetRow term={t("Guardada")}>{fmt(c.updated_at)}</SheetRow>}
          </Sheet>
          {c.source === "env" && <Notice tone="info" title={t("Viene de las variables de entorno")}>
            {t("La eligen MIMIRSYNTH_GRAPH_BACKEND, MIMIRSYNTH_FALKOR_HOST o MIMIRSYNTH_NEO4J_URI en el .env, y mandan sobre lo que se guarde aquí: se cambia editando el .env y reiniciando. Para gestionarla desde esta página, quita esas variables del .env y reinicia.")}
          </Notice>}
          {c.source === "default" && <Text size="sm" c="dimmed" className="ms-measure">{t("Nadie ha elegido otra, así que se usa el FalkorDB que se instala junto a MimirSynth.")}</Text>}
          {saved && <Notice tone="success" title={t("Conexión guardada")}>{saved.changed
            ? t("La instancia usa ya la base de datos nueva, sin reiniciar. Los datos de la anterior siguen allí.")
            : t("La instancia sigue en la misma base de datos, con los datos de conexión nuevos.")}</Notice>}
          <Group gap="xs"><Btn icon="test" loading={check.isPending} onClick={() => check.mutate()}>{t("Probar la conexión")}</Btn></Group>
          {check.data && <GraphTestResult r={check.data} />}
          <MutationError error={check.error} />
        </Stack>}
        {editing && c && <EditConnection cur={c} onClose={() => setEditing(false)}
          onSaved={(s) => { setEditing(false); setSaved(s); check.reset(); qc.setQueryData(["admin-graph"], s); qc.invalidateQueries({ queryKey: ["ai-status"] }); if (s.changed) qc.invalidateQueries(); }} />}
      </SettingsBody>
    </SettingsGroup>
    {c && <ExistingGraphs key={c.address} />}
  </>);
}
