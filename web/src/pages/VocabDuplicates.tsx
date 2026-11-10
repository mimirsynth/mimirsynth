import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { Block, Btn, Check, DataTable, DialogActions, Loading, Modal, Notice, Pill, MutationError, EmptyState, ViewBar } from "../ui";
import { OpsTable, type VocabOp } from "./VocabOps";

type Member = { uuid: string; name: string; labels: string[]; degree: number };
type Group_ = { key: string; members: Member[] };
type Preview = { keeper: { uuid: string; name: string }; items: { uuid: string; name: string; facts: number; mentions: number; between: number; repeated_facts: number }[] };

/** Content quality → Duplicates: groups of entities with the same name but for a version or case. Each group is a block with its table
 *  (which one stays, which ones merge into it) and its two decisions; under them, the recent merges and what was set aside. */
export default function VocabDuplicates({ graph, groups, ignored, isAdmin }: { graph: string; groups: Group_[]; ignored: string[]; isAdmin: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [keeper, setKeeper] = useState<Record<string, string>>({});
  const [off, setOff] = useState<Record<string, boolean>>({});          // uuid -> excluido de la fusión
  const [dlg, setDlg] = useState<{ keeper: string; merge: string[] } | null>(null);
  const { data: ops } = useQuery({ queryKey: ["vocab-types", graph], queryFn: () => get<{ ops: VocabOp[] }>("vocab/types", { graph }) });
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
    <>
      <ViewBar title={t("Duplicados")} meta={groups.length ? t("{{n}} grupos", { n: groups.length }) : undefined}
        help={<>{t("Grupos de entidades con el mismo nombre salvo versión o mayúsculas. No todos son duplicados (Debian 12 y Debian 13 no lo son): marca cuáles fusionar y cuál es la principal. Fusionar mueve los hechos y menciones a la principal; el duplicado queda oculto, no borrado, y se puede deshacer. Antes se guarda una copia del grafo. Fusiona un administrador.")}{" "}
          {t("El nombre fusionado se guarda en la principal, así que lo que se ingiera después con ese nombre irá a ella; los alias de relaciones, en cambio, están en")}{" "}
          <Btn kind="link" component={Link} to="/vocabulario?tab=ali">{t("Vocabulario → Alias")}</Btn>.</>} />
      <MutationError error={ignore.error ?? unignore.error} />
      {groups.length === 0 && <EmptyState>{t("No hay posibles duplicados.")}</EmptyState>}
      {groups.map((g) => {
        const k = keeperOf(g);
        const sel = g.members.filter((m) => m.uuid !== k && !off[m.uuid]);
        return (
          <Block key={g.key} title={g.key} count={g.members.length}
            actions={isAdmin && <>
              <Btn size="row" icon="close" loading={ignore.isPending && ignore.variables === g.key} onClick={() => ignore.mutate(g.key)}>{t("No son duplicados")}</Btn>
              <Btn size="row" icon="check" disabled={sel.length === 0} onClick={() => { merge.reset(); setDlg({ keeper: k, merge: sel.map((m) => m.uuid) }); }}>{t("Revisar fusión ({{n}})", { n: sel.length })}</Btn>
            </>}>
            <DataTable aria-label={g.key}>
              <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Nombre")}</DataTable.Th><DataTable.Th>{t("Tipo")}</DataTable.Th><DataTable.Th>{t("Hechos")}</DataTable.Th>
                {isAdmin && <DataTable.Th>{t("Fusionar")}</DataTable.Th>}<DataTable.Th>{t("Principal")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
              <DataTable.Tbody>{g.members.map((m) => (
                <DataTable.Tr key={m.uuid}>
                  <DataTable.Td><Link to={`/entidad/${m.uuid}`}>{m.name}</Link></DataTable.Td>
                  <DataTable.Td>{m.labels.length ? m.labels.map((l) => <Pill key={l}>{l}</Pill>) : "—"}</DataTable.Td>
                  <DataTable.Td className="ms-data">{m.degree}</DataTable.Td>
                  {isAdmin && <DataTable.Td>{m.uuid !== k && <Check checked={!off[m.uuid]} onChange={(e) => setOff({ ...off, [m.uuid]: !e.currentTarget.checked })} aria-label={t("Fusionar {{name}}", { name: m.name })} />}</DataTable.Td>}
                  <DataTable.Td>{m.uuid === k ? <Pill tone="success">{t("principal")}</Pill> : isAdmin ? <Btn size="row" onClick={() => setKeeper({ ...keeper, [g.key]: m.uuid })}>{t("Hacer principal")}</Btn> : null}</DataTable.Td>
                </DataTable.Tr>))}</DataTable.Tbody>
            </DataTable>
          </Block>);
      })}
      {merges.length > 0 && <Block title={t("Fusiones recientes")} count={merges.length} help={t("Solo se puede deshacer la última, mientras no haya otro cambio de vocabulario después.")}>
        <MutationError error={revert.error} />
        <OpsTable ops={merges} lastApplied={lastApplied?.id} canRevert={isAdmin} reverting={revert.isPending} onRevert={(id) => revert.mutate(id)} label={t("Fusiones recientes")} />
      </Block>}
      {ignored.length > 0 && <Block title={t("Descartados como «no son duplicados»")} count={ignored.length}>
        <DataTable aria-label={t("Descartados como «no son duplicados»")}>
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Grupo")}</DataTable.Th>{isAdmin && <DataTable.ActionsHead />}</DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{ignored.map((k) => <DataTable.Tr key={k}><DataTable.Td>{k}</DataTable.Td>
            {isAdmin && <DataTable.Td><Btn size="row" icon="undo" loading={unignore.isPending && unignore.variables === k} onClick={() => unignore.mutate(k)}>{t("Restaurar")}</Btn></DataTable.Td>}</DataTable.Tr>)}</DataTable.Tbody>
        </DataTable>
      </Block>}

      <Modal opened={!!dlg} onClose={() => setDlg(null)} title={t("Fusionar entidades duplicadas")} size="lg">
        <Stack gap="sm">
          {!preview.data && <Loading label={t("Calculando…")} />}
          {preview.data && <>
            <Text size="sm">{t("Todo lo de las entidades marcadas pasa a")} <b>{preview.data.keeper.name}</b>.</Text>
            <DataTable><DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Se fusiona")}</DataTable.Th><DataTable.Th>{t("Hechos")}</DataTable.Th><DataTable.Th>{t("Menciones")}</DataTable.Th><DataTable.Th>{t("Entre ambas")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
              <DataTable.Tbody>{preview.data.items.map((i) => <DataTable.Tr key={i.uuid}><DataTable.Td>{i.name}</DataTable.Td><DataTable.Td className="ms-data">{i.facts}{i.repeated_facts > 0 && t(" ({{repeated_facts}} repetidos)", { repeated_facts: i.repeated_facts })}</DataTable.Td><DataTable.Td className="ms-data">{i.mentions}</DataTable.Td><DataTable.Td className="ms-data">{i.between}</DataTable.Td></DataTable.Tr>)}</DataTable.Tbody></DataTable>
            <Notice tone="warn">{t("Cambia datos del grafo. Se guarda una copia previa y la fusión se deshace desde «Fusiones recientes» mientras no hagas otro cambio de vocabulario después. Los hechos que queden repetidos no se eliminan.")}</Notice>
          </>}
          <MutationError error={merge.error} />
          <DialogActions><Btn kind="ghost" onClick={() => setDlg(null)}>{t("Cancelar")}</Btn><Btn kind="danger" icon="check" disabled={!preview.data} loading={merge.isPending} onClick={() => merge.mutate()}>{t("Fusionar")}</Btn></DialogActions>
        </Stack>
      </Modal>
    </>
  );
}
