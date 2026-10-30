import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Brain, fmt, get, send } from "../api";
import { Btn, Check, EmptyState, ListCard, MutationError, Notice, PasswordField, Pill, ProgressBar } from "../ui";

type State = "queued" | "running" | "failed" | "cancelled" | "ready" | "downloaded" | "expired";
type Item = {
  id: number; state: State; done: number; total: number; message: string; error: string; user: string; created_at: string;
  vectors: boolean; encrypted: boolean; size?: number; expires_at?: string; downloaded_at?: string;
  graph?: { nodes: number; edges: number; dump_omitted: string | null };
  counts?: { proposals: number; documents: number; originals_omitted: Record<string, number> };
  secrets?: { masked: Record<string, number>; flagged: Record<string, number> };
};
type Exports = { ttl_hours: number; items: Item[] };

const STATES: Record<State, { label: string; tone: "neutral" | "success" | "warn" | "danger" | "alt" }> = {
  queued: { label: T("En cola"), tone: "neutral" }, running: { label: T("En marcha"), tone: "alt" }, failed: { label: T("Fallida"), tone: "danger" },
  cancelled: { label: T("Cancelada"), tone: "neutral" }, ready: { label: T("Lista para descargar"), tone: "success" },
  downloaded: { label: T("Descargada"), tone: "neutral" }, expired: { label: T("Caducada"), tone: "warn" },
};
const MIN_PASSWORD = 12;
const human = (n: number) => (n >= 1 << 30 ? `${(n / (1 << 30)).toFixed(1)} GB` : n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);
const sum = (o?: Record<string, number>) => Object.values(o ?? {}).reduce((a, b) => a + b, 0);

/** Lo que lleva un paquete terminado y lo que se ha quedado fuera por los secretos. */
function Contents({ it }: { it: Item }) {
  const { t } = useTranslation();
  if (!it.graph || !it.counts) return null;
  const masked = sum(it.secrets?.masked), omitted = sum(it.counts.originals_omitted);
  return (
    <Stack gap={2}>
      <Text size="xs">{t("Nodos: {{n}} · aristas: {{e}} · propuestas: {{p}} · documentos: {{d}}", { n: it.graph.nodes, e: it.graph.edges, p: it.counts.proposals, d: it.counts.documents })}
        {it.vectors ? ` · ${t("con vectores")}` : ""}{it.encrypted ? ` · ${t("cifrado")}` : ""}</Text>
      {masked > 0 && <Text size="xs" c="dimmed">{t("Secretos enmascarados: {{n}}.", { n: masked })}</Text>}
      {it.graph.dump_omitted === "secrets" && <Text size="xs" c="dimmed">{t("El grafo lleva un secreto: va solo como JSON enmascarado, sin la copia exacta.")}</Text>}
      {omitted > 0 && <Text size="xs" c="dimmed">{t("Originales que no van, por secretos o por no haberse podido revisar: {{n}}.", { n: omitted })}</Text>}
    </Stack>
  );
}

/** Exportar el brain a un paquete: grafo, curación, propuestas, documentos y consultas de referencia; sin miembros ni secretos. */
export default function BrainExport({ brain }: { brain: Brain }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["exports", brain.slug];
  const list = useQuery({ queryKey: key, queryFn: () => get<Exports>(`brains/${brain.slug}/exports`),
    refetchInterval: (q) => (q.state.data?.items.some((i) => i.state === "queued" || i.state === "running") ? 1500 : false) });
  const [vectors, setVectors] = useState(false);
  const [encrypt, setEncrypt] = useState(false);
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState("");
  const start = useMutation({ mutationFn: () => send<{ id: number }>("POST", `brains/${brain.slug}/exports`, { vectors, password: encrypt ? pw : undefined }),
    onSuccess: () => { setPw(""); setPw2(""); qc.invalidateQueries({ queryKey: key }); } });
  const busy = list.data?.items.some((i) => i.state === "queued" || i.state === "running");
  const pwOk = !encrypt || (pw.length >= MIN_PASSWORD && pw === pw2);
  const items = list.data?.items ?? [];
  return (
    <Stack gap="md">
      <Notice tone="info">{t("El paquete lleva el grafo, la ontología y el vocabulario con su historial, las propuestas, los documentos y las consultas de referencia. No lleva miembros, tokens, motores de IA ni canales de aviso, que solo sirven en esta instancia. Todo pasa antes por el detector de secretos: lo que detecta con seguridad se enmascara.")}</Notice>
      <Check checked={vectors} onChange={(e) => setVectors(e.currentTarget.checked)} label={t("Incluir los vectores")}
        description={t("Los embeddings del índice de búsqueda y los del grafo en su copia JSON. Evitan recalcularlos al importar con el mismo modelo, pero el paquete crece mucho.")} />
      <Check checked={encrypt} onChange={(e) => setEncrypt(e.currentTarget.checked)} label={t("Cifrar con una contraseña")}
        description={t("Sin la contraseña no se puede abrir el paquete. No se guarda en ningún sitio: si la pierdes, el paquete no se puede recuperar.")} />
      {encrypt && <Group grow align="flex-start">
        <PasswordField label={t("Contraseña")} description={t("Al menos 12 caracteres.")} value={pw} onChange={(e) => setPw(e.currentTarget.value)} autoComplete="new-password" />
        <PasswordField label={t("Repite la contraseña")} value={pw2} onChange={(e) => setPw2(e.currentTarget.value)} autoComplete="new-password"
          error={pw2 && pw2 !== pw ? t("No coincide") : undefined} />
      </Group>}
      <MutationError error={start.error} />
      <Group gap="xs">
        <Btn kind="primary" icon="download" disabled={!pwOk || busy} loading={start.isPending} onClick={() => start.mutate()}>{t("Exportar")}</Btn>
      </Group>
      <Text size="xs" c="dimmed">{t("Se prepara como un trabajo. El paquete se descarga una sola vez y se borra al descargarlo; si nadie lo descarga, caduca a las {{h}} horas.", { h: list.data?.ttl_hours ?? 24 })}</Text>
      {items.length ? (
        <Stack gap="xs">{items.map((it) => (
          <ListCard key={it.id} title={fmt(it.created_at)} aside={<Pill tone={STATES[it.state].tone}>{t(STATES[it.state].label)}</Pill>}
            meta={[it.user, it.size != null ? human(it.size) : "", it.state === "ready" && it.expires_at ? t("Hasta {{d}}", { d: fmt(it.expires_at) }) : ""].filter(Boolean).join(" · ")}
            actions={it.state === "ready" && <Btn size="row" icon="download" component="a" href={`/api/brains/${brain.slug}/exports/${it.id}/download`}
              onClick={() => setTimeout(() => qc.invalidateQueries({ queryKey: key }), 1500)}>{t("Descargar")}</Btn>}>
            {it.state === "running" || it.state === "queued" ? <ProgressBar done={it.done} total={it.total} text={it.message || t("En cola")} />
              : it.state === "failed" ? <Text size="xs" c="dimmed">{it.error}</Text> : <Contents it={it} />}
          </ListCard>))}
        </Stack>
      ) : list.isSuccess && <EmptyState>{t("Este brain no se ha exportado todavía.")}</EmptyState>}
    </Stack>
  );
}
