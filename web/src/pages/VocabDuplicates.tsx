import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, Check, DataTable, FillArea, Modal, Notice, Panel, Pill, MutationError, EmptyState } from "../ui";

type Member = { uuid: string; name: string; labels: string[]; degree: number };
type Group_ = { key: string; members: Member[] };
type Preview = { keeper: { uuid: string; name: string }; items: { uuid: string; name: string; facts: number; mentions: number; between: number; repeated_facts: number }[] };
type Ops = { ops: { id: number; kind: string; summary: string; status: string; created_at: string }[] };

export default function VocabDuplicates({ graph, groups, ignored, isAdmin }: { graph: string; groups: Group_[]; ignored: string[]; isAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [keeper, setKeeper] = useState<Record<string, string>>({});
  const [off, setOff] = useState<Record<string, boolean>>({});          // uuid -> excluido de la fusión
  const [dlg, setDlg] = useState<{ keeper: string; merge: string[] } | null>(null);
  const { data: ops } = useQuery({ queryKey: ["vocab-types", graph], queryFn: () => get<Ops>("vocab/types", { graph }) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["vocab", graph] }); qc.invalidateQueries({ queryKey: ["vocab-types", graph] }); };
  const preview = useQuery({ queryKey: ["dup-preview", graph, dlg], enabled: !!dlg, queryFn: () => send<Preview>("POST", "vocab/duplicates/preview", dlg, { graph }) });
  const merge = useMutation({ mutationFn: () => send("POST", "vocab/duplicates/merge", dlg, { graph }), onSuccess: () => { setDlg(null); refresh(); } });
  const ignore = useMutation({ mutationFn: (key: string) => send("POST", "vocab/duplicates/ignore", { key }, { graph }), onSuccess: refresh });
  const unignore = useMutation({ mutationFn: (key: string) => send("DELETE", "vocab/duplicates/ignore", undefined, { graph, key }), onSuccess: refresh });
  const revert = useMutation({ mutationFn: (id: number) => send("POST", `vocab/ops/${id}/revert`, undefined, { graph }), onSuccess: refresh });
  const lastApplied = ops?.ops.find((o) => o.status === "applied");
  const merges = (ops?.ops ?? []).filter((o) => o.kind === "entity.merge");
  const keeperOf = (g: Group_) => keeper[g.key] ?? g.members[0].uuid;       // por defecto, la de más grado

  return (
    <FillArea>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          {t("Grupos de entidades con el mismo nombre salvo versión o mayúsculas. No todos son duplicados (Debian 12 y Debian 13 no lo son): marca cuáles fusionar y cuál es la principal. Fusionar mueve los hechos y menciones a la principal; el duplicado queda oculto, no borrado, y se puede deshacer. Antes se guarda una copia del grafo.")}
</Text>
        {groups.length === 0 && <Text c="dimmed">{t("Sin candidatos.")}</Text>}
        {groups.map((g) => {
          const k = keeperOf(g);
          const sel = g.members.filter((m) => m.uuid !== k && !off[m.uuid]);
          return (
            <Panel key={g.key} withBorder p="xs">
              <DataTable fz="sm">
                <DataTable.Thead><DataTable.Tr><DataTable.Th w={150}>{t("Principal")}</DataTable.Th>{isAdmin && <DataTable.Th w={90}>{t("Fusionar")}</DataTable.Th>}<DataTable.Th>{t("Nombre")}</DataTable.Th><DataTable.Th>{t("Tipo")}</DataTable.Th><DataTable.Th>{t("Hechos")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
                <DataTable.Tbody>{g.members.map((m) => (
                  <DataTable.Tr key={m.uuid}>
                    <DataTable.Td>{m.uuid === k ? <Pill size="xs" tone="success">{t("principal")}</Pill> : isAdmin ? <Btn size="row" onClick={() => setKeeper({ ...keeper, [g.key]: m.uuid })}>{t("Hacer principal")}</Btn> : null}</DataTable.Td>
                    {isAdmin && <DataTable.Td>{m.uuid !== k && <Check checked={!off[m.uuid]} onChange={(e) => setOff({ ...off, [m.uuid]: !e.currentTarget.checked })} aria-label={t("Fusionar {{name}}", { name: m.name })} />}</DataTable.Td>}
                    <DataTable.Td><Text fw={m.uuid === k ? 600 : 400}>{m.name}</Text></DataTable.Td>
                    <DataTable.Td>{m.labels.length ? m.labels.map((l) => <Pill key={l} size="xs">{l}</Pill>) : <Text span c="dimmed">—</Text>}</DataTable.Td>
                    <DataTable.Td>{m.degree}</DataTable.Td>
                  </DataTable.Tr>))}</DataTable.Tbody>
              </DataTable>
              {isAdmin && <Group justify="flex-end" mt="xs">
                <Btn size="row" icon="close" loading={ignore.isPending} onClick={() => ignore.mutate(g.key)}>{t("No son duplicados")}</Btn>
                <Btn size="row" icon="check" disabled={sel.length === 0} onClick={() => { merge.reset(); setDlg({ keeper: k, merge: sel.map((m) => m.uuid) }); }}>{t("Revisar fusión (")}{sel.length})</Btn>
              </Group>}
            </Panel>);
        })}
        {merges.length > 0 && (
          <Stack gap={4}>
            <Text fw={600} size="sm">{t("Fusiones recientes")}</Text>
            <DataTable fz="sm"><DataTable.Tbody>{merges.map((o) => (
              <DataTable.Tr key={o.id}><DataTable.Td w={140}>{fmt(o.created_at)}</DataTable.Td><DataTable.Td>{o.summary}</DataTable.Td>
                <DataTable.Td w={140}>{o.status === "reverted" ? <Pill size="xs">{t("deshecho")}</Pill> : isAdmin && o.id === lastApplied?.id
                  ? <Btn size="row" icon="undo" loading={revert.isPending} onClick={() => revert.mutate(o.id)}>{t("Deshacer")}</Btn> : null}</DataTable.Td></DataTable.Tr>))}</DataTable.Tbody></DataTable>
            <MutationError error={revert.error} />
          </Stack>)}
        {ignored.length > 0 && (
          <Stack gap={4}>
            <Text fw={600} size="sm">{t("Descartados como «no son duplicados» (")}{ignored.length})</Text>
            <Group gap={6}>{ignored.map((k) => <Pill key={k}>{k}{isAdmin && <> · <Btn kind="link" onClick={() => unignore.mutate(k)}>{t("restaurar")}</Btn></>}</Pill>)}</Group>
          </Stack>)}
      </Stack>

      <Modal opened={!!dlg} onClose={() => setDlg(null)} title={t("Fusionar entidades duplicadas")} centered size="lg">
        <Stack>
          {!preview.data && <EmptyState>{t("Calculando…")}</EmptyState>}
          {preview.data && <>
            <Text size="sm">{t("Todo lo de las entidades marcadas pasa a")} <b>{preview.data.keeper.name}</b>.</Text>
            <DataTable fz="sm"><DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Se fusiona")}</DataTable.Th><DataTable.Th>{t("Hechos")}</DataTable.Th><DataTable.Th>{t("Menciones")}</DataTable.Th><DataTable.Th>{t("Entre ambas")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
              <DataTable.Tbody>{preview.data.items.map((i) => <DataTable.Tr key={i.uuid}><DataTable.Td>{i.name}</DataTable.Td><DataTable.Td>{i.facts}{i.repeated_facts > 0 && t(" ({{repeated_facts}} repetidos)", { repeated_facts: i.repeated_facts })}</DataTable.Td><DataTable.Td>{i.mentions}</DataTable.Td><DataTable.Td>{i.between}</DataTable.Td></DataTable.Tr>)}</DataTable.Tbody></DataTable>
            <Notice tone="warn">{t("Cambia datos del grafo. Se guarda una copia previa y la fusión se deshace desde «Fusiones recientes» mientras no hagas otro cambio de vocabulario después. Los hechos que queden repetidos no se eliminan.")}</Notice>
          </>}
          <MutationError error={merge.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setDlg(null)}>{t("Cancelar")}</Btn><Btn kind="danger" icon="check" disabled={!preview.data} loading={merge.isPending} onClick={() => merge.mutate()}>{t("Fusionar")}</Btn></Group>
        </Stack>
      </Modal>
    </FillArea>
  );
}
