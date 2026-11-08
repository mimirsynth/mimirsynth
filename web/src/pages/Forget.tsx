import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { send } from "../api";
import { Btn, Modal, MutationError, Notice, Panel, Pill, TextField, type Tone } from "../ui";
import { T } from "../i18n";

type Item = { uuid?: string; id?: number; name?: string; fact?: string; source?: string; target?: string; title?: string; query?: string;
  chunks?: number; entity?: boolean; episodes?: number };
type Layer = { key: string; where: string; action: string; count: number; items?: Item[]; unavailable?: boolean;
  facts?: number; current?: number; merged?: number; mentions?: number; text?: number; chunks?: number; ratings?: number };
type Report = { entity: { uuid: string; name: string; aliases: string[] }; terms: string[]; layers: Layer[] };

/** What each layer is and what deleting would do there (issue 134). */
const LAYER: Record<string, string> = {
  entity: T("La entidad y sus hechos"), episodes: T("Episodios que la mencionan"), other_facts: T("Hechos de otras entidades que la nombran"),
  other_summaries: T("Resúmenes de otras entidades que la nombran"), similar_entities: T("Otras entidades con un nombre o alias suyo"),
  snapshots: T("Copias del grafo para deshacer fusiones"), episode_chunks: T("Índice de los episodios"), documents: T("Documentos de Conocimiento"),
  proposals: T("Propuestas"), recall_samples: T("Muestra de consultas reales"), recall_logs: T("Registros del recall y sus valoraciones"),
  replay_runs: T("Repeticiones de la muestra"), summary_suggestions: T("Resúmenes propuestos"), jobs: T("Trabajos"), notifications: T("Avisos"),
  webhook_events: T("Eventos de webhooks"), audit: T("Auditoría"), ref_runs: T("Ejecuciones de las consultas de referencia"),
  curator_runs: T("Ejecuciones del curador"), retype_suggestions: T("Tipos propuestos"), vocab_history: T("Historial de cambios del vocabulario"), fact_records: T("Confirmaciones, sondas y fechas de sus hechos"),
  ref_queries: T("Consultas de referencia"), backups: T("Copias de seguridad"), logs: T("Logs de la aplicación"), other_systems: T("Otros sistemas"),
};
const ACTION: Record<string, { label: string; tone: Tone }> = {
  delete: { label: T("Se borraría"), tone: "danger" }, purge: { label: T("Se borraría su texto"), tone: "danger" },
  clean: { label: T("Se limpiaría"), tone: "warn" }, block: { label: T("Se bloquearía"), tone: "warn" },
  review: { label: T("A revisar"), tone: "neutral" }, outside: { label: T("Fuera de alcance"), tone: "neutral" },
};
const WHERE: Record<string, string> = { graph: T("Grafo"), snapshots: T("Copias del grafo"), index: T("Índices"), database: T("Base de datos"), outside: T("Fuera de MimirSynth") };
const NOTE: Record<string, string> = {
  episodes: T("Si el resto de un episodio vale, el LLM del brain lo reescribiría sin la persona como propuesta nueva."),
  documents: T("El documento no se volvería a indexar hasta que cambie en su origen; hay que corregirlo allí."),
  vocab_history: T("Deshacer esos cambios antiguos puede dejar de funcionar."),
  backups: T("Las copias hechas antes conservan los datos hasta que caduquen."), logs: T("Revisa los logs del servidor y de los proxies."),
  other_systems: T("Si la misma información está en otras memorias o sistemas, aquí no se borra."),
};

function itemText(i: Item): string {
  if (i.fact) return `«${i.fact}»`;
  if (i.query) return `«${i.query}»`;
  return i.name ?? i.title ?? "";
}

/** The report of what deleting an entity would touch (issue 134): read-only, for the brain's owner. */
export function ForgetDialog({ graph, entity, onClose }: { graph: string; entity: { uuid: string; name: string }; onClose: () => void }) {
  const { t } = useTranslation();
  const [aliases, setAliases] = useState("");
  const go = useMutation({ mutationFn: () => send<Report>("POST", `brains/${graph}/forget/report`,
    { entity: entity.uuid, aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean) }) });
  const r = go.data;
  const [typed, setTyped] = useState("");
  const del = useMutation({ mutationFn: () => send<{ job: number }>("POST", `brains/${graph}/forget/run`,
    { entity: entity.uuid, aliases: aliases.split(",").map((a) => a.trim()).filter(Boolean), confirm: typed }) });
  return (
    <Modal opened onClose={onClose} size="lg" title={t("Derecho al olvido: «{{n}}»", { n: entity.name })}>
      <Stack gap="sm">
        <Notice tone="info">{t("Este informe no borra nada: dice qué se tocaría en cada sitio si se borrara esta entidad, y qué quedaría para revisar a mano.")}</Notice>
        <TextField label={t("Otros nombres con que aparece")} description={t("Separados por comas: un email, un apodo… Se buscan como palabras completas, sin mayúsculas ni tildes.")}
          value={aliases} onChange={(e) => setAliases(e.currentTarget.value)} />
        <Group justify="flex-end"><Btn kind="primary" icon="search" loading={go.isPending} onClick={() => go.mutate()}>{t("Ver el informe")}</Btn></Group>
        <MutationError error={go.error} />
        {r && <Stack gap="xs">
          <Text size="xs" c="dimmed">{t("Se ha buscado: {{v}}", { v: r.terms.map((x) => `«${x}»`).join(", ") })}</Text>
          {r.layers.map((l) => { const a = ACTION[l.action] ?? ACTION.review; return (
            <Panel key={l.key} withBorder p="sm"><Stack gap={4}>
              <Group justify="space-between" gap="xs" wrap="nowrap">
                <Text size="sm" fw={600}>{t(LAYER[l.key] ?? l.key)} <Text span size="xs" c="dimmed">· {t(WHERE[l.where] ?? l.where)}</Text></Text>
                <Group gap="xs" wrap="nowrap">{l.where !== "outside" && <Text size="sm" className="ms-data">{l.unavailable ? "—" : l.count}</Text>}
                  <Pill size="xs" tone={l.count || l.where === "outside" ? a.tone : "neutral"}>{t(a.label)}</Pill></Group>
              </Group>
              {l.key === "entity" && <Text size="xs" c="dimmed">{t("{{n}} hechos suyos, {{c}} vigentes", { n: l.facts ?? 0, c: l.current ?? 0 })}{l.merged ? ` · ${t("{{n}} duplicados fusionados en ella", { n: l.merged })}` : ""}</Text>}
              {l.key === "episodes" && !!l.count && <Text size="xs" c="dimmed">{t("{{m}} enlazados a la entidad y {{x}} que la nombran en el texto", { m: l.mentions ?? 0, x: l.text ?? 0 })}</Text>}
              {l.key === "recall_logs" && !!l.ratings && <Text size="xs" c="dimmed">{t("con {{n}} valoraciones", { n: l.ratings })}</Text>}
              {l.unavailable && <Text size="xs" c="dimmed">{t("Esta instancia no tiene este índice (necesita PostgreSQL con pgvector).")}</Text>}
              {NOTE[l.key] && (l.count > 0 || l.where === "outside") && <Text size="xs" c="dimmed">{t(NOTE[l.key])}</Text>}
              {!!l.items?.length && <Stack gap={2}>{l.items.map((i, n) => <Text key={i.uuid ?? i.id ?? i.name ?? n} size="xs">
                {i.uuid && (l.key === "other_summaries" || l.key === "similar_entities")
                  ? <Link to={`/entidad/${i.uuid}`}>{i.name}</Link> : itemText(i)}
                {l.key === "snapshots" && ` — ${i.entity ? t("tiene la entidad") : t("no tiene la entidad")}, ${t("{{n}} episodios que la nombran", { n: i.episodes ?? 0 })}`}
                {l.key === "documents" && ` — ${t("{{n}} trozos", { n: i.chunks ?? 0 })}`}
              </Text>)}{l.count > l.items.length && <Text size="xs" c="dimmed">{t("y {{n}} más", { n: l.count - l.items.length })}</Text>}</Stack>}
            </Stack></Panel>); })}
          <Panel withBorder p="sm"><Stack gap="xs">
            <Text size="sm" fw={600}>{t("Borrar")}</Text>
            <Text size="xs" c="dimmed">{t("Hace lo que dice el informe y no se puede deshacer. Lo que queda «a revisar» no se toca: apúntalo antes, porque después la entidad ya no existe. Para confirmar, escribe su nombre tal cual.")}</Text>
            {del.data ? <Notice tone="success">{t("Borrado en marcha (trabajo {{id}}). El resultado, con los recuentos por capa, queda en Trabajos.", { id: del.data.job })}{" "}
              <Btn kind="link" component={Link} to="/trabajos">{t("Ver los trabajos")}</Btn></Notice>
              : <Group gap="xs" align="flex-end">
                <TextField label={t("Nombre de la entidad")} placeholder={entity.name} value={typed} onChange={(e) => setTyped(e.currentTarget.value)} w={260} />
                <Btn kind="danger" loading={del.isPending} disabled={typed.trim() !== entity.name.trim()} onClick={() => del.mutate()}>{t("Borrar para siempre")}</Btn>
              </Group>}
            <MutationError error={del.error} />
          </Stack></Panel>
        </Stack>}
      </Stack>
    </Modal>
  );
}
