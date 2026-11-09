import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { List, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { get } from "../api";
import { Notice } from "../ui";

// What each kind of sealed value is, in the words of the screens where it is entered again.
const KIND: Record<string, string> = {
  two_factor: T("Doble factor de las cuentas (app de autenticación)"),
  llm: T("Claves de API de los motores LLM"),
  embedding: T("Claves de API de los motores de embeddings"),
  decider: T("Claves de API de los decisores"),
  oidc: T("Secretos de los proveedores de identidad (OIDC)"),
  smtp: T("Contraseña del servidor de correo (SMTP)"),
  notifications: T("Secretos de los canales de notificación"),
  webhooks: T("Secretos de los webhooks de entrada"),
  doc_sources: T("Credenciales de las fuentes de documentos"),
  graph: T("Contraseña de la base de datos del grafo"),
};

type Sealed = { ok: boolean; unreadable: Record<string, number>; total: number };

/** For instance administrators, at the top of Administration: the instance runs with another MIMIRSYNTH_SESSION_SECRET than the one
 *  that sealed its stored secrets (issue 193). Nothing is shown while they can be read. */
export default function SealedNotice() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["sealed"], queryFn: () => get<Sealed>("settings/sealed"), retry: false, refetchOnWindowFocus: false });
  if (!q.data || q.data.ok) return null;
  return (
    <Notice tone="danger" title={t("La clave secreta de la instancia no abre los secretos guardados")}>
      <Text size="sm">{t("MIMIRSYNTH_SESSION_SECRET no es la clave con la que se cifraron. Pasa al restaurar una copia en otro servidor, al copiar la base de datos a otra instalación o al editar el .env por error. Secretos guardados que no se pueden leer: {{total}}.", { total: q.data.total })}</Text>
      <List size="sm" mt={4}>{Object.entries(q.data.unreadable).map(([k, n]) => <List.Item key={k}>{t(KIND[k] ?? k)}: {n}</List.Item>)}</List>
      <Text size="sm" mt={4}>{t("Vuelve a poner en el .env la clave con la que se instaló y reinicia. Si se ha perdido, introduce de nuevo esos secretos y quita el doble factor de esas cuentas en Usuarios («Quitar doble factor»); el aviso desaparece cuando ya no queda ninguno sin leer.")}</Text>
    </Notice>
  );
}
