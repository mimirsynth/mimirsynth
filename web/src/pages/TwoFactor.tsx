import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import { Btn, CodeBlock, Form, MutationError, Notice, PasswordField, Pill, QrCode, TextField } from "../ui";

type Status = { enabled: boolean; recovery_left: number; required: boolean; has_password: boolean };
type Begin = { secret: string; uri: string; svg: string };

/** Códigos de recuperación recién generados: es la única vez que se ven. */
function Codes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const { t } = useTranslation();
  return (
    <Stack gap="sm">
      <Notice tone="warn" title={t("Guarda tus códigos de recuperación")}>{t("Cada código sirve una sola vez si pierdes el móvil. Cópialos a un gestor de contraseñas: no volverán a mostrarse.")}</Notice>
      <CodeBlock copy select>{codes.join("\n")}</CodeBlock>
      <Group><Btn size="row" kind="primary" onClick={onDone}>{t("Los he guardado")}</Btn></Group>
    </Stack>
  );
}

/** Doble factor con app de autenticación (TOTP): alta con QR, códigos de recuperación, baja y regeneración. */
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

  const confirm = (m: typeof disable, label: string, kind: "primary" | "danger") => (
    <Form onSubmit={() => m.mutate()}>
      <PasswordField label={t("Contraseña")} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
      <TextField label={t("Código de la app o de recuperación")} autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.currentTarget.value)} />
      <MutationError error={m.error} />
      <Group gap="xs"><Btn size="row" type="submit" kind={kind} loading={m.isPending} disabled={!password || !code}>{label}</Btn><Btn size="row" kind="ghost" onClick={reset}>{t("Cancelar")}</Btn></Group>
    </Form>
  );

  return (
    <Stack gap="sm">
      <Group gap="xs"><Text fw={600} size="sm">{t("Doble factor")}</Text><Pill size="xs" tone={s.enabled ? "success" : undefined}>{s.enabled ? "activado" : "desactivado"}</Pill>{s.required && <Pill size="xs" tone="warn">{t("exigido por el administrador")}</Pill>}</Group>
      {step === "idle" && !s.enabled && <>
        <Text size="sm" c="dimmed">{t("Además de la contraseña pedirá un código de 6 dígitos de una app de autenticación (Aegis, 2FAS, Google Authenticator, Bitwarden…).")}</Text>
        {!s.has_password
          ? <Notice tone="info">{t("Define antes una contraseña propia: el doble factor protege el acceso con contraseña.")}</Notice>
          : <Group><Btn size="row" kind="primary" onClick={() => setStep("password")}>{t("Activar doble factor")}</Btn></Group>}
      </>}
      {step === "idle" && s.enabled && <>
        <Text size="sm" c="dimmed">{t("Te quedan")} {s.recovery_left} {t("códigos de recuperación sin usar.")}</Text>
        <Group gap="xs"><Btn size="row" icon="refresh" onClick={() => setStep("regen")}>{t("Generar códigos nuevos")}</Btn>{!s.required && <Btn size="row" kind="danger" onClick={() => setStep("disable")}>{t("Desactivar")}</Btn>}</Group>
      </>}
      {step === "password" && (
        <Form onSubmit={() => start.mutate()}>
          <PasswordField label={t("Confirma tu contraseña")} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} />
          <MutationError error={start.error} />
          <Group gap="xs"><Btn size="row" type="submit" kind="primary" loading={start.isPending} disabled={!password}>{t("Continuar")}</Btn><Btn size="row" kind="ghost" onClick={reset}>{t("Cancelar")}</Btn></Group>
        </Form>)}
      {step === "scan" && begin && (
        <Form onSubmit={() => enable.mutate()}>
          <Text size="sm">{t("1. Escanea el código con tu app de autenticación.")}</Text>
          <QrCode svg={begin.svg} label={t("Código QR para la app de autenticación")} />
          <Text size="xs" c="dimmed">{t("¿No puedes escanearlo? Introduce esta clave a mano:")}</Text>
          <CodeBlock copy select>{begin.secret}</CodeBlock>
          <Text size="sm">{t("2. Escribe el código de 6 dígitos que muestra la app.")}</Text>
          <TextField label={t("Código")} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.currentTarget.value)} />
          <MutationError error={enable.error} />
          <Group gap="xs"><Btn size="row" type="submit" kind="primary" loading={enable.isPending} disabled={code.trim().length < 6}>{t("Activar")}</Btn><Btn size="row" kind="ghost" onClick={reset}>{t("Cancelar")}</Btn></Group>
        </Form>)}
      {step === "disable" && confirm(disable, t("Desactivar doble factor"), "danger")}
      {step === "regen" && confirm(regen, t("Generar códigos nuevos"), "primary")}
    </Stack>
  );
}
