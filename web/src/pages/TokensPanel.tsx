import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, Check, ClearFilters, ColHead, ConfirmDialog, DataTable, EmptyState, Modal, MutationError, Notice, Pill, SecretReveal, SelectField, TextField, useTableView } from "../ui";

type Tok = {
  id: number; name: string; role: string; prefix: string; brain?: string; brain_slug?: string; created_at: string; last_used_at: string | null; mine: boolean;
  scopes: string[]; all_scopes: boolean; expires_at: string | null; expired: boolean; replaced_by: number | null;
};
type BrainOpt = { slug: string; name: string; role: string };

export const ROLE: Record<string, string> = { reader: T("Lector"), contributor: T("Colaborador"), curator: T("Curador"), admin: T("Administrador"), owner: T("Propietario") };
const ORDER = ["reader", "contributor", "curator", "admin", "owner"];
const SCOPES: { value: string; label: string; help: string }[] = [
  { value: "recall", label: T("Consultar"), help: T("Recall y lectura de la memoria") },
  { value: "documents", label: T("Documentos"), help: T("Pasajes en el recall y lectura de documentos") },
  { value: "propose", label: T("Proponer"), help: T("Enviar propuestas y correcciones") },
];
const DAYS = [30, 90, 365];
const GRACE = [0, 1, 24, 72, 168];
const IDLE_DAYS = 30; // a partir de aquí la tabla dice «sin usar desde hace N días»
const daysSince = (d: string) => Math.floor((Date.now() - new Date(d).getTime()) / 86400000);

/** Caducidad de un token: la fecha, «sin caducidad» (con la sugerencia de rotarlo), «caducado» o, tras una rotación, hasta cuándo sigue valiendo. */
function Expiry({ tok }: { tok: Tok }) {
  const { t } = useTranslation();
  if (tok.expired) return <Pill tone="danger" size="xs">{t("caducado")}</Pill>;
  if (tok.replaced_by) return <Text size="xs">{t("rotado; vale hasta {{d}}", { d: fmt(tok.expires_at!) })}</Text>;
  if (!tok.expires_at) return <Pill tone="warn" size="xs">{t("sin caducidad")}</Pill>;
  return <Text size="xs">{fmt(tok.expires_at)}</Text>;
}

/** Tokens de API: tabla con revocación confirmada, rotación, alta y diálogo de «se muestra una sola vez». Con `brain` fijo (Administración) lista los de
 *  ese brain; sin él (Mi cuenta) lista los del usuario en todos los brains y deja elegir el brain al crear. El rol de un token nunca supera el del usuario en
 *  ese brain y no es administrador; su alcance (consultar, documentos, proponer) lo limita aún más. */
export default function TokensPanel({ brain, brains }: { brain?: string; brains: BrainOpt[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = brain ? ["tokens", brain] : ["my-tokens"];
  const list = useQuery({ queryKey: key, queryFn: () => get<Tok[]>(brain ? `brains/${brain}/tokens` : "me/tokens") });
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<{ token_max_days?: number }>("config") });
  const cap = cfg.data?.token_max_days ?? 0;
  const dayOptions = [...DAYS.filter((d) => !cap || d <= cap), ...(cap && !DAYS.includes(cap) ? [cap] : [])].sort((a, b) => a - b)
    .map((d) => ({ value: String(d), label: t("{{n}} días", { n: d }) })).concat(cap ? [] : [{ value: "never", label: t("Sin caducidad") }]);
  const [target, setTarget] = useState<string | null>(brain ?? null);
  const [name, setName] = useState("");
  const [role, setRole] = useState<string | null>("reader");
  const [days, setDays] = useState<string | null>(null);
  const [scopes, setScopes] = useState<string[]>(SCOPES.map((s) => s.value));
  const [fresh, setFresh] = useState<{ token: string; note?: string; title?: string } | null>(null);
  const [ask, setAsk] = useState<Tok | null>(null);
  const [rotating, setRotating] = useState<Tok | null>(null);
  const [grace, setGrace] = useState<string | null>("24");
  const slug = brain ?? target;
  const roleCap = ORDER.indexOf(brains.find((b) => b.slug === slug)?.role ?? "contributor");
  const roleOptions = ORDER.slice(0, 3).filter((r) => ORDER.indexOf(r) <= roleCap).map((r) => ({ value: r, label: t(ROLE[r]) }));
  const daysValue = days ?? (dayOptions.find((o) => o.value === "90") ?? dayOptions[dayOptions.length - 1])?.value ?? null;
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const create = useMutation({
    mutationFn: () => send<{ token: string }>("POST", `brains/${slug}/tokens`, { name: name.trim(), role, scopes, days: daysValue === "never" ? null : Number(daysValue) }),
    onSuccess: (r) => { setFresh({ token: r.token }); setName(""); refresh(); } });
  const revoke = useMutation({ mutationFn: (t: Tok) => send("DELETE", `brains/${t.brain_slug ?? brain}/tokens/${t.id}`), onSuccess: refresh });
  const rotate = useMutation({
    mutationFn: (tok: Tok) => send<{ token: string; old_expires_at: string }>("POST", `brains/${tok.brain_slug ?? brain}/tokens/${tok.id}/rotate`, { grace_hours: Number(grace) }),
    onSuccess: (r) => { setRotating(null); setFresh({ token: r.token, title: t("Token rotado"), note: Number(grace) ? t("Cópialo ahora: es la única vez que se muestra. El anterior sigue valiendo hasta {{d}}: actualiza antes el agente que lo usa.", { d: fmt(r.old_expires_at) }) : undefined }); refresh(); } });
  const v = useTableView(list.data ?? [], {
    name: { get: (t: Tok) => t.name }, brain: { get: (t: Tok) => t.brain ?? "", exact: true }, role: { get: (t: Tok) => t.role, label: (r: string) => t(ROLE[r] ?? r), exact: true },
    prefix: { get: (t: Tok) => t.prefix }, expires: { get: (t: Tok) => t.expires_at ?? "9999" }, used: { get: (t: Tok) => t.last_used_at ?? "" } });
  const forever = (list.data ?? []).filter((x) => !x.expires_at && x.mine).length;
  const toggle = (s: string, on: boolean) => setScopes((cur) => SCOPES.map((x) => x.value).filter((x) => (x === s ? on : cur.includes(x))));
  return (
    <Stack gap="xs">
      <SecretReveal value={fresh?.token ?? ""} title={fresh?.title} note={fresh?.note} onClose={() => setFresh(null)} />
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title={t("Revocar token")} action={t("Revocar token")} subject={ask && `${ask.name}${ask.brain ? ` · ${ask.brain}` : ""} (${ask.prefix}…)`}
        warning={t("Lo que use este token deja de poder acceder. No se puede deshacer.")} onConfirm={() => revoke.mutateAsync(ask!)} />
      <Modal opened={!!rotating} onClose={() => setRotating(null)} title={t("Rotar token")} centered>
        <Stack gap="xs">
          <Text size="sm">{t("Se crea un token nuevo con el mismo nombre, rol, alcance y duración. El anterior sigue valiendo durante el periodo de gracia, para que dé tiempo a actualizar el agente que lo usa, y después caduca.")}</Text>
          <SelectField label={t("Periodo de gracia")} w={220} value={grace} onChange={setGrace} allowDeselect={false}
            data={GRACE.map((h) => ({ value: String(h), label: h === 0 ? t("Ninguno: el anterior deja de valer ya") : h < 24 ? t("{{n}} hora", { n: h }) : t("{{n}} días", { n: h / 24 }) }))} />
          <MutationError error={rotate.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setRotating(null)}>{t("Cancelar")}</Btn>
            <Btn kind="primary" icon="refresh" loading={rotate.isPending} onClick={() => rotate.mutate(rotating!)}>{t("Rotar")}</Btn></Group>
        </Stack>
      </Modal>
      {forever > 0 && <Notice tone="warn">{t("Tienes tokens sin caducidad: rótalos para que el nuevo caduque. El anterior sigue valiendo el periodo de gracia que elijas.")}</Notice>}
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Nombre")}</ColHead>
          {!brain && <ColHead sort={v.sortProps("brain")} filter={v.select("brain")}>{t("Brain")}</ColHead>}
          <ColHead sort={v.sortProps("role")} filter={v.select("role")}>{t("Rol")}</ColHead>
          <ColHead>{t("Alcance")}</ColHead>
          <ColHead filter={v.text("prefix")}>{t("Prefijo")}</ColHead>
          <ColHead sort={v.sortProps("expires")}>{t("Caduca")}</ColHead>
          <ColHead sort={v.sortProps("used")}>{t("Último uso")}</ColHead>
          <DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((tok) => (
          <DataTable.Tr key={tok.id}>
            <DataTable.Td>{tok.name}</DataTable.Td>
            {!brain && <DataTable.Td>{tok.brain}</DataTable.Td>}
            <DataTable.Td>{t(ROLE[tok.role] ?? tok.role)}</DataTable.Td>
            <DataTable.Td>{tok.all_scopes ? t("todo") : tok.scopes.map((s) => t(SCOPES.find((x) => x.value === s)?.label ?? s)).join(", ")}</DataTable.Td>
            <DataTable.Td><Text span className="ms-data" size="xs">{tok.prefix}…</Text></DataTable.Td>
            <DataTable.Td><Expiry tok={tok} /></DataTable.Td>
            <DataTable.Td>{tok.last_used_at ? <>{fmt(tok.last_used_at)}{daysSince(tok.last_used_at) >= IDLE_DAYS && <Text size="xs" c="dimmed">{t("sin usar desde hace {{n}} días", { n: daysSince(tok.last_used_at) })}</Text>}</> : t("nunca")}</DataTable.Td>
            <DataTable.Td><Group gap={6} wrap="nowrap">
              {tok.mine && !tok.replaced_by && !tok.expired && <Btn size="row" icon="refresh" onClick={() => { setGrace("24"); rotate.reset(); setRotating(tok); }}>{t("Rotar")}</Btn>}
              <Btn kind="danger" size="row" icon="trash" onClick={() => setAsk(tok)}>{t("Revocar")}</Btn>
            </Group></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
      {list.data?.length === 0 && <EmptyState>{t("No hay tokens activos.")}</EmptyState>}
      <Group align="flex-end" gap="xs">
        {!brain && <SelectField label={t("Brain")} w={220} data={brains.map((b) => ({ value: b.slug, label: b.name }))} value={target} onChange={(v) => { setTarget(v); setRole("reader"); }} placeholder={t("Elige un brain")} />}
        <TextField label={t("Nombre")} placeholder={t("Claude Code (portátil)")} value={name} onChange={(e) => setName(e.currentTarget.value)} w={260} />
        <SelectField label={t("Rol")} w={160} data={roleOptions} value={role} onChange={setRole} allowDeselect={false} />
        <SelectField label={t("Caducidad")} w={160} data={dayOptions} value={daysValue} onChange={setDays} allowDeselect={false} />
        <Btn kind="primary" icon="plus" disabled={!slug || !name.trim() || !role || !scopes.length} loading={create.isPending} onClick={() => create.mutate()}>{t("Crear token")}</Btn>
      </Group>
      <Group gap="md">
        <Text size="xs" c="dimmed">{t("Alcance:")}</Text>
        {SCOPES.map((s) => <Check key={s.value} label={t(s.label)} description={t(s.help)} checked={scopes.includes(s.value)} onChange={(e) => toggle(s.value, e.currentTarget.checked)} />)}
      </Group>
      {cap > 0 && <Text size="xs" c="dimmed">{t("En esta instancia un token caduca como mucho a los {{n}} días.", { n: cap })}</Text>}
      <MutationError error={create.error} />
    </Stack>
  );
}
