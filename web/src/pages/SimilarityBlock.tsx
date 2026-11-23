import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Stack } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fmt, fmtNum, get, send } from "../api";
import { Block, Btn, CellText, DataState, DataTable, EmptyState, MutationError } from "../ui";

type Baseline = { pairs: number; p50: number | null; p90: number | null; p95: number | null; p99: number | null };
type Same = { pairs: number; p10: number | null; p50: number | null; under_p99: number | null };
type Measurement = { model: string | null; dim: number | null; facts: number; measured_at: string; too_few: boolean; baseline: Baseline | null; same: Same | null };
type Sim = { measurement: Measurement | null; thresholds: { key: string; cosine: number }[]; suggested_recall_min: number | null; min_facts: number };

/** What each threshold decides, as a curator reads it. */
const THRESHOLD: Record<string, [string, string]> = {
  close: [T("«Muy parecido» al revisar una propuesta"), T("calibrado: lo que dos hechos cualesquiera de este brain casi nunca alcanzan")],
  near_duplicate: [T("Repetidos del curador"), T("dos hechos entre las mismas entidades que dicen lo mismo")],
  recall_min: [T("Mínimo del recall"), T("por debajo, un hecho no entra en el contexto (para toda la instancia)")],
  distil_cover: [T("Cubierto por una nota del curador"), T("un hecho que la nota destilada ya recoge")],
};

/** How similar two facts of this brain usually are, and where each threshold sits on that scale (issue 468). With today's embedding
 *  models two unrelated facts score high and close together, so a fixed threshold says little until it is read against the brain. */
export default function SimilarityBlock({ graph, canAdmin }: { graph: string; canAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["similarity", graph];
  const q = useQuery({ queryKey: key, queryFn: () => get<Sim>(`brains/${graph}/similarity`), staleTime: 60_000 });
  const again = useMutation({ mutationFn: () => send<Sim>("POST", `brains/${graph}/similarity/measure`), onSuccess: (r) => qc.setQueryData(key, r) });
  const d = q.data, m = d?.measurement, b = m?.baseline;
  const where = (c: number) => (!b || b.p50 == null || b.p95 == null || b.p99 == null ? "—"
    : c >= b.p99 ? t("por encima de casi cualquier par") : c >= b.p95 ? t("por encima de lo habitual") : c >= b.p50 ? t("dentro de lo habitual") : t("por debajo de lo habitual"));
  return (
    <Block title={t("Similitud en este brain")}
      help={t("Con los modelos de embeddings actuales, dos hechos sin relación puntúan alto y muy juntos, así que un umbral fijo dice poco por sí solo. Aquí se mide cuánto se parecen dos hechos cualesquiera de este brain (pares al azar) y cuánto los que un curador dio por iguales, y dónde cae cada umbral en esa escala. «Muy parecido», al revisar una propuesta, ya usa esta medida; el resto de umbrales solo se muestran: cámbialos después de probarlos con las consultas de referencia.")}
      meta={m ? t("medido el {{date}} con {{model}}", { date: fmt(m.measured_at), model: m.model ?? "—" }) : undefined}
      actions={canAdmin ? <Btn size="row" icon="refresh" loading={again.isPending} onClick={() => again.mutate()}>{t("Medir de nuevo")}</Btn> : undefined}>
      <MutationError error={again.error} />
      {!d ? <DataState query={q} /> : !m ? <EmptyState>{t("No se ha podido medir: el grafo no responde. Mientras, se usan los umbrales fijos.")}</EmptyState>
        : m.too_few ? <EmptyState>{t("Este brain tiene {{n}} hechos vigentes; hacen falta {{min}} para medirlo. Mientras, se usan los umbrales fijos.", { n: m.facts, min: d.min_facts })}</EmptyState>
        : <Stack gap="sm">
          <CellText sub={t("{{n}} pares al azar de hechos vigentes sobre cosas distintas", { n: b!.pairs })}>
            {t("Dos hechos cualesquiera: mediana {{p50}} · el 95 % por debajo de {{p95}} · el 99 % por debajo de {{p99}}", { p50: fmtNum(b!.p50, 2), p95: fmtNum(b!.p95, 2), p99: fmtNum(b!.p99, 2) })}</CellText>
          {m.same && m.same.pairs > 0
            ? <CellText sub={m.same.under_p99 ? t("{{p}} de ellos queda por debajo de lo que alcanzan dos hechos cualesquiera: ahí la similitud sola no los distingue", { p: `${Math.round(m.same.under_p99 * 100)} %` }) : t("Todos quedan por encima de lo que alcanzan dos hechos cualesquiera")}>
                {t("Hechos que un curador dio por iguales: {{n}} pares, mediana {{p50}}", { n: m.same.pairs, p50: fmtNum(m.same.p50, 2) })}</CellText>
            : <CellText sub={t("Salen de las propuestas de repetidos del curador y de las uniones aprobadas en las revisiones de tema.")}>{t("Aún no hay hechos que un curador haya dado por iguales.")}</CellText>}
          <DataTable fz="sm" aria-label={t("Umbrales en uso")}>
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Umbral")}</DataTable.Th><DataTable.Th ta="right">{t("Similitud")}</DataTable.Th><DataTable.Th>{t("Dónde cae")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{d.thresholds.map((x) => (
              <DataTable.Tr key={x.key}>
                <DataTable.Td><CellText sub={THRESHOLD[x.key] ? t(THRESHOLD[x.key][1]) : undefined}>{THRESHOLD[x.key] ? t(THRESHOLD[x.key][0]) : x.key}</CellText></DataTable.Td>
                <DataTable.Td ta="right" className="ms-data">{fmtNum(x.cosine, 2)}</DataTable.Td>
                <DataTable.Td>{where(x.cosine)}</DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable>
          {d.suggested_recall_min != null && <CellText sub={t("Pruébalo antes en «Consultas de referencia» con un barrido del mínimo de similitud, y con la muestra de consultas si la guardas.")}>
            {t("Para el mínimo del recall en este brain, un valor por probar: {{v}}", { v: fmtNum(d.suggested_recall_min, 2) })}</CellText>}
        </Stack>}
    </Block>
  );
}
