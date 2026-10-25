import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import AdminProviders from "./AdminProviders";
import { Btn, DataState, MutationError, Notice, NumberField, PasswordField, SelectField, SettingsGroup, SettingsRow, TextField } from "../ui";

type Item = { key: string; group: string; group_label: string; label: string; help: string; type: "int" | "float" | "str" | "url" | "choice"; choices?: { value: string; label: string }[]; unit: string; min: number | null; max: number | null; value: string | number; default: string | number; changed: boolean };
type Data = { groups: { key: string; label: string }[]; items: Item[]; secrets: Record<string, { set: boolean; changed: boolean }> };

const GROUP_HELP: Record<string, string> = {
  general: T("Preferencias generales de la instancia."),
  security: T("Cómo se protegen las cuentas con contraseña: longitud mínima, bloqueo tras intentos fallidos y caducidad de los enlaces."),
  mail: T("Servidor de correo saliente. Se usa para enviar invitaciones y enlaces de recuperación de contraseña."),
  identity: T("Datos comunes a todos los proveedores de inicio de sesión."),
  docs: T("Límites de la memoria documental: qué se acepta al subir o escanear."),
  recall: T("Cómo se buscan y mezclan los pasajes de documentos con los hechos cuando un agente pide contexto."),
  ingest: T("Reintentos de la ingesta y cuánto tiempo se conservan los trabajos."),
};

/** Un ajuste: el control se guarda con «Guardar» (solo aparece si ha cambiado) y «Restaurar» vuelve al valor por defecto. */
function ItemRow({ it, onDone }: { it: Item; onDone: () => void }) {
  const { t } = useTranslation();
  const [v, setV] = useState<string | number>(it.value);
  const dirty = String(v) !== String(it.value);
  const save = useMutation({ mutationFn: () => send("PUT", `settings/${it.key}`, { value: v }), onSuccess: onDone });
  const reset = useMutation({ mutationFn: () => send("DELETE", `settings/${it.key}`), onSuccess: () => { onDone(); } });
  const label = it.unit ? `${t(it.label)} (${t(it.unit)})` : t(it.label);
  return (
    <SettingsRow label={t(it.label)} help={<>{t(it.help)}{it.unit && ` (${t(it.unit)})`}</>}>
      {it.type === "choice"
        ? <SelectField aria-label={label} allowDeselect={false} value={String(v)} data={(it.choices ?? []).map((c) => ({ ...c, label: t(c.label) }))} onChange={(x) => setV(x ?? "")} />
        : it.type === "int" || it.type === "float"
          ? <NumberField aria-label={label} value={v as number} min={it.min ?? undefined} max={it.max ?? undefined} decimalScale={it.type === "float" ? 2 : 0} step={it.type === "float" ? 0.01 : 1} onChange={(n) => setV(n === "" ? "" : Number(n))} />
          : <TextField aria-label={label} value={String(v)} placeholder={it.type === "url" ? "https://…" : undefined} onChange={(e) => setV(e.currentTarget.value)} />}
      <MutationError error={save.error ?? reset.error} />
      {(dirty || it.changed) && (
        <Group gap={6} align="center">
          {dirty && <Btn size="row" kind="primary" disabled={v === ""} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn>}
          {dirty && <Btn size="row" kind="ghost" onClick={() => setV(it.value)}>{t("Cancelar")}</Btn>}
          {!dirty && it.changed && <Btn size="row" icon="undo" loading={reset.isPending} onClick={() => { reset.mutate(); setV(it.default); }}>{t("Restaurar")}</Btn>}
          {!dirty && it.changed && <Text size="xs" c="dimmed">{t("Por defecto:")} {String(it.default) || t("vacío")}</Text>}
        </Group>)}
    </SettingsRow>
  );
}

/** Secreto: nunca se muestra; se escribe uno nuevo o se borra el guardado. */
function SecretItem({ k, label, help, state, onDone }: { k: string; label: string; help: string; state: { set: boolean; changed: boolean }; onDone: () => void }) {
  const { t } = useTranslation();
  const [v, setV] = useState("");
  const save = useMutation({ mutationFn: (value: string) => send("PUT", `settings/secret/${k}`, { value }), onSuccess: () => { setV(""); onDone(); } });
  return (
    <SettingsRow label={label} help={help}>
      <PasswordField aria-label={label} value={v} placeholder={state.set ? t("Guardado (escribe para cambiarlo)") : t("Sin definir")} autoComplete="new-password" onChange={(e) => setV(e.currentTarget.value)} />
      <MutationError error={save.error} />
      {(v || state.changed) && (
        <Group gap={6} align="center">
          {v && <Btn size="row" kind="primary" loading={save.isPending} onClick={() => save.mutate(v)}>{t("Guardar")}</Btn>}
          {v && <Btn size="row" kind="ghost" onClick={() => setV("")}>{t("Cancelar")}</Btn>}
          {!v && state.changed && <Btn size="row" icon="trash" loading={save.isPending} onClick={() => save.mutate("")}>{t("Quitar")}</Btn>}
        </Group>)}
    </SettingsRow>
  );
}

/** Envía un correo de prueba con la configuración guardada. */
function MailCheck() {
  const { t } = useTranslation();
  const [to, setTo] = useState("");
  const test = useMutation({ mutationFn: () => send("POST", "settings/smtp/test", { to }) });
  return (
    <SettingsRow label={t("Correo de prueba")} help={t("Envía un mensaje con la configuración guardada para comprobar que funciona.")}>
      <TextField aria-label={t("Enviar un correo de prueba a")} type="email" placeholder={t("tu@correo.com")} value={to} onChange={(e) => setTo(e.currentTarget.value)} />
      <Group gap={6}><Btn size="row" icon="refresh" loading={test.isPending} disabled={!to} onClick={() => test.mutate()}>{t("Enviar prueba")}</Btn></Group>
      <MutationError error={test.error} />
      {test.isSuccess && <Notice tone="success">{t("Correo enviado a")} {to}{t(". Revisa la bandeja (y el spam).")}</Notice>}
    </SettingsRow>
  );
}

/** Una sección de ajustes de la instancia (seguridad, correo, identidad, documentos, recuerdo o ingesta). Los cambios se aplican sin reiniciar. */
export default function AdminSettings({ group }: { group: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: () => get<Data>("settings") });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["settings"] }); qc.invalidateQueries({ queryKey: ["config"] }); qc.invalidateQueries({ queryKey: ["admin-users"] }); };
  return (
    <DataState query={q}>
      {(d) => {
        const g = d.groups.find((x) => x.key === group) ?? d.groups[0];
        return (<>
          {g.key === "identity" && <AdminProviders />}
          <SettingsGroup key={g.key} title={t(g.label)} description={t(GROUP_HELP[g.key])}>
            {d.items.filter((i) => i.group === g.key).map((it) => <ItemRow key={`${it.key}:${String(it.value)}`} it={it} onDone={refresh} />)}
            {g.key === "mail" && <>
              <SecretItem k="smtp_password" label={t("Contraseña SMTP")} help={t("Se guarda cifrada y no se vuelve a mostrar.")} state={d.secrets.smtp_password} onDone={refresh} />
              <MailCheck />
            </>}
          </SettingsGroup></>);
      }}
    </DataState>
  );
}
