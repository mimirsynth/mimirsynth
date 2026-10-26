import { tr } from "../i18n";
import { useTranslation } from "react-i18next";
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
  user: { get: (u: U) => `${u.name} ${u.email ?? ""}` }, role: { get: (u: U) => (u.is_admin ? "admin" : "user"), label: (v: string) => (v === "admin" ? tr("Administrador") : tr("Usuario")), exact: true },
  login: { get: (u: U) => u.last_login ?? "" }, brains: { get: (u: U) => u.brains },
};

function CreateDialog({ opened, onClose, onCreated }: { opened: boolean; onClose: () => void; onCreated: (l: Link | null) => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ email: "", name: "", is_admin: false, mode: "invite", password: "" });
  const create = useMutation({ mutationFn: () => send<Link & U>("POST", "admin/users", f), onSuccess: (r) => { setF({ email: "", name: "", is_admin: false, mode: "invite", password: "" }); onCreated(r.link ? { link: r.link, emailed: r.emailed } : null); } });
  return (
    <Modal opened={opened} onClose={onClose} title={t("Crear usuario")}>
      <Form onSubmit={() => create.mutate()}>
        <TextField label={t("Email")} type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.currentTarget.value })} autoFocus />
        <TextField label={t("Nombre")} value={f.name} onChange={(e) => setF({ ...f, name: e.currentTarget.value })} />
        <Toggle label={t("Administrador de la instancia")} description={t("Gestiona usuarios, ajustes y todos los brains.")} checked={f.is_admin} onChange={(e) => setF({ ...f, is_admin: e.currentTarget.checked })} />
        <Segments label={t("Acceso")} value={f.mode} onChange={(v) => setF({ ...f, mode: v })} data={[{ value: "invite", label: t("Invitar por enlace") }, { value: "password", label: t("Contraseña temporal") }]} />
        {f.mode === "password"
          ? <PasswordField label={t("Contraseña temporal")} description={t("La persona tendrá que cambiarla al entrar.")} autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.currentTarget.value })} />
          : <Text size="sm" c="dimmed">{t("Se genera un enlace de un solo uso para que elija su contraseña; si hay correo configurado también se le envía.")}</Text>}
        <MutationError error={create.error} />
        <Group justify="flex-end"><Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn><Btn kind="primary" type="submit" loading={create.isPending} disabled={!f.email || (f.mode === "password" && !f.password)}>{t("Crear")}</Btn></Group>
      </Form>
    </Modal>
  );
}

function UserPanel({ id, me, brains, onClose, onLink }: { id: number; me: number | undefined; brains: Brain[]; onClose: () => void; onLink: (l: Link, title: string) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-user", id], queryFn: () => get<Detail>(`admin/users/${id}`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-user", id] }); qc.invalidateQueries({ queryKey: ["admin-users"] }); };
  const patch = useMutation({ mutationFn: (b: Record<string, unknown>) => send("PATCH", `admin/users/${id}`, b), onSuccess: refresh });
  const link = useMutation({ mutationFn: () => send<Link>("POST", `admin/users/${id}/link`), onSuccess: (r) => { refresh(); onLink(r, r.purpose === "invite" ? t("Enlace de invitación") : t("Enlace para restablecer la contraseña")); } });
  const act = useMutation({ mutationFn: (path: string) => send("POST", `admin/users/${id}/${path}`), onSuccess: refresh });
  const member = useMutation({ mutationFn: (b: { slug: string; role: string | null }) => send("PUT", `admin/users/${id}/memberships`, b), onSuccess: refresh });
  const [askDel, setAskDel] = useState(false);
  const [add, setAdd] = useState({ slug: "", role: "reader" });
  const u = q.data;
  const self = u?.id === me;
  const free = brains.filter((b) => !u?.memberships.some((m) => m.slug === b.slug));
  return (
    <SidePanel opened onClose={onClose} title={u ? (u.name || u.email || t("Usuario")) : t("Usuario")}>
      <DataState query={q}>
        {(d) => (
          <Stack>
            <ConfirmDialog opened={askDel} onClose={() => setAskDel(false)} title={t("Eliminar usuario")} subject={d.email ?? d.name} action={t("Eliminar")}
              warning={t("Se anonimiza la cuenta, se le quitan accesos, sesiones y tokens, y el email queda libre. Sus propuestas y la auditoría se conservan como «Usuario eliminado».")}
              onConfirm={async () => { await send("DELETE", `admin/users/${id}`); qc.invalidateQueries({ queryKey: ["admin-users"] }); onClose(); }} />
            <Group gap={6}>
              <Pill size="xs" tone={TONE[d.status]}>{t(STATUS[d.status])}</Pill>
              {d.is_admin && <Pill size="xs" tone="alt">{t("administrador")}</Pill>}
              {d.locked && <Pill size="xs" tone="danger">{t("bloqueado")}</Pill>}
              {d.has_password && <Pill size="xs">{t("contraseña")}</Pill>}
              {d.totp_enabled && <Pill size="xs" tone="success">{t("2FA")}</Pill>}
              {d.identities.map((i) => <Pill key={i} size="xs">{i.toUpperCase()}</Pill>)}
            </Group>
            <Text size="sm" c="dimmed">{t("{{email}} · alta {{created}} · último acceso {{login}}", { email: d.email, created: fmt(d.created_at), login: fmt(d.last_login) })}</Text>
            <MutationError error={patch.error ?? link.error ?? act.error ?? member.error} />

            <Title order={5}>{t("Cuenta")}</Title>
            <Toggle label={t("Administrador de la instancia")} checked={d.is_admin} disabled={self || patch.isPending} onChange={(e) => patch.mutate({ is_admin: e.currentTarget.checked })} description={self ? t("No puedes cambiar tu propio rol.") : t("Gestiona usuarios, ajustes y todos los brains.")} />
            <Group gap={6}>
              {d.status !== "invited" && (d.status === "active"
                ? <Btn size="row" disabled={self} loading={patch.isPending} onClick={() => patch.mutate({ status: "disabled" })}>{t("Deshabilitar")}</Btn>
                : <Btn size="row" loading={patch.isPending} onClick={() => patch.mutate({ status: "active" })}>{t("Habilitar")}</Btn>)}
              {d.status !== "disabled" && <Btn size="row" icon="refresh" loading={link.isPending} onClick={() => link.mutate()}>{d.status === "invited" ? t("Nuevo enlace de invitación") : t("Restablecer contraseña")}</Btn>}
              {d.locked && <Btn size="row" loading={act.isPending} onClick={() => act.mutate("unlock")}>{t("Desbloquear")}</Btn>}
              {d.totp_enabled && <Btn size="row" loading={act.isPending} onClick={() => act.mutate("mfa/reset")}>{t("Quitar doble factor")}</Btn>}
              <Btn size="row" icon="logout" loading={act.isPending} onClick={() => act.mutate("logout")}>{t("Cerrar sus sesiones")}</Btn>
              <Btn kind="danger" size="row" icon="trash" disabled={self} onClick={() => setAskDel(true)}>{t("Eliminar")}</Btn>
            </Group>

            <Title order={5}>{t("Brains")}</Title>
            {d.is_admin && <Text size="xs" c="dimmed">{t("Como administrador de la instancia es propietario implícito de todos los brains.")}</Text>}
            {d.memberships.length === 0 && <Text size="sm" c="dimmed">{t("Sin acceso a ningún brain.")}</Text>}
            {d.memberships.map((m) => (
              <Group key={m.slug} gap="xs" wrap="nowrap" justify="space-between">
                <Text size="sm" fw={500}>{m.name}</Text>
                <Group gap={6} wrap="nowrap">
                  <SelectField aria-label={t("Rol en {{name}}", { name: m.name })} w={150} allowDeselect={false} value={m.role} data={ROLE_OPTS.map((o) => ({ ...o, label: t(o.label) }))} onChange={(v) => v && member.mutate({ slug: m.slug, role: v })} />
                  <Btn size="row" icon="close" onClick={() => member.mutate({ slug: m.slug, role: null })}>{t("Quitar")}</Btn>
                </Group>
              </Group>))}
            {free.length > 0 && (
              <Group gap={6} wrap="nowrap" align="flex-end">
                <SelectField label={t("Añadir a un brain")} placeholder={t("Elige un brain")} value={add.slug || null} onChange={(v) => setAdd({ ...add, slug: v ?? "" })} data={free.map((b) => ({ value: b.slug, label: b.name }))} />
                <SelectField aria-label={t("Rol")} w={150} allowDeselect={false} value={add.role} onChange={(v) => setAdd({ ...add, role: v ?? "reader" })} data={ROLE_OPTS.map((o) => ({ ...o, label: t(o.label) }))} />
                <Btn size="row" icon="plus" disabled={!add.slug} onClick={() => { member.mutate({ slug: add.slug, role: add.role }); setAdd({ ...add, slug: "" }); }}>{t("Añadir")}</Btn>
              </Group>)}
          </Stack>)}
      </DataState>
    </SidePanel>
  );
}

/** Administración de usuarios: alta por invitación o contraseña temporal, roles, brains, deshabilitar, restablecer y eliminar. */
export default function AdminUsers({ me }: { me?: number }) {
  const { t } = useTranslation();
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
          <CreateDialog opened={creating} onClose={() => setCreating(false)} onCreated={(l) => { setCreating(false); qc.invalidateQueries({ queryKey: ["admin-users"] }); if (l) setShown({ ...l, title: t("Enlace de invitación") }); }} />
          <SecretReveal value={shown?.link ?? ""} title={shown?.title} note={shown?.emailed ? t("Se ha enviado también por correo. Es de un solo uso y caduca; puedes generar otro cuando quieras.") : t("Envíaselo a la persona (no se ha enviado ningún correo). Es de un solo uso y caduca; puedes generar otro cuando quieras.")} onClose={() => setShown(null)} />
          {open !== null && <UserPanel id={open} me={me} brains={brains.data ?? []} onClose={() => setOpen(null)} onLink={(l, title) => setShown({ link: l.link, title, emailed: l.emailed })} />}
          {!d.smtp && <Notice tone="warn" title={t("Sin servidor de correo")}>{t("Las invitaciones y la recuperación de contraseña no se pueden enviar: los enlaces se copian desde aquí y se entregan a mano.")} <Link to="/admin?seccion=mail">{t("Configurar el correo (SMTP)")}</Link></Notice>}
          <Group justify="space-between">
            <Segments label={t("Estado")} value={status} onChange={setStatus} data={[{ value: "all", label: t("Todos"), count: count("all") }, ...Object.entries(STATUS).map(([k, l]) => ({ value: k, label: l[0].toUpperCase() + l.slice(1) + "s", count: count(k) }))]} />
            <Btn kind="primary" icon="plus" onClick={() => setCreating(true)}>{t("Crear usuario")}</Btn>
          </Group>
          <ClearFilters active={v.active} onClear={v.clear} />
          <DataTable fz="sm">
            <DataTable.Thead><DataTable.Tr>
              <ColHead sort={v.sortProps("user")} filter={v.text("user", t("Nombre o email…"))}>{t("Usuario")}</ColHead>
              <ColHead filter={v.select("role")}>{t("Rol")}</ColHead>
              <ColHead>{t("Acceso")}</ColHead>
              <ColHead>{t("Estado")}</ColHead>
              <ColHead sort={v.sortProps("brains")}>{t("Brains")}</ColHead>
              <ColHead sort={v.sortProps("login")}>{t("Último acceso")}</ColHead>
              <DataTable.ActionsHead />
            </DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{v.rows.map((u) => (
              <DataTable.Tr key={u.id}>
                <DataTable.Td><Text size="sm" fw={500}>{u.name}</Text><Text size="xs" c="dimmed">{u.email}</Text></DataTable.Td>
                <DataTable.Td>{u.is_admin ? <Pill size="xs" tone="alt">{t("administrador")}</Pill> : t("Usuario")}</DataTable.Td>
                <DataTable.Td><Group gap={4}>{u.has_password && <Pill size="xs">{t("contraseña")}</Pill>}{u.identities.map((i) => <Pill key={i} size="xs">{i.toUpperCase()}</Pill>)}{!u.has_password && u.identities.length === 0 && "—"}</Group></DataTable.Td>
                <DataTable.Td><Pill size="xs" tone={TONE[u.status]}>{t(STATUS[u.status])}</Pill>{u.locked && <Pill size="xs" tone="danger"> {t("bloqueado")}</Pill>}</DataTable.Td>
                <DataTable.Td>{u.is_admin ? "todos" : u.brains}</DataTable.Td>
                <DataTable.Td>{fmt(u.last_login)}</DataTable.Td>
                <DataTable.Td><Btn size="row" onClick={() => setOpen(u.id)}>{t("Gestionar")}</Btn></DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable>
        </Stack>)}
    </DataState>
  );
}
