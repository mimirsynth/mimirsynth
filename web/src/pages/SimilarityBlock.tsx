import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { fmt, fmtNum, get, send } from "../api";
import { Block, Btn, CellText, DataState, DataTable, EmptyState, MutationError } from "../ui";

type Baseline = { pairs: number; p50: number | null; p90: number | null; p95: number | null; p99: number | null };
type Same = { pairs: number; p10: number | null; p50: number | null; under_p99: number | null };
type Measurement = { model: string | null; dim: number | null; facts: number; measured_at: string; too_few: boolean; reason?: "facts" | "pairs";
  baseline: Baseline | null; same: Same | null };
type Sim = { measurement: Measurement | null; thresholds: { key: string; cosine: number }[]; suggested_recall_min: number | null; min_facts: number };
type Rung = { key: string; label: string; sub?: ReactNode; cosine: number; reference?: boolean };

/** What each threshold decides, as a curator reads it: short, the «i» says the rest. */
const THRESHOLD: Record<string, [string, string]> = {
  close: [T("«Muy parecido» en una propuesta"), T("calibrado con este brain")],
  near_duplicate: [T("Repetidos del curador"), T("mismas entidades, mismo hecho")],
  recall_min: [T("Mínimo del recall"), T("para toda la instancia")],
  distil_cover: [T("Cubierto por una nota del curador"), T("ya lo recoge la nota")],
};
/** One ladder of words for where a similarity sits, here and in a proposal's facts. */
export const LADDER = { well_above: T("muy por encima de lo habitual"), above: T("por encima de lo habitual"), usual: T("lo habitual"),
  below: T("por debajo de lo habitual") };

/** How similar two facts of this brain usually are, and where each threshold sits on that scale (issue 468): one table from the lowest
 *  similarity to the highest, with the brain's own reference points among the thresholds. With today's embedding models two unrelated
 *  facts score high and close together, so a fixed threshold says little until it is read against the brain. */
export default function SimilarityBlock({ graph, canAdmin }: { graph: string; canAdmin: boolean }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const key = ["similarity", graph];
  const q = useQuery({ queryKey: key, queryFn: () => get<Sim>(`brains/${graph}/similarity`), staleTime: 60_000 });
  const again = useMutation({ mutationFn: () => send<Sim>("POST", `brains/${graph}/similarity/measure`), onSuccess: (r) => qc.setQueryData(key, r) });
  const d = q.data, m = d?.measurement, b = m && !m.too_few ? m.baseline : null;
  const pct = (x: number) => new Intl.NumberFormat(i18n.language, { style: "percent", maximumFractionDigits: 0 }).format(x);
  // «well above» starts where «very similar» does (the p99, never under the fixed floor), as on a proposal's fact cards
  const closeCut = d?.thresholds.find((x) => x.key === "close")?.cosine ?? Infinity;
  const where = (c: number) => (!b || b.p50 == null || b.p95 == null ? "—"
    : t(c >= closeCut ? LADDER.well_above : c >= b.p95 ? LADDER.above : c >= b.p50 ? LADDER.usual : LADDER.below));
  const tryIt = d?.suggested_recall_min != null
    ? <>{t("por probar en este brain: {{v}}", { v: fmtNum(d.suggested_recall_min, 2) })} · <Btn kind="link" className="ms-link-inline" component={Link} to="/preguntar?tab=referencia">{t("Consultas de referencia")}</Btn></>
    : undefined;
  const rungs: Rung[] = [
    ...(d?.thresholds ?? []).map((x) => ({ key: x.key, label: THRESHOLD[x.key] ? t(THRESHOLD[x.key][0]) : x.key,
      // «very similar» is calibrated only when the brain's p99 sets it; otherwise it is the fixed minimum
      sub: x.key === "recall_min" && tryIt ? <>{t(THRESHOLD.recall_min[1])} · {tryIt}</>
        : x.key === "close" && !(b && b.p99 != null && x.cosine === b.p99) ? t("mínimo fijo")
        : THRESHOLD[x.key] ? t(THRESHOLD[x.key][1]) : undefined, cosine: x.cosine })),
    ...(b && b.p50 != null && b.p95 != null && b.p99 != null ? [
      { key: "p50", label: t("Mediana de dos hechos cualesquiera"), sub: t("{{n}} pares al azar sobre cosas distintas", { n: b.pairs }), cosine: b.p50, reference: true },
      { key: "p95", label: t("El 95 % de esos pares queda por debajo"), cosine: b.p95, reference: true },
      { key: "p99", label: t("El 99 % de esos pares queda por debajo"), cosine: b.p99, reference: true }] : []),
    ...(b && m?.same && m.same.pairs > 0 && m.same.p50 != null ? [{ key: "same", label: t("Mediana de los que un curador dio por iguales"), cosine: m.same.p50, reference: true,
      sub: m.same.under_p99 ? t("{{n}} pares; {{p}} quedan donde llegan dos hechos cualesquiera", { n: m.same.pairs, p: pct(m.same.under_p99) }) : t("{{n}} pares", { n: m.same.pairs }) }] : []),
  ].sort((x, y) => x.cosine - y.cosine);
  const table = <DataTable fz="sm" aria-label={t("Umbrales en uso")}>
    <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Umbral")}</DataTable.Th><DataTable.Th ta="right">{t("Similitud")}</DataTable.Th>{b && <DataTable.Th>{t("Dónde cae")}</DataTable.Th>}</DataTable.Tr></DataTable.Thead>
    <DataTable.Tbody>{rungs.map((r) => (
      <DataTable.Tr key={r.key}>
        {/* the brain's own reference points, muted: the rows a curator acts on are the thresholds */}
        <DataTable.Td><CellText sub={r.sub}>{r.reference ? <span className="ms-listcard-meta">{r.label}</span> : r.label}</CellText></DataTable.Td>
        <DataTable.Td ta="right" className="ms-data">{fmtNum(r.cosine, 2)}</DataTable.Td>
        {b && <DataTable.Td>{r.reference ? <span className="ms-listcard-meta">—</span> : where(r.cosine)}</DataTable.Td>}
      </DataTable.Tr>))}</DataTable.Tbody>
  </DataTable>;
  return (
    <Block title={t("Similitud en este brain")}
      help={t("Con los modelos de embeddings actuales, dos hechos sin relación puntúan alto y muy juntos, así que un umbral fijo dice poco por sí solo. Aquí se mide cuánto se parecen dos hechos cualesquiera de este brain (pares al azar) y cuánto los que un curador dio por iguales, y se ordena todo de menor a mayor similitud con los umbrales en uso. «Muy parecido», al revisar una propuesta, ya usa esta medida; el resto de umbrales solo se muestran: cámbialos después de probarlos con las consultas de referencia.")}
      meta={m ? <span aria-live="polite">{t("medido el {{date}} con {{model}}", { date: fmt(m.measured_at), model: m.model ?? "—" })}</span> : undefined}
      actions={canAdmin ? <Btn size="row" icon="refresh" loading={again.isPending} onClick={() => again.mutate()}>{t("Medir de nuevo")}</Btn> : undefined}>
      <MutationError error={again.error} />
      {!d ? <DataState query={q} /> : <>
        {!m ? <EmptyState>{t("No se ha podido medir: el grafo no responde. Mientras, se usan los umbrales fijos.")}</EmptyState>
          : m.too_few ? <EmptyState>{m.reason === "pairs"
            ? t("Sus hechos vigentes no dan pares sobre cosas distintas con los que medirlo (casi todos unen las mismas entidades, o les falta el embedding). Mientras, se usan los umbrales fijos.")
            : t("Este brain tiene {{n}} hechos vigentes; hacen falta {{min}} para medirlo. Mientras, se usan los umbrales fijos.", { n: m.facts, min: d.min_facts })}</EmptyState>
          : null}
        {table}
      </>}
    </Block>
  );
}
