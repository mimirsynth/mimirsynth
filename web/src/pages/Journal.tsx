import { locale } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { FillArea, FilterBar, Page, Pager, Panel, Pill, SidePanel, PageHeader, ListCard } from "../ui";
import { useDebouncedValue } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Episode, fmt, get } from "../api";

const day = (iso: string) => { const d = new Date(iso).toLocaleDateString(locale(), { weekday: "long", day: "numeric", month: "long", year: "numeric" }); return d.charAt(0).toUpperCase() + d.slice(1); };

/** Los episodios, del más reciente al más antiguo, con un encabezado por día. */
function groupByDay(items: Episode[]): [string, Episode[]][] {
  const m = new Map<string, Episode[]>();
  for (const e of items) { const d = day(e.created_at); m.set(d, [...(m.get(d) ?? []), e]); }
  return [...m.entries()];
}

export default function Journal({ graph }: { graph: string }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ q: "", source: "", since: "", until: "", order: "desc" });
  const [dq] = useDebouncedValue(f.q, 300);
  const [page, setPage] = useState({ offset: 0, limit: 50 });
  const [params] = useSearchParams();
  const [open, setOpen] = useState<string | null>(() => params.get("episodio"));  // a link from an entity page opens that episode
  const setFilter = (p: Partial<typeof f>) => { setF((x) => ({ ...x, ...p })); setPage((x) => ({ ...x, offset: 0 })); };
  const sources = useQuery({ queryKey: ["episode-sources", graph], staleTime: 60_000, queryFn: () => get<{ source: string; count: number }[]>("episodes/sources", { graph }) });
  const list = useQuery({ queryKey: ["episodes", graph, dq, f.source, f.since, f.until, f.order, page.offset, page.limit], placeholderData: keepPreviousData,
    queryFn: () => get<{ total: number; items: Episode[] }>("episodes", { graph, q: dq, source: f.source, since: f.since, until: f.until, order: f.order, limit: page.limit, offset: page.offset }) });
  const detail = useQuery({ queryKey: ["episode", graph, open], enabled: !!open, queryFn: () => get<Episode>(`episodes/${open}`, { graph }) });
  const filtered = !!(f.q || f.source || f.since || f.until);
  const items = list.data?.items ?? [];
  return (
    <Page>
      <PageHeader title={t("Diario")} description={<>{t("Lo que se le ha contado al brain, tal cual y por orden de llegada: cada propuesta aprobada, nota o mensaje es un episodio. De cada episodio se extraen después los")} <b>{t("hechos")}</b> {t("(la pestaña Hechos), que son el conocimiento ya destilado.")}</>} />
      <FilterBar search={{ value: f.q, onChange: (v) => setFilter({ q: v }), placeholder: t("Texto o título del episodio…") }} active={filtered}
        onClear={() => { setF({ q: "", source: "", since: "", until: "", order: f.order }); setPage((p) => ({ ...p, offset: 0 })); }}
        filters={[
          { kind: "select", label: t("Tipo"), value: f.source, onChange: (v) => setFilter({ source: v }), allLabel: t("Todos"), options: (sources.data ?? []).map((s) => ({ value: s.source, label: s.source, count: s.count })) },
          { kind: "date", label: t("Desde"), value: f.since, onChange: (v) => setFilter({ since: v }) },
          { kind: "date", label: t("Hasta"), value: f.until, onChange: (v) => setFilter({ until: v }) },
          { kind: "select", label: t("Orden"), value: f.order, onChange: (v) => setFilter({ order: v || "desc" }), clearable: false, options: [{ value: "desc", label: t("Más recientes") }, { value: "asc", label: t("Más antiguos") }] },
        ]} />
      <FillArea><Stack gap="xs">
        {groupByDay(items).map(([d, eps]) => (
          <Stack key={d} gap="xs">
            <Text className="ms-tl-date" size="xs" fw={600}>{d}</Text>
            {eps.map((e) => (
              <ListCard key={e.uuid} title={e.name} aside={new Date(e.created_at).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })} onOpen={() => setOpen(e.uuid)}
                tags={<><Pill size="xs">{e.source}</Pill><Pill size="xs">{String(e.facts)} {t("hechos")}</Pill></>}>
                <Text size="sm" c="dimmed" lineClamp={2}>{e.snippet}</Text>
              </ListCard>))}
          </Stack>))}
        {list.data && items.length === 0 && <Text c="dimmed">{filtered ? t("Ningún episodio coincide con los filtros.") : t("Aún no hay episodios.")}</Text>}
      </Stack></FillArea>
      <Pager total={list.data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} />
      <SidePanel opened={!!open} onClose={() => setOpen(null)} title={detail.data?.name}>
        {detail.data && (
          <Stack>
            <Text size="xs" c="dimmed">{fmt(detail.data.created_at)}</Text>
            <Text className="ms-prose">{detail.data.content}</Text>
            <Title order={5}>{t("Hechos extraídos")}</Title>
            {(detail.data.facts as any[]).map((x) => (
              <Text key={x.uuid} size="sm" td={x.status === "invalidated" ? "line-through" : undefined} c={x.status === "invalidated" ? "dimmed" : undefined}>
                • {x.fact}
              </Text>
            ))}
          </Stack>
        )}
      </SidePanel>
    </Page>
  );
}
