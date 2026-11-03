import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Btn, MutationError, Modal, SelectField } from "../ui";
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
      <Stack>
        <Text size="sm" c="dimmed">{t("Tipo actual: {{types}}.", { types: current.length ? current.join(", ") : t("(sin tipo)") })} {t("Solo se ofrecen los tipos de la ontología del brain. El cambio se puede deshacer en Vocabulario → Tipos de entidad → Cambios recientes.")}</Text>
        <SelectField label={t("Nuevo tipo")} searchable value={type} onChange={setType} nothingFoundMessage={t("Ningún tipo coincide")}
          data={types.filter((i) => !(current.length === 1 && current[0] === i.name)).map((i) => i.name)} />
        {desc && <Text size="xs" c="dimmed">{desc}</Text>}
        {q.data && types.length === 0 && <Text size="sm" c="dimmed">{t("Este brain no tiene tipos en su ontología. Aplica un paquete en Vocabulario → Ontología.")}</Text>}
        <MutationError error={error} />
        <Group justify="flex-end"><Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind="primary" icon="check" disabled={!type} loading={pending} onClick={() => type && onPick(type)}>{t("Cambiar tipo")}</Btn></Group>
      </Stack>
    </Modal>
  );
}
