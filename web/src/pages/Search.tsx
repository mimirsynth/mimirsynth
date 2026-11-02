import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { fmt, send } from "../api";
import { Btn, EmptyState, FillArea, ListCard, MutationError, Page, PageHeader, Panel, Pill, SearchBar } from "../ui";
import { ROLE } from "./TokensPanel";

type Fact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; name: string; source: string; target: string; source_uuid: string; target_uuid: string };
type Chunk = { id: number; episode_uuid?: string; name: string; text: string; valid_at: string | null };
type Passage = { document_id: number; chunk_idx: number; title: string; text: string };
type BrainHits = { slug: string; name: string; role: string; state: "ok" | "timeout" | "error"; facts: Fact[]; chunks: Chunk[]; documents: Passage[] };
type Res = { query: string; brains: BrainHits[]; ms: number };

/** A page of a brain, opened on that brain: the app switches to it from `?brain=` (the link of the email summary does the same). */
const inBrain = (path: string, slug: string) => `${path}${path.includes("?") ? "&" : "?"}brain=${slug}`;

/** One search over every brain the person can read (issue 129), with the results grouped by brain. Each result opens in its brain. */
export default function Search() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const run = useMutation({ mutationFn: (query: string) => send<Res>("POST", "search", { query }) });
  const go = (query: string) => { if (!query.trim()) return; setParams({ q: query }, { replace: true }); run.mutate(query); };
  useEffect(() => { if (params.get("q")) run.mutate(params.get("q")!); }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const r = run.data;
  const found = (r?.brains ?? []).filter((b) => b.facts.length || b.chunks.length || b.documents.length);
  const quiet = (r?.brains ?? []).filter((b) => b.state === "ok" && !b.facts.length && !b.chunks.length && !b.documents.length);
  const failed = (r?.brains ?? []).filter((b) => b.state !== "ok");
  return (
    <Page>
      <PageHeader title={t("Buscar en todos mis brains")} description={t("La misma búsqueda que Preguntar, a la vez en todos los brains que puedes leer, con los resultados agrupados por brain. No usa la federación: cada brain con tu propio rol.")} />
      <FillArea><Stack gap="sm">
        <SearchBar mode="submit" value={q} onChange={setQ} placeholder={t("¿Dónde está Nextcloud ahora?")} onSubmit={go} loading={run.isPending}
          submitted={!!run.data} onClear={() => { setQ(""); run.reset(); setParams({}, { replace: true }); }} />
        <MutationError error={run.error} />
        {r && <Text size="xs" c="dimmed">{t("{{n}} brains consultados · {{ms}} ms", { n: r.brains.length, ms: r.ms })}</Text>}
        {failed.length > 0 && <Group gap={6}>{failed.map((b) => <Pill key={b.slug} size="xs" tone={b.state === "timeout" ? "warn" : "danger"}>
          {b.name} · {b.state === "timeout" ? t("no respondió a tiempo") : t("falló")}</Pill>)}</Group>}
        {r && !found.length && <EmptyState>{t("Nada encontrado en tus brains.")}</EmptyState>}
        {found.map((b) => (
          <Panel key={b.slug} className="ms-card">
            <Group justify="space-between" mb="xs">
              <Group gap="xs"><Title order={5}>{b.name}</Title><Pill size="xs">{t(ROLE[b.role] ?? b.role)}</Pill></Group>
              <Btn size="row" kind="link" component={Link} to={inBrain(`/preguntar?q=${encodeURIComponent(r!.query)}`, b.slug)}>{t("Abrir en Preguntar")}</Btn>
            </Group>
            <Stack gap="xs">
              {b.facts.map((f) => (
                <ListCard key={f.uuid} invalid={f.status === "invalidated"}
                  tags={<><Link to={inBrain(`/entidad/${f.source_uuid}`, b.slug)} className="ms-nolink"><Pill size="xs">{f.source}</Pill></Link>
                    <Text size="xs" className="ms-data">{f.name}</Text><Link to={inBrain(`/entidad/${f.target_uuid}`, b.slug)} className="ms-nolink"><Pill size="xs">{f.target}</Pill></Link></>}
                  meta={<>{fmt(f.valid_at)}{f.invalid_at ? ` → ${fmt(f.invalid_at)}` : ""}</>}>{f.fact}</ListCard>))}
              {b.chunks.map((c) => (
                <ListCard key={`c-${c.id}`} title={c.episode_uuid ? <Link to={inBrain(`/diario?episodio=${c.episode_uuid}`, b.slug)}>{c.name}</Link> : c.name}
                  aside={fmt(c.valid_at)}>{c.text}</ListCard>))}
              {b.documents.map((p) => (
                <ListCard key={`d-${p.document_id}-${p.chunk_idx}`} title={<Link to={inBrain(`/conocimiento?doc=${p.document_id}`, b.slug)}>{p.title}</Link>}>{p.text}</ListCard>))}
            </Stack>
          </Panel>))}
        {quiet.length > 0 && <Text size="xs" c="dimmed">{t("Sin resultados en: {{names}}", { names: quiet.map((b) => b.name).join(", ") })}</Text>}
      </Stack></FillArea>
    </Page>
  );
}
