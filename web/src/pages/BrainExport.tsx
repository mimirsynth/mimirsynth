import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Brain, fmt, get, send } from "../api";
import { Block, Btn, CellText, DataState, DataTable, EmptyState, MutationError, PasswordField, Pill, ProgressBar, SettingsBody, SettingsRow, Toggle, SettingsGroup } from "../ui";

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

/** Lo que lleva un paquete terminado y, en su segunda línea, lo que se ha quedado fuera por los secretos. */
function Contents({ it }: { it: Item }) {
  const { t } = useTranslation();
  if (!it.graph || !it.counts) return null;
  const masked = sum(it.secrets?.masked), omitted = sum(it.counts.originals_omitted);
  const notes = [
    masked > 0 && t("Secretos enmascarados: {{n}}.", { n: masked }),
    it.graph.dump_omitted === "secrets" && t("El grafo lleva un secreto: va solo como JSON enmascarado, sin la copia exacta."),
    it.graph.dump_omitted === "backend" && t("Esta base de datos de grafos no hace copias exactas: el grafo va solo como JSON."),
    omitted > 0 && t("Originales que no van, por secretos o por no haberse podido revisar: {{n}}.", { n: omitted }),
  ].filter(Boolean);
  return (
    <CellText sub={notes.length ? notes.join(" ") : undefined}>
      {t("Nodos: {{n}} · aristas: {{e}} · propuestas: {{p}} · documentos: {{d}}", { n: it.graph.nodes, e: it.graph.edges, p: it.counts.proposals, d: it.counts.documents })}
      {it.vectors ? ` · ${t("con vectores")}` : ""}{it.encrypted ? ` · ${t("cifrado")}` : ""}
    </CellText>
  );
}

/** Exportar el brain a un paquete: grafo, curación, propuestas, documentos y consultas de referencia; sin miembros ni secretos. Its parts are
 *  the children of the settings group that titles it (Administration → Export): the bar (the «i» and «Export»), a row per option, and the
 *  packages made as a table below. */
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
    <SettingsGroup title={t("Exportar")} description={t("Una copia de este brain en un paquete, para guardarla aparte o llevarla a otra instancia.")}
      help={t("El paquete lleva el grafo, la ontología y el vocabulario con su historial, las propuestas, los documentos y las consultas de referencia. No lleva miembros, tokens, motores de IA ni canales de aviso, que solo sirven en esta instancia. Todo pasa antes por el detector de secretos: lo que detecta con seguridad se enmascara.")}
      action={<Btn kind="primary" icon="download" disabled={!pwOk || busy} loading={start.isPending} onClick={() => start.mutate()}>{t("Exportar")}</Btn>}>
      {start.error ? <SettingsBody><MutationError error={start.error} /></SettingsBody> : null}
      <SettingsRow label={t("Incluir los vectores")} help={t("Los embeddings del índice de búsqueda y los del grafo en su copia JSON. Evitan recalcularlos al importar con el mismo modelo, pero el paquete crece mucho.")}>
        <Toggle aria-label={t("Incluir los vectores")} checked={vectors} onChange={(e) => setVectors(e.currentTarget.checked)} />
      </SettingsRow>
      <SettingsRow label={t("Cifrar con una contraseña")} help={t("Sin la contraseña no se puede abrir el paquete. No se guarda en ningún sitio: si la pierdes, el paquete no se puede recuperar.")}>
        <Toggle aria-label={t("Cifrar con una contraseña")} checked={encrypt} onChange={(e) => setEncrypt(e.currentTarget.checked)} />
        {encrypt && <>
          <PasswordField aria-label={t("Contraseña")} placeholder={t("Contraseña")} description={t("Al menos 12 caracteres.")} value={pw} onChange={(e) => setPw(e.currentTarget.value)} autoComplete="new-password" />
          <PasswordField aria-label={t("Repite la contraseña")} placeholder={t("Repite la contraseña")} value={pw2} onChange={(e) => setPw2(e.currentTarget.value)} autoComplete="new-password"
            error={pw2 && pw2 !== pw ? t("No coincide") : undefined} />
        </>}
      </SettingsRow>
      <SettingsBody>
        <Block title={t("Paquetes")} count={list.data ? items.length : undefined}
          help={t("Se prepara como un trabajo. El paquete se descarga una sola vez y se borra al descargarlo; si nadie lo descarga, caduca a las {{h}} horas.", { h: list.data?.ttl_hours ?? 24 })}>
          {!list.data ? <DataState query={list} /> : items.length ? <DataTable fz="sm" aria-label={t("Paquetes")}>
            <DataTable.Thead><DataTable.Tr>
              <DataTable.Th>{t("Creada")}</DataTable.Th><DataTable.Th>{t("Estado")}</DataTable.Th><DataTable.Th>{t("Contenido")}</DataTable.Th><DataTable.Th>{t("Tamaño")}</DataTable.Th><DataTable.ActionsHead />
            </DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{items.map((it) => (
              <DataTable.Tr key={it.id}>
                <DataTable.Td><CellText sub={it.user}><span className="ms-data">{fmt(it.created_at)}</span></CellText></DataTable.Td>
                <DataTable.Td><CellText data sub={it.state === "ready" && it.expires_at ? t("Hasta {{d}}", { d: fmt(it.expires_at) }) : undefined}>
                  <Pill tone={STATES[it.state].tone}>{t(STATES[it.state].label)}</Pill></CellText></DataTable.Td>
                <DataTable.Td>{it.state === "running" || it.state === "queued" ? <ProgressBar done={it.done} total={it.total} text={it.message || t("En cola")} />
                  : it.state === "failed" ? it.error : <Contents it={it} />}</DataTable.Td>
                <DataTable.Td className="ms-data">{it.size != null ? human(it.size) : "—"}</DataTable.Td>
                <DataTable.Td>{it.state === "ready" && <Btn size="row" icon="download" component="a" href={`/api/brains/${brain.slug}/exports/${it.id}/download`}
                  onClick={() => setTimeout(() => qc.invalidateQueries({ queryKey: key }), 1500)}>{t("Descargar")}</Btn>}</DataTable.Td>
              </DataTable.Tr>))}</DataTable.Tbody>
          </DataTable> : <EmptyState>{t("Este brain no se ha exportado todavía.")}</EmptyState>}
        </Block>
      </SettingsBody>
    </SettingsGroup>
  );
}
