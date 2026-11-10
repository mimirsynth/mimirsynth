import { useTranslation } from "react-i18next";
import { Group } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fmt, fmtDay, get, send } from "../api";
import { Block, Btn, DataState, DataTable, EmptyState, ListCard, MutationError, Pill, SettingsGroup, SettingsRow, Toggle, ViewBar, type Tone } from "../ui";
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

const RUN_STATUS: Record<string, { label: string; tone: Tone }> = { done: { label: T("terminada"), tone: "success" }, discarded: { label: T("descartada"), tone: "neutral" },
  error: { label: T("con error"), tone: "danger" }, running: { label: T("en marcha"), tone: "neutral" }, stopped: { label: T("detenida"), tone: "warn" } };

/** One finding as a list card: the subject and relation, the fact the curator keeps (or why the facts would leave) and the ones it would
 *  replace, the evidence a person looks at before confirming. The noise rule it fell under goes as a tag. */
function FindingCard({ f }: { f: Finding }) {
  const { t } = useTranslation();
  if (f.pass === "distil") return (
    <ListCard title={f.subject} aside={t("{{n}} episodios casi iguales (similitud ≥ {{s}})", { n: f.episodes?.length ?? 0, s: f.similarity ?? "" })}>
      {(f.episodes ?? []).map((e) => <div key={e.uuid}>{e.name} <span className="ms-data">({fmtDay(e.valid_at)})</span>: «{e.text}»</div>)}
    </ListCard>);
  const why = f.rule ? NOISE_RULE[f.rule] : ALONE[f.pass];
  return (
    <ListCard title={<>{f.subject} · <span className="ms-data">{f.relation}</span></>} tags={f.rule && RULE_NAME[f.rule] ? <Pill>{t(RULE_NAME[f.rule])}</Pill> : undefined}
      note={f.replace.length ? f.replace.map((r) => <div key={r.uuid}>{t("Se invalidaría:")} «{r.fact}» {r.valid_at && <span className="ms-data">({fmtDay(r.valid_at)})</span>}</div>) : undefined}>
      {f.keep ? <>{t("Se queda:")} «{f.keep.fact}» {f.keep.valid_at && <span className="ms-data">({fmtDay(f.keep.valid_at)})</span>}</> : (why ? t(why) : f.why)}
    </ListCard>);
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
  return (
    <Block title={t("Archivados")} count={items.length} help={t("Siguen en el grafo, pero el recall no los trae salvo que se pida. Restaurar uno lo devuelve al recall.")}>
      <MutationError error={restore.error} />
      <DataTable aria-label={t("Archivados")}>
        <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Hecho")}</DataTable.Th><DataTable.Th>{t("Entidad")}</DataTable.Th><DataTable.Th>{t("Archivado")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{items.map((a) => <DataTable.Tr key={a.fact_uuid}>
          <DataTable.Td>{a.fact ? `«${a.fact}»` : <span className="ms-data">{a.fact_uuid}</span>}</DataTable.Td>
          <DataTable.Td>{a.source_uuid ? <Link to={`/entidad/${a.source_uuid}`}>{a.source}</Link> : "—"}</DataTable.Td>
          <DataTable.Td className="ms-data">{fmtDay(a.archived_at)}</DataTable.Td>
          <DataTable.Td><Btn size="row" icon="undo" loading={restore.isPending && restore.variables === a.fact_uuid} onClick={() => restore.mutate(a.fact_uuid)}>{t("Restaurar")}</Btn></DataTable.Td>
        </DataTable.Tr>)}</DataTable.Tbody>
      </DataTable>
    </Block>);
}

/** The scheduled curator (issue 300): its passes as settings, what each would propose, the runs waiting for a person, the archived facts
 *  and the last runs. */
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
  const past = runs.data?.items.filter((r) => r.status !== "waiting").slice(0, 10) ?? [];
  const previewed = preview.variables ? PASS[preview.variables] : undefined;
  return (
    <>
      <ViewBar title={t("Curador")}
        help={t("El curador recorre el grafo una vez al día y convierte lo que encuentra en propuestas en cuarentena, con su evidencia. No cambia nada por su cuenta: cada propuesta la decide un curador, una a una, y se puede deshacer. Busca contradicciones claras en las relaciones funcionales, hechos repetidos entre las mismas entidades, hechos pasados de su vida útil, ruido y hechos que nunca se recuperan (los archiva); cada pasada se activa por separado. Si la cobertura de las consultas de referencia baja tras aprobar sus propuestas, se detiene y avisa.")}
        meta={s.data && (s.data.enabled ? t("Activado en este brain") : t("Desactivado en este brain"))}
        actions={<><Btn kind="link" component={Link} to="/propuestas?estado=pending">{t("Ir a las propuestas")}</Btn>
          <Btn kind="primary" icon="refresh" loading={run.isPending} onClick={() => run.mutate()}>{t("Ejecutar ahora")}</Btn></>} />
      <MutationError error={save.error ?? run.error ?? decide.error ?? preview.error} />
      {s.data ? <SettingsGroup title={t("Pasadas")}>
        <SettingsRow label={t("Activar el curador en este brain")} help={isAdmin ? t("Si una pasada fuera a proponer más de {{n}} cambios a la vez, espera a que alguien mire una muestra y la confirme.", { n: s.data.batch })
          : t("El curador está desactivado; lo activa un administrador del brain.")}>
          <Toggle checked={s.data.enabled} disabled={!isAdmin} aria-label={t("Activar el curador en este brain")} onChange={(e) => save.mutate({ enabled: e.currentTarget.checked })} />
        </SettingsRow>
        {Object.entries(PASS).map(([id, label]) => { const p = s.data.precision[id]; return (
          <SettingsRow key={id} label={t(label)} help={!p || p.precision === null ? t("Todavía no se ha decidido ninguna de sus propuestas.")
            : t("Precisión: {{pct}} de sus propuestas aprobadas ({{a}} aprobadas, {{r}} rechazadas, {{w}} pendientes).", { pct: `${Math.round(p.precision * 100)} %`, a: p.approved, r: p.rejected, w: p.pending })}>
            <Group gap="xs" wrap="nowrap">
              <Btn size="row" icon="search" loading={preview.isPending && preview.variables === id} onClick={() => preview.mutate(id)}>{t("Ver qué propondría")}</Btn>
              <Toggle checked={!!s.data.passes[id]} disabled={!isAdmin} aria-label={t(label)} onChange={(e) => save.mutate({ passes: { [id]: e.currentTarget.checked } })} />
            </Group>
          </SettingsRow>); })}
      </SettingsGroup> : <DataState query={s} />}
      {preview.data && previewed && <Block title={t("Qué propondría: {{pass}}", { pass: t(previewed) })} count={preview.data.count}
        help={t("Una vista previa: no crea nada todavía.")}
        meta={Object.entries(preview.data.by_rule ?? {}).map(([rule, n]) => `${RULE_NAME[rule] ? t(RULE_NAME[rule]) : rule}: ${t("{{n}} hallazgos", { n })}`).join(" · ") || undefined}
        actions={<Btn kind="ghost" size="row" icon="close" onClick={() => preview.reset()}>{t("Cerrar")}</Btn>}>
        {preview.data.count ? preview.data.findings.map((f) => <FindingCard key={fkey(f)} f={f} />) : <EmptyState>{t("Ahora no propondría nada.")}</EmptyState>}
      </Block>}
      {waiting.length > 0 && <Block title={t("Esperan tu confirmación")} count={waiting.length}
        help={t("Una ejecución que propondría muchos cambios a la vez espera a que alguien mire su muestra. Si es correcta, se crean las propuestas y cada una se decide aparte.")}>
        {waiting.map((r) => <ListCard key={r.id} title={t("Ejecución del {{day}}", { day: fmtDay(r.day) })}
          aside={t("{{n}} cambios", { n: Object.values(r.findings).reduce((a, b) => a + b, 0) })}
          actions={<><Btn kind="primary" size="row" loading={decide.isPending} onClick={() => decide.mutate({ id: r.id, verb: "confirm" })}>{t("Crear las propuestas")}</Btn>
            <Btn size="row" loading={decide.isPending} onClick={() => decide.mutate({ id: r.id, verb: "discard" })}>{t("Descartar")}</Btn></>}>
          {Object.values(r.sample ?? {}).flat().map((f) => <div key={fkey(f)}>{f.subject} · <span className="ms-data">{f.relation}</span>{f.replace[0] ? `: «${f.replace[0].fact}»` : ""}</div>)}
        </ListCard>)}
      </Block>}
      <Archived graph={graph} />
      {past.length > 0 && <Block title={t("Últimas ejecuciones")}>
        <DataTable aria-label={t("Últimas ejecuciones")}>
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Día")}</DataTable.Th><DataTable.Th>{t("Estado")}</DataTable.Th><DataTable.Th>{t("Propuestas")}</DataTable.Th><DataTable.Th>{t("Terminada")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{past.map((r) => { const st = RUN_STATUS[r.status] ?? RUN_STATUS.running; return <DataTable.Tr key={r.id}>
            <DataTable.Td className="ms-data">{fmtDay(r.day)}</DataTable.Td>
            <DataTable.Td><Pill tone={st.tone}>{t(st.label)}</Pill>{r.error ? ` ${r.error}` : ""}</DataTable.Td>
            <DataTable.Td className="ms-data">{r.proposals.length}</DataTable.Td>
            <DataTable.Td className="ms-data">{r.finished_at ? fmt(r.finished_at) : "—"}</DataTable.Td>
          </DataTable.Tr>; })}</DataTable.Tbody>
        </DataTable>
      </Block>}
    </>
  );
}
