import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, Check, ConfirmDialog, DataState, DataTable, EmptyState, ListCard, Modal, MutationError, Notice, PasswordField, Pill, SelectField, SettingsBody, SettingsGroup, TextField } from "../ui";
import { SEVERITY } from "./Notifications";
import AdminSettings from "./AdminSettings";

type Channel = { id: number; name: string; kind: string; config: Record<string, string>; has_secret: boolean; enabled: boolean; min_severity: string; events: string[]; last: { status: string; at: string; error: string } | null };
type Catalog = { events: { key: string; severity: string; label: string }[]; kinds: Record<string, { config: string[]; secret: string | null }> };
type Draft = { name: string; kind: string; config: Record<string, string>; secret: string; enabled: boolean; min_severity: string; events: string[] };
type Delivery = { id: number; channel: string; kind: string; status: string; attempts: number; error: string; title: string; severity: string; created_at: string; sent_at: string | null };

const KINDS = [
  { value: "telegram", label: T("Telegram") }, { value: "ntfy", label: T("ntfy") }, { value: "gotify", label: T("Gotify") },
  { value: "webhook", label: T("Webhook") }, { value: "email", label: T("Correo") },
];
const FIELD_LABEL: Record<string, { label: string; hint?: string; ph?: string }> = {
  to: { label: T("Destinatarios"), hint: T("Direcciones separadas por comas. Se envían con el servidor SMTP de Administración → Correo."), ph: "admin@example.com" },
  url: { label: T("URL del servidor"), ph: "https://" },
  topic: { label: T("Tema"), hint: T("El tema de ntfy al que se publica. Quien lo conozca puede leerlo en un servidor público: usa un nombre difícil de adivinar o un servidor propio.") },
  chat_id: { label: T("Chat"), hint: T("Identificador del chat, grupo o canal (los grupos empiezan por -100…). El bot debe estar dentro."), ph: "-1001234567890" },
  thread_id: { label: T("Tema del grupo (opcional)"), hint: T("Número del tema si el grupo usa temas.") },
  api_url: { label: T("Servidor de la API (opcional)"), hint: T("Solo si usas un servidor propio de la API de bots. Vacío = el de Telegram."), ph: "https://api.telegram.org" },
};
const SECRET_LABEL: Record<string, string> = { telegram: T("Token del bot"), ntfy: T("Token de acceso (opcional)"), gotify: T("Token de la aplicación"), webhook: T("Clave de firma HMAC (opcional)") };
const SEVS = ["info", "warning", "critical"];
// Descripciones de los eventos que envía el servidor (se traducen aquí: el servidor solo manda la clave en castellano).
export const EVENT_LABELS = [
  T("Un modelo de IA (LLM, embeddings o decisor) no responde"), T("Una propuesta aprobada no se pudo ingerir tras los reintentos"), T("Un trabajo en segundo plano ha fallado"),
  T("Una fuente de documentos no se pudo sincronizar"), T("El grafo (FalkorDB) no responde"), T("Hay una versión nueva de MimirSynth"), T("Una cuenta se ha bloqueado por intentos fallidos"),
  T("Un cambio de modelo de embeddings lleva tiempo sin terminar y sus vectores sombra ocupan memoria"),
  T("Las consultas de referencia de un brain empeoran tras un cambio de modelo de embeddings"),
  T("Hay hechos vigentes que se contradicen en una relación de un solo valor"), T("Un token de API caduca en pocos días"),
  T("Hay hechos vigentes que han superado la vida útil de su relación y piden revisión"), T("Un brain ha gastado el 80 % o el 100 % de su presupuesto de IA del mes"),
  T("Un webhook de entrada ha llegado a su tope diario de propuestas"),
];

function ChannelForm({ initial, id, cat, onClose }: { initial: Draft; id: number | null; cat: Catalog; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [d, setD] = useState<Draft>(initial);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => id === null ? send("POST", "notifications/channels", d) : send("PUT", `notifications/channels/${id}`, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["notify-channels"] }); onClose(); } });
  const fields = cat.kinds[d.kind]?.config ?? [];
  const needsSecret = d.kind === "telegram" || d.kind === "gotify";
  const ok = d.name.trim() && (d.kind === "email" ? d.config.to?.trim() : d.kind === "telegram" ? d.config.chat_id?.trim() && (id !== null || d.secret) : d.kind === "ntfy" ? d.config.topic?.trim() : d.config.url?.trim()) && (!needsSecret || id !== null || d.secret);
  return (
    <Stack gap="xs">
      <TextField label={t("Nombre")} placeholder={t("Telegram del homelab")} value={d.name} onChange={(e) => set("name", e.currentTarget.value)} data-autofocus />
      {id === null && <SelectField label={t("Tipo")} data={KINDS.map((k) => ({ value: k.value, label: t(k.label) }))} value={d.kind} allowDeselect={false} onChange={(v) => v && setD({ ...d, kind: v, config: {}, secret: "" })} />}
      {fields.map((f) => <TextField key={f} label={t(FIELD_LABEL[f]?.label ?? f)} description={FIELD_LABEL[f]?.hint ? t(FIELD_LABEL[f].hint!) : undefined} placeholder={FIELD_LABEL[f]?.ph} value={d.config[f] ?? ""} onChange={(e) => set("config", { ...d.config, [f]: e.currentTarget.value })} />)}
      {cat.kinds[d.kind]?.secret && <PasswordField label={t(SECRET_LABEL[d.kind] ?? "Secreto")} description={id !== null ? t("Vacío = conservar el guardado. Nunca se muestra.") : undefined} autoComplete="off" value={d.secret} onChange={(e) => set("secret", e.currentTarget.value)} />}
      <SelectField label={t("Severidad mínima")} description={t("Por debajo de esta severidad no se envía nada por este canal.")} data={SEVS.map((s) => ({ value: s, label: t(SEVERITY[s].label) }))} value={d.min_severity} allowDeselect={false} onChange={(v) => v && set("min_severity", v)} />
      <Stack gap={4}>
        <Text size="sm" fw={500}>{t("Eventos")}</Text>
        <Text size="xs" c="dimmed">{t("Sin ninguno marcado, el canal recibe todos.")}</Text>
        {cat.events.map((e) => <Check key={e.key} label={t(e.label)} checked={d.events.includes(e.key)} onChange={(ev) => set("events", ev.currentTarget.checked ? [...d.events, e.key] : d.events.filter((x) => x !== e.key))} />)}
      </Stack>
      <Check label={t("Canal activo")} checked={d.enabled} onChange={(e) => set("enabled", e.currentTarget.checked)} />
      <MutationError error={save.error} />
      <Group justify="flex-end"><Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn><Btn kind="primary" icon="save" disabled={!ok} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn></Group>
    </Stack>
  );
}

function Test({ c }: { c: Channel }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const test = useMutation({ mutationFn: () => send<{ ok: boolean; error?: string }>("POST", `notifications/channels/${c.id}/test`), onSettled: () => qc.invalidateQueries({ queryKey: ["notify-channels"] }) });
  return (
    <Stack gap={4}>
      <Btn size="row" icon="test" loading={test.isPending} onClick={() => test.mutate()}>{t("Enviar prueba")}</Btn>
      <MutationError error={test.error} />
      {test.data && (test.data.ok ? <Notice tone="success">{t("Enviado. Comprueba que ha llegado.")}</Notice> : <Notice tone="danger">{test.data.error}</Notice>)}
    </Stack>
  );
}

function Deliveries() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [status, setStatus] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["notify-deliveries", status], queryFn: () => get<{ total: number; items: Delivery[] }>("notifications/deliveries", { status: status ?? undefined, limit: "30" }), refetchInterval: 15000 });
  const retry = useMutation({ mutationFn: (id: number) => send("POST", `notifications/deliveries/${id}/retry`), onSuccess: () => qc.invalidateQueries({ queryKey: ["notify-deliveries"] }) });
  const tone = (s: string) => (s === "sent" ? "success" : s === "failed" ? "danger" : "warn");
  const label = (s: string) => (s === "sent" ? t("enviado") : s === "failed" ? t("fallido") : t("pendiente"));
  return (
    <Stack gap="xs">
      <SelectField size="xs" w={200} aria-label={t("Estado")} placeholder={t("Todos los estados")} clearable data={[{ value: "pending", label: t("Pendientes") }, { value: "failed", label: t("Fallidos") }, { value: "sent", label: t("Enviados") }]} value={status} onChange={setStatus} />
      <DataState query={q}>{() => (
        q.data?.items.length ? <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Aviso")}</DataTable.Th><DataTable.Th>{t("Canal")}</DataTable.Th><DataTable.Th>{t("Estado")}</DataTable.Th><DataTable.Th>{t("Fecha")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{q.data.items.map((d) => (
            <DataTable.Tr key={d.id}>
              <DataTable.Td>{d.kind === "recovery" ? `${t("Recuperado")}: ` : ""}{d.title}</DataTable.Td>
              <DataTable.Td>{d.channel}</DataTable.Td>
              <DataTable.Td><Pill size="xs" tone={tone(d.status)}>{label(d.status)}</Pill>{d.error && <Text size="xs" c="dimmed">{d.error}</Text>}</DataTable.Td>
              <DataTable.Td>{fmt(d.sent_at ?? d.created_at)}</DataTable.Td>
              <DataTable.Td>{d.status === "failed" && <Btn size="row" icon="refresh" onClick={() => retry.mutate(d.id)}>{t("Reintentar")}</Btn>}</DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable> : <EmptyState>{t("Aún no se ha enviado nada.")}</EmptyState>
      )}</DataState>
    </Stack>
  );
}

/** Administración → Notificaciones: canales de salida (Telegram, ntfy, Gotify, webhook, correo), historial de envíos y ajustes de agrupación y silencio. */
export default function AdminNotifications() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notify-channels"], queryFn: () => get<Channel[]>("notifications/channels") });
  const cat = useQuery({ queryKey: ["notify-catalog"], queryFn: () => get<Catalog>("notifications/catalog") });
  const [form, setForm] = useState<{ draft: Draft; id: number | null } | null>(null);
  const [del, setDel] = useState<Channel | null>(null);
  const remove = useMutation({ mutationFn: (c: Channel) => send("DELETE", `notifications/channels/${c.id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["notify-channels"] }) });
  const empty: Draft = { name: "", kind: "telegram", config: {}, secret: "", enabled: true, min_severity: "warning", events: [] };
  const evLabel = (k: string) => cat.data?.events.find((e) => e.key === k)?.label ?? k;
  return (
    <Stack gap="md">
      <SettingsGroup title={t("Canales")} description={t("Adónde se envían los avisos del sistema. Los avisos también aparecen siempre en la campana de la interfaz, haya o no canales.")}
        action={<Btn size="row" kind="primary" icon="plus" disabled={!cat.data} onClick={() => setForm({ draft: empty, id: null })}>{t("Añadir canal")}</Btn>}>
        <SettingsBody><DataState query={q}>{() => (
          <Stack gap="xs">
            {q.data?.length === 0 && <EmptyState>{t("Aún no hay canales: los avisos solo salen en la campana.")}</EmptyState>}
            {q.data?.map((c) => (
              <ListCard key={c.id} title={c.name} aside={<Pill tone={c.enabled ? "success" : "neutral"}>{c.enabled ? t("Activo") : t("Desactivado")}</Pill>}
                tags={<><Pill size="xs">{t(KINDS.find((k) => k.value === c.kind)?.label ?? c.kind)}</Pill><Pill size="xs">{t("desde")} {t(SEVERITY[c.min_severity]?.label ?? c.min_severity)}</Pill>
                  {c.events.length ? c.events.map((e) => <Pill key={e} size="xs">{t(evLabel(e))}</Pill>) : <Pill size="xs">{t("todos los eventos")}</Pill>}</>}
                meta={c.last ? `${t("último envío")}: ${c.last.status === "sent" ? t("correcto") : c.last.status === "failed" ? t("fallido") : t("pendiente")} · ${fmt(c.last.at)}${c.last.error ? ` · ${c.last.error}` : ""}` : t("sin envíos todavía")}
                actions={<Stack gap={6}><Group gap={6}>
                  <Btn size="row" icon="edit" onClick={() => setForm({ id: c.id, draft: { name: c.name, kind: c.kind, config: c.config, secret: "", enabled: c.enabled, min_severity: c.min_severity, events: c.events } })}>{t("Editar")}</Btn>
                  <Btn size="row" kind="danger" icon="trash" onClick={() => setDel(c)}>{t("Borrar")}</Btn></Group><Test c={c} /></Stack>} />))}
          </Stack>
        )}</DataState></SettingsBody>
      </SettingsGroup>
      <SettingsGroup title={t("Historial de envíos")} description={t("Cada envío con su resultado. Los fallos se reintentan solos con espera creciente; los que agotan los intentos se pueden reintentar a mano.")}><SettingsBody><Deliveries /></SettingsBody></SettingsGroup>
      <AdminSettings group="notifications" />
      <Modal opened={!!form} onClose={() => setForm(null)} title={form?.id === null ? t("Añadir canal") : t("Editar canal")} size="lg">
        {form && cat.data && <ChannelForm initial={form.draft} id={form.id} cat={cat.data} onClose={() => setForm(null)} />}
      </Modal>
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar canal")} action={t("Borrar canal")} subject={del?.name} warning={t("Deja de recibir avisos y se borra su historial de envíos.")} onConfirm={() => remove.mutateAsync(del!)} />
    </Stack>
  );
}
