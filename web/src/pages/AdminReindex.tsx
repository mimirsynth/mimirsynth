import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { fmt, get, send } from "../api";
import { Btn, Check, ConfirmDialog, MutationError, Notice, ProgressBar } from "../ui";

// Cambio de modelo de embeddings (#48): relleno en sombra, intercambio y descarte. La API está en embeddings_admin.py.
type Job = { id: number; status: string; done: number; total: number | null; message: string; error: string; title: string; finished_at: string | null;
  result?: { model?: string; dim?: number; previous?: { model: string; dim: number } } | null };
type Shadow = { engine_id: number; engine: string; model: string; dim: number; state: "running" | "failed" | "ready" | "switching"; started_at: string; updated_at: string };
type Status = { job: Job | null; switch_job: Job | null; shadow: Shadow | null; orphan: boolean };
type Estimate = { partial: boolean; graphs: number; graphs_estimated: number; graph_items: number; chunks: number; calls: number;
  falkor: { need_bytes: number; free_bytes: number | null; ok: boolean }; postgres: { need_bytes: number } };
export type EngineRef = { id: number; name: string; model: string; dim?: number };

const KEY = ["embedding-reindex"];
const active = (j?: Job | null) => !!j && (j.status === "queued" || j.status === "running");
const mb = (b?: number | null) => (b == null ? "—" : b === 0 ? "0 MB" : b < 2 ** 20 ? "< 1 MB" : `${Math.round(b / 2 ** 20).toLocaleString()} MB`);

/** Confirmación del relleno en sombra, con la estimación (cota superior) antes de empezar. */
export function StartReindex({ engine, onClose }: { engine: EngineRef | null; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const est = useQuery({ queryKey: ["embedding-estimate", engine?.id], enabled: !!engine, staleTime: 60000,
    queryFn: () => get<Estimate>(`embedding-engines/${engine!.id}/reindex/estimate`) });
  const start = useMutation({ mutationFn: () => send("POST", `embedding-engines/${engine!.id}/reindex`), onSuccess: () => qc.invalidateQueries({ queryKey: KEY }) });
  const e = est.data;
  return (
    <ConfirmDialog opened={!!engine} onClose={onClose} tone="primary" title={t("Calcular los vectores del modelo nuevo")} action={t("Calcular en sombra")}
      subject={engine && `${engine.name} · ${engine.model}${engine.dim ? ` · ${engine.dim}d` : ""}`} disabled={!e || !e.falkor.ok}
      warning={t("Se calculan con este motor los vectores de todos los brains y se guardan aparte: nada de lo que se usa cambia hasta el intercambio, que se confirma después. Puede tardar y consume llamadas al motor.")}
      onConfirm={() => start.mutateAsync()}>
      {!e ? <Text size="sm" c="dimmed">{t("Estimando…")}</Text> : <Stack gap={4}>
        <Text size="sm">{t("Hasta {{items}} elementos del grafo y {{chunks}} trozos: unas {{calls}} llamadas al motor.", { items: e.graph_items.toLocaleString(), chunks: e.chunks.toLocaleString(), calls: e.calls.toLocaleString() })}</Text>
        <Text size="sm">{t("Memoria en FalkorDB: unos {{need}}; libre: {{free}}.", { need: mb(e.falkor.need_bytes), free: mb(e.falkor.free_bytes) })}</Text>
        <Text size="sm">{t("PostgreSQL: unos {{need}} más. El espacio libre en disco no se puede consultar desde aquí: compruébalo tú.", { need: mb(e.postgres.need_bytes) })}</Text>
        {e.partial && <Text size="xs" c="dimmed">{t("Estimación parcial: {{done}} de {{graphs}} grafos.", { done: e.graphs_estimated, graphs: e.graphs })}</Text>}
        {!e.falkor.ok && <Notice tone="danger">{t("FalkorDB no tiene memoria libre suficiente para los vectores nuevos.")}</Notice>}
      </Stack>}
      <MutationError error={est.error} />
    </ConfirmDialog>
  );
}

/** Estado del cambio de modelo: progreso, sombras listas o sin terminar, intercambio y resultado. */
export function ReindexPanel({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const st = useQuery({ queryKey: KEY, queryFn: () => get<Status>("embedding-engines/reindex"),
    refetchInterval: (q) => (active(q.state.data?.job) || active(q.state.data?.switch_job) ? 2000 : false) });
  const refresh = () => qc.invalidateQueries({ queryKey: KEY });
  const cancel = useMutation({ mutationFn: (id: number) => send("POST", `embedding-engines/reindex/${id}/cancel`), onSuccess: refresh });
  const retry = useMutation({ mutationFn: (id: number) => send("POST", `embedding-engines/reindex/${id}/retry`), onSuccess: refresh });
  const discard = useMutation({ mutationFn: () => send("POST", "embedding-engines/reindex/discard"), onSuccess: refresh });
  const doSwitch = useMutation({ mutationFn: () => send("POST", "embedding-engines/reindex/switch", { backup_confirmed: true }), onSuccess: refresh });
  const [askSwitch, setAskSwitch] = useState(false);
  const [backup, setBackup] = useState(false);
  const [askDiscard, setAskDiscard] = useState(false);
  const d = st.data;
  const sw = d?.switch_job;
  const switched = sw?.status === "done";
  useEffect(() => { if (switched) onDone(); }, [switched, sw?.id]);  // al terminar, la lista de motores cambia (nuevo por defecto)
  if (!d) return null;
  const fill = d.job, sh = d.shadow;
  const running = active(sw) ? sw : active(fill) ? fill : null;
  const lastSwitchFailed = !!sw && !!sh && sw.status === "failed" && !!sw.finished_at && sw.finished_at >= sh.started_at;
  return (
    <Stack gap="xs">
      {running && <Notice tone="info" title={running.title}>
        <Stack gap="xs">
          <ProgressBar done={running.done} total={running.total ?? 0} text={running.total ? `${running.done}/${running.total} · ${running.message}` : running.message || "…"} />
          <Group><Btn kind="danger" size="row" icon="close" loading={cancel.isPending} onClick={() => cancel.mutate(running.id)}>{t("Cancelar")}</Btn></Group>
        </Stack>
      </Notice>}
      {!running && sh?.state === "ready" && <Notice tone="success" title={t("Vectores de «{{engine}}» ({{model}}, {{dim}}d) listos en sombra", { engine: sh.engine, model: sh.model, dim: sh.dim })}>
        <Stack gap="xs">
          <Text size="sm">{t("El modelo en uso no ha cambiado. Cuando quieras, cambia al modelo nuevo: se pausan un momento las escrituras de vectores y se intercambia todo de una vez.")}</Text>
          {lastSwitchFailed && <Text size="sm" className="ms-text-danger">{t("El último intento de cambio no se completó y todo sigue con el motor anterior: {{error}}", { error: sw!.error })}</Text>}
          <Group gap="xs"><Btn kind="primary" size="row" icon="check" onClick={() => { setBackup(false); setAskSwitch(true); }}>{t("Cambiar al modelo nuevo")}</Btn>
            <Btn kind="danger" size="row" icon="trash" onClick={() => setAskDiscard(true)}>{t("Descartar")}</Btn></Group>
        </Stack>
      </Notice>}
      {!running && sh && sh.state !== "ready" && <Notice tone="warn" title={t("Hay un cálculo en sombra hacia «{{engine}}» sin terminar", { engine: sh.engine })}>
        <Stack gap="xs">
          <Text size="sm">{t("Sus vectores ocupan memoria mientras tanto. Reinténtalo (solo calcula lo que falta) o descártalo. Desde {{date}}.", { date: fmt(sh.updated_at) })}</Text>
          {fill?.error && <Text size="sm" className="ms-text-danger">{fill.error}</Text>}
          <Group gap="xs">{fill && (fill.status === "failed" || fill.status === "cancelled") && <Btn size="row" icon="refresh" loading={retry.isPending} onClick={() => retry.mutate(fill.id)}>{t("Reintentar")}</Btn>}
            <Btn kind="danger" size="row" icon="trash" onClick={() => setAskDiscard(true)}>{t("Descartar")}</Btn></Group>
        </Stack>
      </Notice>}
      {!running && !sh && switched && sw!.result?.model && <Notice tone="success" title={t("Modelo de embeddings cambiado a «{{model}}» ({{dim}}d) el {{date}}", { model: sw!.result.model, dim: sw!.result.dim, date: fmt(sw!.finished_at) })}>
        <Stack gap={4}>
          <Text size="sm">{t("Recalibra la similitud mínima de un pasaje del recall (Administración → Recuerdo): la de «{{previous}}» no vale para el modelo nuevo.", { previous: sw!.result.previous?.model ?? "" })}</Text>
          <Text size="sm">{t("Los agentes que escriben directamente en Graphiti siguen usando el modelo anterior hasta que los cambies: pásalos al mismo modelo.")}</Text>
        </Stack>
      </Notice>}
      {!running && !sh && fill?.status === "cancelled" && !switched && <Text size="xs" c="dimmed">{t("Último cálculo en sombra cancelado: se descartó todo lo calculado.")}</Text>}
      <MutationError error={cancel.error ?? retry.error ?? discard.error} />
      <ConfirmDialog opened={askSwitch} onClose={() => setAskSwitch(false)} tone="primary" title={t("Cambiar al modelo nuevo")} action={t("Cambiar de modelo")} disabled={!backup}
        subject={sh && `${sh.engine} · ${sh.model} · ${sh.dim}d`}
        warning={t("Se completa lo que haya cambiado, se pausan un momento las escrituras de vectores (ingesta, índice, documentos) y se intercambian todos los vectores en una sola operación. Si algo falla, todo sigue con el motor anterior.")}
        onConfirm={() => doSwitch.mutateAsync()}>
        <Check checked={backup} onChange={(e) => setBackup(e.currentTarget.checked)} label={t("He hecho una copia de seguridad de FalkorDB y PostgreSQL")} />
        <Notice tone="warn">{t("Después del cambio, recalibra la similitud mínima de un pasaje del recall (Administración → Recuerdo). Los agentes que escriben directamente en Graphiti seguirán con el modelo anterior hasta que los cambies.")}</Notice>
      </ConfirmDialog>
      <ConfirmDialog opened={askDiscard} onClose={() => setAskDiscard(false)} title={t("Descartar los vectores en sombra")} action={t("Descartar")}
        subject={sh && `${sh.engine} · ${sh.model} · ${sh.dim}d`}
        warning={t("Se borran todos los vectores calculados en sombra (en FalkorDB y en PostgreSQL). El modelo en uso no cambia; para volver a intentarlo habrá que calcularlos de nuevo.")}
        onConfirm={() => discard.mutateAsync()} />
    </Stack>
  );
}
