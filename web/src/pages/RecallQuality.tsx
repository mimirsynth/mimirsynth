import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fmt, get, send } from "../api";
import { Btn, Check, DataTable, EmptyState, MutationError, Notice, StatCard, StatGrid } from "../ui";

type Counts = { useful: number; irrelevant: number; incorrect: number };
type Quality = { days: number; recalls: number; rated_recalls: number; ratings: number; by_kind: Record<string, Counts>;
  buckets: Record<string, ({ range: string } & Counts)[]>; incorrect: { kind: string; text: string; similarity: number | null; created_at: string; proposal_id: number | null }[];
  keep_query_text: boolean; query_text_days: number; rate_hours: number };

export const KIND: Record<string, string> = { fact: T("Hechos"), chunk: T("Fragmentos de episodios"), doc: T("Pasajes de documentos") };
const pct = (c: Counts) => { const n = c.useful + c.irrelevant + c.incorrect; return n ? Math.round((100 * c.irrelevant) / n) : null; };

/** Calidad del recall según quien lo usa: proporción de irrelevantes por tipo y por tramo de similitud, junto al total de recalls. */
export default function RecallQuality({ graph, canAdmin }: { graph: string; canAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["recall-quality", graph];
  const q = useQuery({ queryKey: key, queryFn: () => get<Quality>(`brains/${graph}/recall/quality`, { days: 30 }) });
  const keep = useMutation({ mutationFn: (v: boolean) => send("PUT", `brains/${graph}/recall/settings`, { keep_query_text: v }), onSuccess: () => qc.invalidateQueries({ queryKey: key }) });
  const d = q.data;
  const csv = () => {
    if (!d) return;
    const lines = ["kind,range,useful,irrelevant,incorrect", ...Object.entries(d.buckets).flatMap(([k, rows]) => rows.map((r) => `${k},${r.range},${r.useful},${r.irrelevant},${r.incorrect}`))];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n") + "\n"], { type: "text/csv" }));
    a.download = `recall-quality-${graph}.csv`; a.click(); URL.revokeObjectURL(a.href);
  };
  if (!d) return null;
  return (
    <Stack gap="md">
      <Notice tone="info">{t("Lo que dicen quienes usan el recall (desde Preguntar, la API o la herramienta «rate» del MCP) en los últimos 30 días. Las valoraciones llegan sobre todo cuando algo falla: compáralas con el total de recalls antes de mover un umbral. «Incorrecto» en un hecho, de un colaborador o más, propone su corrección.")}</Notice>
      <StatGrid>
        <StatCard label={t("Recalls")} value={d.recalls} />
        <StatCard label={t("Recalls valorados")} value={d.rated_recalls} />
        <StatCard label={t("Valoraciones")} value={d.ratings} />
      </StatGrid>
      {d.ratings ? <>
        <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Tipo")}</DataTable.Th><DataTable.Th>{t("Útil")}</DataTable.Th><DataTable.Th>{t("Irrelevante")}</DataTable.Th>
            <DataTable.Th>{t("Incorrecto")}</DataTable.Th><DataTable.Th>{t("% irrelevante")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{Object.entries(d.by_kind).map(([k, c]) => (
            <DataTable.Tr key={k}><DataTable.Td>{t(KIND[k] ?? k)}</DataTable.Td><DataTable.Td>{c.useful}</DataTable.Td><DataTable.Td>{c.irrelevant}</DataTable.Td>
              <DataTable.Td>{c.incorrect}</DataTable.Td><DataTable.Td>{pct(c) ?? "—"}{pct(c) !== null ? " %" : ""}</DataTable.Td></DataTable.Tr>))}</DataTable.Tbody>
        </DataTable>
        <Group justify="space-between"><Text size="sm" fw={600}>{t("Por similitud")}</Text><Btn size="row" icon="download" onClick={csv}>{t("Descargar CSV")}</Btn></Group>
        <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Tipo")}</DataTable.Th><DataTable.Th>{t("Similitud")}</DataTable.Th><DataTable.Th>{t("Útil")}</DataTable.Th>
            <DataTable.Th>{t("Irrelevante")}</DataTable.Th><DataTable.Th>{t("Incorrecto")}</DataTable.Th><DataTable.Th>{t("% irrelevante")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{Object.entries(d.buckets).flatMap(([k, rows]) => rows.map((r) => (
            <DataTable.Tr key={`${k}-${r.range}`}><DataTable.Td>{t(KIND[k] ?? k)}</DataTable.Td><DataTable.Td>{r.range}</DataTable.Td><DataTable.Td>{r.useful}</DataTable.Td>
              <DataTable.Td>{r.irrelevant}</DataTable.Td><DataTable.Td>{r.incorrect}</DataTable.Td><DataTable.Td>{pct(r) ?? "—"}{pct(r) !== null ? " %" : ""}</DataTable.Td></DataTable.Tr>)))}</DataTable.Tbody>
        </DataTable>
        {d.incorrect.length > 0 && <Stack gap={4}>
          <Text size="sm" fw={600}>{t("Valorados como incorrectos")}</Text>
          {d.incorrect.map((i, n) => <Text key={n} size="xs">{fmt(i.created_at)} · {t(KIND[i.kind] ?? i.kind)} · «{i.text}»{i.proposal_id
            ? <> · <Link to="/propuestas">{t("corrección #{{id}}", { id: i.proposal_id })}</Link></> : ` · ${t("sin corrección")}`}</Text>)}
        </Stack>}
      </> : <EmptyState>{t("Nadie ha valorado el recall en los últimos 30 días.")}</EmptyState>}
      {canAdmin && <Check checked={d.keep_query_text} onChange={(e) => keep.mutate(e.currentTarget.checked)} label={t("Guardar el texto de las consultas")}
        description={t("Por defecto solo se guarda una huella y la longitud de cada consulta, porque llevan los prompts de las personas. Con esto se guarda el texto, que se borra a los {{n}} días; al desmarcarlo se borra ya.", { n: d.query_text_days })} />}
      <MutationError error={keep.error} />
    </Stack>
  );
}
