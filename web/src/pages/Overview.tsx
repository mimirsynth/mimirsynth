import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fmtDay, fmtNum, get, send, Overview as O } from "../api";
import { AreaChart, BarList, Btn, ColGrid, DataState, EmptyState, EntityChip, FillArea, HIDROMIEL, Meter, Page, PageHeader, Pill, PIZARRA, Section, Segments, SERIES, StatCard, StatGrid, TrendStat } from "../ui";
import { T, locale } from "../i18n";
import type { Attention } from "./Quality";
import { PURPOSE } from "./AiUsage";
import GettingStarted from "./GettingStarted";
import NoLlmNotice from "./NoLlmNotice";

const CURATORS = ["curator", "admin", "owner"];
const ADMINS = ["admin", "owner"];

type Activity = {
  weeks: string[]; episodes: number[]; facts_learned: number[]; facts_invalidated: number[];
  fact_status: { current: number; invalidated: number; future: number };
  top_relations: { name: string; count: number }[]; top_entities: { uuid: string; name: string; degree: number; labels: string[] }[];
  documents: { by_status: Record<string, number>; total: number; chunks: number };
};

// ---- To review ----

/** Each line of «To review», the most urgent first: what is waiting, a note on what it is, and the tool where it is decided. */
const REVIEW: { key: keyof Attention; label: string; hint: string; action: string; to: string }[] = [
  { key: "proposals", label: T("Propuestas esperando una decisión"), hint: T("de agentes y personas"), action: T("Revisar"), to: "/propuestas?estado=pending&tipo=memory" },
  { key: "corrections", label: T("Correcciones pendientes"), hint: T("de agentes o de valoraciones «incorrecto»"), action: T("Revisar"), to: "/propuestas?estado=pending&tipo=correction" },
  { key: "failed", label: T("Propuestas cuya ingesta falló"), hint: T("se reintentan o se rechazan"), action: T("Ver"), to: "/propuestas?tab=decididas&estado=failed" },
  { key: "summaries", label: T("Resúmenes de entidades por aprobar"), hint: T("propuestos por el LLM tras la ingesta"), action: T("Revisar"), to: "/calidad?tab=summaries" },
  { key: "duplicates", label: T("Grupos de posibles duplicados"), hint: T("entidades que parecen la misma"), action: T("Fusionar"), to: "/calidad?tab=dup" },
  { key: "conflicts", label: T("Posibles contradicciones"), hint: T("dos valores para una relación que admite uno"), action: T("Resolver"), to: "/calidad?tab=conflicts" },
  { key: "stale", label: T("Hechos a revisar"), hint: T("pasados de su vida útil"), action: T("Revisar"), to: "/calidad?tab=stale" },
  { key: "retype", label: T("Tipos dudosos con un cambio propuesto"), hint: T("se pueden aceptar en bloque"), action: T("Corregir"), to: "/calidad?tab=corrector" },
  { key: "refqueries", label: T("Consultas de referencia que empeoraron"), hint: T("en la última ejecución"), action: T("Ver"), to: "/preguntar?tab=referencia" },
];

/** What waits for a curator's decision: each line its count, what it is and the button to the tool that decides it. */
function ToReview({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["attention", graph], queryFn: () => get<Attention>(`brains/${graph}/attention`), staleTime: 30000 });
  const count = (k: keyof Attention) => (q.data?.[k] as number | null | undefined) ?? 0;
  const lines = REVIEW.filter((l) => count(l.key) > 0);
  const total = lines.reduce((a, l) => a + count(l.key), 0);
  return (
    <Section title={t("Por revisar")} actions={total > 0 && <Text size="sm" c="dimmed">{t("{{n}} decisiones pendientes", { n: fmtNum(total) })}</Text>}>
      {!q.data ? <DataState query={q} /> : lines.length ? (
        <div className="ms-review">{lines.map((l, i) => {
          const oldest = l.key === "proposals" ? q.data?.proposals_oldest : null;
          const hint = oldest ? t("{{hint}} · la más antigua, del {{day}}", { hint: t(l.hint), day: fmtDay(oldest) }) : t(l.hint);
          return (
            <div key={l.key} className="ms-review-row">
              <span><Pill size="sm" tone={i === 0 ? "warn" : undefined}>{fmtNum(count(l.key))}</Pill></span>
              <span className="ms-review-text"><span className="ms-review-label">{t(l.label)}</span><span className="ms-review-hint">{hint}</span></span>
              <Btn size="row" component={Link} to={l.to}>{t(l.action)}</Btn>
            </div>);
        })}</div>
      ) : <EmptyState>{t("Nada necesita tu atención.")}</EmptyState>}
    </Section>
  );
}

// ---- Movement ----

type Counts = { facts_new: number | null; facts_gone: number | null; docs_new: number; proposals_new: number; proposals_decided: number };
type Changes = Counts & { days: number; bucket: "hour" | "day"; previous: Counts; series: { [K in keyof Counts]: number[] | null } };

/** The figure against the same period before: «+38 % vs the previous 7 days», «the same as…», or the figure before when it was 0. */
function vsBefore(now: number | null, before: number | null, days: string, t: (k: string, o?: Record<string, unknown>) => string) {
  if (now === null || before === null) return t("no se pudo leer el grafo");
  const period = days === "1" ? t("las 24 h anteriores") : t("los {{n}} días anteriores", { n: days });
  if (now === before) return t("igual que {{period}}", { period });
  if (before === 0) return t("0 en {{period}}", { period });
  const p = Math.round((100 * (now - before)) / before);
  return t("{{pct}} frente a {{period}}", { pct: `${p > 0 ? "+" : ""}${p.toLocaleString(locale())} %`, period });
}

/** What moved in the brain in the last day, week or month: each figure with its shape over the period and the comparison with the period before. */
function Movement({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [days, setDays] = useState("7");
  const q = useQuery({ queryKey: ["changes", graph, days], queryFn: () => get<Changes>(`brains/${graph}/changes`, { days }), staleTime: 60000 });
  const d = q.data;
  return (
    <Section title={t("Movimiento")} actions={<Segments label={t("Periodo")} value={days} onChange={setDays}
      data={[{ value: "1", label: t("24 h") }, { value: "7", label: t("7 días") }, { value: "30", label: t("30 días") }]} />}>
      {!d ? <DataState query={q} /> : (
        <div className="ms-trends">
          <TrendStat label={t("Hechos nuevos")} to="/hechos" value={fmtNum(d.facts_new)} values={d.series.facts_new} color={SERIES[0]}
            note={vsBefore(d.facts_new, d.previous.facts_new, days, t)} />
          <TrendStat label={t("Invalidados")} to="/hechos" value={fmtNum(d.facts_gone)} values={d.series.facts_gone} color="var(--ms-invalidado)"
            note={vsBefore(d.facts_gone, d.previous.facts_gone, days, t)} />
          <TrendStat label={t("Propuestas")} to="/propuestas?tab=decididas" value={`${fmtNum(d.proposals_new)} / ${fmtNum(d.proposals_decided)}`}
            values={d.series.proposals_new} color={HIDROMIEL} note={t("recibidas / decididas")} />
          <TrendStat label={t("Documentos")} to="/conocimiento" value={fmtNum(d.docs_new)} values={d.series.docs_new} color={PIZARRA}
            note={vsBefore(d.docs_new, d.previous.docs_new, days, t)} />
        </div>)}
    </Section>
  );
}

// ---- What the brain knows ----

const DOC_STATUS: Record<string, string> = { indexing: T("indexando"), pending: T("en cola"), error: T("con error") };

/** The volume of the brain, how it grew week by week, and what is most connected. For everyone who can read the brain. */
function Knowledge({ graph, data }: { graph: string; data: O }) {
  const { t } = useTranslation();
  const [weeks, setWeeks] = useState("26");
  const q = useQuery({ queryKey: ["overview-activity", graph, weeks], queryFn: () => get<Activity>("overview/activity", { graph, weeks }) });
  const a = q.data;
  const totals = [
    { value: a ? a.fact_status.current : data.facts_total - data.facts_invalidated, label: t("hechos vigentes"), to: "/hechos" },
    { value: data.facts_invalidated, label: t("invalidados"), to: "/hechos" },
    { value: data.entities, label: t("entidades"), to: "/grafo" },
    { value: data.episodes, label: t("episodios"), to: "/diario" },
    ...(a ? [{ value: a.documents.total, label: t("documentos"), to: "/conocimiento" }] : []),
  ];
  return (
    <Section title={t("Qué sabe el brain")} actions={data.first_episode_at && <Text size="xs" c="dimmed">{t("desde el {{day}}", { day: fmtDay(data.first_episode_at) })}</Text>}>
      <Stack gap="md">
        <div className="ms-totals">{totals.map((x) => (
          <Link key={x.label} to={x.to} className="ms-total"><span className="ms-total-value">{fmtNum(x.value)}</span><span className="ms-total-label">{x.label}</span></Link>))}</div>
        <Stack gap={6} className="ms-rule-top">
          <Group justify="space-between" gap="xs">
            <span className="ms-subhead">{t("Actividad semanal")}</span>
            <Segments label={t("Intervalo")} value={weeks} onChange={setWeeks}
              data={[{ value: "12", label: t("12 semanas") }, { value: "26", label: t("26 semanas") }, { value: "52", label: t("1 año") }]} />
          </Group>
          {a ? <AreaChart labels={a.weeks} series={[{ name: t("Hechos aprendidos"), values: a.facts_learned }, { name: t("Episodios"), values: a.episodes, color: HIDROMIEL },
            { name: t("Hechos invalidados"), values: a.facts_invalidated, color: "var(--ms-invalidado)" }]} /> : <DataState query={q} />}
        </Stack>
        <ColGrid min={260}>
          <Stack gap={8} className="ms-rule-top">
            <span className="ms-subhead">{t("Entidades más conectadas")}</span>
            {!a ? <EmptyState>{t("Cargando…")}</EmptyState> : a.top_entities.length ? <div className="ms-chips">{a.top_entities.map((e) => (
              <EntityChip key={e.uuid ?? e.name} name={`${e.name} · ${e.degree}`} type={e.labels[0]} to={e.uuid ? `/entidad/${e.uuid}` : undefined} />))}</div>
              : <EmptyState>{t("Sin entidades")}</EmptyState>}
          </Stack>
          <Stack gap={8} className="ms-rule-top">
            <span className="ms-subhead">{t("Entidades por tipo")}</span>
            <BarList items={data.by_label.slice(0, 6).map((l) => ({ label: l.label, value: l.count }))} />
          </Stack>
          <Stack gap={8} className="ms-rule-top">
            <span className="ms-subhead">{t("Documentos")}</span>
            {a ? <>
              <Group gap={8} align="baseline"><span className="ms-figure">{fmtNum(a.documents.by_status.active ?? 0)}</span>
                <Text size="sm" c="dimmed">{t("indexados · {{n}} trozos", { n: fmtNum(a.documents.chunks) })}</Text></Group>
              <Group gap={6}>{Object.entries(a.documents.by_status).filter(([k, v]) => k !== "active" && v > 0).map(([k, v]) => (
                <Pill key={k} size="xs" tone={k === "error" ? "danger" : "warn"}>{v} {t(DOC_STATUS[k] ?? k)}</Pill>))}</Group>
              <div><Btn kind="link" component={Link} to="/conocimiento">{t("Ir a Conocimiento")}</Btn></div>
            </> : <EmptyState>{t("Cargando…")}</EmptyState>}
          </Stack>
        </ColGrid>
      </Stack>
    </Section>
  );
}

// ---- Memory health ----

type HealthMetrics = {
  coverage: number | null; expected?: number; found?: number; reference_queries?: number;
  staleness: number | null; stale_results?: number; noise: number | null; noise_queries?: number;
  redundancy: number | null; redundant_facts?: number; current_facts?: number; redundancy_sampled?: boolean;
  contradictions: number | null; stale_facts: number | null; failed: string[]; probes_paused?: boolean;
  retrievable?: number | null; selftested?: number; not_retrievable?: number;
};
type HealthRun = { id: number; day: string; status: string; metrics: HealthMetrics | null; finished_at: string | null };
type Health = { items: HealthRun[]; latest: HealthRun | null; measuring: boolean };

/** The parts of a measurement that can fail on their own, as the sentence «Could not measure: …» names them. */
const HEALTH_PARTS: Record<string, string> = {
  probes: T("las preguntas de prueba"), redundancy: T("la redundancia"), contradictions: T("las contradicciones"), stale_facts: T("los hechos a revisar"),
  retrievable: T("las propuestas que se recuperan"),
};

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toLocaleString(locale(), { style: "percent", maximumFractionDigits: 1 }));

/** Memory health (issue 292): the figures of the last daily measurement, each with the one of a week before. What cannot be measured in this
 *  brain goes in one sentence that says why, instead of a card with a dash. Only for those who curate. */
function MemoryHealth({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["health", graph], queryFn: () => get<Health>(`brains/${graph}/health`, { days: 30 }), staleTime: 60000,
    refetchInterval: (query) => (query.state.data?.measuring ? 5000 : false) });
  const run = useMutation({ mutationFn: () => send("POST", `brains/${graph}/health/run`), onSettled: () => qc.invalidateQueries({ queryKey: ["health", graph] }) });
  const last = q.data?.latest;
  const m = last?.metrics;
  const before = last && q.data?.items.filter((r) => r.status === "done" && r.metrics && Date.parse(r.day) <= Date.parse(last.day) - 7 * 86400000).slice(-1)[0]?.metrics;
  const ago = (v: string) => t("hace 7 días: {{value}}", { value: v });
  const measuring = q.data?.measuring || run.isPending;
  const cards: { label: string; value: string; hint?: string }[] = [];
  const missing: string[] = [];
  if (m) {
    if (m.coverage === null) missing.push(t("la cobertura (no hay consultas de referencia con textos esperados)"));
    else cards.push({ label: t("Cobertura"), value: pct(m.coverage), hint: before ? ago(pct(before.coverage)) : t("{{found}} de {{expected}} textos esperados", { found: m.found ?? 0, expected: m.expected ?? 0 }) });
    if (m.staleness === null) missing.push(t("los resultados desactualizados (no hay consultas de referencia)"));
    else cards.push({ label: t("Resultados con algo desactualizado"), value: pct(m.staleness), hint: before ? ago(pct(before.staleness)) : t("{{n}} de {{total}} consultas de referencia", { n: m.stale_results ?? 0, total: m.reference_queries ?? 0 }) });
    if (m.noise !== null) cards.push({ label: t("Ruido"), value: fmtNum(m.noise), hint: before ? ago(fmtNum(before.noise)) : t("elementos por pregunta vaga; lo ideal es 0") });
    if (m.redundancy !== null) cards.push({ label: t("Redundancia"), value: pct(m.redundancy),
      hint: before ? ago(pct(before.redundancy)) : m.redundancy_sampled ? t("unos {{n}} hechos repiten otro (estimado)", { n: m.redundant_facts ?? 0 }) : t("{{n}} hechos repiten otro", { n: m.redundant_facts ?? 0 }) });
    if (m.contradictions === null) missing.push(t("las contradicciones (ninguna relación es funcional)"));
    else cards.push({ label: t("Contradicciones abiertas"), value: fmtNum(m.contradictions), hint: before ? ago(fmtNum(before.contradictions)) : undefined });
    if (m.retrievable === null || m.retrievable === undefined) missing.push(t("las propuestas que se recuperan (ninguna comprobada en 30 días)"));
    else cards.push({ label: t("Propuestas que se recuperan"), value: pct(m.retrievable), hint: before ? ago(pct(before.retrievable)) : t("{{n}} de {{total}} ingeridas en 30 días", { n: (m.selftested ?? 0) - (m.not_retrievable ?? 0), total: m.selftested ?? 0 }) });
    if (m.stale_facts === null) missing.push(t("los hechos a revisar (ninguna relación tiene vida útil)"));
    else cards.push({ label: t("Hechos a revisar"), value: fmtNum(m.stale_facts), hint: before ? ago(fmtNum(before.stale_facts)) : undefined });
  }
  return (
    <Section title={t("Salud de la memoria")} hint={t("Se mide sola una vez al día. Las cifras se explican en la wiki, en «Salud de la memoria».")}
      actions={<>
        {last && <Text size="xs" c="dimmed">{t("Medida el {{day}}", { day: fmtDay(last.day) })}</Text>}
        <Btn size="row" icon="refresh" loading={measuring} disabled={measuring} onClick={() => run.mutate()}>{measuring ? t("Midiendo…") : t("Medir ahora")}</Btn>
      </>}>
      {!q.data ? <DataState query={q} /> : !m ? <EmptyState>{t("Todavía no hay ninguna medición.")}</EmptyState> : (
        <Stack gap="sm">
          {cards.length > 0 && <StatGrid>{cards.map((c) => <StatCard key={c.label} label={c.label} value={c.value} hint={c.hint} />)}</StatGrid>}
          {missing.length > 0 && <div className="ms-note-box">{t("Sin medir: {{parts}}.", { parts: missing.join("; ") })}</div>}
          {m.probes_paused && <Text size="sm" c="dimmed">{t("Las preguntas de prueba no se hicieron: el brain ha llegado a su presupuesto de IA.")}</Text>}
          {!!m.failed.length && <Text size="sm" c="dimmed">{t("No se pudo medir: {{parts}}.", { parts: m.failed.map((p) => t(HEALTH_PARTS[p] ?? p)).join(", ") })}</Text>}
        </Stack>)}
    </Section>
  );
}

// ---- AI usage ----

type UsageRow = { purpose: string; prompt_tokens: number; completion_tokens: number; errors_429: number };
type Budget = { limit: number | null; unit: "tokens" | "cost"; used: number; paused: boolean };
type BrainUsage = { rows: UsageRow[]; budget: Budget };

/** What the brain has spent on AI engines this month: against its budget when it has one, where it is heading by the end of the month, what
 *  it went on and how often the provider limited the rate. Only for administrators of the brain, like the full page in Administration. */
function AiSpend({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const today = new Date();
  const day = today.getDate(), monthDays = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  const q = useQuery({ queryKey: ["ai-usage", graph, "month", day], queryFn: () => get<BrainUsage>(`brains/${graph}/ai-usage`, { days: day }), staleTime: 300000 });
  const d = q.data;
  const compact = (n: number) => n.toLocaleString(locale(), { notation: "compact", maximumFractionDigits: 2 });
  const money = (n: number) => n.toLocaleString(locale(), { maximumFractionDigits: 2 });
  const rows = d?.rows ?? [];
  const tokens = rows.reduce((a, r) => a + r.prompt_tokens + r.completion_tokens, 0);
  const b = d?.budget;
  const cost = !!b?.limit && b.unit === "cost";
  const used = b?.limit ? b.used : tokens;
  const show = (n: number) => (cost ? money(n) : compact(n));
  const projected = (used / day) * monthDays;
  const byPurpose = new Map<string, number>();
  for (const r of rows) byPurpose.set(r.purpose, (byPurpose.get(r.purpose) ?? 0) + r.prompt_tokens + r.completion_tokens);
  const errors429 = rows.reduce((a, r) => a + r.errors_429, 0);
  return (
    <Section title={t("Uso de IA")} actions={<Text size="xs" c="dimmed">{today.toLocaleDateString(locale(), { month: "long", year: "numeric" })}</Text>}>
      {!d || !b ? <DataState query={q} /> : (
        <Stack gap="sm">
          <Stack gap={6}>
            <Group justify="space-between" align="baseline" gap="xs">
              <span><span className="ms-figure">{show(used)}</span> <Text span size="sm" c="dimmed">{b.limit
                ? (cost ? t("de {{limit}} de coste estimado", { limit: money(b.limit) }) : t("de {{limit}} tokens", { limit: compact(b.limit) }))
                : t("tokens, sin presupuesto")}</Text></span>
              {b.limit ? <Text size="sm" className="ms-data">{pct(used / b.limit)}</Text> : null}
            </Group>
            {b.limit ? <Meter value={used / b.limit} mark={0.8} label={t("Presupuesto del mes usado")} tone={b.paused || used >= b.limit ? "danger" : used >= 0.8 * b.limit ? "warn" : undefined} /> : null}
            <Text size="xs" c="dimmed">{b.paused ? t("Presupuesto agotado: la ingesta está en pausa.")
              : b.limit ? t("A este ritmo, unos {{n}} a fin de mes · aviso al 80 %", { n: show(projected) })
              : t("A este ritmo, unos {{n}} tokens a fin de mes", { n: compact(projected) })}</Text>
          </Stack>
          <Stack gap={8} className="ms-rule-top">
            <span className="ms-subhead">{t("En qué se va (% de los tokens)")}</span>
            {tokens > 0 ? <BarList items={[...byPurpose.entries()].sort((x, y) => y[1] - x[1]).slice(0, 5)
              .map(([p, n]) => ({ label: t(PURPOSE[p] ?? p), value: Math.round((100 * n) / tokens), hint: t("{{n}} tokens", { n: compact(n) }) }))} />
              : <EmptyState>{t("Sin llamadas a motores de IA este mes.")}</EmptyState>}
          </Stack>
          <Group justify="space-between" gap="xs">
            <Text size="xs" c="dimmed">{errors429 > 0 ? t("{{n}} respuestas 429 este mes: el proveedor limitó el ritmo", { n: errors429 }) : t("Ninguna respuesta 429 este mes")}</Text>
            <Btn kind="link" component={Link} to="/admin?seccion=brain-usage">{t("Ver el detalle")}</Btn>
          </Group>
        </Stack>)}
    </Section>
  );
}

export default function Overview({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["overview", graph], queryFn: () => get<O>("overview", { graph }) });
  const data = q.data;
  if (!data) return <DataState query={q} />;
  const curator = CURATORS.includes(role), admin = ADMINS.includes(role);
  return (
    <Page>
      <PageHeader title={t("Resumen")} />
      <FillArea><Stack gap="md">
        <NoLlmNotice role={role} />
        <GettingStarted role={role} />
        {curator && <ColGrid min={420}><ToReview graph={graph} /><Movement graph={graph} /></ColGrid>}
        <Knowledge graph={graph} data={data} />
        {curator && (
          <ColGrid min={340}>
            <div className={admin ? "ms-span2" : undefined}><MemoryHealth graph={graph} /></div>
            {admin && <AiSpend graph={graph} />}
          </ColGrid>)}
      </Stack></FillArea>
    </Page>
  );
}
