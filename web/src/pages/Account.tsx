import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { tr, setLanguage } from "../i18n";
import { TwoFactor } from "./TwoFactor";
import { Passkeys } from "./Passkeys";
import { Group, Stack, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { fmt, get, send } from "../api";
import TokensPanel, { ROLE } from "./TokensPanel";
import { Avatar, Btn, ClearFilters, ColHead, CopyBtn, DataTable, FillArea, Modal, Notice, Page, Panel, Pill, SelectField, TextField, useTableView, MutationError, ConfirmDialog, DataState, PageHeader, FilePicker, Form, LanguageSelect, PasswordField, SettingsBody, SettingsGroup, SettingsLayout, SettingsRow, SubNav, useTabParam } from "../ui";

type Profile = {
  id: number; name: string; idp_name: string; display_name: string; email: string | null; is_admin: boolean; auth_mode: string;
  avatar: string; has_custom_avatar: boolean; has_password: boolean; account_url: string; created_at: string; last_login: string | null;
  brains: { slug: string; name: string; role: string }[];
};
type Act = { ts: string; action: string; detail: Record<string, unknown> };

const ACTION: Record<string, string> = {
  login: T("Inicio de sesión"), "account.profile": T("Perfil actualizado"), "account.avatar": T("Avatar cambiado"), "account.sessions.revoke": T("Sesiones cerradas en otros dispositivos"),
  "token.create": T("Token creado"), "token.revoke": T("Token revocado"), "document.upload": T("Documento subido"), "document.delete": T("Documento borrado"), "document.reindex": T("Documento reindexado"),
  "proposal.submit": T("Propuesta enviada"), "proposal.approved": T("Propuesta aprobada"), "proposal.rejected": T("Propuesta rechazada"), "proposal.ingested": T("Propuesta ingerida"), "proposal.failed": T("Ingesta fallida"),
  "vocab.alias.add": T("Alias creado"), "vocab.alias.delete": T("Alias quitado"), "vocab.revert": T("Cambio deshecho"), "vocab.duplicates.ignore": T("Grupo marcado como «no son duplicados»"),
  "vocab.entity.merge": T("Entidades fusionadas"), "vocab.type.create": T("Tipo de entidad creado"), "vocab.type.edit": T("Tipo de entidad editado"), "vocab.type.delete": T("Tipo de entidad quitado"),
  "vocab.type.rename": T("Tipo de entidad renombrado"), "vocab.type.merge": T("Tipos de entidad fusionados"), "vocab.relation.create": T("Tipo de relación creado"), "vocab.relation.edit": T("Tipo de relación editado"),
  "vocab.relation.delete": T("Tipo de relación quitado"), "vocab.map.set": T("Regla del mapa cambiada"), "vocab.instructions.edit": T("Instrucciones de extracción editadas"),
  "vocab.fact.edit": T("Hecho editado"), "vocab.fact.invalidate": T("Hecho invalidado"), "vocab.fact.reactivate": T("Hecho reactivado"), "vocab.fact.delete": T("Hecho borrado"),
};
const what = (a: Act) => { const s = typeof a.detail?.summary === "string" ? a.detail.summary : ""; return (tr(ACTION[a.action] ?? a.action)) + (s ? ` — ${s}` : ""); };

/** Cambio (o primera definición) de la contraseña propia. */
type Ident = { identities: { id: number; provider: string; name: string; email: string; created_at: string }[]; can_unlink: boolean; available: { slug: string; name: string }[] };

/** Identidades externas vinculadas a la cuenta: otras formas de entrar. Vincular abre el proveedor y vuelve aquí. */
function Identities({ onMsg }: { onMsg: (m: { tone: "info" | "danger"; text: string }) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["my-identities"], queryFn: () => get<Ident>("me/identities") });
  const [del, setDel] = useState<{ id: number; name: string } | null>(null);
  const unlink = useMutation({ mutationFn: (id: number) => send("DELETE", `me/identities/${id}`), onSuccess: () => { qc.invalidateQueries({ queryKey: ["my-identities"] }); onMsg({ tone: "info", text: t("Identidad desvinculada.") }); } });
  return (
    <SettingsGroup title={t("Identidades vinculadas")} description={t("Proveedores externos con los que puedes entrar a esta cuenta. Vincula otro para tener más de una forma de acceso.")}>
      <SettingsBody>
        <DataState query={q}>
          {(d) => <Stack gap="xs">
            {d.identities.length === 0 && <Text size="sm" c="dimmed">{t("Todavía no has vinculado ningún proveedor.")}</Text>}
            {d.identities.map((i) => (
              <Group key={i.id} justify="space-between" wrap="nowrap">
                <Group gap={8}><Pill>{i.name}</Pill><Text size="sm" className="ms-breakall">{i.email || "—"}</Text><Text size="xs" c="dimmed">{fmt(i.created_at)}</Text></Group>
                <Btn size="row" kind="danger" icon="trash" disabled={!d.can_unlink} title={d.can_unlink ? undefined : t("Es tu única forma de entrar: pon una contraseña antes.")} onClick={() => setDel({ id: i.id, name: i.name })}>{t("Desvincular")}</Btn>
              </Group>))}
            {d.available.length > 0 && <Group gap={6}>{d.available.map((a) => <Btn key={a.slug} size="row" component="a" href={`/api/me/identities/link/${a.slug}`} icon="plus">{t("Vincular {{name}}", { name: a.name })}</Btn>)}</Group>}
          </Stack>}
        </DataState>
        <MutationError error={unlink.error} />
      </SettingsBody>
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Desvincular identidad")} action={t("Desvincular")}
        warning={t("Dejarás de poder entrar con «{{name}}». Podrás volver a vincularla cuando quieras.", { name: del?.name })} onConfirm={() => unlink.mutateAsync(del!.id)} />
    </SettingsGroup>
  );
}

function PasswordForm({ has, onDone }: { has: boolean; onDone: () => void }) {
  const { t } = useTranslation();
  const [f, setF] = useState({ current: "", pw: "", again: "" });
  const m = useMutation({ mutationFn: () => send("POST", "me/password", { current: f.current, new: f.pw }), onSuccess: () => { setF({ current: "", pw: "", again: "" }); onDone(); } });
  const mismatch = f.again !== "" && f.pw !== f.again;
  return (
    <Form onSubmit={() => m.mutate()}>
      {has && <PasswordField label={t("Contraseña actual")} autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.currentTarget.value })} />}
      <PasswordField label={t("Contraseña nueva")} autoComplete="new-password" value={f.pw} onChange={(e) => setF({ ...f, pw: e.currentTarget.value })} />
      <PasswordField label={t("Repite la contraseña nueva")} autoComplete="new-password" value={f.again} error={mismatch ? t("No coinciden") : undefined} onChange={(e) => setF({ ...f, again: e.currentTarget.value })} />
      <MutationError error={m.error} />
      <Group><Btn size="row" type="submit" kind="primary" loading={m.isPending} disabled={!f.pw || mismatch || f.again === "" || (has && !f.current)}>{has ? t("Cambiar contraseña") : t("Definir contraseña")}</Btn></Group>
    </Form>
  );
}

function ActivityTable({ rows }: { rows: Act[] }) {
  const { t } = useTranslation();
  const v = useTableView(rows, { ts: { get: (a: Act) => a.ts }, what: { get: (a: Act) => what(a) } });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr><ColHead width={170} sort={v.sortProps("ts")}>{t("Cuándo")}</ColHead><ColHead filter={v.text("what", t("Buscar en la actividad…"))}>{t("Qué")}</ColHead></DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((a, i) => <DataTable.Tr key={i}><DataTable.Td>{fmt(a.ts)}</DataTable.Td><DataTable.Td>{what(a)}</DataTable.Td></DataTable.Tr>)}</DataTable.Tbody>
      </DataTable>
    </Stack>
  );
}

export default function Account() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const file = useRef<HTMLInputElement>(null);
  const prof = useQuery({ queryKey: ["profile"], queryFn: () => get<Profile>("me/profile") });
  const act = useQuery({ queryKey: ["my-activity"], queryFn: () => get<Act[]>("me/activity") });
  const [name, setName] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ tone: "info" | "danger"; text: string } | null>(null);
  const refreshMe = () => { qc.invalidateQueries({ queryKey: ["profile"] }); qc.invalidateQueries({ queryKey: ["me"] }); qc.invalidateQueries({ queryKey: ["my-activity"] }); };
  const saveName = useMutation({ mutationFn: (n: string) => send("PATCH", "me/profile", { display_name: n }), onSuccess: () => { setName(null); setMsg({ tone: "info", text: t("Nombre actualizado.") }); refreshMe(); } });
  const upload = useMutation({
    mutationFn: async (f: File) => { const r = await fetch("/api/me/avatar", { method: "POST", credentials: "include", body: f }); if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText); },
    onSuccess: () => { setMsg({ tone: "info", text: t("Avatar actualizado.") }); refreshMe(); }, onError: (e) => setMsg({ tone: "danger", text: (e as Error).message }) });
  const saveLocale = useMutation({ mutationFn: (l: string) => send("PATCH", "me/profile", { locale: l }), onSuccess: refreshMe });
  const removeAvatar = useMutation({ mutationFn: () => send("DELETE", "me/avatar"), onSuccess: refreshMe });
  const [askAvatar, setAskAvatar] = useState(false);
  const logout = useMutation({ mutationFn: () => send("POST", "auth/logout"), onSuccess: () => { qc.clear(); window.location.href = "/"; } });
  const others = useMutation({ mutationFn: () => send("POST", "me/sessions/revoke-others"), onSuccess: () => { setMsg({ tone: "info", text: t("Se cerró la sesión en el resto de dispositivos.") }); refreshMe(); } });

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("linked")) setMsg({ tone: "info", text: t("Identidad vinculada.") });
    else if (q.get("link_error")) setMsg({ tone: "danger", text: q.get("link_error") === "taken" ? t("Esa identidad ya pertenece a otra cuenta.") : t("No se pudo vincular: vuelve a intentarlo.") });
    if (q.has("linked") || q.has("link_error")) window.history.replaceState(null, "", window.location.pathname + "?seccion=seguridad");
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const [section, setSection] = useTabParam("perfil", "seccion");
  const nav = [{ heading: t("Cuenta") }, { value: "perfil", label: t("Perfil") }, { value: "seguridad", label: t("Seguridad") }, { heading: t("Acceso") }, { value: "tokens", label: t("Tokens de API") }, { heading: t("Historial") }, { value: "actividad", label: t("Actividad") }];
  const p = prof.data;
  if (!p) return <DataState query={prof} />;
  const editing = name !== null;
  return (
    <Page>
      <ConfirmDialog opened={askAvatar} onClose={() => setAskAvatar(false)} title={t("Quitar avatar")} action={t("Quitar avatar")}
        warning={t("Se vuelve a usar la imagen de tu proveedor de identidad, o las iniciales.")} onConfirm={() => removeAvatar.mutateAsync()} />
      <PageHeader title={t("Mi cuenta")} description={t("Tu perfil, tus tokens de API en todos los brains, tus sesiones y tu actividad reciente.")} />
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
      <FillArea>
        <SettingsLayout nav={<><SubNav label={t("Secciones de Mi cuenta")} value={section} onChange={setSection} items={nav} />
          {p.auth_mode !== "off" && <div className="ms-subnav-exit"><Btn fullWidth icon="logout" loading={logout.isPending} onClick={() => logout.mutate()}>{t("Cerrar sesión")}</Btn></div>}</>}>
          {section === "perfil" && <>
            <SettingsGroup title={t("Perfil")} description={t("Cómo te ven el resto de personas en la aplicación.")}>
              <SettingsBody><Stack gap="sm">
                <Group wrap="nowrap" gap="md" align="center">
                  <Avatar src={p.avatar} name={p.name} size={72} />
                  <Stack gap={6}>
                    <Group gap={6}>
                      <FilePicker size="row" label={t("Cambiar avatar")} accept="image/png,image/jpeg,image/webp" loading={upload.isPending} onFiles={(fl) => upload.mutate(fl[0])} />
                      {p.has_custom_avatar && <Btn kind="danger" size="row" icon="trash" onClick={() => setAskAvatar(true)}>{t("Quitar")}</Btn>}
                    </Group>
                    <Text size="xs" c="dimmed">{t("PNG, JPEG o WebP, hasta 1 MB.")}{!p.has_custom_avatar && p.avatar ? t(" Ahora usas la imagen de tu proveedor de identidad.") : ""}</Text>
                  </Stack>
                </Group>
                <TextField label={t("Nombre visible")} description={t("Vacío = el de tu proveedor de identidad ({{v}}).", { v: p.idp_name || "—" })} value={editing ? name! : p.display_name}
                  placeholder={p.idp_name} onChange={(e) => setName(e.currentTarget.value)} maxLength={80} />
                <LanguageSelect label={t("Idioma")} value={i18n.language} onChange={(l) => { setLanguage(l); saveLocale.mutate(l); }} />
                {editing && <Group><Btn size="row" icon="check" loading={saveName.isPending} onClick={() => saveName.mutate(name!)}>{t("Guardar")}</Btn><Btn size="row" onClick={() => setName(null)}>{t("Cancelar")}</Btn></Group>}
              </Stack></SettingsBody>
            </SettingsGroup>
            <SettingsGroup title={t("Cuenta")} description={t("Datos de tu cuenta y brains a los que tienes acceso.")}>
              <SettingsRow label={t("Correo")}>{p.email ?? "—"}</SettingsRow>
              <SettingsRow label={t("Rol en la instancia")}>{p.is_admin ? <Pill tone="alt">{t("administrador de la instancia")}</Pill> : <Pill>{t("usuario")}</Pill>}</SettingsRow>
              <SettingsRow label={t("Cuenta creada")}>{fmt(p.created_at)}</SettingsRow>
              <SettingsRow label={t("Último acceso")}>{fmt(p.last_login)}</SettingsRow>
              <SettingsRow label={t("Tus brains")}>
                <Group gap={6}>{p.brains.length === 0 ? <Text size="sm" c="dimmed">{t("Todavía no tienes acceso a ningún brain.")}</Text> : p.brains.map((b) => <Pill key={b.slug} title={b.slug}>{b.name} · {t(ROLE[b.role] ?? b.role)}</Pill>)}</Group>
              </SettingsRow>
            </SettingsGroup>
          </>}
          {section === "seguridad" && (p.auth_mode === "off"
            ? <SettingsGroup title={t("Seguridad")}><SettingsBody><Notice tone="warn">{t("Esta instancia está en modo prototipo, sin inicio de sesión: no hay contraseña ni sesiones que gestionar.")}</Notice></SettingsBody></SettingsGroup>
            : <>
              <SettingsGroup title={t("Contraseña")} description={p.has_password ? t("Cámbiala cuando quieras; se cierra la sesión en el resto de dispositivos.") : t("Para poder entrar también directamente, sin depender del proveedor de identidad.")}>
                <SettingsBody><PasswordForm has={p.has_password} onDone={() => { setMsg({ tone: "info", text: t("Contraseña actualizada. Se cerró la sesión en el resto de dispositivos.") }); refreshMe(); }} /></SettingsBody>
              </SettingsGroup>
              <Identities onMsg={setMsg} />
              <SettingsGroup title={t("Llaves de acceso")} description={t("Passkeys: la huella, el rostro o el PIN de tu dispositivo en lugar de la contraseña.")}><SettingsBody><Passkeys hasPassword={p.has_password} onChange={refreshMe} /></SettingsBody></SettingsGroup>
              {p.has_password && <SettingsGroup title={t("Verificación en dos pasos")} description={t("Además de la contraseña, pide un código de una app de autenticación.")}><SettingsBody><TwoFactor /></SettingsBody></SettingsGroup>}
              <SettingsGroup title={t("Sesiones")} description={t("Si crees que alguien más tiene abierta tu sesión, ciérrala en todos los demás dispositivos. Esta sesión sigue abierta.")}>
                <SettingsBody><Group gap="xs">
                  <Btn size="row" icon="logout" loading={others.isPending} onClick={() => others.mutate()}>{t("Cerrar sesión en otros dispositivos")}</Btn>
                  <Btn size="row" icon="logout" loading={logout.isPending} onClick={() => logout.mutate()}>{t("Salir")}</Btn>
                  {p.account_url && <Btn size="row" component="a" href={p.account_url} target="_blank" rel="noopener noreferrer" icon="login">{t("Cuenta en tu proveedor de identidad")}</Btn>}
                </Group></SettingsBody>
              </SettingsGroup>
            </>)}
          {section === "tokens" && (
            <SettingsGroup title={t("Mis tokens de API")} description={t("Para plugins y agentes. Cada token vale para un solo brain y nunca tiene más rol que el tuyo. Se muestra una única vez al crearlo.")}>
              <SettingsBody><TokensPanel brains={p.brains} /></SettingsBody>
            </SettingsGroup>)}
          {section === "actividad" && <SettingsGroup title={t("Actividad reciente")} description={t("Lo último que has hecho con tu cuenta.")}><SettingsBody><ActivityTable rows={act.data ?? []} /></SettingsBody></SettingsGroup>}
        </SettingsLayout>
      </FillArea>

    </Page>
  );
}
