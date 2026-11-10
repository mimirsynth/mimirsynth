import { useTranslation } from "react-i18next";
import { fmt } from "../api";
import { Btn, DataTable, Pill } from "../ui";

export type VocabOp = { id: number; kind: string; summary: string; status: string; created_at: string };

/** The log of vocabulary changes (merges, alias clean-ups, type changes) as one table: when, what, and its state or «Undo». Only the last
 *  change still applied can be undone (`lastApplied`), and only by whoever may (`canRevert`). The same in every place that lists them. */
export function OpsTable({ ops, lastApplied, canRevert, reverting, onRevert, label }:
  { ops: VocabOp[]; lastApplied?: number; canRevert: boolean; reverting: boolean; onRevert: (id: number) => void; label: string }) {
  const { t } = useTranslation();
  return (
    <DataTable aria-label={label}>
      <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Fecha")}</DataTable.Th><DataTable.Th>{t("Cambio")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
      <DataTable.Tbody>{ops.map((o) => (
        <DataTable.Tr key={o.id}>
          <DataTable.Td className="ms-data">{fmt(o.created_at)}</DataTable.Td>
          <DataTable.Td>{o.summary}</DataTable.Td>
          <DataTable.Td>{o.status === "reverted" ? <Pill>{t("deshecho")}</Pill> : canRevert && o.id === lastApplied
            ? <Btn size="row" icon="undo" loading={reverting} onClick={() => onRevert(o.id)}>{t("Deshacer")}</Btn> : null}</DataTable.Td>
        </DataTable.Tr>))}</DataTable.Tbody>
    </DataTable>
  );
}
