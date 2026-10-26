import { useTranslation } from "react-i18next";
import { Group, Text } from "@mantine/core";
import { Btn } from "./Btn";
import { SelectField } from "./Fields";

/** Paginación por desplazamiento: «1–50 de 492», anterior/siguiente y tamaño de página. */
export function Pager({ total, offset, limit, onChange, sizes = [25, 50, 100, 200] }:
  { total: number; offset: number; limit: number; onChange: (p: { offset: number; limit: number }) => void; sizes?: number[] }) {
  const { t } = useTranslation();
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <Group justify="space-between" gap="sm" wrap="wrap">
      <Text size="xs" c="dimmed">{total === 0 ? t("Sin resultados") : `${from}–${to} de ${total}`}</Text>
      <Group gap={6} wrap="wrap">
        <SelectField w={150} aria-label={t("Elementos por página")} allowDeselect={false} value={String(limit)} onChange={(v) => v && onChange({ offset: 0, limit: Number(v) })} data={sizes.map((n) => ({ value: String(n), label: t("{{n}} por página", { n: n }) }))} />
        <Btn disabled={offset <= 0} onClick={() => onChange({ offset: Math.max(0, offset - limit), limit })}>{t("Anterior")}</Btn>
        <Btn disabled={offset + limit >= total} onClick={() => onChange({ offset: offset + limit, limit })}>{t("Siguiente")}</Btn>
      </Group>
    </Group>
  );
}
