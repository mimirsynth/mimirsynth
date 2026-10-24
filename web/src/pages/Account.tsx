import { TwoFactor } from "./TwoFactor";
import { Group, Stack, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { fmt, get, send } from "../api";
import TokensPanel, { ROLE } from "./TokensPanel";
import { Avatar, Btn, ClearFilters, ColHead, CopyBtn, DataTable, FillArea, Modal, Notice, Page, Panel, Pill, SelectField, TextField, useTableView, MutationError, ConfirmDialog, DataState, PageHeader, FilePicker, Form, PasswordField, SettingsBody, SettingsGroup, SettingsLayout, SettingsRow, SubNav, useTabParam } from "../ui";

type Profile = {
  id: number; name: string; idp_name: string; display_name: string; email: string | null; is_admin: boolean; auth_mode: string;
  avatar: string; has_custom_avatar: boolean; has_password: boolean; account_url: string; created_at: string; last_login: string | null;
  brains: { slug: string; name: string; role: string }[];
};
type Act = { ts: string; action: string; detail: Record<string, unknown> };

const ACTION: Record<string, string> = {
  login: "Inicio de sesión", "account.profile": "Perfil actualizado", "account.avatar": "Avatar cambiado", "account.sessions.revoke": "Sesiones cerradas en otros dispositivos",
  "token.create": "Token creado", "token.revoke": "Token revocado", "document.upload": "Documento subido", "document.delete": "Documento borrado", "document.reindex": "Documento reindexado",
  "proposal.submit": "Propuesta enviada", "proposal.approved": "Propuesta aprobada", "proposal.rejected": "Propuesta rechazada", "proposal.ingested": "Propuesta ingerida", "proposal.failed": "Ingesta fallida",
  "vocab.alias.add": "Alias creado", "vocab.alias.delete": "Alias quitado", "vocab.revert": "Cambio deshecho", "vocab.duplicates.ignore": "Grupo marcado como «no son duplicados»",
  "vocab.entity.merge": "Entidades fusionadas", "vocab.type.create": "Tipo de entidad creado", "vocab.type.edit": "Tipo de entidad editado", "vocab.type.delete": "Tipo de entidad quitado",
  "vocab.type.rename": "Tipo de entidad renombrado", "vocab.type.merge": "Tipos de entidad fusionados", "vocab.relation.create": "Tipo de relación creado", "vocab.relation.edit": "Tipo de relación editado",
  "vocab.relation.delete": "Tipo de relación quitado", "vocab.map.set": "Regla del mapa cambiada", "vocab.instructions.edit": "Instrucciones de extracción editadas",
  "vocab.fact.edit": "Hecho editado", "vocab.fact.invalidate": "Hecho invalidado", "vocab.fact.reactivate": "Hecho reactivado", "vocab.fact.delete": "Hecho borrado",
};
const what = (a: Act) => { const s = typeof a.detail?.summary === "string" ? a.detail.summary : ""; return (ACTION[a.action] ?? a.action) + (s ? ` — ${s}` : ""); };

/** Cambio (o primera definición) de la contraseña propia. */
function PasswordForm({ has, onDone }: { has: boolean; onDone: () => void }) {
  const [f, setF] = useState({ current: "", pw: "", again: "" });
  const m = useMutation({ mutationFn: () => send("POST", "me/password", { current: f.current, new: f.pw }), onSuccess: () => { setF({ current: "", pw: "", again: "" }); onDone(); } });
  const mismatch = f.again !== "" && f.pw !== f.again;
  return (
    <Form onSubmit={() => m.mutate()}>
      {has && <PasswordField label="Contraseña actual" autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.currentTarget.value })} />}
      <PasswordField label="Contraseña nueva" autoComplete="new-password" value={f.pw} onChange={(e) => setF({ ...f, pw: e.currentTarget.value })} />
      <PasswordField label="Repite la contraseña nueva" autoComplete="new-password" value={f.again} error={mismatch ? "No coinciden" : undefined} onChange={(e) => setF({ ...f, again: e.currentTarget.value })} />
      <MutationError error={m.error} />
      <Group><Btn size="row" type="submit" kind="primary" loading={m.isPending} disabled={!f.pw || mismatch || f.again === "" || (has && !f.current)}>{has ? "Cambiar contraseña" : "Definir contraseña"}</Btn></Group>
    </Form>
  );
}

function ActivityTable({ rows }: { rows: Act[] }) {
  const v = useTableView(rows, { ts: { get: (a: Act) => a.ts }, what: { get: (a: Act) => what(a) } });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead width={170} sort={v.sortProps("ts")}>Cuándo</ColHead><ColHead filter={v.text("what", "Buscar en la actividad…")}>Qué</ColHead></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((a, i) => <DataTable.Tr key={i}><DataTable.Td>{fmt(a.ts)}</DataTable.Td><DataTable.Td>{what(a)}</DataTable.Td></DataTable.Tr>)}</DataTable.Tbody>
      </DataTable>
    </Stack>
  );
}

export default function Account() {
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const prof = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("me/profile") });
  const act = useQuery({ queryKey: ["my-activity"], queryFn: () => get<Act[]>("me/activity") });
  const [name, setName] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "info" | "danger"; text: string } | null>(null);
  const refreshMe = () => { qc.invalidateQueries({ queryKey: ["profile"] }); qc.invalidateQueries({ queryKey: ["me"] }); qc.invalidateQueries({ queryKey: ["my-activity"] }); };
  const saveName = useMutation({ mutationFn: (n: string) => send("PATCH", "me/profile", { display_name: n }), onSuccess: () => { setName(null); setMsg({ tone: "info", text: "Nombre actualizado." }); refreshMe(); } });
  const upload = useMutation({
    mutationFn: async (f: File) => { const r = await fetch("/api/me/avatar", { method: "POST", credentials: "include", body: f }); if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText); },
    onSuccess: () => { setMsg({ tone: "info", text: "Avatar actualizado." }); refreshMe(); }, onError: (e) => setMsg({ tone: "danger", text: (e as Error).message }) });
  const removeAvatar = useMutation({ mutationFn: () => send("DELETE", "me/avatar"), onSuccess: refreshMe });
  const [askAvatar, setAskAvatar] = useState(false);
  const logout = useMutation({ mutationFn: () => send("POST", "auth/logout"), onSuccess: () => { qc.clear(); window.location.href = "/"; } });
  const others = useMutation({ mutationFn: () => send("POST", "me/sessions/revoke-others"), onSuccess: () => { setMsg({ tone: "info", text: "Se cerró la sesión en el resto de dispositivos." }); refreshMe(); } });

  const [section, setSection] = useTabParam("perfil", "seccion");
  const nav = [{ heading: "Cuenta" }, { value: "perfil", label: "Perfil" }, { value: "seguridad", label: "Seguridad" }, { heading: "Acceso" }, { value: "tokens", label: "Tokens de API" }, { heading: "Historial" }, { value: "actividad", label: "Actividad" }];
  const p = prof.data;
  if (!p) return <DataState query={prof} />;
  const editing = name !== null;
  return (
    <Page>
      <ConfirmDialog opened={askAvatar} onClose={() => setAskAvatar(false)} title="Quitar avatar" action="Quitar avatar"
        warning="Se vuelve a usar la imagen de tu proveedor de identidad, o las iniciales." onConfirm={() => removeAvatar.mutateAsync()} />
      <PageHeader title="Mi cuenta" description="Tu perfil, tus tokens de API en todos los brains, tus sesiones y tu actividad reciente." />
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
      <FillArea>
        <SettingsLayout nav={<SubNav label="Secciones de Mi cuenta" value={section} onChange={setSection} items={nav} />}>
          {section === "perfil" && <>
            <SettingsGroup title="Perfil" description="Cómo te ven el resto de personas en la aplicación.">
              <SettingsBody><Stack gap="sm">
                <Group wrap="nowrap" gap="md" align="center">
                  <Avatar src={p.avatar} name={p.name} size={72} />
                  <Stack gap={6}>
                    <Group gap={6}>
                      <FilePicker size="row" label="Cambiar avatar" accept="image/png,image/jpeg,image/webp" loading={upload.isPending} onFiles={(fl) => upload.mutate(fl[0])} />
                      {p.has_custom_avatar && <Btn kind="danger" size="row" icon="trash" onClick={() => setAskAvatar(true)}>Quitar</Btn>}
                    </Group>
                    <Text size="xs" c="dimmed">PNG, JPEG o WebP, hasta 1 MB.{!p.has_custom_avatar && p.avatar ? " Ahora usas la imagen de tu proveedor de identidad." : ""}</Text>
                  </Stack>
                </Group>
                <TextField label="Nombre visible" description={`Vacío = el de tu proveedor de identidad (${p.idp_name || "—"}).`} value={editing ? name! : p.display_name}
                  placeholder={p.idp_name} onChange={(e) => setName(e.currentTarget.value)} maxLength={80} />
                {editing && <Group><Btn size="row" icon="check" loading={saveName.isPending} onClick={() => saveName.mutate(name!)}>Guardar</Btn><Btn size="row" onClick={() => setName(null)}>Cancelar</Btn></Group>}
              </Stack></SettingsBody>
            </SettingsGroup>
            <SettingsGroup title="Cuenta" description="Datos de tu cuenta y brains a los que tienes acceso.">
              <SettingsRow label="Correo">{p.email ?? "—"}</SettingsRow>
              <SettingsRow label="Rol en la instancia">{p.is_admin ? <Pill tone="alt">administrador de la instancia</Pill> : <Pill>usuario</Pill>}</SettingsRow>
              <SettingsRow label="Cuenta creada">{fmt(p.created_at)}</SettingsRow>
              <SettingsRow label="Último acceso">{fmt(p.last_login)}</SettingsRow>
              <SettingsRow label="Tus brains">
                <Group gap={6}>{p.brains.length === 0 ? <Text size="sm" c="dimmed">Todavía no tienes acceso a ningún brain.</Text> : p.brains.map((b) => <Pill key={b.slug} title={b.slug}>{b.name} · {ROLE[b.role] ?? b.role}</Pill>)}</Group>
              </SettingsRow>
            </SettingsGroup>
          </>}
          {section === "seguridad" && (p.auth_mode === "off"
            ? <SettingsGroup title="Seguridad"><SettingsBody><Notice tone="warn">Esta instancia está en modo prototipo, sin inicio de sesión: no hay contraseña ni sesiones que gestionar.</Notice></SettingsBody></SettingsGroup>
            : <>
              <SettingsGroup title="Contraseña" description={p.has_password ? "Cámbiala cuando quieras; se cierra la sesión en el resto de dispositivos." : "Para poder entrar también directamente, sin depender del proveedor de identidad."}>
                <SettingsBody><PasswordForm has={p.has_password} onDone={() => { setMsg({ tone: "info", text: "Contraseña actualizada. Se cerró la sesión en el resto de dispositivos." }); refreshMe(); }} /></SettingsBody>
              </SettingsGroup>
              {p.has_password && <SettingsGroup title="Verificación en dos pasos" description="Además de la contraseña, pide un código de una app de autenticación."><SettingsBody><TwoFactor /></SettingsBody></SettingsGroup>}
              <SettingsGroup title="Sesiones" description="Si crees que alguien más tiene abierta tu sesión, ciérrala en todos los demás dispositivos. Esta sesión sigue abierta.">
                <SettingsBody><Group gap="xs">
                  <Btn size="row" icon="logout" loading={others.isPending} onClick={() => others.mutate()}>Cerrar sesión en otros dispositivos</Btn>
                  <Btn size="row" icon="logout" loading={logout.isPending} onClick={() => logout.mutate()}>Salir</Btn>
                  {p.account_url && <Btn size="row" component="a" href={p.account_url} target="_blank" rel="noopener noreferrer" icon="login">Cuenta en tu proveedor de identidad</Btn>}
                </Group></SettingsBody>
              </SettingsGroup>
            </>)}
          {section === "tokens" && (
            <SettingsGroup title="Mis tokens de API" description="Para plugins y agentes. Cada token vale para un solo brain y nunca tiene más rol que el tuyo. Se muestra una única vez al crearlo.">
              <SettingsBody><TokensPanel brains={p.brains} /></SettingsBody>
            </SettingsGroup>)}
          {section === "actividad" && <SettingsGroup title="Actividad reciente" description="Lo último que has hecho con tu cuenta."><SettingsBody><ActivityTable rows={act.data ?? []} /></SettingsBody></SettingsGroup>}
        </SettingsLayout>
      </FillArea>

    </Page>
  );
}
