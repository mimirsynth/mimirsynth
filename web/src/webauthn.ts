/** Puente entre el JSON del servidor (base64url) y la API WebAuthn del navegador. */
const dec = (s: string) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(s.length / 4) * 4, "=")), (c) => c.charCodeAt(0)).buffer;
const enc = (b: ArrayBuffer | null) => (b ? btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "") : null);

export const passkeysSupported = () => typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials;

type Desc = { id: string; type: "public-key"; transports?: AuthenticatorTransport[] };
const descs = (l?: Desc[]) => l?.map((c) => ({ ...c, id: dec(c.id) }));

/** Pide al dispositivo crear una llave con las opciones del servidor y devuelve la credencial lista para enviar. */
export async function createPasskey(o: Record<string, any>): Promise<Record<string, unknown>> { // eslint-disable-line @typescript-eslint/no-explicit-any
  const cred = (await navigator.credentials.create({ publicKey: { ...o, challenge: dec(o.challenge), user: { ...o.user, id: dec(o.user.id) }, excludeCredentials: descs(o.excludeCredentials) } as PublicKeyCredentialCreationOptions })) as PublicKeyCredential | null;
  if (!cred) throw new Error("cancelado");
  const r = cred.response as AuthenticatorAttestationResponse;
  return { id: cred.id, rawId: enc(cred.rawId), type: cred.type, response: { clientDataJSON: enc(r.clientDataJSON), attestationObject: enc(r.attestationObject), transports: r.getTransports?.() ?? [] } };
}

/** Pide al dispositivo firmar el reto (entrada sin contraseña o segundo factor). */
export async function getPasskey(o: Record<string, any>): Promise<Record<string, unknown>> { // eslint-disable-line @typescript-eslint/no-explicit-any
  const cred = (await navigator.credentials.get({ publicKey: { ...o, challenge: dec(o.challenge), allowCredentials: descs(o.allowCredentials) } as PublicKeyCredentialRequestOptions })) as PublicKeyCredential | null;
  if (!cred) throw new Error("cancelado");
  const r = cred.response as AuthenticatorAssertionResponse;
  return { id: cred.id, rawId: enc(cred.rawId), type: cred.type, response: { clientDataJSON: enc(r.clientDataJSON), authenticatorData: enc(r.authenticatorData), signature: enc(r.signature), userHandle: enc(r.userHandle) } };
}

/** Mensaje legible para los fallos habituales del navegador (cancelar el gesto no es un error de la aplicación). */
export function passkeyError(e: unknown): string | null {
  const n = (e as { name?: string })?.name;
  if (n === "NotAllowedError" || n === "AbortError" || (e as Error)?.message === "cancelado") return null;
  return (e as Error)?.message || String(e);
}
