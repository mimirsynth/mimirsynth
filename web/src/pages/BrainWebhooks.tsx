import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Brain, fmt, get, send } from "../api";
import { T } from "../i18n";
import { Btn, CodeBlock, ConfirmDialog, DataTable, EmptyState, Modal, MutationError, Notice, NumberField, Pill, SecretReveal, SelectField, TextArea,
  TextField, Toggle } from "../ui";

type Hook = { id: number; name: string; template: string; config: Record<string, unknown>; enabled: boolean; auto_approve: boolean; daily_cap: number;
  per_minute: number; path: string; received: number; rejected: number; today: number; last_at: string | null; last_error: string; secret?: string };
type List = { items: Hook[]; templates: Record<string, string>; group_minutes: number };
type Ev = { id: number; kind: string; outcome: string; title: string; count: number; first_at: string; last_at: string; resolved_at: string | null;
  proposal_id: number | null; resolution_id: number | null };
type Draft = { name: string; template: string; auto_approve: boolean; daily_cap: number | string; per_minute: number | string; enabled: boolean;
  title: string; text: string; at: string; state: string; fingerprint: string };
const EMPTY: Draft = { name: "", template: "alertmanager", auto_approve: false, daily_cap: 200, per_minute: 60, enabled: true, title: "", text: "", at: "", state: "", fingerprint: "" };
const OUTCOME: Record<string, string> = { open: T("abierta"), proposed: T("propuesta"), closed: T("cerrada"), capped: T("sobre el tope"), blocked: T("bloqueada") };
/** The last problem of a webhook, as the server records it. */
const PROBLEM: Record<string, string> = { bad_secret: T("una petición llegó con un secreto o una firma incorrectos"), rate_limited: T("se pasó del límite de peticiones por minuto"),
  not_json: T("el cuerpo no era JSON"), no_events: T("la plantilla no sacó ningún evento de la última petición") };
const TEMPLATE: Record<string, string> = { generic: T("Genérica") };   // the others are product names

/** Incoming webhooks of a brain (issue 122): alerts and deployments from other tools become proposals through a template. */
export default function BrainWebhooks({ brain }: { brain: Brain }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["webhooks", brain.slug];
  const q = useQuery({ queryKey: key, queryFn: () => get<List>(`brains/${brain.slug}/webhooks`) });
  const [edit, setEdit] = useState<{ id: number | null; d: Draft } | null>(null);
  const [secret, setSecret] = useState<{ value: string; url: string } | null>(null);
  const [del, setDel] = useState<Hook | null>(null);
  const [log, setLog] = useState<Hook | null>(null);
  const [sample, setSample] = useState(""); const [ghEvent, setGhEvent] = useState("workflow_run");
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const url = (h: Hook) => `${window.location.origin}${h.path}`;
  const body = (d: Draft) => ({ name: d.name, template: d.template, auto_approve: d.auto_approve, daily_cap: Number(d.daily_cap) || 200,
    per_minute: Number(d.per_minute) || 60, enabled: d.enabled,
    config: d.template === "generic" ? { title: d.title, text: d.text, at: d.at, state: d.state, fingerprint: d.fingerprint } : {} });
  const save = useMutation({
    mutationFn: (e: { id: number | null; d: Draft }) => e.id === null ? send<Hook>("POST", `brains/${brain.slug}/webhooks`, body(e.d)) : send<Hook>("PUT", `brains/${brain.slug}/webhooks/${e.id}`, body(e.d)),
    onSuccess: (h) => { setEdit(null); refresh(); if (h.secret) setSecret({ value: h.secret, url: url(h) }); } });
  const rotate = useMutation({ mutationFn: (h: Hook) => send<Hook>("POST", `brains/${brain.slug}/webhooks/${h.id}/rotate`),
    onSuccess: (h) => { refresh(); if (h.secret) setSecret({ value: h.secret, url: url(h) }); } });
  const remove = useMutation({ mutationFn: (h: Hook) => send("DELETE", `brains/${brain.slug}/webhooks/${h.id}`), onSuccess: refresh });
  const preview = useMutation({ mutationFn: (d: Draft) => send<{ events: { state: string; title: string; text: string; at: string | null }[] }>("POST",
    `brains/${brain.slug}/webhooks/preview`, { template: d.template, config: body(d).config, body: sample, event: d.template === "github_actions" ? ghEvent : "" }) });
  const events = useQuery({ queryKey: ["webhook-events", brain.slug, log?.id], enabled: !!log, queryFn: () => get<Ev[]>(`brains/${brain.slug}/webhooks/${log!.id}/events`) });
  const d = q.data;
  const templates = Object.entries(d?.templates ?? {}).map(([value, label]) => ({ value, label: t(TEMPLATE[value] ?? label) }));
  const set = (p: Partial<Draft>) => setEdit((e) => e && { ...e, d: { ...e.d, ...p } });
  const open = (h?: Hook) => { preview.reset(); setSample(""); setEdit({ id: h?.id ?? null, d: h ? { ...EMPTY, ...h, ...(h.config as Partial<Draft>) } : { ...EMPTY } }); };
  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">{t("Lo que pasa en la infraestructura (una alerta, un despliegue, un pipeline, una copia fallida) entra como propuesta de memoria episódica: «qué pasó y cuándo». Cada webhook tiene su dirección y su secreto, y una plantilla que lee el JSON de su emisor. Una alerta que se repite no crea una propuesta por aviso: se agrupa y, si se resuelve en {{n}} minutos, queda una sola con su inicio y su fin.", { n: d?.group_minutes ?? 15 })}</Text>
      <Group><Btn kind="primary" icon="plus" onClick={() => open()}>{t("Crear webhook")}</Btn></Group>
      <MutationError error={q.error ?? rotate.error ?? remove.error} />
      {d && (d.items.length ? <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Nombre")}</DataTable.Th><DataTable.Th>{t("Plantilla")}</DataTable.Th><DataTable.Th>{t("Recibidos")}</DataTable.Th>
          <DataTable.Th>{t("Hoy")}</DataTable.Th><DataTable.Th>{t("Último")}</DataTable.Th><DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{d.items.map((h) => (
          <DataTable.Tr key={h.id}>
            <DataTable.Td><Group gap={6}><Text size="sm" fw={500}>{h.name}</Text>{!h.enabled && <Pill size="xs" tone="warn">{t("desactivado")}</Pill>}
              {h.auto_approve && <Pill size="xs" tone="alt">{t("de confianza")}</Pill>}</Group>
              <Text size="xs" c="dimmed" className="ms-data">{url(h)}</Text></DataTable.Td>
            <DataTable.Td>{t(TEMPLATE[h.template] ?? d.templates[h.template] ?? h.template)}</DataTable.Td>
            <DataTable.Td>{h.received}{h.rejected > 0 && <Text size="xs" c="dimmed">{t("{{n}} rechazados", { n: h.rejected })}</Text>}</DataTable.Td>
            <DataTable.Td>{t("{{n}} de {{cap}}", { n: h.today, cap: h.daily_cap })}</DataTable.Td>
            <DataTable.Td>{fmt(h.last_at)}{h.last_error && <Text size="xs" c="dimmed">{t(PROBLEM[h.last_error] ?? h.last_error)}</Text>}</DataTable.Td>
            <DataTable.Td><Group gap={4} wrap="nowrap">
              <Btn size="row" onClick={() => setLog(h)}>{t("Registro")}</Btn>
              <Btn size="row" icon="edit" onClick={() => open(h)}>{t("Editar")}</Btn>
              <Btn size="row" icon="refresh" loading={rotate.isPending && rotate.variables?.id === h.id} onClick={() => rotate.mutate(h)}>{t("Nuevo secreto")}</Btn>
              <Btn size="row" kind="danger" icon="trash" onClick={() => setDel(h)}>{t("Borrar")}</Btn>
            </Group></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : <EmptyState>{t("Sin webhooks. Crea uno para cada emisor (Alertmanager, CheckMK, un repositorio…).")}</EmptyState>)}

      <Modal opened={!!edit} onClose={() => setEdit(null)} title={edit?.id ? t("Editar webhook") : t("Crear webhook")} size="lg">
        {edit && <Stack>
          <Group grow align="flex-start">
            <TextField label={t("Nombre")} value={edit.d.name} onChange={(e) => set({ name: e.currentTarget.value })} placeholder={t("Alertas de producción")} />
            <SelectField label={t("Plantilla")} data={templates} value={edit.d.template} allowDeselect={false} onChange={(v) => v && set({ template: v })} />
          </Group>
          {edit.d.template === "generic" && <Stack gap="xs">
            <Text size="xs" c="dimmed">{t("Escribe el título y el texto con {{ph}} para sacar valores del JSON (las listas, con su número: alerts.0.labels). Con «Estado», los valores resolved, ok, up o recovery cierran la alerta; sin él, cada petición es un evento.", { ph: "{{campo.subcampo}}" })}</Text>
            <TextField label={t("Título")} value={edit.d.title} onChange={(e) => set({ title: e.currentTarget.value })} placeholder="{{check.name}} · {{check.host}}" />   {/* i18n-ok: JSON paths, not words */}
            <TextField label={t("Texto")} value={edit.d.text} onChange={(e) => set({ text: e.currentTarget.value })} placeholder="{{check.output}}" />   {/* i18n-ok: JSON paths, not words */}
            <Group grow>   {/* i18n-ok: JSON paths, not words */}
              <TextField label={t("Fecha (ruta)")} value={edit.d.at} onChange={(e) => set({ at: e.currentTarget.value })} placeholder="time" />   {/* i18n-ok: JSON paths, not words */}
              <TextField label={t("Estado (ruta)")} value={edit.d.state} onChange={(e) => set({ state: e.currentTarget.value })} placeholder="check.status" />   {/* i18n-ok: JSON paths, not words */}
              <TextField label={t("Huella (ruta)")} value={edit.d.fingerprint} onChange={(e) => set({ fingerprint: e.currentTarget.value })} placeholder="check.id" />   {/* i18n-ok: JSON paths, not words */}
            </Group>
          </Stack>}
          <Group grow align="flex-start">
            <NumberField label={t("Propuestas al día")} min={1} max={10000} value={edit.d.daily_cap} onChange={(v) => set({ daily_cap: v })}
              description={t("Lo que pase del tope queda en el registro, sin proponerse, y avisa una vez.")} />
            <NumberField label={t("Peticiones por minuto")} min={1} max={6000} value={edit.d.per_minute} onChange={(v) => set({ per_minute: v })}
              description={t("Más rápido responde 429: el emisor reintenta.")} />
          </Group>
          <Toggle label={t("De confianza: aprobar sus propuestas sin revisión")} checked={edit.d.auto_approve} onChange={(e) => set({ auto_approve: e.currentTarget.checked })}
            description={t("Solo para emisores fiables. Siguen el tope diario, y una propuesta en la que el detector de secretos marque algo va siempre a revisión.")} />
          {edit.id !== null && <Toggle label={t("Activo")} checked={edit.d.enabled} onChange={(e) => set({ enabled: e.currentTarget.checked })} />}
          <Stack gap="xs">
            <Text size="sm" fw={600}>{t("Probar la plantilla")}</Text>
            <TextArea autosize minRows={3} maxRows={10} value={sample} onChange={(e) => setSample(e.currentTarget.value)} placeholder={t("Pega un JSON de ejemplo del emisor")} />
            {edit.d.template === "github_actions" && <SelectField label={t("Evento de GitHub (cabecera X-GitHub-Event)")} data={["workflow_run", "deployment_status", "ping"]}
              value={ghEvent} allowDeselect={false} onChange={(v) => v && setGhEvent(v)} />}
            <Group><Btn icon="test" disabled={!sample.trim()} loading={preview.isPending} onClick={() => preview.mutate(edit.d)}>{t("Probar")}</Btn></Group>
            <MutationError error={preview.error} />
            {preview.data && (preview.data.events.length ? preview.data.events.map((e, i) => (
              <Notice key={i} tone="info" title={`${e.state === "firing" ? t("Alerta activa") : e.state === "resolved" ? t("Alerta resuelta") : t("Evento")} · ${e.title}`}>
                <Text size="xs" c="dimmed">{fmt(e.at)}</Text><Text size="sm" className="ms-prose">{e.text}</Text></Notice>))
              : <Notice tone="warn">{t("La plantilla no saca ningún evento de este cuerpo: no es de este emisor o no anuncia nada terminado.")}</Notice>)}
          </Stack>
          <MutationError error={save.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setEdit(null)}>{t("Cancelar")}</Btn>
            <Btn kind="primary" icon="check" disabled={!edit.d.name.trim()} loading={save.isPending} onClick={() => save.mutate(edit)}>{t("Guardar")}</Btn></Group>
        </Stack>}
      </Modal>

      <SecretReveal value={secret?.value ?? ""} title={t("Secreto del webhook")} onClose={() => setSecret(null)}
        note={t("Cópialo ahora: es la única vez que se muestra. Configúralo en el emisor junto con la dirección {{url}}: como firma HMAC-SHA256 del cuerpo (X-Hub-Signature-256) o en la cabecera Authorization: Bearer.", { url: secret?.url ?? "" })} />
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar webhook")} action={t("Borrar")} subject={del?.name}
        warning={t("Su dirección deja de funcionar y se borra su registro. Las propuestas que ya creó se quedan.")} onConfirm={() => remove.mutateAsync(del!)} />
      <Modal opened={!!log} onClose={() => setLog(null)} title={t("Registro de «{{name}}»", { name: log?.name ?? "" })} size="xl">
        {events.data && (events.data.length ? <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Qué")}</DataTable.Th><DataTable.Th>{t("Avisos")}</DataTable.Th><DataTable.Th>{t("Desde")}</DataTable.Th>
            <DataTable.Th>{t("Hasta")}</DataTable.Th><DataTable.Th>{t("Estado")}</DataTable.Th><DataTable.Th>{t("Propuestas")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{events.data.map((e) => (
            <DataTable.Tr key={e.id}>
              <DataTable.Td><Text size="sm">{e.title}</Text><Text size="xs" c="dimmed">{e.kind === "alert" ? t("alerta") : t("evento")}</Text></DataTable.Td>
              <DataTable.Td>{e.count}</DataTable.Td><DataTable.Td>{fmt(e.first_at)}</DataTable.Td><DataTable.Td>{fmt(e.resolved_at)}</DataTable.Td>
              <DataTable.Td><Pill size="xs" tone={e.outcome === "capped" || e.outcome === "blocked" ? "warn" : undefined}>{t(OUTCOME[e.outcome] ?? e.outcome)}</Pill></DataTable.Td>
              <DataTable.Td>{[e.proposal_id, e.resolution_id].filter(Boolean).map((p) => `#${p}`).join(", ") || "—"}</DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable> : <EmptyState>{t("Este webhook no ha recibido nada todavía.")}</EmptyState>)}
        <Text size="xs" c="dimmed" mt="xs">{t("Del cuerpo recibido no se guarda nada: solo el título, las fechas, el número de avisos y las propuestas que se crearon. Se olvida a los 90 días.")}</Text>
      </Modal>
    </Stack>
  );
}
