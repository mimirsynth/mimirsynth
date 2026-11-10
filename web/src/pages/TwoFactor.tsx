import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { Btn, CodeBlock, DialogActions, Form, Modal, MutationError, Notice, PasswordField, Pill, QrCode, TextField, ViewBar } from "../ui";

type Status = { enabled: boolean; recovery_left: number; required: boolean; has_password: boolean };
type Begin = { secret: string; uri: string; svg: string };

/** Códigos de recuperación recién generados: es la única vez que se ven. */
function Codes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { t } = useTranslation();
  return (
    <Stack gap="sm">
      <Notice tone="warn" title={t("Guarda tus códigos de recuperación")}>{t("Cada código sirve una sola vez si pierdes el móvil. Cópialos a un gestor de contraseñas: no volverán a mostrarse.")}</Notice>
      <CodeBlock copy select>{codes.join("\n")}</CodeBlock>
      <Group><Btn kind="primary" onClick={onDone}>{t("Los he guardado")}</Btn></Group>
    </Stack>
  );
}

/** Doble factor con app de autenticación (TOTP): alta con QR, códigos de recuperación, baja y regeneración. A view inside the settings group
 *  (or the sign-in card) that holds it: its bar says whether it is on and holds the actions; each one asks for its confirmation in a dialog. */
export function TwoFactor({ onChange }: { onChange?: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const st = useQuery({ queryKey: ["2fa"], queryFn: () => get<Status>("me/2fa") });
  const [step, setStep] = useState<"idle" | "password" | "scan" | "disable" | "regen">("idle");
  const [password, setPassword] = useState(""); const [code, setCode] = useState("");
  const [begin, setBegin] = useState<Begin | null>(null); const [codes, setCodes] = useState<string[] | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["2fa"] }); qc.invalidateQueries({ queryKey: ["me"] }); onChange?.(); };
  const reset = () => { setStep("idle"); setPassword(""); setCode(""); setBegin(null); };
  const start = useMutation({ mutationFn: () => send<Begin>("POST", "me/2fa/begin", { password }), onSuccess: (d) => { setBegin(d); setStep("scan"); setCode(""); } });
  const enable = useMutation({ mutationFn: () => send<{ recovery_codes: string[] }>("POST", "me/2fa/enable", { code }), onSuccess: (d) => { setCodes(d.recovery_codes); reset(); refresh(); } });
  const disable = useMutation({ mutationFn: () => send("POST", "me/2fa/disable", { password, code }), onSuccess: () => { reset(); refresh(); } });
  const regen = useMutation({ mutationFn: () => send<{ recovery_codes: string[] }>("POST", "me/2fa/recovery", { password, code }), onSuccess: (d) => { setCodes(d.recovery_codes); reset(); refresh(); } });
  if (!st.data) return null;
  const s = st.data;
  if (codes) return <Codes codes={codes} onDone={() => setCodes(null)} />;

  const cancel = <Btn kind="ghost" onClick={reset}>{t("Cancelar")}</Btn>;
  const confirm = (m: typeof disable, label: string, kind: "primary" | "danger") => (
    <Form onSubmit={() => m.mutate()}>
      <PasswordField label={t("Contraseña")} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} data-autofocus />
      <TextField label={t("Código de la app o de recuperación")} autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.currentTarget.value)} />
      <MutationError error={m.error} />
      <DialogActions>{cancel}<Btn type="submit" kind={kind} loading={m.isPending} disabled={!password || !code}>{label}</Btn></DialogActions>
    </Form>
  );
  const title = step === "disable" ? t("Desactivar doble factor") : step === "regen" ? t("Generar códigos nuevos") : t("Activar doble factor");

  return (
    <>
      <Modal opened={step !== "idle"} onClose={reset} title={title}>
        {step === "password" && (
          <Form onSubmit={() => start.mutate()}>
            <PasswordField label={t("Confirma tu contraseña")} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} data-autofocus />
            <MutationError error={start.error} />
            <DialogActions>{cancel}<Btn type="submit" kind="primary" loading={start.isPending} disabled={!password}>{t("Continuar")}</Btn></DialogActions>
          </Form>)}
        {step === "scan" && begin && (
          <Form onSubmit={() => enable.mutate()}>
            <Text size="sm">{t("1. Escanea el código con tu app de autenticación.")}</Text>
            <QrCode svg={begin.svg} label={t("Código QR para la app de autenticación")} />
            <Text size="sm">{t("¿No puedes escanearlo? Introduce esta clave a mano:")}</Text>
            <CodeBlock copy select>{begin.secret}</CodeBlock>
            <Text size="sm">{t("2. Escribe el código de 6 dígitos que muestra la app.")}</Text>
            <TextField label={t("Código")} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.currentTarget.value)} />
            <MutationError error={enable.error} />
            <DialogActions>{cancel}<Btn type="submit" kind="primary" loading={enable.isPending} disabled={code.trim().length < 6}>{t("Activar")}</Btn></DialogActions>
          </Form>)}
        {step === "disable" && confirm(disable, t("Desactivar doble factor"), "danger")}
        {step === "regen" && confirm(regen, t("Generar códigos nuevos"), "primary")}
      </Modal>
      <ViewBar title={t("Verificación en dos pasos")}
        help={t("Además de la contraseña pedirá un código de 6 dígitos de una app de autenticación (Aegis, 2FAS, Google Authenticator, Bitwarden…).")}
        meta={<Group gap="xs">
          <Pill tone={s.enabled ? "success" : undefined}>{s.enabled ? t("activado") : t("desactivado")}</Pill>
          {s.required && <Pill tone="warn">{t("exigido por el administrador")}</Pill>}
          {s.enabled && <span>{t("Te quedan")} <span className="ms-data">{s.recovery_left}</span> {t("códigos de recuperación sin usar.")}</span>}
        </Group>}
        actions={s.enabled
          ? <><Btn icon="refresh" onClick={() => setStep("regen")}>{t("Generar códigos nuevos")}</Btn>{!s.required && <Btn kind="danger" onClick={() => setStep("disable")}>{t("Desactivar")}</Btn>}</>
          : s.has_password && <Btn kind="primary" onClick={() => setStep("password")}>{t("Activar doble factor")}</Btn>} />
      {!s.enabled && !s.has_password && <Notice tone="warn">{t("Define antes una contraseña propia: el doble factor protege el acceso con contraseña.")}</Notice>}
    </>
  );
}
