import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { fmt, get, send } from "../api";
import { Btn, Check, ConfirmDialog, DataTable, EmptyState, MutationError, Notice, Pill, Radio, RadioGroup, Segments } from "../ui";

type Fact = { uuid: string; fact: string; target: string; valid_at: string | null; created_at: string | null };
type Group_ = { source: string; source_uuid: string; relation: string; target_type: string; facts: Fact[]; targets: number; likely_multi: boolean; relation_ratio: number;
  suggestion: { keep: string; invalidate: string[]; clear: boolean; dated_by: "valid_at" | "created_at" } };
type Stat = { relation: string; sources: number; groups: number; ratio: number; functional: boolean; max_targets: number; likely_multi: boolean };
type Dismissed = { id: number; source: string; relation: string; target_type: string; facts: number; created_at: string };
type Scan = { scanned: number; truncated: boolean; functional: string[]; total: number; groups: Group_[]; by_relation?: Stat[]; generic_facts?: number; dismissed?: Dismissed[] };
type EdgeType = { name: string; description: string; functional?: boolean };

const ONTOLOGY = "/vocabulario?tab=onto";
/** The Ontology tab with a relation's edit dialog open. */
const editRelation = (name: string) => `${ONTOLOGY}&rel=${encodeURIComponent(name)}`;
/** The graph's spelling of a relation (HostedOn → HOSTED_ON), to find it in the ontology. */
const canon = (s: string) => s.trim().replace(/([a-z0-9])([A-Z])/g, "$1_$2").replace(/[\s-]+/g, "_").toUpperCase();
const key = (g: Group_) => `${g.source_uuid}|${g.relation}|${g.target_type}`;

/** A fact's sentence, cut to two lines with a control to read it whole. */
function FactText({ text }: { text: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const long = text.length > 160;
  return (<Stack gap={0} align="flex-start">
    <Text size="sm" c="dimmed" lineClamp={open ? undefined : 2}>{text}</Text>
    {long && <Btn kind="link" onClick={() => setOpen((x) => !x)}>{open ? t("Ver menos") : t("Ver entero")}</Btn>}
  </Stack>);
}

/** The proposal for a group, in words: the newest fact when the dates say so, otherwise the person decides. */
function Suggestion({ g }: { g: Group_ }) {
  const { t } = useTranslation();
  const keep = g.facts.find((f) => f.uuid === g.suggestion.keep);
  if (g.likely_multi) return <Pill size="xs" tone="warn" title={t("Esta relación tiene muchos destinos vigentes por sujeto: probablemente admite varios valores a la vez.")}>{t("probablemente varios valores")}</Pill>;
  if (g.suggestion.clear) return <Group gap={6} wrap="nowrap"><Text size="sm">{keep?.target}</Text><Pill size="xs" tone="success">{t("el más reciente")}</Pill></Group>;
  return g.suggestion.dated_by === "created_at"
    ? <Pill size="xs" tone="warn" title={t("Algún hecho no tiene fecha de validez: la que se ve es cuándo se aprendió, que no dice cuál es más actual.")}>{t("solo fecha de aprendizaje: decide tú")}</Pill>
    : <Pill size="xs" tone="warn" title={t("Los hechos tienen la misma fecha de validez.")}>{t("misma fecha: decide tú")}</Pill>;
}

/** Why a group probably is not a contradiction: the relation holds several values. Offers to unmark it. */
function ManyValues({ g, edge, canMark, unmarking, onUnmark }: { g: Group_; edge?: EdgeType; canMark: boolean; unmarking: boolean; onUnmark: () => void }) {
  const { t } = useTranslation();
  return (<Notice tone="warn" title={t("Probablemente no es una contradicción")}>
    {g.targets >= 3
      ? t("«{{source}}» tiene {{n}} destinos vigentes en esta relación: probablemente admite varios valores a la vez.", { source: g.source, n: g.targets })
      : t("El {{pct}} % de los sujetos tiene varios destinos vigentes en esta relación: probablemente admite varios valores a la vez.", { pct: Math.round(g.relation_ratio * 100) })}{" "}
    {t("Si es así, desmarca «Un solo valor a la vez» en Ontología.")}{" "}
    <Btn kind="link" component={Link} to={editRelation(edge?.name ?? g.relation)}>{t("Editar la relación")}</Btn>
    {canMark && edge?.functional && <>{" · "}<Btn kind="link" loading={unmarking} onClick={onUnmark}>{t("Desmarcar ahora")}</Btn></>}
  </Notice>);
}

/** An open group: keep only one fact, or tick the ones that are no longer true; or say it is not a contradiction. At least one fact
 * always stays current, and invalidating more than one asks first. */
function GroupDetail({ g, canResolve, busy, onResolve, onDismiss, warning }: { g: Group_; canResolve: boolean; busy: boolean;
  onResolve: (keep: string | null, drop: string[]) => Promise<unknown>; onDismiss: () => void; warning?: ReactNode }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState(g.likely_multi ? "some" : "one");
  const [keep, setKeep] = useState(g.suggestion.clear ? g.suggestion.keep : "");   // without a clear proposal the person chooses
  const [ticked, setTicked] = useState<string[]>([]);
  const [asking, setAsking] = useState(false);
  const kept = g.facts.find((f) => f.uuid === keep);
  const drop = mode === "some" ? ticked
    : kept ? g.facts.filter((f) => f.target.toLowerCase().trim() !== kept.target.toLowerCase().trim()).map((f) => f.uuid) : [];
  const allTicked = mode === "some" && ticked.length === g.facts.length;
  const when = (f: Fact) => (f.valid_at ? t("cierto desde {{date}}", { date: fmt(f.valid_at) }) : t("aprendido el {{date}}", { date: fmt(f.created_at) }));
  const label = (f: Fact) => <>{f.target} <Text span size="xs" c="dimmed" fw={400}>· {when(f)}</Text></>;
  const run = () => onResolve(mode === "one" ? keep : null, drop);
  const go = () => (drop.length > 1 ? setAsking(true) : void run().catch(() => undefined));   // the page shows the error
  const tick = (u: string, on: boolean) => setTicked((cur) => (on ? [...cur, u] : cur.filter((x) => x !== u)));
  return (
    <Stack gap="sm" py="xs">
      {warning}
      {canResolve && <Segments label={t("Cómo resolver")} value={mode} onChange={setMode}
        data={[{ value: "one", label: t("Quedarse solo con uno") }, { value: "some", label: t("Invalidar los que ya no son ciertos") }]} />}
      {!canResolve ? <Stack gap="sm" mah={320} className="ms-scroll">
        {g.facts.map((f) => <Stack key={f.uuid} gap={0}><Text size="sm" fw={600}>{label(f)}</Text><FactText text={f.fact} /></Stack>)}
      </Stack> : mode === "one" ? <RadioGroup value={keep} onChange={setKeep} label={t("¿Qué hecho sigue siendo cierto?")}>
        <Stack gap="sm" mah={320} className="ms-scroll" pt={6}>
          {g.facts.map((f) => <Radio key={f.uuid} value={f.uuid} label={label(f)} description={<FactText text={f.fact} />} />)}
        </Stack>
      </RadioGroup> : <Stack gap={6}>
        <Text size="sm" fw={600}>{t("¿Qué hechos ya no son ciertos?")}</Text>
        <Stack gap="sm" mah={320} className="ms-scroll">
          {g.facts.map((f) => <Check key={f.uuid} checked={ticked.includes(f.uuid)} onChange={(e) => tick(f.uuid, e.currentTarget.checked)}
            label={label(f)} description={<FactText text={f.fact} />} />)}
        </Stack>
      </Stack>}
      {canResolve ? <Group gap="xs">
        <Btn kind="primary" icon="check" loading={busy} disabled={!drop.length || allTicked} onClick={go}>
          {mode === "some" ? t("Invalidar los marcados ({{n}})", { n: ticked.length })
            : keep ? t("Resolver: invalidar los otros {{n}}", { n: drop.length }) : t("Elige primero el que se queda")}</Btn>
        <Btn kind="secondary" icon="close" loading={busy} onClick={onDismiss}>{t("No es una contradicción")}</Btn>
        {allTicked && <Text size="xs" c="dimmed">{t("Deja al menos uno sin marcar: alguno tiene que seguir vigente.")}</Text>}
      </Group> : <Text size="xs" c="dimmed">{t("Esta relación no está marcada como de un solo valor: aquí solo se mide. Márcala para poder resolver.")}</Text>}
      <ConfirmDialog opened={asking} onClose={() => setAsking(false)} title={t("Invalidar {{n}} hechos", { n: drop.length })}
        warning={t("Los {{n}} hechos dejarán de estar vigentes. Se puede deshacer desde el historial del vocabulario, uno a uno.", { n: drop.length })}
        action={t("Invalidar {{n}} hechos", { n: drop.length })} onConfirm={run}>
        <Stack gap={4}>{g.facts.filter((f) => drop.includes(f.uuid)).map((f) => <Text key={f.uuid} size="sm">{f.target}</Text>)}</Stack>
      </ConfirmDialog>
    </Stack>
  );
}

/** Hechos vigentes que se contradicen en una relación de un solo valor: mismo sujeto, misma relación, destinos distintos. */
export default function VocabConflicts({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canResolve = ["curator", "admin", "owner"].includes(role);
  const canMark = ["admin", "owner"].includes(role);   // the ontology is edited by the brain's administrators
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [showDismissed, setShowDismissed] = useState(false);
  const q = useQuery({ queryKey: ["conflicts", graph, all], enabled: canResolve, queryFn: () => get<Scan>(`brains/${graph}/conflicts`, { all }) });
  const onto = useQuery({ queryKey: ["ontology", graph], enabled: canMark, queryFn: () => get<{ ontology: { edge_types: EdgeType[] } }>(`brains/${graph}/ontology`) });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["conflicts", graph] }); qc.invalidateQueries({ queryKey: ["facts", graph] }); };
  const resolve = useMutation({ mutationFn: (v: { keep: string | null; invalidate: string[] }) => send("POST", `brains/${graph}/conflicts/resolve`, v),
    onSuccess: () => { setOpen(null); refresh(); } });
  const dismiss = useMutation({ mutationFn: (g: Group_) => send("POST", `brains/${graph}/conflicts/dismiss`,
    { source_uuid: g.source_uuid, source: g.source, relation: g.relation, target_type: g.target_type, facts: g.facts.map((f) => f.uuid) }),
    onSuccess: () => { setOpen(null); refresh(); } });
  const undismiss = useMutation({ mutationFn: (id: number) => send("DELETE", `brains/${graph}/conflicts/dismiss/${id}`), onSuccess: refresh });
  const mark = useMutation({ mutationFn: ({ e, on }: { e: EdgeType; on: boolean }) => send("PUT", `vocab/relations/${e.name}`, { description: e.description, functional: on }, { graph }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ontology", graph] }); refresh(); } });
  if (!canResolve) return <EmptyState>{t("Revisar contradicciones es cosa de un curador o superior.")}</EmptyState>;
  const d = q.data;
  const edge = (rel: string) => onto.data?.ontology.edge_types.find((e) => canon(e.name) === rel);
  return (
    <Stack gap="md">
      <Notice tone="info" title={t("Para qué sirve")}>
        {t("Aquí aparecen hechos vigentes que no pueden ser ciertos a la vez: el mismo sujeto con destinos distintos en una relación de un solo valor, como un equipo en dos salas. Abre cada grupo y quédate solo con el hecho que sigue siendo cierto, o marca los que ya no lo son: se invalidan, siempre queda alguno vigente y se puede deshacer desde el historial del vocabulario. Si no es una contradicción, pulsa «No es una contradicción» y el grupo deja de salir hasta que llegue un hecho nuevo; si la relación admite varios valores, desmárcala en Ontología.")}
      </Notice>
      <Group gap="xs">
        <Btn kind={all ? "primary" : "secondary"} icon="search" onClick={() => { setAll((x) => !x); setOpen(null); }}>{all ? t("Volver a las relaciones de un solo valor") : t("Medir en todas las relaciones")}</Btn>
        {d && <Text size="xs" c="dimmed">{t("{{n}} hechos vigentes analizados.", { n: d.scanned })}{d.truncated ? ` ${t("Se ha llegado al máximo: faltan hechos.")}` : ""}</Text>}
      </Group>
      <MutationError error={q.error ?? resolve.error ?? dismiss.error ?? undismiss.error ?? mark.error} />
      {d && !all && !d.functional.length && <Notice tone="warn" title={t("Ninguna relación está marcada como de un solo valor")}>
        {t("Sin esa marca no se buscan contradicciones. Mide primero en todas las relaciones y marca solo las que de verdad admitan un único valor a la vez.")}{" "}
        <Btn kind="link" onClick={() => setAll(true)}>{t("Medir ahora")}</Btn>{" · "}<Btn kind="link" component={Link} to={ONTOLOGY}>{t("Ir a Ontología")}</Btn></Notice>}
      {d?.by_relation && <Stack gap="xs">
        <Text fw={600} size="sm">{t("Candidatos por relación")}</Text>
        <Text size="xs" c="dimmed">{t("Proporción de sujetos con más de un destino vigente del mismo tipo, de menor a mayor. Las candidatas a un solo valor son las de proporción baja con algún caso; las que salen como «probablemente varios valores» (algún sujeto con 3 destinos o más, o al menos una cuarta parte de los sujetos con varios) no conviene marcarlas. Solo lee: no cambia nada.")}</Text>
        <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Relación")}</DataTable.Th><DataTable.Th>{t("Sujetos")}</DataTable.Th><DataTable.Th>{t("Con varios destinos")}</DataTable.Th><DataTable.Th>{t("Proporción")}</DataTable.Th><DataTable.Th>{t("Un solo valor")}</DataTable.Th></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{d.by_relation.filter((s) => s.groups > 0).map((s) => {
            const e = edge(s.relation);
            return (<DataTable.Tr key={s.relation}>
              <DataTable.Td><Group gap={6} wrap="nowrap"><Text size="sm" className="ms-data">{s.relation}</Text>
                {s.likely_multi && <Pill size="xs" tone="warn" title={t("Algún sujeto tiene 3 destinos o más, o al menos una cuarta parte de los sujetos tiene varios: no conviene marcarla como de un solo valor.")}>{t("probablemente varios valores")}</Pill>}</Group></DataTable.Td>
              <DataTable.Td>{s.sources}</DataTable.Td><DataTable.Td>{s.groups}</DataTable.Td>
              <DataTable.Td>{`${Math.round(s.ratio * 100)} %`}</DataTable.Td>
              <DataTable.Td>{s.functional ? <Group gap={6} wrap="nowrap"><Pill size="xs" tone="alt">{t("sí")}</Pill>
                  {canMark && e && s.likely_multi && <Btn size="row" loading={mark.isPending} onClick={() => mark.mutate({ e, on: false })}>{t("Desmarcar")}</Btn>}</Group>
                : canMark && e ? <Btn size="row" loading={mark.isPending} onClick={() => mark.mutate({ e, on: true })}>{t("Marcar")}</Btn>
                : canMark ? <Text size="xs" c="dimmed">{t("no está en la ontología")}</Text> : t("no")}</DataTable.Td>
            </DataTable.Tr>);
          })}</DataTable.Tbody>
        </DataTable>
      </Stack>}
      {!!d?.generic_facts && <Text size="xs" c="dimmed">{t("{{n}} hechos con relaciones genéricas (RELATES_TO y parecidas) no se comparan: pueden unir cualquier cosa.", { n: d.generic_facts })}</Text>}
      {d && (d.groups.length ? <Stack gap="xs">
        <Text fw={600} size="sm">{t("Posibles contradicciones ({{n}})", { n: d.total })}</Text>
        <Text size="xs" c="dimmed">{t("«Tipo del destino» es el tipo de entidad de los destinos: solo se comparan destinos del mismo tipo. «Decide tú» sale cuando las fechas no dicen cuál es el actual: o son iguales, o solo dicen cuándo se aprendió cada hecho.")}</Text>
        <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr>
            <DataTable.Th>{t("Sujeto")}</DataTable.Th><DataTable.Th>{t("Relación")}</DataTable.Th><DataTable.Th>{t("Tipo del destino")}</DataTable.Th>
            <DataTable.Th>{t("Hechos")}</DataTable.Th><DataTable.Th>{t("Propuesta")}</DataTable.Th><DataTable.ActionsHead />
          </DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{d.groups.map((g) => {
            const k = key(g), isOpen = open === k;
            return (<Fragment key={k}>
              <DataTable.Tr>
                <DataTable.Td>{g.source}</DataTable.Td><DataTable.Td className="ms-data">{g.relation}</DataTable.Td>
                <DataTable.Td>{g.target_type === "Entity" ? t("sin tipo") : g.target_type}</DataTable.Td><DataTable.Td>{g.facts.length}</DataTable.Td>
                <DataTable.Td><Suggestion g={g} /></DataTable.Td>
                <DataTable.Td><Btn size="row" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : k)}>{isOpen ? t("Cerrar") : t("Revisar")}</Btn></DataTable.Td>
              </DataTable.Tr>
              {isOpen && <DataTable.Tr><DataTable.Td colSpan={6}>
                <GroupDetail g={g} canResolve={!all || d.functional.includes(g.relation)} busy={resolve.isPending || dismiss.isPending}
                  onResolve={(keep, drop) => resolve.mutateAsync({ keep, invalidate: drop })} onDismiss={() => dismiss.mutate(g)}
                  warning={g.likely_multi && <ManyValues g={g} edge={edge(g.relation)} canMark={canMark} unmarking={mark.isPending}
                    onUnmark={() => { const e = edge(g.relation); if (e) mark.mutate({ e, on: false }); }} />} />
              </DataTable.Td></DataTable.Tr>}
            </Fragment>);
          })}</DataTable.Tbody>
        </DataTable>
        {d.total > d.groups.length && <Text size="xs" c="dimmed">{t("Se muestran los primeros {{n}}.", { n: d.groups.length })}</Text>}
      </Stack> : (!all && d.functional.length > 0 && <EmptyState>{t("No hay contradicciones en las relaciones de un solo valor.")}</EmptyState>))}
      {!!d?.dismissed?.length && <Stack gap="xs">
        <Group gap="xs"><Text fw={600} size="sm">{t("Marcados como no contradicción ({{n}})", { n: d.dismissed.length })}</Text>
          <Btn kind="link" onClick={() => setShowDismissed((x) => !x)}>{showDismissed ? t("Ocultar") : t("Ver")}</Btn></Group>
        {showDismissed && <DataTable fz="sm">
          <DataTable.Thead><DataTable.Tr><DataTable.Th>{t("Sujeto")}</DataTable.Th><DataTable.Th>{t("Relación")}</DataTable.Th><DataTable.Th>{t("Hechos")}</DataTable.Th><DataTable.Th>{t("Marcado")}</DataTable.Th><DataTable.ActionsHead /></DataTable.Tr></DataTable.Thead>
          <DataTable.Tbody>{d.dismissed.map((x) => (
            <DataTable.Tr key={x.id}>
              <DataTable.Td>{x.source}</DataTable.Td><DataTable.Td className="ms-data">{x.relation}</DataTable.Td><DataTable.Td>{x.facts}</DataTable.Td><DataTable.Td>{fmt(x.created_at)}</DataTable.Td>
              <DataTable.Td><Btn size="row" icon="undo" loading={undismiss.isPending} onClick={() => undismiss.mutate(x.id)}>{t("Volver a mostrar")}</Btn></DataTable.Td>
            </DataTable.Tr>))}</DataTable.Tbody>
        </DataTable>}
      </Stack>}
    </Stack>
  );
}
