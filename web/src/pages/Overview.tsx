import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { fmt, fmtDay, fmtNum, get, send, Overview as O } from "../api";
import { AreaChart, BarList, Btn, Donut, Page, Panel, Pill, StatCard, DataState, PageHeader, FillArea, HIDROMIEL, PIZARRA, StatGrid, ColGrid, EmptyState, Section, Segments } from "../ui";
import { T, locale } from "../i18n";
import type { Attention } from "./Quality";
import GettingStarted from "./GettingStarted";
import NoLlmNotice from "./NoLlmNotice";

type Activity = {
  weeks: string[]; episodes: number[]; facts_learned: number[]; facts_invalidated: number[];
  fact_status: { current: number; invalidated: number; future: number };
  top_relations: { name: string; count: number }[]; top_entities: { name: string; degree: number; labels: string[] }[];
  documents: { by_status: Record<string, number>; total: number; chunks: number };
};

/** Each line of «Needs your attention»: what is waiting, and the tool where it is decided. */
const ATTENTION: { key: keyof Attention; label: string; to: string }[] = [
  { key: "proposals", label: T("Propuestas esperando una decisión"), to: "/propuestas?estado=pending&tipo=memory" },
  { key: "corrections", label: T("Correcciones pendientes, de agentes o de valoraciones «incorrecto»"), to: "/propuestas?estado=pending&tipo=correction" },
  { key: "failed", label: T("Propuestas cuya ingesta falló"), to: "/propuestas?tab=decididas&estado=failed" },
  { key: "duplicates", label: T("Grupos de posibles duplicados"), to: "/calidad?tab=dup" },
  { key: "conflicts", label: T("Posibles contradicciones"), to: "/calidad?tab=conflicts" },
  { key: "stale", label: T("Hechos a revisar, pasados de su vida útil"), to: "/calidad?tab=stale" },
  { key: "retype", label: T("Tipos dudosos con un cambio propuesto"), to: "/calidad?tab=corrector" },
  { key: "summaries", label: T("Resúmenes de entidades propuestos por aprobar"), to: "/calidad?tab=summaries" },
  { key: "refqueries", label: T("Consultas de referencia que empeoraron en la última ejecución"), to: "/preguntar?tab=referencia" },
];

/** What waits for a curator's decision, each line a link to the tool where it is decided. Only for those who can act. */
function NeedsAttention({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["attention", graph], queryFn: () => get<Attention>(`brains/${graph}/attention`), staleTime: 30000 });
  const lines = ATTENTION.filter((l) => (q.data?.[l.key] ?? 0) > 0);
  return (
    <Section title={t("Necesita tu atención")}>
      {!q.data ? <DataState query={q} /> : lines.length ? <Stack gap={6}>{lines.map((l) => (
        <div key={l.key} className="ms-countrow"><span><Pill size="sm" tone="warn">{q.data[l.key]}</Pill></span>
          <Btn kind="link" component={Link} to={l.to}>{t(l.label)}</Btn></div>))}</Stack>
        : <Text size="sm" c="dimmed">{t("Nada necesita tu atención.")}</Text>}
    </Section>
  );
}

type Changes = { days: number; facts_new: number | null; facts_gone: number | null; docs_new: number; proposals_new: number; proposals_decided: number };

/** Each line of «What changed»: the same counts as the email summary, plus the proposals that came in and were decided. */
const CHANGES: { key: keyof Changes; label: string; to: string }[] = [
  { key: "facts_new", label: T("Hechos nuevos"), to: "/hechos" },
  { key: "facts_gone", label: T("Hechos invalidados"), to: "/hechos" },
  { key: "docs_new", label: T("Documentos añadidos"), to: "/conocimiento" },
  { key: "proposals_new", label: T("Propuestas recibidas"), to: "/propuestas" },
  { key: "proposals_decided", label: T("Propuestas decididas"), to: "/propuestas?tab=decididas" },
];

/** What moved in the brain in the last day or week, next to what waits for a decision. Only for those who curate. */
function WhatChanged({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [days, setDays] = useState("7");
  const q = useQuery({ queryKey: ["changes", graph, days], queryFn: () => get<Changes>(`brains/${graph}/changes`, { days }), staleTime: 60000 });
  const lines = CHANGES.filter((l) => ((q.data?.[l.key] as number | null) ?? 0) > 0);
  return (
    <Section title={t("Lo que ha cambiado")}>
      <Stack gap="xs">
        <Segments label={t("Periodo")} value={days} onChange={setDays} data={[{ value: "1", label: t("Últimas 24 h") }, { value: "7", label: t("Últimos 7 días") }]} />
        {!q.data ? <DataState query={q} /> : lines.length ? <Stack gap={6}>{lines.map((l) => (
          <div key={l.key} className="ms-countrow"><span><Pill size="sm">{q.data[l.key] as number}</Pill></span>
            <Btn kind="link" component={Link} to={l.to}>{t(l.label)}</Btn></div>))}</Stack>
          : <Text size="sm" c="dimmed">{days === "1" ? t("Nada nuevo en las últimas 24 horas.") : t("Nada nuevo en los últimos 7 días.")}</Text>}
      </Stack>
    </Section>
  );
}

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

/** Memory health (issue 292): the last daily measurement, each number with the one of a week before. Only for those who curate. */
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
  return (
    <Section title={t("Salud de la memoria")} hint={t("Se mide sola una vez al día. Las cifras se explican en la wiki, en «Salud de la memoria».")}>
      <Stack gap="sm">
        <Group justify="space-between" gap="xs">
          <Text size="sm" c="dimmed">{last ? t("Medida el {{day}}.", { day: fmtDay(last.day) }) : q.data ? t("Todavía no hay ninguna medición.") : ""}</Text>
          <Btn size="row" icon="refresh" loading={measuring} disabled={measuring} onClick={() => run.mutate()}>{measuring ? t("Midiendo…") : t("Medir ahora")}</Btn>
        </Group>
        {!q.data ? <DataState query={q} /> : m && (
          <StatGrid>
            <StatCard label={t("Cobertura")} value={pct(m.coverage)}
              hint={m.coverage === null ? t("sin consultas de referencia con textos esperados") : before ? ago(pct(before.coverage)) : t("{{found}} de {{expected}} textos esperados", { found: m.found ?? 0, expected: m.expected ?? 0 })} />
            <StatCard label={t("Resultados con algo desactualizado")} value={pct(m.staleness)}
              hint={m.staleness === null ? t("sin consultas de referencia") : before ? ago(pct(before.staleness)) : t("{{n}} de {{total}} consultas de referencia", { n: m.stale_results ?? 0, total: m.reference_queries ?? 0 })} />
            <StatCard label={t("Ruido")} value={fmtNum(m.noise)} hint={before ? ago(fmtNum(before.noise)) : t("elementos por pregunta vaga; lo ideal es 0")} />
            <StatCard label={t("Redundancia")} value={pct(m.redundancy)}
              hint={before ? ago(pct(before.redundancy)) : m.redundancy_sampled ? t("unos {{n}} hechos repiten otro (estimado)", { n: m.redundant_facts ?? 0 }) : t("{{n}} hechos repiten otro", { n: m.redundant_facts ?? 0 })} />
            <StatCard label={t("Contradicciones abiertas")} value={fmtNum(m.contradictions)} hint={m.contradictions === null ? t("ninguna relación es funcional") : before ? ago(fmtNum(before.contradictions)) : undefined} />
            <StatCard label={t("Propuestas que se recuperan")} value={pct(m.retrievable)}
              hint={m.retrievable === null || m.retrievable === undefined ? t("ninguna comprobada en 30 días") : before ? ago(pct(before.retrievable)) : t("{{n}} de {{total}} ingeridas en 30 días", { n: (m.selftested ?? 0) - (m.not_retrievable ?? 0), total: m.selftested ?? 0 })} />
            <StatCard label={t("Hechos a revisar")} value={fmtNum(m.stale_facts)} hint={m.stale_facts === null ? t("ninguna relación tiene vida útil") : before ? ago(fmtNum(before.stale_facts)) : undefined} />
          </StatGrid>)}
        {m?.probes_paused && <Text size="sm" c="dimmed">{t("Las preguntas de prueba no se hicieron: el brain ha llegado a su presupuesto de IA.")}</Text>}
        {!!m?.failed.length && <Text size="sm" c="dimmed">{t("No se pudo medir: {{parts}}.", { parts: m.failed.map((p) => t(HEALTH_PARTS[p] ?? p)).join(", ") })}</Text>}
      </Stack>
    </Section>
  );
}

export default function Overview({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["overview", graph], queryFn: () => get<O>("overview", { graph }) });
  const data = q.data;
  const act = useQuery({ queryKey: ["overview-activity", graph], queryFn: () => get<Activity>("overview/activity", { graph, weeks: 26 }) });
  if (!data) return <DataState query={q} />;
  const a = act.data;
  const last = (v: number[] | undefined) => (v ?? []).slice(-1)[0] ?? 0;
  const status = a?.fact_status;
  return (
    <Page>
      <PageHeader title={t("Resumen")} description={<>{t("Estado del brain «{{graph}}»: volumen de conocimiento, actividad por semanas y lo más conectado.", { graph })}{data.last_episode && <> {t("Último episodio: {{name}} · {{date}}.", { name: data.last_episode.name, date: fmt(data.last_episode.created_at) })}</>}</>} />
      <FillArea><Stack gap="md">
      <NoLlmNotice role={role} />
      <GettingStarted role={role} />
      {["curator", "admin", "owner"].includes(role) && <ColGrid min={320}><NeedsAttention graph={graph} /><WhatChanged graph={graph} /></ColGrid>}
      {["curator", "admin", "owner"].includes(role) && <MemoryHealth graph={graph} />}
      <StatGrid>
        <StatCard label={t("Episodios")} value={data.episodes} hint={a ? t("+{{episodes}} esta semana", { episodes: last(a.episodes) }) : t("memoria episódica")} />
        <StatCard label={t("Entidades")} value={data.entities} />
        <StatCard label={t("Hechos")} value={data.facts_total} hint={a ? t("+{{facts_learned}} esta semana", { facts_learned: last(a.facts_learned) }) : t("memoria semántica")} />
        <StatCard label={t("Invalidados")} value={data.facts_invalidated} hint={t("dejaron de ser ciertos")} />
        <StatCard label={t("Comunidades")} value={data.communities} />
      </StatGrid>

      <ColGrid min={340}>
        <div className="ms-span2">
          <Section title={t("Actividad semanal · últimas 26 semanas")}>
            {a ? <AreaChart labels={a.weeks} series={[{ name: t("Hechos aprendidos"), values: a.facts_learned }, { name: t("Episodios"), values: a.episodes, color: HIDROMIEL }, { name: t("Hechos invalidados"), values: a.facts_invalidated, color: "var(--ms-invalidado)" }]} /> : <EmptyState>{t("Cargando…")}</EmptyState>}
          </Section>
        </div>
        <Section title={t("Estado de los hechos")}>
          {status ? <Donut center={t("hechos")} slices={[{ label: t("Vigentes"), value: status.current }, { label: t("Invalidados"), value: status.invalidated, color: "var(--ms-invalidado)" }, ...(status.future ? [{ label: t("Futuros"), value: status.future, color: PIZARRA }] : [])]} /> : <EmptyState>{t("Cargando…")}</EmptyState>}
        </Section>
      </ColGrid>

      <ColGrid min={300}>
        <Section title={t("Entidades por tipo")}><BarList items={data.by_label.slice(0, 8).map((l) => ({ label: l.label, value: l.count }))} /></Section>
        <Section title={t("Relaciones más usadas")}><BarList color={HIDROMIEL} items={(a?.top_relations ?? []).map((r) => ({ label: r.name, value: r.count }))} empty={a ? t("Sin hechos") : t("Cargando…")} /></Section>
        <Section title={t("Entidades más conectadas")}><BarList color={PIZARRA} items={(a?.top_entities ?? []).map((e) => ({ label: e.name, value: e.degree, hint: e.labels.join(", ") }))} empty={a ? t("Sin entidades") : t("Cargando…")} /></Section>
      </ColGrid>

      {a && (
        <Section title={t("Conocimiento documental")} hint={t("Los documentos se suben y consultan en la pestaña Conocimiento.")}>
          <Group gap="xl" align="center">
            <StatCard inline label={t("documentos")} value={a.documents.total} />
            <StatCard inline label={t("trozos indexados")} value={a.documents.chunks} />
            <Group gap={6}>{Object.entries(a.documents.by_status).map(([k, v]) => <Pill key={k} size="xs" tone={k === "active" ? "success" : k === "error" ? "danger" : "warn"}>{v} {({ active: t("indexados"), indexing: t("indexando"), pending: t("en cola"), error: t("con error") } as Record<string, string>)[k] ?? k}</Pill>)}</Group>
          </Group>
        </Section>)}
      </Stack></FillArea>
    </Page>
  );
}
