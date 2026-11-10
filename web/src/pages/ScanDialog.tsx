import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useState } from "react";
import { Btn, DialogActions, Modal, MutationError, NumberField } from "../ui";

/** Starting an analysis that asks the engine or the decider about many entities (summaries, entity types): how many, what it costs, and
 *  «Analyze». The same dialog wherever such an analysis is started, so the view's bar keeps a single «Analyze…» button. */
export function ScanDialog({ opened, onClose, title, cost, initial, max = 1000, pending, error, onRun }:
  { opened: boolean; onClose: () => void; title: string; cost: string; initial: number; max?: number; pending: boolean; error: unknown; onRun: (limit: number) => Promise<unknown> }) {
  const { t } = useTranslation();
  const [limit, setLimit] = useState<number | string>(initial);
  return (
    <Modal opened={opened} onClose={onClose} title={title}>
      <Stack gap="sm">
        <Text size="sm">{cost}</Text>
        <NumberField label={t("Entidades a analizar")} min={1} max={max} value={limit} onChange={setLimit} data-autofocus />
        <MutationError error={error} />
        <DialogActions>
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind="primary" icon="search" loading={pending} disabled={!Number(limit)} onClick={() => onRun(Number(limit)).then(onClose, () => undefined)}>{t("Analizar")}</Btn>
        </DialogActions>
      </Stack>
    </Modal>
  );
}
