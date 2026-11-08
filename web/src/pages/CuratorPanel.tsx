import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fmt, fmtDay, get, send } from "../api";
import { Btn, Check, EmptyState, MutationError, Notice, Panel, Pill } from "../ui";
import { T } from "../i18n";

type Fact = { uuid: string; fact: string; target: string; valid_at: string | null };
type Finding = { pass: string; rule?: string; similarity?: number; episodes?: { uuid: string; name: string; valid_at: string | null; text: string }[]; subject: string; relation: string; keep: Fact | null; replace: Fact[]; why?: string };
type Precision = { approved: number; rejected: number; pending: number; precision: number | null };
type Settings = { enabled: boolean; passes: Record<string, boolean>; batch: number; precision: Record<string, Precision> };
type Run = { id: number; day: string; status: string; reason: string; error: string; finished_at: string | null; findings: Record<string, number>;
  proposals: number[]; sample?: Record<string, Finding[]> };

const PASS: Record<string, string> = { contradictions: T("Contradicciones en relaciones funcionales"), redundancy: T("Hechos repetidos entre las mismas entidades"), obsolescence: T("Hechos pasados de su vida útil"), noise: T("Ruido: hechos que no dicen nada útil"), archive: T("Archivar lo que nunca se recupera"), distil: T("Destilar episodios que repiten la misma lección") };

// Why a finding that keeps nothing would leave: the noise pass says which of its rules it fell under (issue 325).
const NOISE_RULE: Record<string, string> = { placeholder: T("Un extremo es un comodín («esto», «algo»), no una cosa del mundo."),
  meta: T("Habla de la propia memoria, no del mundo que describe."), generic: T("Relación genérica cuyo texto no dice nada más que sus dos entidades."),
  change: T("Cuenta un cambio como suceso y otro hecho vigente ya dice el resultado.") };
const RULE_NAME: Record<string, string> = { placeholder: T("Comodines"), meta: T("Sobre la propia memoria"), generic: T("Relaciones genéricas"),
  change: T("Cambios contados como suceso") };
const ALONE: Record<string, string> = { obsolescence: T("Pasado de su vida útil y sin confirmar."), archive: T("Sin recuperar en mucho tiempo y sin confirmar.") };

const fkey = (f: Finding) => f.episodes?.[0]?.uuid ?? (f.keep ?? f.replace[0]).uuid;

const RUN_STATUS: Record<string, string> = { done: T("terminada"), discarded: T("descartada"), error: T("con error"), running: T("en marcha"), stopped: T("detenida") };

/** One finding: the fact the curator keeps and the ones it would replace, the evidence a person looks at before confirming. */
function FindingRow({ f }: { f: Finding }) {
  const { t } = useTranslation();
  if (f.pass === "distil") return (<Panel withBorder p="sm"><Stack gap={4}>
    <Text size="sm" fw={600}>{f.subject} · {t("{{n}} episodios casi iguales (similitud ≥ {{s}})", { n: f.episodes?.length ?? 0, s: f.similarity ?? "" })}</Text>
    {(f.episodes ?? []).map((e) => <Text key={e.uuid} size="xs" c="dimmed">{e.name} <span className="ms-data">({fmtDay(e.valid_at)})</span>: «{e.text}»</Text>)}
  </Stack></Panel>);
  const why = f.rule ? NOISE_RULE[f.rule] : ALONE[f.pass];
  return (<Panel withBorder p="sm"><Stack gap={4}>
    <Text size="sm" fw={600}>{f.subject} · <span className="ms-data">{f.relation}</span></Text>
    {f.keep ? <Text size="xs">{t("Se queda:")} «{f.keep.fact}» {f.keep.valid_at && <span className="ms-data">({fmtDay(f.keep.valid_at)})</span>}</Text>
      : <Text size="xs" c="dimmed">{why ? t(why) : f.why}</Text>}
    {f.replace.map((r) => <Text key={r.uuid} size="xs" c="dimmed">{t("Se invalidaría:")} «{r.fact}» {r.valid_at && <span className="ms-data">({fmtDay(r.valid_at)})</span>}</Text>)}
  </Stack></Panel>);
}

type ArchivedFact = { fact_uuid: string; fact: string | null; source: string | null; source_uuid: string | null; archived_at: string; reason: string };

/** The facts archived because nobody recalled them (issue 297): out of the recall, untouched in the graph, restored with one click. */
function Archived({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["archived", graph], queryFn: () => get<{ items: ArchivedFact[] }>(`brains/${graph}/archive`) });
  const restore = useMutation({ mutationFn: (u: string) => send("DELETE", `brains/${graph}/archive/${u}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["archived", graph] }) });
  const items = q.data?.items ?? [];
  if (!items.length) return null;
  return (<Stack gap={4}>
    <Text size="sm" fw={600}>{t("Archivados ({{n}})", { n: items.length })}</Text>
    <Text size="xs" c="dimmed">{t("Siguen en el grafo, pero el recall no los trae salvo que se pida. Restaurar uno lo devuelve al recall.")}</Text>
    {items.map((a) => <Group key={a.fact_uuid} justify="space-between" gap="xs" wrap="nowrap">
      <Text size="xs">{a.fact ? `«${a.fact}»` : a.fact_uuid}{a.source_uuid && <> · <Link to={`/entidad/${a.source_uuid}`}>{a.source}</Link></>} · {fmtDay(a.archived_at)}</Text>
      <Btn size="row" icon="undo" loading={restore.isPending && restore.variables === a.fact_uuid} onClick={() => restore.mutate(a.fact_uuid)}>{t("Restaurar")}</Btn>
    </Group>)}
    <MutationError error={restore.error} />
  </Stack>);
}

/** The scheduled curator (issue 300): what its passes would propose, the runs waiting for a person, and how often curators agreed. */
export default function CuratorPanel({ graph, isAdmin }: { graph: string; isAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const refresh = () => { qc.invalidateQueries({ queryKey: ["curator", graph] }); qc.invalidateQueries({ queryKey: ["attention", graph] }); };
  const s = useQuery({ queryKey: ["curator", graph, "settings"], queryFn: () => get<Settings>(`brains/${graph}/curator/settings`) });
  const runs = useQuery({ queryKey: ["curator", graph, "runs"], queryFn: () => get<{ items: Run[] }>(`brains/${graph}/curator/runs`),
    refetchInterval: (q) => (q.state.data?.items.some((r) => r.status === "queued" || r.status === "running") ? 4000 : false) });
  const preview = useMutation({ mutationFn: (pass: string) => send<{ count: number; findings: Finding[]; batch: number; by_rule?: Record<string, number> }>("POST", `brains/${graph}/curator/preview`, undefined, { pass }) });
  const save = useMutation({ mutationFn: (c: { enabled?: boolean; passes?: Record<string, boolean> }) => send("PUT", `brains/${graph}/curator/settings`,
    { enabled: c.enabled ?? s.data?.enabled, passes: { ...s.data?.passes, ...c.passes }, batch: s.data?.batch }), onSuccess: refresh });
  const run = useMutation({ mutationFn: () => send("POST", `brains/${graph}/curator/run`), onSettled: refresh });
  const decide = useMutation({ mutationFn: ({ id, verb }: { id: number; verb: "confirm" | "discard" }) => send("POST", `brains/${graph}/curator/runs/${id}/${verb}`), onSuccess: refresh });
  const waiting = runs.data?.items.filter((r) => r.status === "waiting") ?? [];
  return (
    <Stack gap="sm">
      <Notice tone="info">{t("El curador recorre el grafo una vez al día y convierte lo que encuentra en propuestas en cuarentena, con su evidencia. No cambia nada por su cuenta: cada propuesta la decide un curador, una a una, y se puede deshacer. Busca contradicciones claras en las relaciones funcionales, hechos repetidos entre las mismas entidades, hechos pasados de su vida útil, ruido y hechos que nunca se recuperan (los archiva); cada pasada se activa por separado. Si la cobertura de las consultas de referencia baja tras aprobar sus propuestas, se detiene y avisa.")}</Notice>
      {s.data && <Group gap="md">
        {isAdmin ? <Check checked={s.data.enabled} onChange={(e) => save.mutate({ enabled: e.currentTarget.checked })} label={t("Activar el curador en este brain")}
          description={t("Si una pasada fuera a proponer más de {{n}} cambios a la vez, espera a que alguien mire una muestra y la confirme.", { n: s.data.batch })} />
          : <Text size="sm">{s.data.enabled ? t("El curador está activado en este brain.") : t("El curador está desactivado; lo activa un administrador del brain.")}</Text>}
      </Group>}
      {s.data && Object.entries(PASS).map(([id, label]) => { const p = s.data.precision[id]; return (
        <Group key={id} gap="md" align="flex-start">
          <Check checked={!!s.data.passes[id]} disabled={!isAdmin} onChange={(e) => save.mutate({ passes: { [id]: e.currentTarget.checked } })} label={t(label)}
            description={!p || p.precision === null ? t("Todavía no se ha decidido ninguna de sus propuestas.")
              : t("Precisión: {{pct}} de sus propuestas aprobadas ({{a}} aprobadas, {{r}} rechazadas, {{w}} pendientes).", { pct: `${Math.round(p.precision * 100)} %`, a: p.approved, r: p.rejected, w: p.pending })} />
          <Btn size="row" icon="search" loading={preview.isPending && preview.variables === id} onClick={() => preview.mutate(id)}>{t("Ver qué propondría")}</Btn>
        </Group>); })}
      <Group gap="xs">
        <Btn icon="refresh" loading={run.isPending} onClick={() => run.mutate()}>{t("Ejecutar ahora")}</Btn>
        <Btn kind="link" component={Link} to="/propuestas?estado=pending">{t("Ir a las propuestas")}</Btn>
      </Group>
      <MutationError error={save.error ?? run.error ?? decide.error ?? preview.error} />
      {preview.data && (preview.data.count ? <Stack gap="xs">
        <Text size="sm">{t("Propondría {{n}} cambios (sin crear nada todavía):", { n: preview.data.count })}</Text>
        {Object.keys(preview.data.by_rule ?? {}).length ? Object.entries(preview.data.by_rule ?? {}).map(([rule, n]) => <Stack key={rule} gap="xs">
          <Text size="sm" fw={600}>{RULE_NAME[rule] ? t(RULE_NAME[rule]) : rule} <span className="ms-data">· {t("{{n}} hallazgos", { n })}</span></Text>
          {preview.data!.findings.filter((f) => f.rule === rule).map((f) => <FindingRow key={f.replace[0].uuid} f={f} />)}
        </Stack>) : preview.data.findings.map((f) => <FindingRow key={fkey(f)} f={f} />)}
      </Stack> : <EmptyState>{t("Ahora no propondría nada.")}</EmptyState>)}
      {waiting.map((r) => <Panel key={r.id} withBorder p="sm"><Stack gap="xs">
        <Group gap="xs"><Pill tone="warn">{t("Espera tu confirmación")}</Pill><Text size="sm">{t("La ejecución del {{day}} propondría {{n}} cambios. Mira la muestra: si es correcta, se crean las propuestas (cada una se decide aparte).", { day: fmtDay(r.day), n: Object.values(r.findings).reduce((a, b) => a + b, 0) })}</Text></Group>
        {Object.values(r.sample ?? {}).flat().map((f) => <FindingRow key={fkey(f)} f={f} />)}
        <Group gap="xs"><Btn kind="primary" loading={decide.isPending} onClick={() => decide.mutate({ id: r.id, verb: "confirm" })}>{t("Crear las propuestas")}</Btn>
          <Btn loading={decide.isPending} onClick={() => decide.mutate({ id: r.id, verb: "discard" })}>{t("Descartar")}</Btn></Group>
      </Stack></Panel>)}
      <Archived graph={graph} />
      {!!runs.data?.items.length && <Stack gap={4}>
        <Text size="sm" fw={600}>{t("Últimas ejecuciones")}</Text>
        {runs.data.items.filter((r) => r.status !== "waiting").slice(0, 10).map((r) => <Text key={r.id} size="xs" c="dimmed">
          {fmtDay(r.day)} · {t(RUN_STATUS[r.status] ?? RUN_STATUS.running)}
          {" · "}{t("{{n}} propuestas", { n: r.proposals.length })}{r.finished_at ? ` · ${fmt(r.finished_at)}` : ""}{r.error ? ` · ${r.error}` : ""}</Text>)}
      </Stack>}
    </Stack>
  );
}
