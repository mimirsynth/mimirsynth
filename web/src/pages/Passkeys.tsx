import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, ConfirmDialog, EmptyState, Form, MutationError, Notice, PasswordField, Pill, TextField } from "../ui";
import { createPasskey, passkeyError, passkeysSupported } from "../webauthn";

type Key = { id: number; name: string; created_at: string; last_used_at: string | null; backed_up: boolean };

/** Llaves de acceso (passkeys): entrar sin contraseña con la huella, el rostro o el PIN del dispositivo, o usarlas como segundo factor. */
export function Passkeys({ hasPassword, onChange }: { hasPassword: boolean; onChange?: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["passkeys"], queryFn: () => get<Key[]>("me/passkeys") });
  const [adding, setAdding] = useState(false);
  const [password, setPassword] = useState(""); const [name, setName] = useState("");
  const [ask, setAsk] = useState<Key | null>(null); const [delPw, setDelPw] = useState("");
  const [fail, setFail] = useState<string | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["passkeys"] }); qc.invalidateQueries({ queryKey: ["me"] }); onChange?.(); };
  const reset = () => { setAdding(false); setPassword(""); setName(""); setFail(null); };
  const add = useMutation({
    mutationFn: async () => {
      const opts = await send<Record<string, unknown>>("POST", "me/passkeys/begin", { password });
      const credential = await createPasskey(opts);
      return send("POST", "me/passkeys/finish", { credential, name: name.trim() });
    },
    onSuccess: () => { reset(); refresh(); },
    onError: (e) => setFail(passkeyError(e)) });
  const del = useMutation({ mutationFn: (k: Key) => send("POST", `me/passkeys/${k.id}/delete`, { password: delPw }), onSuccess: () => { setDelPw(""); refresh(); } });
  if (!passkeysSupported()) return <Notice tone="info">{t("Este navegador no admite llaves de acceso.")}</Notice>;
  return (
    <Stack gap="sm">
      <ConfirmDialog opened={!!ask} onClose={() => { setAsk(null); setDelPw(""); }} title={t("Quitar llave de acceso")} action={t("Quitar llave de acceso")} subject={ask?.name}
        warning={t("Dejarás de poder entrar con ella. Si es tu única forma de entrar, antes tendrás que añadir una contraseña o vincular un proveedor.")}
        onConfirm={() => del.mutateAsync(ask!)}>
        {hasPassword && <PasswordField label={t("Confirma tu contraseña")} autoComplete="current-password" value={delPw} onChange={(e) => setDelPw(e.currentTarget.value)} />}
      </ConfirmDialog>
      <Text size="sm" c="dimmed">{t("Entra con la huella, el rostro o el PIN de tu dispositivo, sin escribir la contraseña. Con una llave de acceso ya cuentas con doble factor.")}</Text>
      {list.data?.length ? list.data.map((k) => (
        <Group key={k.id} justify="space-between" wrap="nowrap">
          <Stack gap={0}>
            <Group gap="xs"><Text size="sm" fw={600}>{k.name}</Text>{k.backed_up && <Pill size="xs">{t("sincronizada")}</Pill>}</Group>
            <Text size="xs" c="dimmed">{t("Creada")} {fmt(k.created_at)} · {k.last_used_at ? `${t("último uso")} ${fmt(k.last_used_at)}` : t("sin usar")}</Text>
          </Stack>
          <Btn kind="danger" size="row" icon="trash" onClick={() => setAsk(k)}>{t("Quitar")}</Btn>
        </Group>)) : <EmptyState>{t("Aún no has añadido ninguna llave de acceso.")}</EmptyState>}
      <MutationError error={del.error} />
      {adding
        ? <Form onSubmit={() => add.mutate()}>
            <TextField label={t("Nombre de la llave")} placeholder={t("Portátil, móvil, llave USB…")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
            {hasPassword && <PasswordField label={t("Confirma tu contraseña")} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} />}
            <MutationError error={add.error && passkeyError(add.error) ? add.error : null} />
            {fail === null && add.isError && <Text size="xs" c="dimmed">{t("Has cancelado o el dispositivo no respondió.")}</Text>}
            <Group gap="xs"><Btn size="row" type="submit" kind="primary" loading={add.isPending} disabled={hasPassword && !password}>{t("Crear llave de acceso")}</Btn><Btn size="row" kind="ghost" onClick={reset}>{t("Cancelar")}</Btn></Group>
          </Form>
        : <Group><Btn size="row" icon="plus" onClick={() => setAdding(true)}>{t("Añadir llave de acceso")}</Btn></Group>}
    </Stack>
  );
}
