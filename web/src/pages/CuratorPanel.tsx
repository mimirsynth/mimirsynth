import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fmt, fmtDay, get, send } from "../api";
import { Btn, Check, EmptyState, MutationError, Notice, Panel, Pill } from "../ui";
import { T } from "../i18n";

type Fact = { uuid: string; fact: string; target: string; valid_at: string | null };
type Finding = { pass: string; subject: string; relation: string; keep: Fact | null; replace: Fact[]; why?: string };
type Precision = { approved: number; rejected: number; pending: number; precision: number | null };
type Settings = { enabled: boolean; passes: Record<string, boolean>; batch: number; precision: Record<string, Precision> };
type Run = { id: number; day: string; status: string; reason: string; error: string; finished_at: string | null; findings: Record<string, number>;
  proposals: number[]; sample?: Record<string, Finding[]> };

const PASS: Record<string, string> = { contradictions: T("Contradicciones en relaciones funcionales"), redundancy: T("Hechos repetidos entre las mismas entidades"), obsolescence: T("Hechos pasados de su vida útil"), noise: T("Ruido: hechos que no dicen nada útil") };

const RUN_STATUS: Record<string, string> = { done: T("terminada"), discarded: T("descartada"), error: T("con error"), running: T("en marcha"), stopped: T("detenida") };

/** One finding: the fact the curator keeps and the ones it would replace, the evidence a person looks at before confirming. */
function FindingRow({ f }: { f: Finding }) {
  const { t } = useTranslation();
  return (<Panel withBorder p="sm"><Stack gap={4}>
    <Text size="sm" fw={600}>{f.subject} · <span className="ms-data">{f.relation}</span></Text>
    {f.keep ? <Text size="xs">{t("Se queda:")} «{f.keep.fact}» {f.keep.valid_at && <span className="ms-data">({fmtDay(f.keep.valid_at)})</span>}</Text>
      : <Text size="xs" c="dimmed">{t("Pasado de su vida útil y sin confirmar.")}</Text>}
    {f.replace.map((r) => <Text key={r.uuid} size="xs" c="dimmed">{t("Se invalidaría:")} «{r.fact}» {r.valid_at && <span className="ms-data">({fmtDay(r.valid_at)})</span>}</Text>)}
  </Stack></Panel>);
}

/** The scheduled curator (issue 300): what its passes would propose, the runs waiting for a person, and how often curators agreed. */
export default function CuratorPanel({ graph, isAdmin }: { graph: string; isAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const refresh = () => { qc.invalidateQueries({ queryKey: ["curator", graph] }); qc.invalidateQueries({ queryKey: ["attention", graph] }); };
  const s = useQuery({ queryKey: ["curator", graph, "settings"], queryFn: () => get<Settings>(`brains/${graph}/curator/settings`) });
  const runs = useQuery({ queryKey: ["curator", graph, "runs"], queryFn: () => get<{ items: Run[] }>(`brains/${graph}/curator/runs`),
    refetchInterval: (q) => (q.state.data?.items.some((r) => r.status === "queued" || r.status === "running") ? 4000 : false) });
  const preview = useMutation({ mutationFn: (pass: string) => send<{ count: number; findings: Finding[]; batch: number }>("POST", `brains/${graph}/curator/preview`, undefined, { pass }) });
  const save = useMutation({ mutationFn: (c: { enabled?: boolean; passes?: Record<string, boolean> }) => send("PUT", `brains/${graph}/curator/settings`,
    { enabled: c.enabled ?? s.data?.enabled, passes: { ...s.data?.passes, ...c.passes }, batch: s.data?.batch }), onSuccess: refresh });
  const run = useMutation({ mutationFn: () => send("POST", `brains/${graph}/curator/run`), onSettled: refresh });
  const decide = useMutation({ mutationFn: ({ id, verb }: { id: number; verb: "confirm" | "discard" }) => send("POST", `brains/${graph}/curator/runs/${id}/${verb}`), onSuccess: refresh });
  const waiting = runs.data?.items.filter((r) => r.status === "waiting") ?? [];
  return (
    <Stack gap="sm">
      <Notice tone="info">{t("El curador recorre el grafo una vez al día y convierte lo que encuentra en propuestas en cuarentena, con su evidencia. No cambia nada por su cuenta: cada propuesta la decide un curador, una a una, y se puede deshacer. Busca contradicciones claras en las relaciones funcionales, hechos repetidos entre las mismas entidades, hechos pasados de su vida útil y ruido; cada pasada se activa por separado. Si la cobertura de las consultas de referencia baja tras aprobar sus propuestas, se detiene y avisa.")}</Notice>
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
        {preview.data.findings.map((f) => <FindingRow key={(f.keep ?? f.replace[0]).uuid} f={f} />)}
      </Stack> : <EmptyState>{t("Ahora no propondría nada.")}</EmptyState>)}
      {waiting.map((r) => <Panel key={r.id} withBorder p="sm"><Stack gap="xs">
        <Group gap="xs"><Pill tone="warn">{t("Espera tu confirmación")}</Pill><Text size="sm">{t("La ejecución del {{day}} propondría {{n}} cambios. Mira la muestra: si es correcta, se crean las propuestas (cada una se decide aparte).", { day: fmtDay(r.day), n: Object.values(r.findings).reduce((a, b) => a + b, 0) })}</Text></Group>
        {Object.values(r.sample ?? {}).flat().map((f) => <FindingRow key={(f.keep ?? f.replace[0]).uuid} f={f} />)}
        <Group gap="xs"><Btn kind="primary" loading={decide.isPending} onClick={() => decide.mutate({ id: r.id, verb: "confirm" })}>{t("Crear las propuestas")}</Btn>
          <Btn loading={decide.isPending} onClick={() => decide.mutate({ id: r.id, verb: "discard" })}>{t("Descartar")}</Btn></Group>
      </Stack></Panel>)}
      {!!runs.data?.items.length && <Stack gap={4}>
        <Text size="sm" fw={600}>{t("Últimas ejecuciones")}</Text>
        {runs.data.items.filter((r) => r.status !== "waiting").slice(0, 10).map((r) => <Text key={r.id} size="xs" c="dimmed">
          {fmtDay(r.day)} · {t(RUN_STATUS[r.status] ?? RUN_STATUS.running)}
          {" · "}{t("{{n}} propuestas", { n: r.proposals.length })}{r.finished_at ? ` · ${fmt(r.finished_at)}` : ""}{r.error ? ` · ${r.error}` : ""}</Text>)}
      </Stack>}
    </Stack>
  );
}
