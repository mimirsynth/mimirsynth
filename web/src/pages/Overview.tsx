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
  const q = useQuery({ queryKey: ["overview", graph], queryFn: () => get<O>("overview", { graph }) });
  const data = q.data;
  const act = useQuery({ queryKey: ["overview-activity", graph], queryFn: () => get<Activity>("overview/activity", { graph, weeks: 26 }) });
  if (!data) return <DataState query={q} />;
  const a = act.data;
  const last = (v: number[] | undefined) => (v ?? []).slice(-1)[0] ?? 0;
  const status = a?.fact_status;
  return (
    <Page>
      <PageHeader title="Resumen" description={<>Estado del brain «{graph}»: volumen de conocimiento, actividad por semanas y lo más conectado.{data.last_episode && <> Último episodio: <b>{data.last_episode.name}</b> · {fmt(data.last_episode.created_at)}.</>}</>} />
      <FillArea><Stack gap="md">
      <StatGrid>
        <StatCard label="Episodios" value={data.episodes} hint={a ? `+${last(a.episodes)} esta semana` : "memoria episódica"} />
        <StatCard label="Entidades" value={data.entities} />
        <StatCard label="Hechos" value={data.facts_total} hint={a ? `+${last(a.facts_learned)} esta semana` : "memoria semántica"} />
        <StatCard label="Invalidados" value={data.facts_invalidated} hint="dejaron de ser ciertos" />
        <StatCard label="Comunidades" value={data.communities} />
      </StatGrid>

      <ColGrid min={340}>
        <div className="ms-span2">
          <Section title="Actividad semanal · últimas 26 semanas">
            {a ? <AreaChart labels={a.weeks} series={[{ name: "Hechos aprendidos", values: a.facts_learned }, { name: "Episodios", values: a.episodes, color: HIDROMIEL }, { name: "Hechos invalidados", values: a.facts_invalidated, color: "var(--ms-invalidado)" }]} /> : <EmptyState>Cargando…</EmptyState>}
          </Section>
        </div>
        <Section title="Estado de los hechos">
          {status ? <Donut center="hechos" slices={[{ label: "Vigentes", value: status.current }, { label: "Invalidados", value: status.invalidated, color: "var(--ms-invalidado)" }, ...(status.future ? [{ label: "Futuros", value: status.future, color: PIZARRA }] : [])]} /> : <EmptyState>Cargando…</EmptyState>}
        </Section>
      </ColGrid>

      <ColGrid min={300}>
        <Section title="Entidades por tipo"><BarList items={data.by_label.slice(0, 8).map((l) => ({ label: l.label, value: l.count }))} /></Section>
        <Section title="Relaciones más usadas"><BarList color={HIDROMIEL} items={(a?.top_relations ?? []).map((r) => ({ label: r.name, value: r.count }))} empty={a ? "Sin hechos" : "Cargando…"} /></Section>
        <Section title="Entidades más conectadas"><BarList color={PIZARRA} items={(a?.top_entities ?? []).map((e) => ({ label: e.name, value: e.degree, hint: e.labels.join(", ") }))} empty={a ? "Sin entidades" : "Cargando…"} /></Section>
      </ColGrid>

      {a && (
        <Section title="Conocimiento documental" hint="Los documentos se suben y consultan en la pestaña Conocimiento.">
          <Group gap="xl" align="center">
            <StatCard inline label="documentos" value={a.documents.total} />
            <StatCard inline label="trozos indexados" value={a.documents.chunks} />
            <Group gap={6}>{Object.entries(a.documents.by_status).map(([k, v]) => <Pill key={k} size="xs" tone={k === "active" ? "success" : k === "error" ? "danger" : "warn"}>{v} {({ active: "indexados", indexing: "indexando", pending: "en cola", error: "con error" } as Record<string, string>)[k] ?? k}</Pill>)}</Group>
          </Group>
        </Section>)}
      </Stack></FillArea>
    </Page>
  );
}
