import { tr } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group } from "@mantine/core";
import { Btn, Check, ClearFilters, ConfirmDialog, ColHead, DataState, DataTable, EmptyState, Notice, Pill, ProgressBar, Segments, SliderField, useTableView, MutationError, ViewBar } from "../ui";
import { ScanDialog } from "./ScanDialog";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { TypeDialog } from "./TypePicker";

type Item = { id: number; name: string; current_type: string; suggested_type: string; confidence: number | null; status: string; previous_type: string; reason?: string };
type Ov = { hidden_below_threshold: number; ontology: boolean; decider: boolean; counts: Record<string, number>; progress: { running: boolean; done: number; total: number; error: string | null }; items: Item[] };

const RT_COLS = { name: { get: (i: Item) => i.name }, cur: { get: (i: Item) => i.current_type || tr("sin tipo"), exact: true }, sug: { get: (i: Item) => i.suggested_type, exact: true }, conf: { get: (i: Item) => i.confidence ?? -1 }, reason: { get: (i: Item) => i.reason ?? "" } };

export default function Retype({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isAdmin = ["admin", "owner"].includes(role);
  const [status, setStatus] = useState("pending");
  const [minConf, setMinConf] = useState(0.8);
  const [sel, setSel] = useState<number[]>([]);
  const [scanning, setScanning] = useState(false);
  const base = `brains/${graph}/retype`;
  const q = useQuery({ queryKey: ["retype", graph, status, minConf], enabled: isAdmin, refetchInterval: (c) => (c.state.data?.progress.running ? 3000 : false),
    queryFn: () => get<Ov>(base, { status, min_conf: status === "pending" ? minConf : 0 }) });
  const refresh = () => { setSel([]); qc.invalidateQueries({ queryKey: ["retype", graph] }); };
  const scan = useMutation({ mutationFn: (limit: number) => send("POST", `${base}/scan`, { limit }), onSuccess: refresh });
  const [done, setDone] = useState<string | null>(null);
  const [ask, setAsk] = useState<{ kind: "apply" | "reject"; ids: number[] } | null>(null);
  const apply = useMutation({ mutationFn: (ids: number[]) => send<{ applied: number }>("POST", `${base}/apply`, { ids }),
    onSuccess: (r, ids) => { refresh(); setDone(r.applied === ids.length ? t("{{n}} tipos aplicados. Puedes deshacerlos en la pestaña «Aplicados».", { n: r.applied }) : t("{{n}} de {{total}} aplicados; el resto no encajaba en la ontología actual. Puedes deshacerlos en «Aplicados».", { n: r.applied, total: ids.length })); } });
  const reject = useMutation({ mutationFn: (ids: number[]) => send("POST", `${base}/reject`, { ids }), onSuccess: (_r, ids) => { refresh(); setDone(t("{{n}} propuestas descartadas.", { n: ids.length })); } });
  const revert = useMutation({ mutationFn: (id: number) => send("POST", `${base}/${id}/revert`), onSuccess: refresh });
  const [as, setAs] = useState<Item | null>(null);
  const applyAs = useMutation({ mutationFn: (type: string) => send("POST", `${base}/${as?.id}/apply-as`, { type }),
    onSuccess: (_r, type) => { refresh(); setDone(t("«{{name}}» pasa a {{type}}. Puedes deshacerlo en la pestaña «Aplicados».", { name: as?.name, type })); setAs(null); } });
  const v = useTableView(q.data?.items ?? [], RT_COLS, { key: "conf", dir: "desc" });
  if (!isAdmin) return <EmptyState>{t("Solo los administradores del brain pueden corregir tipos.")}</EmptyState>;
  const d = q.data; const items = v.rows; const p = d?.progress;
  const allIds = items.map((i) => i.id);
  const chosen = sel.filter((id) => allIds.includes(id));  // una fila que un filtro ha ocultado no se aplica por sorpresa
  const summary = (ids: number[]) => Object.entries(items.filter((i) => ids.includes(i.id)).reduce<Record<string, number>>((m, i) => ({ ...m, [i.suggested_type]: (m[i.suggested_type] ?? 0) + 1 }), {})).sort((a, b) => b[1] - a[1]);
  const deciding = status === "pending" || status === "doubtful";
  const STATE_HELP: Record<string, string> = {
    none: t("El decisor no encuentra ningún tipo de la ontología que encaje con estas entidades. No hace falta tocarlas; si hay muchas de una misma clase, es señal de que falta un tipo en la ontología."),
    doubtful: t("Nombres que no parecen una entidad concreta (rutas, opciones, frases, versiones, descripciones de un problema). No tiene sentido darles un tipo; si quieres, descártalas de esta lista."),
  };
  return (
    <>
      <ViewBar title={t("Tipos dudosos")}
        help={<>{t("Graphiti no cambia el tipo de las entidades ya existentes, así que las clasificadas con tipos genéricos (Object, Organization, Location…) se quedan así. El decisor revisa cada una con la ontología del brain como opciones y propone un tipo; un administrador aprueba, y el cambio es reversible.")}
          {STATE_HELP[status] ? <>{" "}{STATE_HELP[status]}</> : null}</>}
        meta={status === "pending" && !!d?.hidden_below_threshold && <>{t("{{n}} más por debajo de ese umbral", { n: d.hidden_below_threshold })} <Btn kind="link" onClick={() => setMinConf(0.5)}>{t("Ver todas")}</Btn></>}
        actions={<>
          <Btn icon="search" disabled={!d?.ontology || !d?.decider || p?.running} onClick={() => { scan.reset(); setScanning(true); }}>{t("Analizar…")}</Btn>
          {deciding && <Btn kind="danger" disabled={!allIds.length} loading={reject.isPending} onClick={() => (chosen.length ? reject.mutate(chosen) : setAsk({ kind: "reject", ids: allIds }))}>
            {chosen.length ? (status === "doubtful" ? t("Descartar seleccionadas") : t("Rechazar seleccionadas")) : (status === "doubtful" ? t("Descartar todas las visibles ({{n}})", { n: allIds.length }) : t("Rechazar todas las visibles ({{n}})", { n: allIds.length }))}</Btn>}
          {status === "pending" && <Btn kind="primary" icon="check" disabled={!allIds.length} onClick={() => setAsk({ kind: "apply", ids: chosen.length ? chosen : allIds })}>
            {chosen.length ? t("Aplicar las seleccionadas ({{n}})", { n: chosen.length }) : t("Aplicar todas las visibles ({{n}})", { n: allIds.length })}</Btn>}
        </>}>
        <Segments label={t("Estado")} value={status} onChange={(x) => { setStatus(x); setSel([]); setDone(null); }}
          data={[["pending", t("Propuestos")], ["doubtful", t("Dudosas")], ["none", t("Sin tipo adecuado")], ["applied", t("Aplicados")], ["rejected", t("Rechazados")], ["same", t("Ya correctos")]].map(([value, label]) => ({ value, label, count: d?.counts[value] ?? 0 }))} />
        {status === "pending" && <SliderField label={t("Confianza mínima")} min={0.5} max={0.99} step={0.01} value={minConf} onChange={setMinConf} />}
        <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      </ViewBar>
      {d && !d.ontology && <Notice tone="warn">{t("Este brain no tiene ontología. Aplica un paquete en Vocabulario → Ontología.")}{" "}<Btn kind="link" component={Link} to="/vocabulario?tab=onto">{t("Ir a Ontología")}</Btn></Notice>}
      {d && !d.decider && <Notice tone="warn">{t("No hay decisor configurado (Administración → Proveedores IA → Decisores).")}</Notice>}
      {p?.running && <ProgressBar done={p.done} total={p.total} text={t("Analizando… {{done}} de {{total}}", { done: p.done, total: p.total })} />}
      {p?.error && !p.running && <Notice tone="warn" title={t("Último error del análisis")}>{p.error}</Notice>}
      {done && <Notice tone="success">{done}</Notice>}
      <MutationError error={apply.error ?? reject.error ?? revert.error} />
      {!d ? <DataState query={q} /> : items.length === 0
        ? <EmptyState>{status === "pending" ? t("Nada propuesto por encima de esa confianza. Baja el umbral o lanza un análisis.") : t("Sin elementos.")}</EmptyState>
        : <DataTable aria-label={t("Tipos dudosos")}>
        <DataTable.Thead><DataTable.Tr>{deciding && <DataTable.Th><Check aria-label={t("Seleccionar todo")} checked={!!allIds.length && chosen.length === allIds.length} onChange={(e) => setSel(e.currentTarget.checked ? allIds : [])} /></DataTable.Th>}
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Entidad")}</ColHead>
          <ColHead sort={v.sortProps("cur")} filter={v.select("cur")}>{t("Tipo actual")}</ColHead>
          {status === "doubtful" || status === "none" ? <ColHead filter={v.text("reason", t("Motivo…"))}>{t("Motivo")}</ColHead> : <><ColHead sort={v.sortProps("sug")} filter={v.select("sug")}>{t("Tipo propuesto")}</ColHead><ColHead sort={v.sortProps("conf")}>{t("Confianza")}</ColHead></>}
          {(status === "applied" || status === "pending") && <DataTable.ActionsHead />}</DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>
          {items.map((i) => (
            <DataTable.Tr key={i.id}>
              {deciding && <DataTable.Td><Check aria-label={t("Seleccionar {{name}}", { name: i.name })} checked={chosen.includes(i.id)} onChange={(e) => setSel(e.currentTarget.checked ? [...sel, i.id] : sel.filter((x) => x !== i.id))} /></DataTable.Td>}
              <DataTable.Td>{i.name}</DataTable.Td><DataTable.Td><Pill>{i.current_type || t("sin tipo")}</Pill></DataTable.Td>
              {status === "doubtful" || status === "none" ? <DataTable.Td>{i.reason || "—"}</DataTable.Td> : <><DataTable.Td><Pill tone="success">{i.suggested_type}</Pill></DataTable.Td><DataTable.Td><Pill tone={(i.confidence ?? 0) >= 0.9 ? "success" : "neutral"}>{i.confidence != null ? `${Math.round(i.confidence * 100)} %` : "—"}</Pill></DataTable.Td></>}
              {status === "pending" && <DataTable.Td><Btn size="row" icon="edit" onClick={() => { applyAs.reset(); setAs(i); }}>{t("Aplicar como…")}</Btn></DataTable.Td>}
              {status === "applied" && <DataTable.Td><Btn size="row" loading={revert.isPending && revert.variables === i.id} onClick={() => revert.mutate(i.id)} icon="undo">{t("Deshacer")}</Btn></DataTable.Td>}
            </DataTable.Tr>))}
        </DataTable.Tbody>
      </DataTable>}
      <ScanDialog opened={scanning} onClose={() => setScanning(false)} title={t("Analizar tipos")} initial={100} pending={scan.isPending} error={scan.error}
        cost={t("El decisor revisa cada entidad con la ontología del brain, empezando por las de tipo genérico. Una llamada por entidad, que cuenta en el consumo de IA del brain.")}
        onRun={(n) => scan.mutateAsync(n)} />
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} tone={ask?.kind === "apply" ? "primary" : "danger"}
        title={ask?.kind === "apply" ? t("Aplicar {{n}} cambios de tipo", { n: ask?.ids.length }) : t("Rechazar {{n}} propuestas", { n: ask?.ids.length })}
        action={ask?.kind === "apply" ? t("Aplicar") : t("Rechazar")}
        warning={ask?.kind === "apply" ? t("Se cambia el tipo de estas entidades en el grafo. Es reversible: cada cambio se puede deshacer en «Aplicados».") : t("Las propuestas se descartan y no se vuelven a ofrecer.")}
        onConfirm={() => (ask!.kind === "apply" ? apply.mutateAsync(ask!.ids) : reject.mutateAsync(ask!.ids))}>
        {ask && <Group gap={6}>{summary(ask.ids).map(([type, n]) => <Pill key={type} tone="success">{type} · {n}</Pill>)}</Group>}
      </ConfirmDialog>
      <TypeDialog graph={graph} opened={!!as} name={as?.name ?? ""} current={as?.current_type ? [as.current_type] : []} onClose={() => setAs(null)}
        onPick={(type) => applyAs.mutate(type)} pending={applyAs.isPending} error={applyAs.error} />
    </>
  );
}
