import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { Btn, Check, ConfirmDialog, CopyBtn, DataState, EmptyState, ListCard, Modal, MutationError, Notice, PasswordField, Pill, SettingsBody, SettingsGroup, TextField } from "../ui";

type Provider = {
  slug: string; name: string; issuer: string; client_id: string; secret_set: boolean; scopes: string; enabled: boolean; trust_unverified_email: boolean; auto_provision: boolean;
  allowed_domains: string; default_roles: string; groups_claim: string; admin_group: string; group_roles: string; redirect_uri: string;
};
type Draft = Omit<Provider, "secret_set" | "redirect_uri"> & { client_secret: string };

const EMPTY: Draft = { slug: "", name: "", issuer: "", client_id: "", client_secret: "", scopes: "openid profile email", enabled: true, trust_unverified_email: false, auto_provision: false, allowed_domains: "", default_roles: "", groups_claim: "groups", admin_group: "", group_roles: "" };

/** Alta y edición de un proveedor: conexión, política de alta y roles por grupo. El secreto nunca se muestra; vacío = conservar el guardado. */
function ProviderForm({ initial, isNew, onClose }: { initial: Draft; isNew: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [d, setD] = useState<Draft>(initial);
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () => isNew ? send("POST", "oidc-providers", d) : send("PUT", `oidc-providers/${initial.slug}`, { ...d, slug: null, client_secret: d.client_secret || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["oidc-providers"] }); qc.invalidateQueries({ queryKey: ["auth-options"] }); onClose(); },
  });
  const ok = d.name.trim() && d.issuer.trim() && d.client_id.trim() && (!isNew || (d.slug.trim() && d.client_secret));
  return (
    <Stack gap="xs">
      {isNew && <TextField label={t("Identificador")} description={t("Va en las URLs de inicio de sesión y de retorno. No se puede cambiar después.")} placeholder={"pocketid"} value={d.slug} onChange={(e) => set("slug", e.currentTarget.value.toLowerCase())} data-autofocus />}
      <TextField label={t("Nombre del botón")} description={t("Aparece en la pantalla de entrada: «Entrar con …».")} value={d.name} onChange={(e) => set("name", e.currentTarget.value)} />
      <TextField label={t("Emisor OIDC (issuer)")} description={t("URL base del proveedor de identidad; debe publicar /.well-known/openid-configuration.")} placeholder={"https://"} value={d.issuer} onChange={(e) => set("issuer", e.currentTarget.value)} />
      <TextField label={t("Client ID")} value={d.client_id} onChange={(e) => set("client_id", e.currentTarget.value)} />
      <PasswordField label={t("Client secret")} description={t("Se guarda cifrado y no se vuelve a mostrar.")} placeholder={isNew ? "" : t("Guardado (escribe para cambiarlo)")} autoComplete="new-password" value={d.client_secret} onChange={(e) => set("client_secret", e.currentTarget.value)} />
      <TextField label={t("Scopes")} description={t("Permisos que se piden al proveedor, separados por espacios.")} value={d.scopes} onChange={(e) => set("scopes", e.currentTarget.value)} />
      <Check label={t("Activo")} description={t("Un proveedor desactivado no aparece en la pantalla de entrada.")} checked={d.enabled} onChange={(e) => set("enabled", e.currentTarget.checked)} />
      <Check label={t("Aceptar emails sin verificar")} description={t("Solo si el proveedor no marca el email como verificado. Quien pueda registrar un email ajeno en el proveedor podría entrar como esa persona.")} checked={d.trust_unverified_email} onChange={(e) => set("trust_unverified_email", e.currentTarget.checked)} />
      <Check label={t("Alta automática")} description={t("Quien entre con un email verificado de uno de los dominios permitidos se da de alta solo, con rol de usuario, el acceso inicial y el que le den sus grupos.")} checked={d.auto_provision} onChange={(e) => set("auto_provision", e.currentTarget.checked)} />
      <TextField label={t("Dominios permitidos")} description={t("Dominios de email (separados por comas, p. ej. example.com) a los que se aplica el alta automática. Vacío = ninguno.")} value={d.allowed_domains} onChange={(e) => set("allowed_domains", e.currentTarget.value)} />
      <TextField label={t("Acceso inicial")} description={t("Brains a los que entra quien se da de alta solo, separados por comas, con el formato brain:rol (roles: reader, contributor). Se aplica una vez, al crear la cuenta; después se gestiona en Usuarios. Ejemplo: docs:reader.")} value={d.default_roles} onChange={(e) => set("default_roles", e.currentTarget.value)} />
      <TextField label={t("Claim de grupos")} description={t("Campo con los grupos de la persona en la identidad del proveedor (suele ser «groups»).")} value={d.groups_claim} onChange={(e) => set("groups_claim", e.currentTarget.value)} />
      <TextField label={t("Grupo de administradores")} description={t("Los miembros de este grupo son administradores de la instancia. Quien sale del grupo pierde el rol en su siguiente inicio de sesión, salvo que sea el último administrador.")} value={d.admin_group} onChange={(e) => set("admin_group", e.currentTarget.value)} />
      <TextField label={t("Roles por grupo")} description={t("Una regla por grupo, separadas por comas, con el formato grupo=brain:rol (roles: reader, contributor, curator, admin). Ejemplo: curadores=docs:curator, lectores=docs:reader.")} value={d.group_roles} onChange={(e) => set("group_roles", e.currentTarget.value)} />
      <MutationError error={save.error} />
      <Group justify="flex-end"><Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn><Btn kind="primary" icon="save" disabled={!ok} loading={save.isPending} onClick={() => save.mutate()}>{t("Guardar")}</Btn></Group>
    </Stack>
  );
}

function Actions({ p, onEdit, onDelete }: { p: Provider; onEdit: () => void; onDelete: () => void }) {
  const { t } = useTranslation();
  const test = useMutation({ mutationFn: () => send<{ issuer: string; pkce: boolean }>("POST", `oidc-providers/${p.slug}/test`, {}) });
  return (
    <Stack gap={6}>
      <Group gap={6}>
        <Btn size="row" icon="edit" onClick={onEdit}>{t("Editar")}</Btn>
        <Btn size="row" icon="refresh" loading={test.isPending} onClick={() => test.mutate()}>{t("Probar conexión")}</Btn>
        <Btn size="row" kind="danger" icon="trash" onClick={onDelete}>{t("Borrar")}</Btn>
      </Group>
      <MutationError error={test.error} />
      {test.data && <Notice tone={test.data.pkce ? "success" : "warn"}>{t("Proveedor alcanzable:")} {test.data.issuer}. {test.data.pkce ? t("Admite PKCE.") : t("No anuncia PKCE (S256); el inicio de sesión puede fallar.")}</Notice>}
    </Stack>
  );
}

/** Administración → Identidad: los proveedores OIDC con los que se puede entrar. Cada uno lleva su propia política de alta y de roles. */
export default function AdminProviders() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["oidc-providers"], queryFn: () => get<Provider[]>("oidc-providers") });
  const [form, setForm] = useState<{ draft: Draft; isNew: boolean } | null>(null);
  const [del, setDel] = useState<Provider | null>(null);
  const remove = useMutation({ mutationFn: (slug: string) => send("DELETE", `oidc-providers/${slug}`), onSuccess: () => { qc.invalidateQueries({ queryKey: ["oidc-providers"] }); qc.invalidateQueries({ queryKey: ["auth-options"] }); } });
  const edit = (p: Provider) => setForm({ isNew: false, draft: { ...p, client_secret: "" } });
  return (
    <SettingsGroup title={t("Proveedores de inicio de sesión")} description={t("Inicio de sesión con proveedores externos (OIDC). Es opcional: por defecto solo entran las personas que ya tienen cuenta. Cada proveedor tiene su propia política de alta automática y de roles según los grupos.")}
      action={<Btn icon="plus" onClick={() => setForm({ isNew: true, draft: EMPTY })}>{t("Añadir proveedor")}</Btn>}>
      <SettingsBody><DataState query={q}>
        {(list) => list.length === 0 ? <EmptyState>{t("No hay proveedores configurados: solo se entra con contraseña.")}</EmptyState> : (
          <Stack gap="xs">
            {list.map((p) => (
              <ListCard key={p.slug} title={p.name} aside={<Pill tone={p.enabled ? "success" : "neutral"}>{p.enabled ? t("Activo") : t("Desactivado")}</Pill>}
                tags={<>{p.auto_provision && <Pill>{t("Alta automática")}</Pill>}{p.admin_group && <Pill tone="alt">{t("Grupo admin")}: {p.admin_group}</Pill>}</>}
                meta={<>{p.issuer} · {p.slug}</>}
                actions={<Actions p={p} onEdit={() => edit(p)} onDelete={() => setDel(p)} />}>
                <Group gap={6} wrap="nowrap"><Text size="sm" c="dimmed">{t("URL de retorno")}</Text><Text size="sm" className="ms-data ms-breakall ms-grow">{p.redirect_uri}</Text><CopyBtn value={p.redirect_uri} /></Group>
              </ListCard>))}
          </Stack>)}
      </DataState></SettingsBody>
      <Modal opened={!!form} onClose={() => setForm(null)} title={form?.isNew ? t("Añadir proveedor") : t("Editar proveedor")} centered size="lg">
        {form && <ProviderForm initial={form.draft} isNew={form.isNew} onClose={() => setForm(null)} />}
      </Modal>
      <ConfirmDialog opened={!!del} onClose={() => setDel(null)} title={t("Borrar proveedor")} action={t("Borrar proveedor")}
        warning={t("Vas a borrar «{{name}}». Se desvinculan las identidades de las personas que entraban por él; si alguien se quedara sin ninguna forma de entrar, el borrado se rechaza.", { name: del?.name })}
        onConfirm={() => remove.mutateAsync(del!.slug)} />
    </SettingsGroup>
  );
}
