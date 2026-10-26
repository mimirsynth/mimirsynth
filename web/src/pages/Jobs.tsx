import { tr, T, locale } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, ColHead, DataTable, FillArea, Notice, Page, Pager, Pill, ProgressBar, SidePanel, type SortDir, type Tone, MutationError, EmptyState, PageHeader, Segments, ClearFilters, SelectField, useServerTableView, CodeBlock } from "../ui";

type Job = {
  id: number; kind: string; label: string; title: string; status: string; done: number; total: number; message: string; error: string; attempts: number;
  retry_of: number | null; user: string; created_at: string; started_at: string | null; finished_at: string | null;
  params?: Record<string, unknown>; log?: { t: string; msg: string }[]; result?: Record<string, unknown> | null;
};
type List = { total: number; counts: Record<string, number>; kinds: { kind: string; label: string }[]; items: Job[] };

const TONE: Record<string, Tone> = { queued: "neutral", running: "warn", done: "success", failed: "danger", cancelled: "neutral" };
const LABEL: Record<string, string> = { queued: T("en cola"), running: T("en marcha"), done: "terminado", failed: "fallido", cancelled: "cancelado" };
const RESULT: Record<string, string> = { added: "nuevos", changed: "cambiados", unchanged: T("sin cambios"), removed: "eliminados", indexed: "indexados", errors: "errores", chunks: "trozos", analyzed: "analizadas" };

function took(a: string | null, b: string | null) {
  if (!a) return "—";
  const s = Math.max(0, Math.round(((b ? new Date(b) : new Date()).getTime() - new Date(a).getTime()) / 1000));
  return s < 60 ? `${s} s` : s < 3600 ? tr("{{v}} min {{v1}} s", { v: Math.floor(s / 60), v1: s % 60 }) : tr("{{v}} h {{v1}} min", { v: Math.floor(s / 3600), v1: Math.floor((s % 3600) / 60) });
}

/** Ejecuciones seguidas e idénticas (mismo trabajo, terminado, lanzado por el sistema: los reescaneos programados) se pliegan en una sola fila.
 *  Los fallidos, los reintentos y lo lanzado por una persona nunca se agrupan: son lo que importa ver. */
type Row = { job: Job; rest: Job[] };
function groupRuns(items: Job[]): Row[] {
  const out: Row[] = [];
  for (const j of items) {
    const last = out[out.length - 1];
    const foldable = (x: Job) => x.status === "done" && !x.user && !x.retry_of;
    if (last && foldable(j) && foldable(last.job) && last.job.kind === j.kind && last.job.title === j.title) last.rest.push(j);
    else out.push({ job: j, rest: [] });
  }
  return out;
}

export default function Jobs({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const canAct = ["curator", "admin", "owner"].includes(role);
  const qc = useQueryClient();
  const { f, sent, setFilter, sortProps, sort, page, setPage, active, clear } = useServerTableView({ q: "", status: "", kind: "" }, { debounced: ["q"] });
  const order: SortDir = sort?.dir ?? "desc";
  const [open, setOpen] = useState<number | null>(null);
  const [unfolded, setUnfolded] = useState<Set<number>>(new Set());
  const toggle = (id: number) => setUnfolded((s) => { const n = new Set(s); if (!n.delete(id)) n.add(id); return n; });

  const list = useQuery({ queryKey: ["jobs", graph, sent.status, sent.kind, sent.q, order, page.offset, page.limit], placeholderData: keepPreviousData, queryFn: () => get<List>("jobs", { graph, status: sent.status, kind: sent.kind, q: sent.q, order, limit: page.limit, offset: page.offset }),
    refetchInterval: (q) => (q.state.data?.items.some((j) => j.status === "queued" || j.status === "running") ? 2000 : 10000) });
  const detail = useQuery({ queryKey: ["job", graph, open], enabled: open !== null, queryFn: () => get<Job>(`jobs/${open}`, { graph }),
    refetchInterval: (q) => (q.state.data && (q.state.data.status === "queued" || q.state.data.status === "running") ? 2000 : false) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["jobs", graph] }); qc.invalidateQueries({ queryKey: ["job", graph] }); qc.invalidateQueries({ queryKey: ["jobs-summary", graph] }); };
  const cancel = useMutation({ mutationFn: (id: number) => send("POST", `jobs/${id}/cancel`, undefined, { graph }), onSuccess: refresh });
  const retry = useMutation({ mutationFn: (id: number) => send<{ id: number }>("POST", `jobs/${id}/retry`, undefined, { graph }), onSuccess: (r) => { refresh(); setOpen(r.id); } });

  const c = list.data?.counts ?? {};
  const d = detail.data;
  return (
    <Page>
      <PageHeader title={t("Trabajos")} description={<>{t("Todo lo que la aplicación hace en segundo plano en este brain: ingestas, indexación de documentos, reescaneo de carpetas y análisis. Con su progreso, su resultado y la opción de reintentar.")}</>} />
      <Segments label={t("Estado")} value={f.status || "all"} onChange={(v) => setFilter({ status: v === "all" ? "" : v })}
        data={[{ value: "all", label: t("Todos"), count: Object.values(c).reduce((a, b) => a + b, 0) }, ...Object.entries(LABEL).map(([k, v]) => ({ value: k, label: v[0].toUpperCase() + v.slice(1), count: c[k] ?? 0 }))]} />
      <ClearFilters active={active} onClear={clear} />
      <MutationError error={list.error} />
      <FillArea>
        <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr>
            <ColHead>{t("Estado")}</ColHead>
            <ColHead filter={{ kind: "text", value: f.q, onChange: (v) => setFilter({ q: v }), placeholder: t("Título del trabajo…"),
              extra: (list.data?.kinds.length ?? 0) > 0 ? <SelectField size="xs" mt={8} label={t("Tipo")} placeholder={t("Todos los tipos")} clearable value={f.kind || null} onChange={(v) => setFilter({ kind: v ?? "" })} data={list.data!.kinds.map((k) => ({ value: k.kind, label: k.label }))} /> : undefined }}>{t("Trabajo")}</ColHead>
            <ColHead width={220}>{t("Progreso")}</ColHead>
            <ColHead sort={sortProps("start")}>{t("Inicio")}</ColHead>
            <ColHead>{t("Duración")}</ColHead>
            <ColHead>{t("Lanzado por")}</ColHead>
            <DataTable.ActionsHead />
          </DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{groupRuns(list.data?.items ?? []).flatMap(({ job: j, rest }) => {
            const row = (x: Job, child = false) => (
              <DataTable.Tr key={x.id} className={child ? "ms-subrow" : undefined}>
                <DataTable.Td><Pill size="xs" tone={TONE[x.status] ?? "neutral"} title={x.error || undefined}>{t(LABEL[x.status] ?? x.status)}</Pill>{x.attempts > 1 && <Text span size="xs" c="dimmed"> · {x.attempts} {t("intentos")}</Text>}</DataTable.Td>
                <DataTable.Td><Text size="sm" fw={500}>{x.title}</Text><Text size="xs" c="dimmed">{x.label}{x.retry_of ? t(" · reintento de #{{retry_of}}", { retry_of: x.retry_of }) : ""}</Text></DataTable.Td>
                <DataTable.Td>{x.status === "running"
                  ? <ProgressBar done={x.done} total={x.total} text={x.total ? `${x.done}/${x.total} · ${x.message}` : x.message || "…"} />
                  : x.status === "failed" ? <Text size="xs" className="ms-text-danger" lineClamp={2}>{x.error}</Text>
                  : x.total ? <Text size="xs" c="dimmed">{x.done}/{x.total}</Text> : <Text size="xs" c="dimmed">{x.status === "queued" ? t("esperando turno") : "—"}</Text>}</DataTable.Td>
                <DataTable.Td>{fmt(x.started_at ?? x.created_at)}</DataTable.Td>
                <DataTable.Td>{x.started_at ? took(x.started_at, x.finished_at) : "—"}</DataTable.Td>
                <DataTable.Td>{x.user || "sistema"}</DataTable.Td>
                <DataTable.Td><Btn size="row" onClick={() => setOpen(x.id)}>{t("Ver")}</Btn></DataTable.Td>
              </DataTable.Tr>);
            if (!rest.length) return [row(j)];
            const all = [j, ...rest], isOpen = unfolded.has(j.id);
            const group = (
              <DataTable.Tr key={`g${j.id}`}>
                <DataTable.Td><Pill size="xs" tone="success">{t("terminado")}</Pill></DataTable.Td>
                <DataTable.Td><Text size="sm" fw={500}>{j.title}</Text><Text size="xs" c="dimmed">{j.label} · {all.length} {t("ejecuciones seguidas sin incidencias")}</Text></DataTable.Td>
                <DataTable.Td><Text size="xs" c="dimmed">{all.length} {t("de")} {all.length} {t("correctas")}</Text></DataTable.Td>
                <DataTable.Td>{fmt(j.started_at ?? j.created_at)}<Text size="xs" c="dimmed">a {fmt(all[all.length - 1].started_at ?? all[all.length - 1].created_at)}</Text></DataTable.Td>
                <DataTable.Td>—</DataTable.Td>
                <DataTable.Td>{t("sistema")}</DataTable.Td>
                <DataTable.Td><Btn size="row" onClick={() => toggle(j.id)} aria-expanded={isOpen}>{isOpen ? t("Ocultar") : t("Mostrar {{length}}", { length: all.length })}</Btn></DataTable.Td>
              </DataTable.Tr>);
            return isOpen ? [group, ...all.map((x) => row(x, true))] : [group];
          })}</DataTable.Tbody>
        </DataTable>
        {list.data?.items.length === 0 && <EmptyState>{t("No hay trabajos")} {active ? t("con ese filtro.") : t("todavía. Aparecerán aquí al ingerir propuestas, subir documentos o escanear carpetas.")}</EmptyState>}
      </FillArea>
      <Pager total={list.data?.total ?? 0} offset={page.offset} limit={page.limit} onChange={setPage} />

      <SidePanel opened={open !== null} onClose={() => setOpen(null)} title={d ? `${d.label} #${d.id}` : t("Trabajo")}>
        {d && (
          <Stack>
            <Text fw={500}>{d.title}</Text>
            <Group gap={6}><Pill size="xs" tone={TONE[d.status] ?? "neutral"}>{t(LABEL[d.status] ?? d.status)}</Pill>{d.attempts > 1 && <Pill size="xs">{d.attempts} {t("intentos")}</Pill>}{d.retry_of && <Pill size="xs">{t("reintento de #")}{d.retry_of}</Pill>}</Group>
            <Text size="xs" c="dimmed">{t("Creado")} {fmt(d.created_at)} {t("· inicio")} {fmt(d.started_at)} {t("· fin")} {fmt(d.finished_at)} {t("· duración")} {took(d.started_at, d.finished_at)} · {d.user || "sistema"}</Text>
            {d.status === "running" && <ProgressBar done={d.done} total={d.total} text={d.total ? `${d.done}/${d.total} · ${d.message}` : d.message || "…"} />}
            {d.error && <Notice tone={d.status === "cancelled" ? "warn" : "danger"}>{d.error}</Notice>}
            {d.result && <Group gap={6}>{Object.entries(d.result).map(([k, v]) => <Pill key={k} size="xs" tone={k === "errors" && Number(v) > 0 ? "danger" : "neutral"}>{`${v} ${t(RESULT[k] ?? k)}`}</Pill>)}</Group>}
            {canAct && (
              <Group gap={6}>
                {(d.status === "queued" || d.status === "running") && <Btn kind="danger" size="row" icon="close" loading={cancel.isPending} onClick={() => cancel.mutate(d.id)}>{t("Cancelar")}</Btn>}
                {(d.status === "failed" || d.status === "cancelled") && <Btn size="row" icon="refresh" loading={retry.isPending} onClick={() => retry.mutate(d.id)}>{t("Reintentar")}</Btn>}
              </Group>)}
            {(cancel.error || retry.error) && <Notice tone="danger">{((cancel.error || retry.error) as Error).message}</Notice>}
            <Title order={5}>{t("Registro")}</Title>
            {d.log && d.log.length > 0
              ? <Stack gap={2}>{d.log.map((l, i) => <Text key={i} size="xs" className="ms-data"><Text span c="dimmed">{new Date(l.t).toLocaleTimeString(locale())} </Text>{l.msg}</Text>)}</Stack>
              : <Text size="xs" c="dimmed">{t("Sin líneas de registro.")}</Text>}
            <Title order={5}>{t("Parámetros")}</Title>
            <CodeBlock>{JSON.stringify(d.params ?? {}, null, 2)}</CodeBlock>
          </Stack>)}
      </SidePanel>
    </Page>
  );
}
