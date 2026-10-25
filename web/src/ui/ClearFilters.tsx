import { useTranslation } from "react-i18next";
import { Group } from "@mantine/core";
import { Btn } from "./Btn";

/** Enlace «Quitar todos los filtros» que aparece solo si hay alguno activo; con la cuenta de filas visibles. */
export function ClearFilters({ active, onClear, shown, total }: { active: boolean; onClear: () => void; shown?: number; total?: number }) {
  const { t } = useTranslation();
  if (!active) return null;
  return <Group><Btn kind="ghost" size="row" onClick={onClear}>{t("Quitar todos los filtros")}{shown !== undefined && total !== undefined ? ` (${shown} de ${total})` : ""}</Btn></Group>;
}
