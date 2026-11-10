import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Btn, DialogActions, EmptyState, MutationError, Modal, SelectField } from "../ui";
import { get } from "../api";

type TypeItem = { name: string; description: string; in_ontology: boolean };

/** Picks the type of one entity among those of the brain's ontology (the same closed list the corrector uses, no free text). */
export function TypeDialog({ graph, opened, name, current, onClose, onPick, pending, error }: {
  graph: string; opened: boolean; name: string; current: string[]; onClose: () => void; onPick: (type: string) => void; pending: boolean; error: unknown }) {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["vocab-types", graph], enabled: opened, queryFn: () => get<{ items: TypeItem[] }>("vocab/types", { graph }) });
  const types = (q.data?.items ?? []).filter((i) => i.in_ontology).sort((a, b) => a.name.localeCompare(b.name));
  const [type, setType] = useState<string | null>(null);
  useEffect(() => { if (opened) setType(null); }, [opened]);
  const desc = types.find((i) => i.name === type)?.description;
  return (
    <Modal opened={opened} onClose={onClose} title={t("Cambiar el tipo de «{{name}}»", { name })}>
      <Stack gap="sm">
        <Text size="sm">{t("Tipo actual: {{types}}.", { types: current.length ? current.join(", ") : t("(sin tipo)") })} {t("Solo se ofrecen los tipos de la ontología del brain. El cambio se puede deshacer en Vocabulario → Tipos de entidad → Cambios recientes.")}</Text>
        {q.data && types.length === 0 ? <EmptyState>{t("Este brain no tiene tipos en su ontología. Aplica un paquete en Vocabulario → Ontología.")}</EmptyState>
          : <SelectField label={t("Nuevo tipo")} description={desc} searchable value={type} onChange={setType} nothingFoundMessage={t("Ningún tipo coincide")}
            data={types.filter((i) => !(current.length === 1 && current[0] === i.name)).map((i) => i.name)} />}
        <MutationError error={error} />
        <DialogActions>
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind="primary" icon="check" disabled={!type} loading={pending} onClick={() => type && onPick(type)}>{t("Cambiar tipo")}</Btn>
        </DialogActions>
      </Stack>
    </Modal>
  );
}
