import { Center, Divider, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get, send } from "../api";
import Logo from "../Logo";
import { TwoFactor } from "./TwoFactor";
import { Btn, EmptyState, Form, MutationError, Notice, Panel, PasswordField, TextField } from "../ui";

type Options = { local: boolean; oidc: boolean; setup: boolean; password_min_length?: number };
const ERRORS: Record<string, string> = { not_invited: "Tu cuenta no está dada de alta en esta instancia. Pide a un administrador que te invite.", disabled: "Tu cuenta está deshabilitada. Contacta con un administrador." };

function Card({ name, subtitle, children }: { name: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <Center className="ms-fullh"><Panel withBorder p="xl" className="ms-authcard"><Stack align="center" gap="md">
      <Logo size={56} name={name} />{subtitle && <Text c="dimmed" size="sm" ta="center">{subtitle}</Text>}
      <Stack w="100%" gap="sm">{children}</Stack>
    </Stack></Panel></Center>
  );
}

/** Dos campos de contraseña que deben coincidir. */
function usePasswordPair() {
  const [pw, setPw] = useState(""); const [again, setAgain] = useState("");
  const mismatch = again !== "" && pw !== again;
  const fields = (min: number, label = "Contraseña") => (<>
    <PasswordField label={label} description={`Al menos ${min} caracteres.`} autoComplete="new-password" value={pw} onChange={(e) => setPw(e.currentTarget.value)} />
    <PasswordField label="Repite la contraseña" autoComplete="new-password" value={again} error={mismatch ? "No coinciden" : undefined} onChange={(e) => setAgain(e.currentTarget.value)} />
  </>);
  return { pw, ok: pw !== "" && pw === again, fields };
}

/** Pantalla de entrada: asistente de primer arranque, o email y contraseña (más OIDC si el administrador lo ha configurado). */
export function AuthScreen({ name }: { name: string }) {
  const qc = useQueryClient();
  const opts = useQuery({ queryKey: ["auth-options"], queryFn: () => get<Options>("auth/options") });
  const [mode, setMode] = useState<"login" | "forgot" | "mfa">("login");
  const [otp, setOtp] = useState("");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [uname, setUname] = useState(""); const [code, setCode] = useState("");
  const pair = usePasswordPair();
  const done = () => qc.invalidateQueries({ queryKey: ["me"] });
  const login = useMutation({ mutationFn: () => send<{ mfa?: boolean }>("POST", "auth/login", { email, password }), onSuccess: (d) => { if (d.mfa) { setMode("mfa"); setOtp(""); } else done(); } });
  const mfa = useMutation({ mutationFn: () => send("POST", "auth/mfa", { code: otp }), onSuccess: done });
  const setup = useMutation({ mutationFn: () => send("POST", "auth/setup", { code, email, name: uname, password: pair.pw }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["auth-options"] }); done(); } });
  const forgot = useMutation({ mutationFn: () => send("POST", "auth/forgot", { email }) });
  const authError = ERRORS[new URLSearchParams(window.location.search).get("auth_error") ?? ""];
  if (!opts.data) return <Center className="ms-fullh"><EmptyState>Cargando…</EmptyState></Center>;
  const min = opts.data.password_min_length ?? 12;

  if (opts.data.setup) {
    return (
      <Card name={name} subtitle="Primer arranque: crea la cuenta de administrador">
        <Form onSubmit={() => setup.mutate()}>
          <Notice tone="info">Escribe el código de instalación que el servicio ha impreso en su log (<code>docker logs</code> del contenedor).</Notice>
          <TextField label="Código de instalación" value={code} onChange={(e) => setCode(e.currentTarget.value)} autoComplete="off" />
          <TextField label="Tu nombre" value={uname} onChange={(e) => setUname(e.currentTarget.value)} autoComplete="name" />
          <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} autoComplete="username" />
          {pair.fields(min)}
          <MutationError error={setup.error} />
          <Btn kind="primary" type="submit" fullWidth loading={setup.isPending} disabled={!code || !uname || !email || !pair.ok}>Crear administrador</Btn>
        </Form>
      </Card>
    );
  }
  if (mode === "mfa") {
    return (
      <Card name={name} subtitle="Verificación en dos pasos">
        <Form onSubmit={() => mfa.mutate()}>
          <Text size="sm" c="dimmed">Escribe el código de 6 dígitos de tu app de autenticación, o uno de tus códigos de recuperación.</Text>
          <TextField label="Código" autoComplete="one-time-code" inputMode="text" autoFocus value={otp} onChange={(e) => setOtp(e.currentTarget.value)} />
          <MutationError error={mfa.error} />
          <Btn kind="primary" type="submit" fullWidth loading={mfa.isPending} disabled={!otp.trim()}>Verificar</Btn>
        </Form>
        <Btn kind="link" onClick={() => { setMode("login"); setPassword(""); }}>Volver a entrar</Btn>
      </Card>
    );
  }
  if (mode === "forgot") {
    return (
      <Card name={name} subtitle="Recuperar la contraseña">
        {forgot.isSuccess
          ? <Notice tone="success">Si existe una cuenta con ese email y el servidor de correo está configurado, recibirás un enlace para elegir una contraseña nueva.</Notice>
          : <Form onSubmit={() => forgot.mutate()}>
              <Text size="sm" c="dimmed">Te enviaremos un enlace por correo. Si el servidor no tiene correo configurado, pídele un enlace a un administrador.</Text>
              <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} autoComplete="username" />
              <MutationError error={forgot.error} />
              <Btn kind="primary" type="submit" fullWidth loading={forgot.isPending} disabled={!email}>Enviar enlace</Btn>
            </Form>}
        <Btn kind="link" onClick={() => setMode("login")}>Volver a entrar</Btn>
      </Card>
    );
  }
  return (
    <Card name={name} subtitle="Memoria para agentes">
      {authError && <Notice tone="warn">{authError}</Notice>}
      <Form onSubmit={() => login.mutate()}>
        <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} autoComplete="username" autoFocus />
        <PasswordField label="Contraseña" value={password} onChange={(e) => setPassword(e.currentTarget.value)} autoComplete="current-password" />
        <MutationError error={login.error} />
        <Btn kind="primary" type="submit" fullWidth icon="login" loading={login.isPending} disabled={!email || !password}>Entrar</Btn>
      </Form>
      <Btn kind="link" onClick={() => setMode("forgot")}>¿Has olvidado la contraseña?</Btn>
      {opts.data.oidc && <><Divider label="o" /><Btn component="a" href="/api/auth/login" fullWidth icon="login">Entrar con tu proveedor de identidad</Btn></>}
    </Card>
  );
}

/** Enlace de invitación o de restablecimiento (`/acceso/<código>`): elige contraseña y entra. */
export function AcceptScreen({ token, name }: { token: string; name: string }) {
  const info = useQuery({ queryKey: ["token", token], retry: false, queryFn: () => get<{ purpose: "invite" | "reset"; email: string; name: string }>(`auth/token/${token}`) });
  const opts = useQuery({ queryKey: ["auth-options"], queryFn: () => get<Options>("auth/options") });
  const [uname, setUname] = useState<string | null>(null);
  const pair = usePasswordPair();
  const accept = useMutation({ mutationFn: () => send("POST", "auth/accept", { token, password: pair.pw, name: uname ?? undefined }), onSuccess: () => window.location.replace("/") });
  if (info.isLoading) return <Center className="ms-fullh"><EmptyState>Comprobando el enlace…</EmptyState></Center>;
  if (info.error) return <Card name={name}><Notice tone="danger" title="Enlace no válido">{(info.error as Error).message}. Pide a un administrador que te envíe uno nuevo.</Notice><Btn component="a" href="/">Ir al inicio</Btn></Card>;
  const d = info.data!;
  return (
    <Card name={name} subtitle={d.purpose === "invite" ? "Te han invitado: elige tu contraseña" : "Elige una contraseña nueva"}>
      <Form onSubmit={() => accept.mutate()}>
        <TextField label="Email" value={d.email} disabled readOnly />
        {d.purpose === "invite" && <TextField label="Tu nombre" value={uname ?? d.name} onChange={(e) => setUname(e.currentTarget.value)} autoComplete="name" />}
        {pair.fields(opts.data?.password_min_length ?? 12, "Contraseña nueva")}
        <MutationError error={accept.error} />
        <Btn kind="primary" type="submit" fullWidth loading={accept.isPending} disabled={!pair.ok}>{d.purpose === "invite" ? "Crear mi cuenta" : "Guardar contraseña"}</Btn>
      </Form>
    </Card>
  );
}

/** Contraseña temporal puesta por un administrador: hay que cambiarla antes de usar la aplicación. */
export function ChangePasswordScreen({ name }: { name: string }) {
  const qc = useQueryClient();
  const [current, setCurrent] = useState("");
  const pair = usePasswordPair();
  const m = useMutation({ mutationFn: () => send("POST", "me/password", { current, new: pair.pw }), onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }) });
  return (
    <Card name={name} subtitle="Tu contraseña es temporal: elige una nueva para continuar">
      <Form onSubmit={() => m.mutate()}>
        <PasswordField label="Contraseña temporal" value={current} onChange={(e) => setCurrent(e.currentTarget.value)} autoComplete="current-password" />
        {pair.fields(12, "Contraseña nueva")}
        <MutationError error={m.error} />
        <Btn kind="primary" type="submit" fullWidth loading={m.isPending} disabled={!current || !pair.ok}>Cambiar contraseña</Btn>
      </Form>
    </Card>
  );
}

/** El administrador exige doble factor y esta cuenta aún no lo tiene: hay que activarlo antes de seguir. */
export function TwoFactorSetupScreen({ name }: { name: string }) {
  const qc = useQueryClient();
  const out = useMutation({ mutationFn: () => send("POST", "auth/logout"), onSuccess: () => window.location.replace("/") });
  return (
    <Card name={name} subtitle="El administrador exige verificación en dos pasos">
      <TwoFactor onChange={() => qc.invalidateQueries({ queryKey: ["me"] })} />
      <Btn kind="link" loading={out.isPending} onClick={() => out.mutate()}>Salir</Btn>
    </Card>
  );
}
