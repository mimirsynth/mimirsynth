import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Brain, get, send } from "../api";
import { Btn, DataTable, EmptyState, MutationError, Notice, Pill, SelectField, TextArea } from "../ui";

type Rule = { rule: string; label: string; certain: boolean; count: number; items: number };
type Item = { kind: "proposal" | "document"; id: number; title: string; findings: { rule: string; label: string; certain: boolean; context: string }[] };
type Scan = { proposals: number; documents: number; truncated: boolean; mode: string; rules: Rule[]; items: Item[]; items_truncated: boolean };
export type SecretFinding = { rule: string; label: string; action: "masked" | "flagged" | "blocked"; count?: number; field?: string };

const MODES = [
  { value: "mask", label: T("Enmascarar (recomendado)") },
  { value: "block", label: T("Bloquear") },
  { value: "warn", label: T("Solo avisar") },
];
const HELP: Record<string, string> = {
  mask: T("Los secretos seguros se sustituyen por «[secreto eliminado: tipo]» antes de guardar. Los posibles se marcan y la propuesta espera a un curador."),
  block: T("Una propuesta con un secreto seguro se rechaza con un mensaje que dice qué tipo es, y un documento con uno no se indexa. Los posibles se marcan."),
  warn: T("No se cambia ni se rechaza nada: todo lo detectado se marca y la propuesta espera a un curador."),
};

/** Resumen de lo que el detector de secretos encontró en una propuesta o un documento, sin el valor. */
export function SecretsNotice({ found }: { found?: SecretFinding[] }) {
  const { t } = useTranslation();
  if (!found?.length) return null;
  const list = (action: string) => {
    const n = new Map<string, number>();
    for (const f of found.filter((x) => x.action === action)) n.set(t(f.label), (n.get(t(f.label)) ?? 0) + (f.count ?? 1));
    return [...n].map(([k, v]) => (v > 1 ? `${k} ×${v}` : k)).join(", ");
  };
  const masked = list("masked"), flagged = list("flagged"), blocked = list("blocked");
  return (
    <Notice tone={blocked || flagged ? "warn" : "info"} title={t("Secretos detectados")}>
      <Stack gap={2}>
        {masked && <Text size="xs">{t("Enmascarados antes de guardar: {{v}}.", { v: masked })}</Text>}
        {flagged && <Text size="xs">{t("Marcados para revisar (no se han tocado): {{v}}.", { v: flagged })}</Text>}
        {blocked && <Text size="xs">{t("No se ha indexado porque el brain bloquea los secretos: {{v}}.", { v: blocked })}</Text>}
      </Stack>
    </Notice>
  );
}

/** Política de secretos del brain: qué hacer con lo que encuentra el detector y análisis en solo lectura de lo ya guardado. */
export default function Secrets({ brain }: { brain: Brain }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [mode, setMode] = useState(brain.secret_mode ?? "mask");
  const [allow, setAllow] = useState(brain.secret_allow ?? "");
  useEffect(() => { setMode(brain.secret_mode ?? "mask"); setAllow(brain.secret_allow ?? ""); }, [brain.slug, brain.secret_mode, brain.secret_allow]);
  const save = useMutation({ mutationFn: () => send<Brain>("PATCH", `brains/${brain.slug}`, { secret_mode: mode, secret_allow: allow }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brains"] }) });
  const scan = useMutation({ mutationFn: () => get<Scan>(`brains/${brain.slug}/secrets/scan`) });
  const changed = mode !== (brain.secret_mode ?? "mask") || allow !== (brain.secret_allow ?? "");
  const r = scan.data;
  return (
    <Stack gap="md">
      <Notice tone="info">{t("Antes de guardar una propuesta (también las de los agentes por MCP) o de indexar un documento, se buscan credenciales: claves de nube, tokens, claves privadas, JWT, cabeceras Authorization y contraseñas en URLs. Un valor aleatorio asignado a «password», «token» o «secret» se trata como posible y solo se marca. Ni la auditoría ni las notificaciones guardan el valor.")}</Notice>
      <Stack gap={4}>
        <SelectField label={t("Qué hacer con un secreto")} w={320} data={MODES.map((m) => ({ ...m, label: t(m.label) }))} value={mode} onChange={(v) => v && setMode(v)} allowDeselect={false} />
        <Text size="xs" c="dimmed">{t(HELP[mode] ?? "")}</Text>
      </Stack>
      <TextArea label={t("Excepciones")} autosize minRows={2} maxRows={8} value={allow} onChange={(e) => setAllow(e.currentTarget.value)}
        description={t("Una por línea. «rule:jwt» desactiva una regla; cualquier otra línea es una expresión regular y lo que encaje con ella no se trata como secreto. Las líneas con # son comentarios.")} />
      <MutationError error={save.error} />
      <Group gap="xs">
        <Btn kind="primary" icon="save" disabled={!changed} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn>
        <Btn icon="search" loading={scan.isPending} onClick={() => scan.mutate()}>{t("Analizar lo ya guardado")}</Btn>
      </Group>
      <Text size="xs" c="dimmed">{t("El análisis pasa el detector por las propuestas y los documentos indexados del brain, con las excepciones guardadas, sin cambiar nada. Sirve para ver aciertos y falsos positivos antes de cambiar la política. Lo que ya está en el grafo no se analiza.")}</Text>
      <MutationError error={scan.error} />
      {r && <Stack gap="xs">
        <Text size="sm">{t("Propuestas analizadas: {{p}}. Documentos analizados: {{d}}.", { p: r.proposals, d: r.documents })}{r.truncated ? ` ${t("Se ha parado al llegar al máximo de texto: faltan documentos.")}` : ""}</Text>
        {r.rules.length ? <>
          <DataTable fz="sm">
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Tipo")}</DataTable.Th><DataTable.Th>{t("Clase")}</DataTable.Th><DataTable.Th>{t("Apariciones")}</DataTable.Th><DataTable.Th>{t("En")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{r.rules.map((x) => (
              <DataTable.Tr key={x.rule}>
                <DataTable.Td>{t(x.label)} <Text span size="xs" c="dimmed" className="ms-data">{x.rule}</Text></DataTable.Td>
                <DataTable.Td>{x.certain ? <Pill size="xs" tone="danger">{t("seguro")}</Pill> : <Pill size="xs" tone="warn">{t("posible")}</Pill>}</DataTable.Td>
                <DataTable.Td>{x.count}</DataTable.Td>
                <DataTable.Td>{x.items}</DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable>
          <DataTable fz="sm">
            <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Dónde")}</DataTable.Th><DataTable.Th>{t("Tipo")}</DataTable.Th><DataTable.Th>{t("Texto anterior (el valor no se muestra)")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{r.items.flatMap((it) => it.findings.map((f, i) => (
              <DataTable.Tr key={`${it.kind}-${it.id}-${i}`}>
                <DataTable.Td>{i === 0 ? `${it.kind === "proposal" ? t("Propuesta") : t("Documento")} #${it.id} · ${it.title}` : ""}</DataTable.Td>
                <DataTable.Td>{t(f.label)}</DataTable.Td>
                <DataTable.Td><Text size="xs" className="ms-data">…{f.context}</Text></DataTable.Td>
              </DataTable.Tr>)))}</DataTable.Tbody>
          </DataTable>
          {r.items_truncated && <Text size="xs" c="dimmed">{t("Solo se listan los primeros 500 elementos; los recuentos sí son completos.")}</Text>}
        </> : <EmptyState>{t("No se ha encontrado ningún secreto.")}</EmptyState>}
      </Stack>}
    </Stack>
  );
}
