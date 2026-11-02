import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { get, send } from "../api";
import { ROLE } from "./TokensPanel";
import { Btn, DataState, DataTable, Modal, MutationError, Notice, SelectField, SettingsBody, SettingsGroup, SettingsRow } from "../ui";

type Digest = {
  mail: boolean; email: string | null; hour: number; weekday: number; timezone: string;
  brains: { slug: string; name: string; role: string; frequency: "daily" | "weekly" | "never" }[];
};

const browserZone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { return ""; } };
const zones = (): string[] => { try { return (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf?.("timeZone") ?? []; } catch { return []; } };

/** The periodic summary by email: per brain, daily, weekly or never, at the person's hour and time zone. Only counts and links. */
export function DigestSettings() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["my-digest"], queryFn: () => get<Digest>("me/digest") });
  const [draft, setDraft] = useState<Digest | null>(null);
  useEffect(() => { if (q.data) setDraft({ ...q.data, timezone: q.data.timezone || browserZone() }); }, [q.data]);
  const save = useMutation({ mutationFn: (d: Digest) => send<Digest>("PUT", "me/digest", { hour: d.hour, weekday: d.weekday, timezone: d.timezone,
    brains: Object.fromEntries(d.brains.map((b) => [b.slug, b.frequency])) }), onSuccess: (d) => qc.setQueryData(["my-digest"], d) });
  const [preview, setPreview] = useState<{ subject: string; body: string } | null>(null);
  const look = useMutation({ mutationFn: () => get<{ subject: string; body: string }>("me/digest/preview"), onSuccess: setPreview });
  const FREQ = [{ value: "never", label: t("Nunca") }, { value: "daily", label: t("Cada día") }, { value: "weekly", label: t("Cada semana") }];
  const DAYS = [t("lunes"), t("martes"), t("miércoles"), t("jueves"), t("viernes"), t("sábado"), t("domingo")];
  const all = zones();
  const zoneOptions = (all.length ? all : [draft?.timezone || "UTC"]).map((z) => ({ value: z, label: z }));
  const dirty = !!draft && !!q.data && JSON.stringify({ ...draft }) !== JSON.stringify({ ...q.data, timezone: q.data.timezone || browserZone() }) || (!!q.data && !q.data.timezone);
  const subscribed = q.data?.brains.some((b) => b.frequency !== "never");
  return (
    <DataState query={q}>
      {() => !draft ? null : <>
        <SettingsGroup title={t("Resumen por correo")} description={t("Un correo con lo que ha cambiado en tus brains: hechos nuevos e invalidados, documentos y, si curas, lo que espera tu decisión. Solo lleva recuentos y enlaces, nunca el contenido de las memorias. Si un brain no tiene novedades, no se envía.")}>
          <SettingsBody><Stack gap="sm">
            {!draft.mail && <Notice tone="warn">{t("El correo no está configurado en esta instancia: el resumen no se enviará hasta que un administrador lo configure.")}</Notice>}
            {draft.mail && !draft.email && <Notice tone="warn">{t("Tu cuenta no tiene correo: el resumen no se puede enviar.")}</Notice>}
            {draft.brains.length === 0 ? <Text size="sm" c="dimmed">{t("Todavía no tienes acceso a ningún brain.")}</Text> : (
              <DataTable fz="sm">
                <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Brain")}</DataTable.Th><DataTable.Th>{t("Tu rol")}</DataTable.Th><DataTable.Th w={200}>{t("Resumen")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
                <DataTable.Tbody>{draft.brains.map((b, i) => (
                  <DataTable.Tr key={b.slug}>
                    <DataTable.Td>{b.name}</DataTable.Td><DataTable.Td>{t(ROLE[b.role] ?? b.role)}</DataTable.Td>
                    <DataTable.Td><SelectField aria-label={t("Resumen de {{name}}", { name: b.name })} data={FREQ} value={b.frequency} allowDeselect={false}
                      onChange={(v) => setDraft({ ...draft, brains: draft.brains.map((x, j) => (j === i ? { ...x, frequency: (v ?? "never") as Digest["brains"][number]["frequency"] } : x)) })} /></DataTable.Td>
                  </DataTable.Tr>))}
                </DataTable.Tbody>
              </DataTable>)}
          </Stack></SettingsBody>
        </SettingsGroup>
        <SettingsGroup title={t("Cuándo")} description={t("Los resúmenes diarios salen cada día a esta hora; los semanales, el día elegido.")}>
          <SettingsRow label={t("Hora")}>
            <SelectField aria-label={t("Hora")} w={110} allowDeselect={false} value={String(draft.hour)} onChange={(v) => setDraft({ ...draft, hour: Number(v ?? 8) })}
              data={Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: `${String(h).padStart(2, "0")}:00` }))} />
          </SettingsRow>
          <SettingsRow label={t("Día de la semana")} help={t("Solo para los resúmenes semanales.")}>
            <SelectField aria-label={t("Día de la semana")} w={150} allowDeselect={false} value={String(draft.weekday)} onChange={(v) => setDraft({ ...draft, weekday: Number(v ?? 0) })}
              data={DAYS.map((d, i) => ({ value: String(i), label: d }))} />
          </SettingsRow>
          <SettingsRow label={t("Zona horaria")}>
            <SelectField aria-label={t("Zona horaria")} w={260} searchable allowDeselect={false} value={draft.timezone || null} data={zoneOptions}
              onChange={(v) => setDraft({ ...draft, timezone: v ?? "" })} />
          </SettingsRow>
          <SettingsBody><Stack gap="xs">
            <MutationError error={save.error ?? look.error} />
            <Group gap="xs">
              <Btn size="row" kind="primary" icon="check" loading={save.isPending} disabled={!dirty} onClick={() => save.mutate(draft)}>{t("Guardar")}</Btn>
              <Btn size="row" icon="info" loading={look.isPending} disabled={!subscribed || dirty} title={dirty ? t("Guarda primero los cambios.") : undefined} onClick={() => look.mutate()}>{t("Ver un ejemplo")}</Btn>
            </Group>
          </Stack></SettingsBody>
        </SettingsGroup>
        <Modal opened={!!preview} onClose={() => setPreview(null)} title={preview?.subject ?? ""} size="lg">
          <div className="ms-prose">{preview?.body}</div>
        </Modal>
      </>}
    </DataState>
  );
}
