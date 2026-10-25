import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { fmt, get, Overview as O } from "../api";
import { AreaChart, BarList, Donut, Page, Panel, Pill, StatCard, DataState, PageHeader, FillArea, HIDROMIEL, PIZARRA, StatGrid, ColGrid, EmptyState, Section } from "../ui";

type Activity = {
  weeks: string[]; episodes: number[]; facts_learned: number[]; facts_invalidated: number[];
  fact_status: { current: number; invalidated: number; future: number };
  top_relations: { name: string; count: number }[]; top_entities: { name: string; degree: number; labels: string[] }[];
  documents: { by_status: Record<string, number>; total: number; chunks: number };
};

export default function Overview({ graph }: { graph: string }) {
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
            {a ? <AreaChart labels={a.weeks} series={[{ name: t("Hechos aprendidos"), values: a.facts_learned }, { name: "Episodios", values: a.episodes, color: HIDROMIEL }, { name: t("Hechos invalidados"), values: a.facts_invalidated, color: "var(--ms-invalidado)" }]} /> : <EmptyState>{t("Cargando…")}</EmptyState>}
          </Section>
        </div>
        <Section title={t("Estado de los hechos")}>
          {status ? <Donut center="hechos" slices={[{ label: t("Vigentes"), value: status.current }, { label: t("Invalidados"), value: status.invalidated, color: "var(--ms-invalidado)" }, ...(status.future ? [{ label: t("Futuros"), value: status.future, color: PIZARRA }] : [])]} /> : <EmptyState>{t("Cargando…")}</EmptyState>}
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
            <Group gap={6}>{Object.entries(a.documents.by_status).map(([k, v]) => <Pill key={k} size="xs" tone={k === "active" ? "success" : k === "error" ? "danger" : "warn"}>{v} {({ active: "indexados", indexing: "indexando", pending: t("en cola"), error: t("con error") } as Record<string, string>)[k] ?? k}</Pill>)}</Group>
          </Group>
        </Section>)}
      </Stack></FillArea>
    </Page>
  );
}
