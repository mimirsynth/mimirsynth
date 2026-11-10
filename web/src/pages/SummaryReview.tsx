import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { get, send } from "../api";
import { T } from "../i18n";
import { Btn, Check, Compare, ConfirmDialog, DataState, EmptyState, ListCard, MutationError, Notice, NumberField, Pill, ProgressBar, Segments, SelectField, TextArea, ViewBar } from "../ui";
import { ScanDialog } from "./ScanDialog";

type Item = { id: number; entity_uuid: string; name: string; facts: number; reason: string; current: string; proposed: string; applied: string;
  status: string; edited: boolean; flagged: boolean; secrets: { rule: string; label: string; action: string }[]; op: number | null; op_size: number };
type Ov = { engine: boolean; counts: Record<string, number>; progress: { running: boolean; done: number; total: number; error: string | null }; items: Item[] };
type Applied = { applied: number; outdated?: number; skipped?: number; op: number | null };

/** Why a summary was picked, in a few words. */
const REASON: Record<string, string> = {
  long: T("más de 1.000 caracteres"), lines: T("varias líneas"), repeats: T("repite sus hechos"), stale: T("muchos hechos nuevos desde que se aprobó"),
  requested: T("pedido desde su página"),
};
const STATUSES: [string, string][] = [["pending", T("Propuestos")], ["applied", T("Aprobados")], ["rejected", T("Rechazados")],
  ["outdated", T("Retirados")], ["same", T("Sin cambios")], ["reverted", T("Deshechos")]];

/** Summary review (issue 201): the engine proposes a better summary for the entities whose summary is a list of facts; a curator edits it if
 *  needed and approves it, which replaces the entity's summary. Every approval can be undone. */
export default function SummaryReview({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const isAdmin = ["admin", "owner"].includes(role);
  const base = `brains/${graph}/summaries`;
  const [status, setStatus] = useState("pending");
  const [scanning, setScanning] = useState(false);
  const [minFacts, setMinFacts] = useState<number | string>(0);
  const [reason, setReason] = useState<string | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [texts, setTexts] = useState<Record<number, string>>({});
  const [done, setDone] = useState<{ text: string; op: number | null } | null>(null);
  const [ask, setAsk] = useState<number[] | null>(null);
  const q = useQuery({ queryKey: ["summaries", graph, status], refetchInterval: (c) => (c.state.data?.progress.running ? 3000 : false), queryFn: () => get<Ov>(base, { status }) });
  const refresh = () => { setSel([]); qc.invalidateQueries({ queryKey: ["summaries", graph] }); };
  const scan = useMutation({ mutationFn: (limit: number) => send("POST", `${base}/scan`, { limit }), onSuccess: refresh });
  const said = (r: Applied) => [t("{{n}} resúmenes aprobados.", { n: r.applied }),
    r.outdated ? t("{{n}} se han retirado porque el resumen de la entidad cambió desde la propuesta.", { n: r.outdated }) : "",
    r.skipped ? t("{{n}} con posibles secretos se quedan para revisarlos uno a uno.", { n: r.skipped }) : ""].filter(Boolean).join(" ");
  const one = useMutation({ mutationFn: (i: Item) => send<Applied>("POST", `${base}/${i.id}/approve`, { text: texts[i.id] ?? null }),
    onSuccess: (r, i) => { refresh(); setDone({ text: t("Resumen de «{{name}}» aprobado.", { name: i.name }), op: r.op }); } });
  const all = useMutation({ mutationFn: (ids: number[]) => send<Applied>("POST", `${base}/approve`, { ids }), onSuccess: (r) => { refresh(); setDone({ text: said(r), op: r.op }); } });
  const reject = useMutation({ mutationFn: (ids: number[]) => send<{ rejected: number }>("POST", `${base}/reject`, { ids }),
    onSuccess: (r) => { refresh(); setDone({ text: t("{{n}} propuestas rechazadas.", { n: r.rejected }), op: null }); } });
  const undo = useMutation({ mutationFn: (op: number) => send("POST", `brains/${graph}/vocab/ops/${op}/revert`),
    onSuccess: () => { refresh(); qc.invalidateQueries({ queryKey: ["vocab-types", graph] }); setDone({ text: t("Deshecho: las entidades vuelven a tener el resumen de antes."), op: null }); } });
  const d = q.data; const p = d?.progress;
  const items = (d?.items ?? []).filter((i) => i.facts >= Number(minFacts || 0) && (!reason || i.reason === reason));
  const ids = items.map((i) => i.id);
  const chosen = sel.filter((id) => ids.includes(id));   // a row a filter hid is not approved by surprise
  const pending = status === "pending";
  return (
    <>
      <ViewBar title={t("Resúmenes")}
        help={<>{t("Muchas entidades tienen como resumen la lista de sus propios hechos, porque así lo escribía la ingesta. El revisor propone uno mejor, de una a tres frases escritas a partir de los hechos vigentes de la entidad; un curador lo corrige si hace falta y lo aprueba, y ese texto sustituye al resumen. Cada aprobación se puede deshacer.")}{" "}
          {isAdmin ? "" : t("El análisis lo lanza un administrador del brain; los curadores revisan lo propuesto.")}
          {status === "outdated" ? t("Propuestas que no se aplicaron porque el resumen de la entidad cambió entre el análisis y la aprobación, por ejemplo con una ingesta. El próximo análisis la vuelve a mirar.") : ""}</>}
        actions={<>
          {isAdmin && <Btn icon="search" disabled={!d?.engine || p?.running} onClick={() => { scan.reset(); setScanning(true); }}>{t("Analizar…")}</Btn>}
          {pending && <Btn kind="danger" disabled={!chosen.length} loading={reject.isPending} onClick={() => reject.mutate(chosen)}>{t("Rechazar las seleccionadas")}</Btn>}
          {pending && <Btn kind="primary" icon="check" disabled={!ids.length} onClick={() => setAsk(chosen.length ? chosen : ids)}>
            {chosen.length ? t("Aprobar las seleccionadas ({{n}})", { n: chosen.length }) : t("Aprobar todas las visibles ({{n}})", { n: ids.length })}</Btn>}
        </>}>
        <Segments label={t("Estado")} value={status} onChange={(v) => { setStatus(v); setSel([]); setDone(null); }}
          data={STATUSES.map(([value, label]) => ({ value, label: t(label), count: d?.counts[value] ?? 0 }))} />
        {pending && <>
          <NumberField label={t("Con al menos estos hechos")} min={0} value={minFacts} onChange={setMinFacts} />
          <SelectField label={t("Por qué")} clearable placeholder={t("Todos")} value={reason} onChange={setReason}
            data={Object.entries(REASON).map(([value, label]) => ({ value, label: t(label) }))} />
          <Check label={t("Seleccionar todo")} checked={!!ids.length && chosen.length === ids.length} onChange={(e) => setSel(e.currentTarget.checked ? ids : [])} />
        </>}
      </ViewBar>
      {d && !d.engine && <Notice tone="warn">{t("No hay ningún motor LLM configurado (Administración → Proveedores IA).")}</Notice>}
      {p?.running && <ProgressBar done={p.done} total={p.total} text={t("Analizando… {{done}} de {{total}}", { done: p.done, total: p.total })} />}
      {p?.error && !p.running && <Notice tone="warn" title={t("Último error del análisis")}>{p.error}</Notice>}
      {done && <Notice tone="success">{done.text}{done.op && <> <Btn kind="link" loading={undo.isPending} onClick={() => undo.mutate(done.op!)}>{t("Deshacer")}</Btn></>}</Notice>}
      <MutationError error={one.error ?? all.error ?? reject.error ?? undo.error} />
      {!d ? <DataState query={q} /> : items.length === 0 && <EmptyState>{pending ? t("No hay resúmenes propuestos. Lanza un análisis para buscar los pobres.") : t("Sin elementos.")}</EmptyState>}
      {items.map((i) => (
        <ListCard key={i.id}
          title={<>{pending && <Check aria-label={t("Seleccionar {{name}}", { name: i.name })} checked={chosen.includes(i.id)} onChange={(e) => setSel(e.currentTarget.checked ? [...sel, i.id] : sel.filter((x) => x !== i.id))} />}
            <Link to={`/entidad/${i.entity_uuid}`}>{i.name}</Link></>}
          aside={t("{{count}} hechos", { count: i.facts })}
          tags={<>{REASON[i.reason] && <Pill tone="alt">{t(REASON[i.reason])}</Pill>}
            {i.edited && <Pill>{t("editado por un curador")}</Pill>}
            {i.secrets.length > 0 && <Pill tone={i.flagged ? "warn" : "neutral"} title={i.secrets.map((s) => s.label).join(", ")}>
              {i.flagged ? t("posibles secretos: revísalo") : t("secretos tapados")}</Pill>}</>}
          actions={pending ? <>
            <Btn kind="primary" size="row" icon="check" loading={one.isPending && one.variables?.id === i.id} onClick={() => one.mutate(i)}>
              {texts[i.id] !== undefined && texts[i.id] !== i.proposed ? t("Aprobar con mis cambios") : t("Aprobar")}</Btn>
            <Btn kind="danger" size="row" loading={reject.isPending && reject.variables?.includes(i.id)} onClick={() => reject.mutate([i.id])}>{t("Rechazar")}</Btn>
          </> : status === "applied" && i.op ? <Btn size="row" icon="undo" loading={undo.isPending && undo.variables === i.op} onClick={() => undo.mutate(i.op!)}>
              {i.op_size > 1 ? t("Deshacer la aprobación ({{n}} resúmenes)", { n: i.op_size }) : t("Deshacer")}</Btn> : undefined}>
          <Compare items={[
            { label: pending ? t("Ahora") : t("Antes"), children: <div className="ms-clamp">{i.current}</div> },
            { label: status === "applied" ? t("Aprobado") : t("Propuesto"), children: pending
              ? <TextArea aria-label={t("Resumen propuesto para {{name}}", { name: i.name })} autosize minRows={3} maxRows={10} maxLength={1000}
                  value={texts[i.id] ?? i.proposed} onChange={(e) => setTexts({ ...texts, [i.id]: e.currentTarget.value })} />
              : status === "applied" ? i.applied : i.proposed },
          ]} />
        </ListCard>))}
      {isAdmin && <ScanDialog opened={scanning} onClose={() => setScanning(false)} title={t("Analizar resúmenes")} initial={50} pending={scan.isPending} error={scan.error}
        cost={t("Una llamada al motor por entidad, empezando por las que tienen más hechos. Cuenta en el consumo de IA del brain como «Revisión de resúmenes» y se detiene si el brain agota su presupuesto.")}
        onRun={(n) => scan.mutateAsync(n)} />}
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} tone="primary" title={t("Aprobar {{n}} resúmenes", { n: ask?.length ?? 0 })} action={t("Aprobar")}
        warning={t("El texto propuesto sustituye al resumen de cada entidad tal como está, sin tus cambios en las que no hayas aprobado una a una. Se puede deshacer desde Cambios recientes.")}
        onConfirm={() => all.mutateAsync(ask!)} />
    </>
  );
}
