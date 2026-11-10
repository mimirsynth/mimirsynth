import { T } from "../i18n";
import { useTranslation } from "react-i18next";
import { Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, langHeaders, send } from "../api";
import { Btn, CellText, Check, DataState, DataTable, DialogActions, EmptyState, FilePicker, Modal, MutationError, PasswordField, Pill, ProgressBar, Segments, SettingsBody, SettingsGroup, TextField } from "../ui";

type Manifest = {
  slug: string; created_at: string; mimirsynth: string; counts: { proposals?: number; documents?: number }; options: { vectors?: boolean };
  graph: { nodes: number; edges: number; dump: boolean; backend?: string; here?: string; dump_blocker?: string | null; same_falkordb: boolean }; embedding: { model: string; same: boolean };
};
type Upload = { upload_id: string; encrypted: boolean; manifest: Manifest | null };
type State = "queued" | "running" | "done" | "failed" | "cancelled";
type Item = {
  id: number; state: State; done: number; total: number; message: string; error: string; user: string; created_at: string; slug: string; mode: string;
  encrypted: boolean; dump: boolean; upload_id: string; retry_password: boolean; brain?: string;
  graph?: { method: "dump" | "json"; fallback_reason: string | null; nodes: number; edges: number; dump_mismatch?: string[] };
  counts?: { proposals?: number; documents?: { documents: number; sources_disabled: number } };
  vectors?: { reused: boolean; graph_computed: number };
};

const STATES: Record<State, { label: string; tone: "neutral" | "success" | "danger" | "alt" }> = {
  queued: { label: T("En cola"), tone: "neutral" }, running: { label: T("En marcha"), tone: "alt" }, done: { label: T("Importado"), tone: "success" },
  failed: { label: T("Fallida"), tone: "danger" }, cancelled: { label: T("Cancelada"), tone: "neutral" },
};
const WHY_JSON: Record<string, string> = {
  no_dump: T("el paquete no trae la copia exacta"), secrets: T("la copia exacta se quedó fuera por un secreto"),
  falkordb_version: T("otra versión de FalkorDB"), backend: T("la base de datos de origen no hace copias exactas"),
  other_backend: T("esta instancia usa otra base de datos de grafos"), name_taken: T("su grafo original existe en esta instancia"), restore_failed: T("la copia exacta no se pudo restaurar"),
  dump_mismatch: T("la copia exacta no coincidía con la copia JSON y se descartó"),
};
const PART = 32 * 1024 * 1024; // como en los documentos: por debajo del límite habitual de los proxies

async function upload(file: File, progress: (done: number) => void): Promise<Upload> {
  const init = await send<{ upload_id: string; part_size: number }>("POST", "brain-imports/uploads", { filename: file.name, size: file.size });
  const step = Math.min(init.part_size, PART);
  for (let i = 0, off = 0; off < file.size; i++, off += step) {
    const r = await fetch(`/api/brain-imports/uploads/${init.upload_id}/parts/${i}`, { method: "PUT", credentials: "include", headers: langHeaders(), body: file.slice(off, off + step) });
    if (!r.ok) { await send("DELETE", `brain-imports/uploads/${init.upload_id}`).catch(() => undefined); throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText); }
    progress(Math.min(off + step, file.size));
  }
  return send("POST", `brain-imports/uploads/${init.upload_id}/complete`);
}

/** Lo que dice el manifiesto de un paquete sin cifrar, y qué pasará con el grafo y los vectores al importarlo aquí. */
function Contents({ m }: { m: Manifest }) {
  const { t } = useTranslation();
  return (
    <Stack gap={2}>
      <Text size="sm">{t("Brain «{{slug}}», exportado el {{date}} con MimirSynth {{v}}.", { slug: m.slug, date: fmt(m.created_at), v: m.mimirsynth })}</Text>
      <Text size="sm">{t("Nodos: {{n}} · aristas: {{e}} · propuestas: {{p}} · documentos: {{d}}", { n: m.graph.nodes, e: m.graph.edges, p: m.counts.proposals ?? 0, d: m.counts.documents ?? 0 })}</Text>
      <Text size="sm">{m.embedding.same ? t("Mismo modelo de embeddings: se reutilizan los vectores que trae.")
        : t("Otro modelo de embeddings ({{model}}): los vectores se calculan de nuevo al importar.", { model: m.embedding.model })}</Text>
    </Stack>
  );
}

/** What a finished import brought in, for its table cell: the counts, and under them how the graph and the vectors came in. */
function Result({ it }: { it: Item }) {
  const { t } = useTranslation();
  if (it.mode === "structure") return <>{t("Solo la estructura: ontología y alias.")}</>;
  if (!it.graph) return null;
  const disabled = it.counts?.documents?.sources_disabled ?? 0;
  const how = it.graph.method === "dump" ? t("El grafo entró por su copia exacta, y coincide con la copia JSON.")
    : !it.dump ? t("El grafo entró por su copia JSON.")
    : t("El grafo entró por su copia JSON: {{why}}.", { why: t(WHY_JSON[it.graph.fallback_reason ?? ""] ?? WHY_JSON.no_dump) });
  const vectors = !it.vectors?.reused ? t("Vectores calculados de nuevo.") : it.vectors.graph_computed ? t("Vectores reutilizados; calculados los que faltaban ({{n}}).", { n: it.vectors.graph_computed }) : t("Vectores reutilizados.");
  const sources = disabled > 0 ? t("Fuentes de documentos desactivadas hasta que revises su configuración y sus credenciales: {{n}}.", { n: disabled }) : "";
  return (
    <CellText sub={[how, vectors, sources].filter(Boolean).join(" ")}>
      {t("Nodos: {{n}} · aristas: {{e}} · propuestas: {{p}} · documentos: {{d}}", { n: it.graph.nodes, e: it.graph.edges, p: it.counts?.proposals ?? 0, d: it.counts?.documents?.documents ?? 0 })}
    </CellText>
  );
}

/** Importar un brain desde un paquete exportado: lo sube por partes, enseña su manifiesto en un diálogo y lo importa como un brain nuevo. A
 *  view inside the settings group that titles it: the bar (the «i» and «Choose package»), the upload's progress, and the imports as a table. */
export default function BrainImport({ onOpen }: { onOpen: (slug: string) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["brain-imports"];
  const list = useQuery({ queryKey: key, queryFn: () => get<{ items: Item[] }>("brain-imports"),
    refetchInterval: (q) => (q.state.data?.items.some((i) => i.state === "queued" || i.state === "running") ? 1500 : false) });
  const [sent, setSent] = useState<{ done: number; size: number } | null>(null);
  const [up, setUp] = useState<Upload | null>(null);
  const [slug, setSlug] = useState(""); const [name, setName] = useState(""); const [mode, setMode] = useState("full"); const [pw, setPw] = useState(""); const [dump, setDump] = useState(false);
  const pick = useMutation({
    mutationFn: (f: File) => { setSent({ done: 0, size: f.size }); return upload(f, (done) => setSent({ done, size: f.size })); },
    onSuccess: (u) => { setUp(u); setSlug(u.manifest?.slug ?? ""); setName(u.manifest?.slug ?? ""); setMode("full"); setPw(""); setDump(false); },
    onSettled: () => setSent(null),
  });
  const reset = () => { setUp(null); setPw(""); start.reset(); };
  const start = useMutation({ mutationFn: () => send<{ id: number }>("POST", "brain-imports", { upload_id: up!.upload_id, slug, name, mode, dump: mode === "full" && dump, password: up!.encrypted ? pw : undefined }),
    onSuccess: () => { reset(); qc.invalidateQueries({ queryKey: key }); } });
  const discard = useMutation({ mutationFn: () => send("DELETE", `brain-imports/uploads/${up!.upload_id}`), onSettled: reset });
  const busy = list.data?.items.some((i) => i.state === "queued" || i.state === "running");
  const items = list.data?.items ?? [];
  return (
    <SettingsGroup title={t("Importar un brain")} description={t("Un brain nuevo a partir de un paquete exportado.")}
      help={t("Crea un brain nuevo a partir de un paquete exportado, de esta instancia o de otra. Antes de escribir nada se comprueba el paquete entero, y si algo falla a mitad se elimina lo que se haya creado. Quedas como propietario; los miembros, los tokens, los motores de IA y los canales de aviso se configuran aquí.")}
      action={<FilePicker label={t("Elegir paquete")} accept=".gz,.enc" disabled={busy || !!up} loading={pick.isPending} onFiles={(fs) => pick.mutate(fs[0])} />}>
      {/* closing the dialog is «Discard»: the uploaded package is deleted, as before */}
      <Modal opened={!!up} onClose={() => { if (!discard.isPending) discard.mutate(); }} title={t("Importar un brain")}>
        {up && <Stack gap="sm">
          {up.manifest && <Contents m={up.manifest} />}
          <TextField label={t("Slug")} description={t("El del brain nuevo; su grafo se llamará igual.")} value={slug} onChange={(e) => setSlug(e.currentTarget.value)} />
          <TextField label={t("Nombre")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <Segments label={t("Qué importar")} value={mode} onChange={setMode}
            data={[{ value: "full", label: t("Completo") }, { value: "structure", label: t("Solo la estructura") }]} />
          {mode === "structure" && <Text size="sm">{t("Solo la ontología y los alias, como plantilla: sin grafo, propuestas ni documentos.")}</Text>}
          {mode === "full" && <Check checked={dump} onChange={(e) => setDump(e.currentTarget.checked)}
            disabled={!!up.manifest && (!up.manifest.graph.dump || !up.manifest.graph.same_falkordb)} label={t("Restauración rápida (usar la copia exacta)")}
            description={up.manifest && !up.manifest.graph.dump ? t("Este paquete no trae la copia exacta del grafo.")
              : up.manifest && up.manifest.graph.dump_blocker === "other_backend" ? t("La copia exacta solo se restaura en FalkorDB, y esta instancia usa otra base de datos de grafos: el grafo entra por su copia JSON.")
              : up.manifest && !up.manifest.graph.same_falkordb ? t("Esta instancia tiene otra versión de FalkorDB: la copia exacta no se puede usar.")
              : t("Solo para paquetes que hayas exportado tú. La copia exacta entra en FalkorDB tal cual, sin validarla como la copia JSON; después se compara con ella y, si no coincide, se descarta. Cifrar un paquete no lo hace de confianza: cualquiera con la contraseña puede hacer uno.")} />}
          {up.encrypted && <PasswordField label={t("Contraseña del paquete")} description={t("Paquete cifrado: su contenido se comprueba al importarlo, con su contraseña.")}
            value={pw} onChange={(e) => setPw(e.currentTarget.value)} autoComplete="off" />}
          <MutationError error={start.error ?? discard.error} />
          <DialogActions>
            <Btn kind="ghost" loading={discard.isPending} onClick={() => discard.mutate()}>{t("Descartar")}</Btn>
            <Btn kind="primary" icon="upload" disabled={!slug || !name.trim() || (up.encrypted && !pw) || busy} loading={start.isPending} onClick={() => start.mutate()}>{t("Importar")}</Btn>
          </DialogActions>
        </Stack>}
      </Modal>
      <SettingsBody>
      {sent && <ProgressBar done={sent.done} total={sent.size} text={t("Subiendo el paquete")} />}
      <MutationError error={pick.error} />
      {!list.data ? <DataState query={list} /> : items.length ? <DataTable fz="sm" aria-label={t("Importar un brain")}>
        <DataTable.Thead><DataTable.Tr>
          <DataTable.Th>{t("Brain")}</DataTable.Th><DataTable.Th>{t("Estado")}</DataTable.Th><DataTable.Th>{t("Resultado")}</DataTable.Th><DataTable.ActionsHead />
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{items.map((it) => (
          <DataTable.Tr key={it.id}>
            <DataTable.Td><CellText sub={[fmt(it.created_at), it.user, it.mode === "structure" ? t("solo la estructura") : t("completo"), it.encrypted ? t("cifrado") : ""].filter(Boolean).join(" · ")}>
              <span className="ms-data">{it.slug}</span></CellText></DataTable.Td>
            <DataTable.Td><Pill tone={STATES[it.state].tone}>{t(STATES[it.state].label)}</Pill></DataTable.Td>
            <DataTable.Td>{it.state === "running" || it.state === "queued" ? <ProgressBar done={it.done} total={it.total} text={it.message || t("En cola")} />
              : it.state === "failed" ? it.error : it.state === "done" ? <Result it={it} /> : null}</DataTable.Td>
            <DataTable.Td>{it.state === "done" && it.brain ? <Btn size="row" onClick={() => onOpen(it.brain!)}>{t("Abrir")}</Btn>
              : it.retry_password && !up ? <Btn size="row" onClick={() => { setUp({ upload_id: it.upload_id, encrypted: true, manifest: null }); setSlug(it.slug); setName(it.slug); setMode(it.mode); }}>{t("Probar otra contraseña")}</Btn>
              : null}</DataTable.Td>
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable> : <EmptyState>{t("No se ha importado ningún brain todavía.")}</EmptyState>}
      </SettingsBody>
    </SettingsGroup>
  );
}
