import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, ClearFilters, ColHead, ConfirmDialog, DataTable, EmptyState, MutationError, SecretReveal, SelectField, TextField, useTableView } from "../ui";

type Tok = { id: number; name: string; role: string; prefix: string; brain?: string; brain_slug?: string; created_at: string; last_used_at: string | null };
type BrainOpt = { slug: string; name: string; role: string };

export const ROLE: Record<string, string> = { reader: T("Lector"), contributor: T("Colaborador"), curator: T("Curador"), admin: T("Administrador"), owner: T("Propietario") };
const ORDER = ["reader", "contributor", "curator", "admin", "owner"];

/** Tokens de API: tabla con revocación confirmada, alta y diálogo de «se muestra una sola vez». Con `brain` fijo (Administración) lista los de ese brain;
 *  sin él (Mi cuenta) lista los del usuario en todos los brains y deja elegir el brain al crear. El rol de un token nunca supera el del usuario en ese brain y no es administrador. */
export default function TokensPanel({ brain, brains }: { brain?: string; brains: BrainOpt[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = brain ? ["tokens", brain] : ["my-tokens"];
  const list = useQuery({ queryKey: key, queryFn: () => get<Tok[]>(brain ? `brains/${brain}/tokens` : "me/tokens") });
  const [target, setTarget] = useState<string | null>(brain ?? null);
  const [name, setName] = useState("");
  const [role, setRole] = useState<string | null>("reader");
  const [fresh, setFresh] = useState("");
  const [ask, setAsk] = useState<Tok | null>(null);
  const slug = brain ?? target;
  const cap = ORDER.indexOf(brains.find((b) => b.slug === slug)?.role ?? "contributor");
  const roleOptions = ORDER.slice(0, 3).filter((r) => ORDER.indexOf(r) <= cap).map((r) => ({ value: r, label: t(ROLE[r]) }));
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const create = useMutation({ mutationFn: () => send<{ token: string }>("POST", `brains/${slug}/tokens`, { name: name.trim(), role }), onSuccess: (r) => { setFresh(r.token); setName(""); refresh(); } });
  const revoke = useMutation({ mutationFn: (t: Tok) => send("DELETE", `brains/${t.brain_slug ?? brain}/tokens/${t.id}`), onSuccess: refresh });
  const v = useTableView(list.data ?? [], {
    name: { get: (t: Tok) => t.name }, brain: { get: (t: Tok) => t.brain ?? "", exact: true }, role: { get: (t: Tok) => t.role, label: (r: string) => t(ROLE[r] ?? r), exact: true },
    prefix: { get: (t: Tok) => t.prefix }, used: { get: (t: Tok) => t.last_used_at ?? "" } });
  return (
    <Stack gap="xs">
      <SecretReveal value={fresh} onClose={() => setFresh("")} />
      <ConfirmDialog opened={!!ask} onClose={() => setAsk(null)} title={t("Revocar token")} action={t("Revocar token")} subject={ask && `${ask.name}${ask.brain ? ` · ${ask.brain}` : ""} (${ask.prefix}…)`}
        warning={t("Lo que use este token deja de poder acceder. No se puede deshacer.")} onConfirm={() => revoke.mutateAsync(ask!)} />
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Nombre")}</ColHead>
          {!brain && <ColHead sort={v.sortProps("brain")} filter={v.select("brain")}>{t("Brain")}</ColHead>}
          <ColHead sort={v.sortProps("role")} filter={v.select("role")}>{t("Rol")}</ColHead>
          <ColHead filter={v.text("prefix")}>{t("Prefijo")}</ColHead>
          <ColHead sort={v.sortProps("used")}>{t("Último uso")}</ColHead>
          <DataTable.Th />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((tok) => (
          <DataTable.Tr key={tok.id}>
            <DataTable.Td>{tok.name}</DataTable.Td>
            {!brain && <DataTable.Td>{tok.brain}</DataTable.Td>}
            <DataTable.Td>{t(ROLE[tok.role] ?? tok.role)}</DataTable.Td>
            <DataTable.Td><Text span className="ms-data" size="xs">{tok.prefix}…</Text></DataTable.Td>
            <DataTable.Td>{tok.last_used_at ? fmt(tok.last_used_at) : "nunca"}</DataTable.Td>
            <DataTable.Td><Btn kind="danger" size="row" icon="trash" onClick={() => setAsk(tok)}>{t("Revocar")}</Btn></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
      {list.data?.length === 0 && <EmptyState>{t("No hay tokens activos.")}</EmptyState>}
      <Group align="flex-end" gap="xs">
        {!brain && <SelectField label={t("Brain")} w={220} data={brains.map((b) => ({ value: b.slug, label: b.name }))} value={target} onChange={(v) => { setTarget(v); setRole("reader"); }} placeholder={t("Elige un brain")} />}
        <TextField label={t("Nombre")} placeholder={t("Claude Code (portátil)")} value={name} onChange={(e) => setName(e.currentTarget.value)} w={260} />
        <SelectField label={t("Rol")} w={160} data={roleOptions} value={role} onChange={setRole} allowDeselect={false} />
        <Btn kind="primary" icon="plus" disabled={!slug || !name.trim() || !role} loading={create.isPending} onClick={() => create.mutate()}>{t("Crear token")}</Btn>
      </Group>
      <MutationError error={create.error} />
    </Stack>
  );
}
