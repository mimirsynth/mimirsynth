import { locale } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, FilterBar, Segments, Modal, Notice, Pager, Pill, Tabs, TextArea, TextField, MutationError, ConfirmDialog, EmptyState, PageHeader, useTabParam, ListCard } from "../ui";
import { useDebouncedValue } from "@mantine/hooks";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Fact, fmt, get, send, TimelineEvent } from "../api";
import { FillArea, Page } from "../ui";

type Done = { op: number; summary: string };

/** Agrupa los eventos por día (ya vienen del más reciente al más antiguo). */
function groupByDay(evs: TimelineEvent[]): [string, TimelineEvent[]][] {
  const m = new Map<string, TimelineEvent[]>();
  for (const e of evs) {
    const raw = new Date(e.at).toLocaleDateString(locale(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    const d = raw.charAt(0).toUpperCase() + raw.slice(1);
    m.set(d, [...(m.get(d) ?? []), e]);
  }
  return [...m.entries()];
}

export default function Facts({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const canEdit = ["curator", "admin", "owner"].includes(role);
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Fact | null>(null);
  const [text, setText] = useState("");
  const [rel, setRel] = useState("");
  const [del, setDel] = useState<Fact | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const after = (r: Done) => { setDone(r); setEdit(null); setDel(null); qc.invalidateQueries({ queryKey: ["facts", graph] }); qc.invalidateQueries({ queryKey: ["timeline", graph] }); qc.invalidateQueries({ queryKey: ["vocab-types", graph] }); };
  const save = useMutation({ mutationFn: () => send<Done>("PATCH", `facts/${edit?.uuid}`, { fact: text, name: rel }, { graph }), onSuccess: after });
  const inval = useMutation({ mutationFn: (f: Fact) => send<Done>("POST", `facts/${f.uuid}/${f.status === "invalidated" ? "reactivate" : "invalidate"}`, undefined, { graph }), onSuccess: after });
  const remove = useMutation({ mutationFn: () => send<Done>("DELETE", `facts/${del?.uuid}`, undefined, { graph }), onSuccess: after });
  const undo = useMutation({ mutationFn: (id: number) => send("POST", `vocab/ops/${id}/revert`, undefined, { graph }), onSuccess: () => { setDone(null); qc.invalidateQueries({ queryKey: ["facts", graph] }); qc.invalidateQueries({ queryKey: ["vocab-types", graph] }); } });
  const open = (f: Fact) => { save.reset(); setText(f.fact); setRel(f.name); setEdit(f); };
  const [f, setF] = useState({ q: "", status: "all", rel: "", since: "", until: "", order: "desc" });
  const [dq] = useDebouncedValue(f.q, 300);
  const [page, setPage] = useState({ offset: 0, limit: 50 });
  const setFilter = (p: Partial<typeof f>) => { setF((x) => ({ ...x, ...p })); setPage((x) => ({ ...x, offset: 0 })); };
  const [view, setView] = useTabParam("lista", "vista");
  const rels = useQuery({ queryKey: ["fact-relations", graph], staleTime: 60_000, queryFn: () => get<{ name: string; count: number }[]>("facts/relations", { graph }) });
  const { data } = useQuery({ queryKey: ["facts", graph, dq, f.status, f.rel, f.since, f.until, f.order, page.offset, page.limit], enabled: view === "lista", placeholderData: keepPreviousData,
    queryFn: () => get<{ total: number; counts: Record<string, number>; items: Fact[] }>("facts", { graph, q: dq, status: f.status, rel: f.rel, since: f.since, until: f.until, order: f.order, limit: page.limit, offset: page.offset }) });
  const events = useQuery({ queryKey: ["timeline", graph, dq, f.rel, f.since, f.until], enabled: view === "linea", placeholderData: keepPreviousData,
    queryFn: () => get<TimelineEvent[]>("timeline", { graph, entity: dq, rel: f.rel, since: f.since, until: f.until, limit: 300 }) });
  const filtered = !!(f.q || f.rel || f.since || f.until || (view === "lista" && f.status !== "all"));
  const card = (f: Fact) => (
        <ListCard key={f.uuid} invalid={f.status === "invalidated"}
          tags={<><Link to={`/entidad/${f.source_uuid}`} className="ms-nolink"><Pill size="xs">{f.source}</Pill></Link><Text size="xs" className="ms-data">{f.name}</Text>
            <Link to={`/entidad/${f.target_uuid}`} className="ms-nolink"><Pill size="xs">{f.target}</Pill></Link></>}
          meta={<>{t("vigente desde")} {fmt(f.valid_at)}{f.invalid_at && <span className="ms-invalid-date"> {t("· invalidado")} {fmt(f.invalid_at)}</span>}<span> {t("· registrado el")} {fmt(f.created_at)}</span></>}
          actions={canEdit && <>
            <Btn size="row" icon="edit" onClick={() => open(f)}>{t("Editar")}</Btn>
            <Btn size="row" icon={f.status === "invalidated" ? "undo" : "close"} loading={inval.isPending && inval.variables?.uuid === f.uuid} onClick={() => inval.mutate(f)}>{f.status === "invalidated" ? t("Reactivar") : t("Invalidar")}</Btn>
            <Btn kind="danger" size="row" icon="trash" onClick={() => setDel(f)}>{t("Borrar")}</Btn></>}>
          {f.fact}
        </ListCard>
  );
  return (
    <Page>
      <PageHeader title={t("Hechos")} description={<>{t("El conocimiento ya destilado: afirmaciones concretas entre dos entidades (p. ej. «El servicio de correo corre en el servidor 2») con la fecha desde la que son ciertas y, si dejan de serlo, cuándo. Salen de los episodios del Diario. La «Línea temporal» ordena los mismos hechos por cuándo se aprendieron o se invalidaron.")}</>} />
      <Tabs value={view} onChange={setView}>
        <Tabs.List><Tabs.Tab value="lista">{t("Lista")}</Tabs.Tab><Tabs.Tab value="linea">{t("Línea temporal")}</Tabs.Tab></Tabs.List><Tabs.Panel value="lista" keepMounted>{null}</Tabs.Panel><Tabs.Panel value="linea" keepMounted>{null}</Tabs.Panel>
      </Tabs>
      <FilterBar search={{ value: f.q, onChange: (v) => setFilter({ q: v }), placeholder: t("Texto del hecho o nombre de una entidad…") }} active={filtered}
        onClear={() => { setF({ q: "", status: "all", rel: "", since: "", until: "", order: f.order }); setPage((p) => ({ ...p, offset: 0 })); }}
        filters={[
          { kind: "select" as const, label: t("Relación"), value: f.rel, onChange: (v: string) => setFilter({ rel: v }), allLabel: t("Todas"), width: 220, options: (rels.data ?? []).map((r) => ({ value: r.name, label: r.name, count: r.count })) },
          { kind: "date" as const, label: t("Desde"), value: f.since, onChange: (v: string) => setFilter({ since: v }) },
          { kind: "date" as const, label: t("Hasta"), value: f.until, onChange: (v: string) => setFilter({ until: v }) },
          ...(view === "lista" ? [{ kind: "select" as const, label: t("Orden"), value: f.order, onChange: (v: string) => setFilter({ order: v || "desc" }), clearable: false, options: [{ value: "desc", label: t("Más recientes") }, { value: "asc", label: t("Más antiguos") }] }] : []),
        ]} />
      {view === "lista" && <Segments label={t("Estado")} value={f.status} onChange={(v) => setFilter({ status: v })}
        data={[{ value: "all", label: t("Todos"), count: (data?.counts.current ?? 0) + (data?.counts.invalidated ?? 0) }, { value: "current", label: t("Vigentes"), count: data?.counts.current ?? 0 }, { value: "invalidated", label: t("Invalidados"), count: data?.counts.invalidated ?? 0 }]} />}
      {done && <Notice tone="info">{done.summary}. <Btn kind="link" onClick={() => undo.mutate(done.op)}>{t("Deshacer")}</Btn>{undo.error && ` — ${(undo.error as Error).message}`}</Notice>}
      <FillArea>
        {view === "lista" ? <Stack gap="xs">{(data?.items ?? []).map((x) => card(x))}{data && data.items.length === 0 && <Text c="dimmed">{filtered ? t("Ningún hecho coincide con los filtros.") : t("Aún no hay hechos.")}</Text>}</Stack> : (
          <div className="ms-tl">
            {events.isLoading && <EmptyState>{t("Cargando…")}</EmptyState>}
            {(events.data ?? []).length === 0 && !events.isLoading && <EmptyState>{t("Sin eventos.")}</EmptyState>}
            {groupByDay(events.data ?? []).map(([day, evs]) => (
              <div key={day} className="ms-tl-day">
                <Text className="ms-tl-date" size="xs" fw={600}>{day}</Text>
                {evs.map((e) => (
                  <div key={e.uuid + e.event} className="ms-tl-item" data-event={e.event}>
                    <Group gap={6} mb={4}><Pill size="xs" tone={e.event === "invalidated" ? "warn" : "success"}>{e.event === "invalidated" ? t("dejó de ser cierto") : "aprendido"}</Pill><Text size="xs" c="dimmed" className="ms-data">{new Date(e.at).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" })}</Text></Group>
                    {card(e)}
                  </div>))}
              </div>))}
          </div>)}
      </FillArea>
      {view === "lista" && <Pager total={data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} sizes={[25, 50, 100, 200]} />}
      {view === "linea" && (events.data?.length ?? 0) >= 300 && <Text size="xs" c="dimmed">{t("Se muestran los 300 hechos más recientes de los filtros; acota las fechas para ver más atrás.")}</Text>}

      <Modal opened={!!edit} onClose={() => setEdit(null)} title={t("Editar hecho")} centered size="lg">
        <Stack>
          <Text size="xs" c="dimmed">{edit?.source} → {edit?.target}</Text>
          <TextArea label={t("Texto del hecho")} description={t("Al guardar se recalcula su embedding")} minRows={3} autosize value={text} onChange={(e) => setText(e.currentTarget.value)} />
          <TextField label={t("Tipo de relación")} description={t("Se normaliza a MAYÚSCULAS_CON_GUIONES")} value={rel} onChange={(e) => setRel(e.currentTarget.value)} />
          <MutationError error={save.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setEdit(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" disabled={text.trim().length < 3 || (text.trim() === edit?.fact && rel.trim() === edit?.name)} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn></Group>
        </Stack>
      </Modal>
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar hecho")} action={t("Borrar hecho")} subject={<i>{del?.fact}</i>}
        warning={t("Se elimina el hecho del grafo y de la lista de hechos de sus episodios. Si solo ya no es cierto, usa «Invalidar», que conserva el historial. Podrás deshacerlo justo después.")}
        onConfirm={() => remove.mutateAsync()} />
    </Page>
  );
}
