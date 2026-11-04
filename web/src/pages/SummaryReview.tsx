import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { get, send } from "../api";
import { T } from "../i18n";
import { Btn, Check, ConfirmDialog, EmptyState, MutationError, Notice, NumberField, Panel, Pill, ProgressBar, Segments, SelectField, TextArea } from "../ui";
import { TabIntro } from "./Quality";

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
  const [limit, setLimit] = useState<number | string>(50);
  const [minFacts, setMinFacts] = useState<number | string>(0);
  const [reason, setReason] = useState<string | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [texts, setTexts] = useState<Record<number, string>>({});
  const [done, setDone] = useState<{ text: string; op: number | null } | null>(null);
  const [ask, setAsk] = useState<number[] | null>(null);
  const q = useQuery({ queryKey: ["summaries", graph, status], refetchInterval: (c) => (c.state.data?.progress.running ? 3000 : false), queryFn: () => get<Ov>(base, { status }) });
  const refresh = () => { setSel([]); qc.invalidateQueries({ queryKey: ["summaries", graph] }); };
  const scan = useMutation({ mutationFn: () => send("POST", `${base}/scan`, { limit: Number(limit) }), onSuccess: refresh });
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
    <Stack gap="sm">
      <TabIntro>{t("Muchas entidades tienen como resumen la lista de sus propios hechos, porque así lo escribía la ingesta. El revisor propone uno mejor, de una a tres frases escritas a partir de los hechos vigentes de la entidad; un curador lo corrige si hace falta y lo aprueba, y ese texto sustituye al resumen. Cada aprobación se puede deshacer.")}</TabIntro>
      {d && !d.engine && <Notice tone="warn">{t("No hay ningún motor LLM configurado (Administración → Proveedores IA).")}</Notice>}
      {isAdmin ? <Group align="flex-end" gap="xs">
        <NumberField size="xs" label={t("Entidades a analizar")} min={1} max={1000} value={limit} onChange={setLimit} w={150} />
        <Btn kind="primary" icon="search" disabled={!d?.engine || p?.running} loading={scan.isPending} onClick={() => scan.mutate()}>{t("Analizar")}</Btn>
        <Text size="xs" c="dimmed" maw={520}>{t("Una llamada al motor por entidad, empezando por las que tienen más hechos. Cuenta en el consumo de IA del brain como «Revisión de resúmenes» y se detiene si el brain agota su presupuesto.")}</Text>
      </Group> : <Text size="xs" c="dimmed">{t("El análisis lo lanza un administrador del brain; los curadores revisan lo propuesto.")}</Text>}
      <MutationError error={scan.error} />
      {p?.running && <ProgressBar done={p.done} total={p.total} text={t("Analizando… {{done}} de {{total}}", { done: p.done, total: p.total })} />}
      {p?.error && !p.running && <Notice tone="warn">{t("Último error del análisis:")} {p.error}</Notice>}
      <Segments label={t("Estado")} value={status} onChange={(v) => { setStatus(v); setSel([]); setDone(null); }}
        data={STATUSES.map(([value, label]) => ({ value, label: t(label), count: d?.counts[value] ?? 0 }))} />
      {status === "outdated" && <Text size="xs" c="dimmed" maw={760}>{t("Propuestas que no se aplicaron porque el resumen de la entidad cambió entre el análisis y la aprobación, por ejemplo con una ingesta. El próximo análisis la vuelve a mirar.")}</Text>}
      {pending && <Group align="flex-end" gap="xs">
        <NumberField size="xs" label={t("Con al menos estos hechos")} min={0} value={minFacts} onChange={setMinFacts} w={170} />
        <SelectField size="xs" label={t("Por qué")} clearable placeholder={t("Todos")} value={reason} onChange={setReason} w={240}
          data={Object.entries(REASON).map(([value, label]) => ({ value, label: t(label) }))} />
        <Check aria-label={t("Seleccionar todo")} label={t("Todo")} checked={!!ids.length && chosen.length === ids.length} onChange={(e) => setSel(e.currentTarget.checked ? ids : [])} />
        <Btn kind="primary" icon="check" disabled={!ids.length} onClick={() => setAsk(chosen.length ? chosen : ids)}>
          {chosen.length ? t("Aprobar las seleccionadas ({{n}})", { n: chosen.length }) : t("Aprobar todas las visibles ({{n}})", { n: ids.length })}</Btn>
        <Btn kind="danger" size="row" disabled={!chosen.length} loading={reject.isPending} onClick={() => reject.mutate(chosen)}>{t("Rechazar las seleccionadas")}</Btn>
      </Group>}
      {done && <Notice tone="success">{done.text}{done.op && <> <Btn kind="link" loading={undo.isPending} onClick={() => undo.mutate(done.op!)}>{t("Deshacer")}</Btn></>}</Notice>}
      <MutationError error={one.error ?? all.error ?? reject.error ?? undo.error} />
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} tone="primary" title={t("Aprobar {{n}} resúmenes", { n: ask?.length ?? 0 })} action={t("Aprobar")}
        warning={t("El texto propuesto sustituye al resumen de cada entidad tal como está, sin tus cambios en las que no hayas aprobado una a una. Se puede deshacer desde Cambios recientes.")}
        onConfirm={() => all.mutateAsync(ask!)} />
      {items.length === 0 && q.isSuccess && <EmptyState>{pending ? t("No hay resúmenes propuestos. Lanza un análisis para buscar los pobres.") : t("Sin elementos.")}</EmptyState>}
      {items.map((i) => (
        <Panel key={i.id} withBorder p="sm">
          <Stack gap="xs">
            <Group gap="xs" wrap="wrap">
              {pending && <Check aria-label={t("Seleccionar {{name}}", { name: i.name })} checked={chosen.includes(i.id)} onChange={(e) => setSel(e.currentTarget.checked ? [...sel, i.id] : sel.filter((x) => x !== i.id))} />}
              <Text fw={700} size="sm" component={Link} to={`/entidad/${i.entity_uuid}`}>{i.name}</Text>
              <Pill size="xs">{t("{{count}} hechos", { count: i.facts })}</Pill>
              {REASON[i.reason] && <Pill size="xs" tone="alt">{t(REASON[i.reason])}</Pill>}
              {i.edited && <Pill size="xs">{t("editado por un curador")}</Pill>}
              {i.secrets.length > 0 && <Pill size="xs" tone={i.flagged ? "warn" : "neutral"} title={i.secrets.map((s) => s.label).join(", ")}>
                {i.flagged ? t("posibles secretos: revísalo") : t("secretos tapados")}</Pill>}
            </Group>
            <div className="ms-summary-pair">
              <Stack gap={2}>
                <Text size="xs" c="dimmed" fw={700}>{pending ? t("Ahora") : t("Antes")}</Text>
                <Text size="sm" className="ms-prose" lineClamp={10}>{i.current}</Text>
              </Stack>
              <Stack gap={2}>
                <Text size="xs" c="dimmed" fw={700}>{status === "applied" ? t("Aprobado") : t("Propuesto")}</Text>
                {pending ? <TextArea aria-label={t("Resumen propuesto para {{name}}", { name: i.name })} autosize minRows={3} maxRows={10} maxLength={1000}
                  value={texts[i.id] ?? i.proposed} onChange={(e) => setTexts({ ...texts, [i.id]: e.currentTarget.value })} />
                  : <Text size="sm" className="ms-prose">{status === "applied" ? i.applied : i.proposed}</Text>}
              </Stack>
            </div>
            {pending && <Group gap="xs">
              <Btn kind="primary" size="row" icon="check" loading={one.isPending && one.variables?.id === i.id} onClick={() => one.mutate(i)}>
                {texts[i.id] !== undefined && texts[i.id] !== i.proposed ? t("Aprobar con mis cambios") : t("Aprobar")}</Btn>
              <Btn kind="danger" size="row" loading={reject.isPending && reject.variables?.includes(i.id)} onClick={() => reject.mutate([i.id])}>{t("Rechazar")}</Btn>
            </Group>}
            {status === "applied" && i.op && <Group><Btn size="row" icon="undo" loading={undo.isPending && undo.variables === i.op} onClick={() => undo.mutate(i.op!)}>
              {i.op_size > 1 ? t("Deshacer la aprobación ({{n}} resúmenes)", { n: i.op_size }) : t("Deshacer")}</Btn></Group>}
          </Stack>
        </Panel>))}
    </Stack>
  );
}
