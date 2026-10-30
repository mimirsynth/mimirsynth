import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, DataTable, EmptyState, ListCard, MutationError, Notice, Pill, SelectField } from "../ui";

type Fact = { uuid: string; fact: string; target: string; valid_at: string | null; created_at: string | null };
type Group_ = { source: string; source_uuid: string; relation: string; target_type: string; facts: Fact[];
  suggestion: { keep: string; invalidate: string[]; clear: boolean; dated_by: "valid_at" | "created_at" } };
type Stat = { relation: string; sources: number; groups: number; ratio: number; functional: boolean };
type Scan = { scanned: number; truncated: boolean; functional: string[]; total: number; groups: Group_[]; by_relation?: Stat[] };

function ConflictCard({ g, canResolve, onResolve, busy }: { g: Group_; canResolve: boolean; onResolve: (keep: string, drop: string[]) => void; busy: boolean }) {
  const { t } = useTranslation();
  const [keep, setKeep] = useState(g.suggestion.clear ? g.suggestion.keep : "");   // sin propuesta clara, no se elige por la persona
  const kept = g.facts.find((f) => f.uuid === keep);
  const drop = g.facts.filter((f) => f.target.toLowerCase().trim() !== (kept?.target ?? "").toLowerCase().trim()).map((f) => f.uuid);
  return (
    <ListCard title={`${g.source} · ${g.relation}`} tags={g.target_type !== "Entity" ? <Pill size="xs">{g.target_type}</Pill> : undefined}
      aside={g.suggestion.clear ? <Pill size="xs" tone="success">{t("el más reciente es claro")}</Pill>
        : g.suggestion.dated_by === "created_at" ? <Pill size="xs" tone="warn" title={t("Algún hecho no tiene fecha de validez: la que se ve es cuándo se aprendió, que no dice cuál es más actual.")}>{t("solo fecha de aprendizaje: decide tú")}</Pill>
        : <Pill size="xs" tone="warn">{t("misma fecha: decide tú")}</Pill>}
      actions={canResolve && <Group gap={6} wrap="nowrap">
        <SelectField size="xs" w={260} aria-label={t("Hecho que se queda vigente")} placeholder={t("Elige cuál se queda")} data={g.facts.map((f) => ({ value: f.uuid, label: `${f.target} · ${fmt(f.valid_at ?? f.created_at)}` }))} value={keep || null} onChange={(v) => v && setKeep(v)} allowDeselect={false} />
        <Btn size="row" kind="primary" icon="check" loading={busy} disabled={!keep || !drop.length} onClick={() => onResolve(keep, drop)}>{t("Dejar este e invalidar el resto")}</Btn>
      </Group>}>
      <Stack gap={2}>
        {g.facts.map((f) => (
          <Text key={f.uuid} size="sm" fw={f.uuid === keep ? 600 : 400} c={f.uuid === keep ? undefined : "dimmed"}>
            {f.fact} <Text span size="xs" c="dimmed" className="ms-data">({fmt(f.valid_at ?? f.created_at)})</Text></Text>))}
      </Stack>
    </ListCard>
  );
}

/** Hechos vigentes que se contradicen en una relación de un solo valor: mismo sujeto, misma relación, destinos distintos. */
export default function VocabConflicts({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canResolve = ["curator", "admin", "owner"].includes(role);
  const [all, setAll] = useState(false);
  const q = useQuery({ queryKey: ["conflicts", graph, all], enabled: canResolve, queryFn: () => get<Scan>(`brains/${graph}/conflicts`, { all }) });
  const resolve = useMutation({ mutationFn: (v: { keep: string; invalidate: string[] }) => send("POST", `brains/${graph}/conflicts/resolve`, v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["conflicts", graph] }); qc.invalidateQueries({ queryKey: ["facts", graph] }); } });
  if (!canResolve) return <EmptyState>{t("Revisar contradicciones es cosa de un curador o superior.")}</EmptyState>;
  const d = q.data;
  return (
    <Stack gap="md">
      <Notice tone="info">{t("Hechos vigentes con el mismo sujeto y la misma relación y destinos distintos del mismo tipo, en las relaciones marcadas como de un solo valor en la ontología. Se propone dejar el de fecha de validez más reciente; al resolver, los demás se invalidan y se puede deshacer desde el historial del vocabulario. No se usa ningún modelo de IA.")}</Notice>
      <Group gap="xs">
        <Btn kind={all ? "primary" : "secondary"} icon="search" onClick={() => setAll((x) => !x)}>{all ? t("Volver a las relaciones de un solo valor") : t("Medir en todas las relaciones")}</Btn>
        {d && <Text size="xs" c="dimmed">{t("{{n}} hechos vigentes analizados.", { n: d.scanned })}{d.truncated ? ` ${t("Se ha llegado al máximo: faltan hechos.")}` : ""}</Text>}
      </Group>
      <MutationError error={q.error ?? resolve.error} />
      {d && !all && !d.functional.length && <Notice tone="warn">{t("Ninguna relación de la ontología está marcada como de un solo valor, así que no se buscan contradicciones. Mide primero en todas las relaciones y marca en Ontología solo las que de verdad admitan un único valor a la vez.")}</Notice>}
      {d?.by_relation && <Stack gap="xs">
        <Text fw={600} size="sm">{t("Candidatos por relación")}</Text>
        <Text size="xs" c="dimmed">{t("Proporción de sujetos con más de un destino vigente del mismo tipo, de menor a mayor. Las candidatas a un solo valor son las de proporción baja con algún caso; una con muchos casos probablemente admite varios valores. Solo lee: no cambia nada.")}</Text>
        <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Relación")}</DataTable.Th><DataTable.Th>{t("Sujetos")}</DataTable.Th><DataTable.Th>{t("Con varios destinos")}</DataTable.Th><DataTable.Th>{t("Proporción")}</DataTable.Th><DataTable.Th>{t("Un solo valor")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{d.by_relation.filter((s) => s.groups > 0).map((s) => (
            <DataTable.Tr key={s.relation}>
              <DataTable.Td className="ms-data">{s.relation}</DataTable.Td><DataTable.Td>{s.sources}</DataTable.Td><DataTable.Td>{s.groups}</DataTable.Td>
              <DataTable.Td>{`${Math.round(s.ratio * 100)} %`}</DataTable.Td><DataTable.Td>{s.functional ? <Pill size="xs" tone="alt">{t("sí")}</Pill> : t("no")}</DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable>
      </Stack>}
      {d && (d.groups.length ? <Stack gap="xs">
        <Text fw={600} size="sm">{t("Posibles contradicciones ({{n}})", { n: d.total })}</Text>
        {d.groups.map((g) => <ConflictCard key={`${g.source_uuid}-${g.relation}`} g={g} canResolve={!all || d.functional.includes(g.relation)} busy={resolve.isPending}
          onResolve={(keep, drop) => resolve.mutate({ keep, invalidate: drop })} />)}
        {d.total > d.groups.length && <Text size="xs" c="dimmed">{t("Se muestran los primeros {{n}}.", { n: d.groups.length })}</Text>}
      </Stack> : (!all && d.functional.length > 0 && <EmptyState>{t("No hay contradicciones en las relaciones de un solo valor.")}</EmptyState>))}
    </Stack>
  );
}
