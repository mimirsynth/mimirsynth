import { Group, Stack, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Brain, fmt, get, send } from "../api";
import { Btn, ClearFilters, ColHead, ConfirmDialog, DataState, DataTable, Form, Modal, MutationError, Notice, PasswordField, Pill, SecretReveal, Segments, SelectField, SidePanel, TextField, Toggle, useTableView, type Tone } from "../ui";
import { ROLE } from "./TokensPanel";

type U = { id: number; email: string | null; name: string; status: "invited" | "active" | "disabled"; is_admin: boolean; has_password: boolean; identities: string[]; last_login: string | null; created_at: string; brains: number; locked: boolean; must_change_password: boolean; totp_enabled: boolean };
type Detail = U & { memberships: { slug: string; name: string; role: string }[] };
type List = { smtp: boolean; items: U[] };
type Link = { link: string; purpose?: string; emailed: boolean };

const STATUS: Record<string, string> = { active: "activo", invited: "invitado", disabled: "deshabilitado" };
const TONE: Record<string, Tone> = { active: "success", invited: "warn", disabled: "neutral" };
const ROLE_OPTS = Object.entries(ROLE).map(([value, label]) => ({ value, label }));
const COLS = {
  user: { get: (u: U) => `${u.name} ${u.email ?? ""}` }, role: { get: (u: U) => (u.is_admin ? "admin" : "user"), label: (v: string) => (v === "admin" ? "Administrador" : "Usuario"), exact: true },
  login: { get: (u: U) => u.last_login ?? "" }, brains: { get: (u: U) => u.brains },
};

function CreateDialog({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (l: Link | null) => void }) {
  const [f, setF] = useState({ email: "", name: "", is_admin: false, mode: "invite", password: "" });
  const create = useMutation({ mutationFn: () => send<Link & U>("POST", "admin/users", f), onSuccess: (r) => { setF({ email: "", name: "", is_admin: false, mode: "invite", password: "" }); onCreated(r.link ? { link: r.link, emailed: r.emailed } : null); } });
  return (
    <Modal opened={opened} onClose={onClose} title="Crear usuario">
      <Form onSubmit={() => create.mutate()}>
        <TextField label="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.currentTarget.value })} autoFocus />
        <TextField label="Nombre" value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
        <Toggle label="Administrador de la instancia" description="Gestiona usuarios, ajustes y todos los brains." checked={f.is_admin} onChange={(e) => setF({ ...f, is_admin: e.currentTarget.checked })} />
        <Segments label="Acceso" value={f.mode} onChange={(v) => setF({ ...f, mode: v })} data={[{ value: "invite", label: "Invitar por enlace" }, { value: "password", label: "Contraseña temporal" }]} />
        {f.mode === "password"
          ? <PasswordField label="Contraseña temporal" description="La persona tendrá que cambiarla al entrar." autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.currentTarget.value })} />
          : <Text size="sm" c="dimmed">Se genera un enlace de un solo uso para que elija su contraseña; si hay correo configurado también se le envía.</Text>}
        <MutationError error={create.error} />
        <Group justify="flex-end"><Btn kind="ghost" onClick={onClose}>Cancelar</Btn><Btn kind="primary" type="submit" loading={create.isPending} disabled={!f.email || (f.mode === "password" && !f.password)}>Crear</Btn></Group>
      </Form>
    </Modal>
  );
}

function UserPanel({ id, me, brains, onClose, onLink }: { id: number; me: number | undefined; brains: Brain[]; onClose: () => void; onLink: (l: Link, title: string) => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-user", id], queryFn: () => get<Detail>(`admin/users/${id}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-user", id] }); qc.invalidateQueries({ queryKey: ["admin-users"] }); };
  const patch = useMutation({ mutationFn: (b: Record<string, unknown>) => send("PATCH", `admin/users/${id}`, b), onSuccess: refresh });
  const link = useMutation({ mutationFn: () => send<Link>("POST", `admin/users/${id}/link`), onSuccess: (r) => { refresh(); onLink(r, r.purpose === "invite" ? "Enlace de invitación" : "Enlace para restablecer la contraseña"); } });
  const act = useMutation({ mutationFn: (path: string) => send("POST", `admin/users/${id}/${path}`), onSuccess: refresh });
  const member = useMutation({ mutationFn: (b: { slug: string; role: string | null }) => send("PUT", `admin/users/${id}/memberships`, b), onSuccess: refresh });
  const [askDel, setAskDel] = useState(false);
  const [add, setAdd] = useState({ slug: "", role: "reader" });
  const u = q.data;
  const self = u?.id === me;
  const free = brains.filter((b) => !u?.memberships.some((m) => m.slug === b.slug));
  return (
    <SidePanel opened onClose={onClose} title={u ? (u.name || u.email || "Usuario") : "Usuario"}>
      <DataState query={q}>
        {(d) => (
          <Stack>
            <ConfirmDialog opened={askDel} onClose={() => setAskDel(false)} title="Eliminar usuario" subject={d.email ?? d.name} action="Eliminar"
              warning="Se anonimiza la cuenta, se le quitan accesos, sesiones y tokens, y el email queda libre. Sus propuestas y la auditoría se conservan como «Usuario eliminado»."
              onConfirm={async () => { await send("DELETE", `admin/users/${id}`); qc.invalidateQueries({ queryKey: ["admin-users"] }); onClose(); }} />
            <Group gap={6}>
              <Pill size="xs" tone={TONE[d.status]}>{STATUS[d.status]}</Pill>
              {d.is_admin && <Pill size="xs" tone="alt">administrador</Pill>}
              {d.locked && <Pill size="xs" tone="danger">bloqueado</Pill>}
              {d.has_password && <Pill size="xs">contraseña</Pill>}
              {d.totp_enabled && <Pill size="xs" tone="success">2FA</Pill>}
              {d.identities.map((i) => <Pill key={i} size="xs">{i.toUpperCase()}</Pill>)}
            </Group>
            <Text size="sm" c="dimmed">{d.email} · alta {fmt(d.created_at)} · último acceso {fmt(d.last_login)}</Text>
            <MutationError error={patch.error ?? link.error ?? act.error ?? member.error} />

            <Title order={5}>Cuenta</Title>
            <Toggle label="Administrador de la instancia" checked={d.is_admin} disabled={self || patch.isPending} onChange={(e) => patch.mutate({ is_admin: e.currentTarget.checked })} description={self ? "No puedes cambiar tu propio rol." : "Gestiona usuarios, ajustes y todos los brains."} />
            <Group gap={6}>
              {d.status !== "invited" && (d.status === "active"
                ? <Btn size="row" disabled={self} loading={patch.isPending} onClick={() => patch.mutate({ status: "disabled" })}>Deshabilitar</Btn>
                : <Btn size="row" loading={patch.isPending} onClick={() => patch.mutate({ status: "active" })}>Habilitar</Btn>)}
              {d.status !== "disabled" && <Btn size="row" icon="refresh" loading={link.isPending} onClick={() => link.mutate()}>{d.status === "invited" ? "Nuevo enlace de invitación" : "Restablecer contraseña"}</Btn>}
              {d.locked && <Btn size="row" loading={act.isPending} onClick={() => act.mutate("unlock")}>Desbloquear</Btn>}
              {d.totp_enabled && <Btn size="row" loading={act.isPending} onClick={() => act.mutate("mfa/reset")}>Quitar doble factor</Btn>}
              <Btn size="row" icon="logout" loading={act.isPending} onClick={() => act.mutate("logout")}>Cerrar sus sesiones</Btn>
              <Btn kind="danger" size="row" icon="trash" disabled={self} onClick={() => setAskDel(true)}>Eliminar</Btn>
            </Group>

            <Title order={5}>Brains</Title>
            {d.is_admin && <Text size="xs" c="dimmed">Como administrador de la instancia es propietario implícito de todos los brains.</Text>}
            {d.memberships.length === 0 && <Text size="sm" c="dimmed">Sin acceso a ningún brain.</Text>}
            {d.memberships.map((m) => (
              <Group key={m.slug} gap="xs" wrap="nowrap" justify="space-between">
                <Text size="sm" fw={500}>{m.name}</Text>
                <Group gap={6} wrap="nowrap">
                  <SelectField aria-label={`Rol en ${m.name}`} w={150} allowDeselect={false} value={m.role} data={ROLE_OPTS} onChange={(v) => v && member.mutate({ slug: m.slug, role: v })} />
                  <Btn size="row" icon="close" onClick={() => member.mutate({ slug: m.slug, role: null })}>Quitar</Btn>
                </Group>
              </Group>))}
            {free.length > 0 && (
              <Group gap={6} wrap="nowrap" align="flex-end">
                <SelectField label="Añadir a un brain" placeholder="Elige un brain" value={add.slug || null} onChange={(v) => setAdd({ ...add, slug: v ?? "" })} data={free.map((b) => ({ value: b.slug, label: b.name }))} />
                <SelectField aria-label="Rol" w={150} allowDeselect={false} value={add.role} onChange={(v) => setAdd({ ...add, role: v ?? "reader" })} data={ROLE_OPTS} />
                <Btn size="row" icon="plus" disabled={!add.slug} onClick={() => { member.mutate({ slug: add.slug, role: add.role }); setAdd({ ...add, slug: "" }); }}>Añadir</Btn>
              </Group>)}
          </Stack>)}
      </DataState>
    </SidePanel>
  );
}

/** Administración de usuarios: alta por invitación o contraseña temporal, roles, brains, deshabilitar, restablecer y eliminar. */
export default function AdminUsers({ me }: { me?: number }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-users"], queryFn: () => get<List>("admin/users") });
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const [status, setStatus] = useState("all");
  const [open, setOpen] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [shown, setShown] = useState<{ link: string; title: string; emailed: boolean } | null>(null);
  const rows = (q.data?.items ?? []).filter((u) => status === "all" || u.status === status);
  const v = useTableView(rows, COLS, { key: "user", dir: "asc" });
  const count = (s: string) => (q.data?.items ?? []).filter((u) => s === "all" || u.status === s).length;
  return (
    <DataState query={q}>
      {(d) => (
        <Stack gap="sm">
          <CreateDialog opened={creating} onClose={() => setCreating(false)} onCreated={(l) => { setCreating(false); qc.invalidateQueries({ queryKey: ["admin-users"] }); if (l) setShown({ ...l, title: "Enlace de invitación" }); }} />
          <SecretReveal value={shown?.link ?? ""} title={shown?.title} note={shown?.emailed ? "Se ha enviado también por correo. Es de un solo uso y caduca; puedes generar otro cuando quieras." : "Envíaselo a la persona (no se ha enviado ningún correo). Es de un solo uso y caduca; puedes generar otro cuando quieras."} onClose={() => setShown(null)} />
          {open !== null && <UserPanel id={open} me={me} brains={brains.data ?? []} onClose={() => setOpen(null)} onLink={(l, title) => setShown({ link: l.link, title, emailed: l.emailed })} />}
          {!d.smtp && <Notice tone="warn" title="Sin servidor de correo">Las invitaciones y la recuperación de contraseña no se pueden enviar: los enlaces se copian desde aquí y se entregan a mano. <Link to="/admin?seccion=mail">Configurar el correo (SMTP)</Link></Notice>}
          <Group justify="space-between">
            <Segments label="Estado" value={status} onChange={setStatus} data={[{ value: "all", label: "Todos", count: count("all") }, ...Object.entries(STATUS).map(([k, l]) => ({ value: k, label: l[0].toUpperCase() + l.slice(1) + "s", count: count(k) }))]} />
            <Btn kind="primary" icon="plus" onClick={() => setCreating(true)}>Crear usuario</Btn>
          </Group>
          <ClearFilters active={v.active} onClear={v.clear} />
          <DataTable fz="sm">
            <DataTable.Thead><DataTable.Tr>
              <ColHead sort={v.sortProps("user")} filter={v.text("user", "Nombre o email…")}>Usuario</ColHead>
              <ColHead filter={v.select("role")}>Rol</ColHead>
              <ColHead>Acceso</ColHead>
              <ColHead>Estado</ColHead>
              <ColHead sort={v.sortProps("brains")}>Brains</ColHead>
              <ColHead sort={v.sortProps("login")}>Último acceso</ColHead>
              <DataTable.Th />
            </DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{v.rows.map((u) => (
              <DataTable.Tr key={u.id}>
                <DataTable.Td><Text size="sm" fw={500}>{u.name}</Text><Text size="xs" c="dimmed">{u.email}</Text></DataTable.Td>
                <DataTable.Td>{u.is_admin ? <Pill size="xs" tone="alt">administrador</Pill> : "Usuario"}</DataTable.Td>
                <DataTable.Td><Group gap={4}>{u.has_password && <Pill size="xs">contraseña</Pill>}{u.identities.map((i) => <Pill key={i} size="xs">{i.toUpperCase()}</Pill>)}{!u.has_password && u.identities.length === 0 && "—"}</Group></DataTable.Td>
                <DataTable.Td><Pill size="xs" tone={TONE[u.status]}>{STATUS[u.status]}</Pill>{u.locked && <Pill size="xs" tone="danger"> bloqueado</Pill>}</DataTable.Td>
                <DataTable.Td>{u.is_admin ? "todos" : u.brains}</DataTable.Td>
                <DataTable.Td>{fmt(u.last_login)}</DataTable.Td>
                <DataTable.Td><Btn size="row" onClick={() => setOpen(u.id)}>Gestionar</Btn></DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable>
        </Stack>)}
    </DataState>
  );
}
