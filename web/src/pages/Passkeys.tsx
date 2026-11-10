import { useTranslation } from "react-i18next";
import { Group, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";
import { Btn, ConfirmDialog, DataState, DataTable, DialogActions, EmptyState, Form, Modal, MutationError, Notice, PasswordField, Pill, TextField, ViewBar } from "../ui";
import { createPasskey, passkeyError, passkeysSupported } from "../webauthn";

type Key = { id: number; name: string; created_at: string; last_used_at: string | null; backed_up: boolean };

/** Llaves de acceso (passkeys): entrar sin contraseña con la huella, el rostro o el PIN del dispositivo, o usarlas como segundo factor. A view
 *  inside the settings group (or the sign-in card) that holds it: its bar (the «i» and «Añadir llave de acceso», which opens its dialog) and
 *  the keys as a table. */
export function Passkeys({ hasPassword, onChange }: { hasPassword: boolean; onChange?: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["passkeys"], queryFn: () => get<Key[]>("me/passkeys") });
  const [adding, setAdding] = useState(false);
  const [password, setPassword] = useState(""); const [name, setName] = useState("");
  const [ask, setAsk] = useState<Key | null>(null); const [delPw, setDelPw] = useState("");
  const [fail, setFail] = useState<string | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["passkeys"] }); qc.invalidateQueries({ queryKey: ["me"] }); onChange?.(); };
  const reset = () => { setAdding(false); setPassword(""); setName(""); setFail(null); add.reset(); };
  const add = useMutation({
    mutationFn: async () => {
      const opts = await send<Record<string, unknown>>("POST", "me/passkeys/begin", { password });
      const credential = await createPasskey(opts);
      return send("POST", "me/passkeys/finish", { credential, name: name.trim() });
    },
    onSuccess: () => { reset(); refresh(); },
    onError: (e) => setFail(passkeyError(e)) });
  const del = useMutation({ mutationFn: (k: Key) => send("POST", `me/passkeys/${k.id}/delete`, { password: delPw }), onSuccess: () => { setDelPw(""); refresh(); } });
  if (!passkeysSupported()) return <Notice tone="info" title={t("Llaves de acceso")}>{t("Este navegador no admite llaves de acceso.")}</Notice>;
  return (
    <>
      <ConfirmDialog opened={!!ask} onClose={() => { setAsk(null); setDelPw(""); }} title={t("Quitar llave de acceso")} action={t("Quitar llave de acceso")} subject={ask?.name}
        warning={t("Dejarás de poder entrar con ella. Si es tu única forma de entrar, antes tendrás que añadir una contraseña o vincular un proveedor.")}
        onConfirm={() => del.mutateAsync(ask!)}>
        {hasPassword && <PasswordField label={t("Confirma tu contraseña")} autoComplete="current-password" value={delPw} onChange={(e) => setDelPw(e.currentTarget.value)} />}
      </ConfirmDialog>
      <Modal opened={adding} onClose={reset} title={t("Añadir llave de acceso")}>
        <Form onSubmit={() => add.mutate()}>
          <TextField label={t("Nombre de la llave")} placeholder={t("Portátil, móvil, llave USB…")} value={name} onChange={(e) => setName(e.currentTarget.value)} data-autofocus />
          {hasPassword && <PasswordField label={t("Confirma tu contraseña")} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} />}
          <MutationError error={add.error && passkeyError(add.error) ? add.error : null} />
          {fail === null && add.isError && <Text size="sm">{t("Has cancelado o el dispositivo no respondió.")}</Text>}
          <DialogActions><Btn kind="ghost" onClick={reset}>{t("Cancelar")}</Btn>
            <Btn type="submit" kind="primary" loading={add.isPending} disabled={hasPassword && !password}>{t("Crear llave de acceso")}</Btn></DialogActions>
        </Form>
      </Modal>
      <ViewBar title={t("Llaves de acceso")}
        help={t("Entra con la huella, el rostro o el PIN de tu dispositivo, sin escribir la contraseña. Con una llave de acceso ya cuentas con doble factor.")}
        actions={<Btn icon="plus" onClick={() => setAdding(true)}>{t("Añadir llave de acceso")}</Btn>} />
      <MutationError error={del.error} />
      {!list.data ? <DataState query={list} /> : list.data.length ? <DataTable fz="sm" aria-label={t("Llaves de acceso")}>
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Nombre")}</DataTable.Th><DataTable.Th>{t("Creada")}</DataTable.Th><DataTable.Th>{t("Último uso")}</DataTable.Th><DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{list.data.map((k) => (
          <DataTable.Tr key={k.id}>
            <DataTable.Td><Group gap="xs">{k.name}{k.backed_up && <Pill>{t("sincronizada")}</Pill>}</Group></DataTable.Td>
            <DataTable.Td className="ms-data">{fmt(k.created_at)}</DataTable.Td>
            <DataTable.Td className="ms-data">{k.last_used_at ? fmt(k.last_used_at) : t("sin usar")}</DataTable.Td>
            <DataTable.Td><Btn kind="danger" size="row" icon="trash" onClick={() => setAsk(k)}>{t("Quitar")}</Btn></DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : <EmptyState>{t("Aún no has añadido ninguna llave de acceso.")}</EmptyState>}
    </>
  );
}
