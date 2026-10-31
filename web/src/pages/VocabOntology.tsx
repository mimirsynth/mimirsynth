import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { get, send } from "../api";
import { Btn, Check, ClearFilters, ColHead, DataTable, FillArea, Modal, Notice, Pill, SelectField, TextArea, TextField, useTableView, MutationError, ConfirmDialog } from "../ui";

type T = { name: string; description: string; functional?: boolean };
type Rule = { source: string; target: string; edge_types: string[] };
type Onto = { ontology: { entity_types: T[]; edge_types: T[]; edge_type_map: Rule[]; instructions?: string }; configured: boolean; presets: string[]; presets_info?: { name: string; title: string; description: string; version: number; standards: string[]; entity_types: number; edge_types: number }[]; preset_update?: { name: string; installed: number; available: number } | null };
type Done = { op: number; summary: string };
/** Catch-all relation names (what the extractor writes when no type fits): they link anything, so they are never single-valued. */
const GENERIC = new Set(["RELATES_TO", "RELATED_TO", "IS_RELATED_TO", "ASSOCIATED_WITH", "CONNECTED_TO", "LINKED_TO", "MENTIONS"]);
/** The graph's spelling of a relation (HostedOn → HOSTED_ON). */
const canon = (s: string) => s.trim().replace(/([a-z0-9])([A-Z])/g, "$1_$2").replace(/[\s-]+/g, "_").toUpperCase();
const isGeneric = (s: string) => GENERIC.has(canon(s));
type Dlg = { kind: "rel"; item?: T } | { kind: "rel-del"; item: T } | { kind: "rule"; item?: Rule } | { kind: "rule-del"; item: Rule } | { kind: "instr" } | null;

function RelTable({ rows, used, canEdit, onEdit, onDelete }: { rows: T[]; used: (n: string) => number; canEdit: boolean; onEdit: (t: T) => void; onDelete: (t: T) => void }) {
  const { t } = useTranslation();
  const v = useTableView(rows, { name: { get: (t: T) => t.name }, desc: { get: (t: T) => t.description }, used: { get: (t: T) => used(t.name) }, one: { get: (t: T) => (t.functional ? 1 : 0) } });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("name")} filter={v.text("name")}>{t("Relación")}</ColHead>
          <ColHead filter={v.text("desc", t("Buscar en la descripción…"))}>{t("Descripción")}</ColHead>
          <ColHead sort={v.sortProps("used")}>{t("En reglas")}</ColHead>
          <ColHead sort={v.sortProps("one")}>{t("Un solo valor")}</ColHead>
          {canEdit && <DataTable.ActionsHead />}
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((ty) => (
          <DataTable.Tr key={ty.name}>
            <DataTable.Td><Text fw={500} size="sm">{ty.name}</Text></DataTable.Td>
            <DataTable.Td><Text size="sm" c="dimmed" lineClamp={2}>{ty.description}</Text></DataTable.Td>
            <DataTable.Td>{used(ty.name)}</DataTable.Td>
            <DataTable.Td>{ty.functional ? <Pill size="xs" tone="alt" title={t("Un solo valor a la vez: dos destinos vigentes son una posible contradicción")}>{t("sí")}</Pill> : <Text size="sm" c="dimmed">—</Text>}</DataTable.Td>
            {canEdit && <DataTable.Td><Group gap={6} wrap="nowrap"><Btn size="row" icon="edit" onClick={() => onEdit(ty)}>{t("Editar")}</Btn><Btn kind="danger" size="row" icon="trash" onClick={() => onDelete(ty)}>{t("Quitar")}</Btn></Group></DataTable.Td>}
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
    </Stack>
  );
}

function RuleTable({ rows, canEdit, onEdit, onDelete }: { rows: Rule[]; canEdit: boolean; onEdit: (m: Rule) => void; onDelete: (m: Rule) => void }) {
  const { t } = useTranslation();
  const v = useTableView(rows, { source: { get: (m: Rule) => m.source, exact: true }, target: { get: (m: Rule) => m.target, exact: true }, edges: { get: (m: Rule) => m.edge_types.join(" ") } });
  return (
    <Stack gap="xs">
      <ClearFilters active={v.active} onClear={v.clear} shown={v.rows.length} total={v.total} />
      <DataTable fz="sm">
        <DataTable.Thead><DataTable.Tr>
          <ColHead sort={v.sortProps("source")} filter={v.select("source")}>{t("Origen")}</ColHead>
          <ColHead sort={v.sortProps("target")} filter={v.select("target")}>{t("Destino")}</ColHead>
          <ColHead filter={v.text("edges", t("Relación…"))}>{t("Relaciones permitidas")}</ColHead>
          {canEdit && <DataTable.ActionsHead />}
        </DataTable.Tr></DataTable.Thead>
        <DataTable.Tbody>{v.rows.map((m) => (
          <DataTable.Tr key={`${m.source}>${m.target}`}>
            <DataTable.Td>{m.source}</DataTable.Td><DataTable.Td>{m.target}</DataTable.Td>
            <DataTable.Td><Group gap={4}>{m.edge_types.map((e) => <Pill key={e} size="xs">{e}</Pill>)}</Group></DataTable.Td>
            {canEdit && <DataTable.Td><Group gap={6} wrap="nowrap"><Btn size="row" icon="edit" onClick={() => onEdit(m)}>{t("Editar")}</Btn><Btn kind="danger" size="row" icon="trash" onClick={() => onDelete(m)}>{t("Quitar")}</Btn></Group></DataTable.Td>}
          </DataTable.Tr>))}</DataTable.Tbody>
      </DataTable>
    </Stack>
  );
}

export default function VocabOntology({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const canEdit = ["admin", "owner"].includes(role);
  const q = useQuery({ queryKey: ["ontology", graph], queryFn: () => get<Onto>(`brains/${graph}/ontology`) });
  const [preset, setPreset] = useState<string | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [functional, setFunctional] = useState(false);
  const [src, setSrc] = useState<string | null>(null);
  const [tgt, setTgt] = useState<string | null>(null);
  const [edges, setEdges] = useState<string[]>([]);
  const o = q.data?.ontology;

  const refresh = () => { qc.invalidateQueries({ queryKey: ["ontology", graph] }); qc.invalidateQueries({ queryKey: ["vocab-types", graph] }); };
  const finished = (r: Done) => { setDone(r); setDlg(null); refresh(); };
  const [askReplace, setAskReplace] = useState(false);
  const apply = useMutation({ mutationFn: (a: { name: string; mode: "replace" | "merge" }) => send("POST", `brains/${graph}/ontology/preset/${a.name}`, undefined, { mode: a.mode }), onSuccess: () => { setPreset(null); setDone(null); refresh(); } });
  const info = q.data?.presets_info ?? [];
  const chosen = info.find((i) => i.name === preset);
  const upd = q.data?.preset_update;
  const updInfo = info.find((i) => i.name === upd?.name);
  const saveRel = useMutation({
    mutationFn: () => (dlg?.kind === "rel" && dlg.item ? send<Done>("PUT", `vocab/relations/${dlg.item.name}`, { description: desc, functional: functional && !isGeneric(name) }, { graph }) : send<Done>("POST", "vocab/relations", { name, description: desc, functional: functional && !isGeneric(name) }, { graph })),
    onSuccess: finished });
  const delRel = useMutation({ mutationFn: () => send<Done>("DELETE", `vocab/relations/${(dlg as { item: T }).item.name}`, undefined, { graph }), onSuccess: finished });
  const saveRule = useMutation({ mutationFn: () => send<Done>("PUT", "vocab/map", { source: src, target: tgt, edge_types: edges }, { graph }), onSuccess: finished });
  const delRule = useMutation({ mutationFn: () => { const r = (dlg as { item: Rule }).item; return send<Done>("PUT", "vocab/map", { source: r.source, target: r.target, edge_types: [] }, { graph }); }, onSuccess: finished });
  const saveInstr = useMutation({ mutationFn: () => send<Done>("PUT", "vocab/instructions", { instructions: desc }, { graph }), onSuccess: finished });
  const undo = useMutation({ mutationFn: (id: number) => send("POST", `vocab/ops/${id}/revert`, undefined, { graph }), onSuccess: () => { setDone(null); refresh(); } });

  const reset = () => { saveRel.reset(); delRel.reset(); saveRule.reset(); delRule.reset(); saveInstr.reset(); };
  const openRel = (item?: T) => { reset(); setName(item?.name ?? ""); setDesc(item?.description ?? ""); setFunctional(!!item?.functional); setDlg({ kind: "rel", item }); };
  const openRule = (item?: Rule) => { reset(); setSrc(item?.source ?? null); setTgt(item?.target ?? null); setEdges(item?.edge_types ?? []); setDlg({ kind: "rule", item }); };
  const openInstr = () => { reset(); setDesc(o?.instructions ?? ""); setDlg({ kind: "instr" }); };
  const entityNames = ["Entity", ...(o?.entity_types.map((t) => t.name) ?? [])];
  const usedBy = (rel: string) => (o?.edge_type_map ?? []).filter((m) => m.edge_types.includes(rel)).length;
  const toggle = (e: string, on: boolean) => setEdges((cur) => (on ? [...cur, e] : cur.filter((x) => x !== e)));
  // `?rel=NAME` opens that relation's edit dialog (the Contradictions tab links here to unmark a relation).
  const [params, setParams] = useSearchParams();
  const wanted = params.get("rel");
  useEffect(() => {
    if (!wanted || !o) return;
    const item = o.edge_types.find((e) => canon(e.name) === canon(wanted));
    if (item && canEdit) openRel(item);
    setParams((p) => { p.delete("rel"); return p; }, { replace: true });
  }, [wanted, o]);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <FillArea>
      <Stack gap="sm">
        <Text size="sm" c="dimmed">{t("La ontología guía qué tipos de entidad y de relación extrae el ingestor al escribir. Sin ella, el modelo inventa tipos y relaciones libremente. Los tipos de entidad se editan en su pestaña; aquí, las relaciones, las reglas del mapa y las instrucciones. Los cambios guían las ingestas futuras y no modifican lo que ya está en el grafo.")}</Text>
        {done && <Notice tone="info">{done.summary}. <Btn kind="link" onClick={() => undo.mutate(done.op)}>{t("Deshacer")}</Btn>{undo.error && ` — ${(undo.error as Error).message}`}</Notice>}
        {q.data && !q.data.configured && <Notice tone="warn">{t("Este brain no tiene ontología: la extracción es libre. Aplica un paquete o crea tipos para empezar.")}</Notice>}
        {canEdit && upd && <Notice tone="info" title={t("Hay una versión nueva del paquete «{{name}}»", { name: updInfo?.title ?? upd.name })}>
          {t("Tienes la versión {{installed}} y está disponible la {{available}}. Actualizar añade lo que falta (tipos, relaciones y reglas) sin tocar nada de lo que ya tienes ni lo que cambiaste a mano.", { installed: upd.installed, available: upd.available })}{" "}
          <Btn kind="link" loading={apply.isPending} onClick={() => apply.mutate({ name: upd.name, mode: "merge" })}>{t("Actualizar")}</Btn></Notice>}
        {canEdit && (
          <Group align="flex-end" gap="xs">
            <SelectField label={t("Aplicar paquete")} w={300} data={info.map((i) => ({ value: i.name, label: i.title }))} value={preset} onChange={setPreset} placeholder={t("Elige un paquete")} />
            <Btn kind="primary" disabled={!preset} loading={apply.isPending} onClick={() => preset && (q.data?.configured ? setAskReplace(true) : apply.mutate({ name: preset, mode: "replace" }))} icon="check">{q.data?.configured ? t("Sustituir ontología") : t("Aplicar")}</Btn>
            {q.data?.configured && preset && <Btn onClick={() => apply.mutate({ name: preset, mode: "merge" })} loading={apply.isPending} icon="plus">{t("Añadir lo que falta")}</Btn>}
          </Group>)}
        {canEdit && chosen && <Text size="xs" c="dimmed" maw={760}>{chosen.description} {t("{{e}} tipos de entidad y {{r}} de relación, versión {{v}}.", { e: chosen.entity_types, r: chosen.edge_types, v: chosen.version })}{chosen.standards.length > 0 && <> {t("Basado en:")} {chosen.standards.join("; ")}.</>}</Text>}
        {q.data?.configured && canEdit && <Text size="xs" c="dimmed">{t("Sustituir la ontología reemplaza los tipos, las relaciones, el mapa y las instrucciones actuales, incluidos los cambios hechos a mano. «Añadir lo que falta» solo suma lo que no tienes.")}</Text>}
        <ConfirmDialog opened={askReplace} onClose={() => setAskReplace(false)} title={t("Sustituir la ontología")} action={t("Sustituir")}
          warning={t("Se reemplazan los tipos, las relaciones, el mapa y las instrucciones actuales por los del paquete, incluidos los cambios hechos a mano. Las entidades que ya están en el grafo no cambian.")}
          onConfirm={() => apply.mutateAsync({ name: preset!, mode: "replace" })} />
        <MutationError error={apply.error} />
        {o && (
          <>
            <Group gap={6}><Pill>{o.entity_types.length} {t("tipos de entidad")}</Pill><Pill>{o.edge_types.length} {t("tipos de relación")}</Pill><Pill>{o.edge_type_map.length} {t("reglas de mapa")}</Pill></Group>

            <Group justify="space-between"><Text fw={600} size="sm">{t("Tipos de relación")}</Text>{canEdit && <Btn kind="primary" icon="plus" onClick={() => openRel()}>{t("Añadir relación")}</Btn>}</Group>
            <RelTable rows={o.edge_types} used={usedBy} canEdit={canEdit} onEdit={(t) => openRel(t)} onDelete={(t) => { reset(); setDlg({ kind: "rel-del", item: t }); }} />

            <Group justify="space-between"><Text fw={600} size="sm">{t("Reglas del mapa (qué relaciones se permiten entre qué tipos)")}</Text>{canEdit && <Btn kind="primary" icon="plus" disabled={o.edge_types.length === 0} onClick={() => openRule()}>{t("Añadir regla")}</Btn>}</Group>
            <RuleTable rows={o.edge_type_map} canEdit={canEdit} onEdit={(m) => openRule(m)} onDelete={(m) => { reset(); setDlg({ kind: "rule-del", item: m }); }} />

            <Group justify="space-between"><Text fw={600} size="sm">{t("Instrucciones de extracción")}</Text>{canEdit && <Btn size="row" icon="edit" onClick={openInstr}>{t("Editar")}</Btn>}</Group>
            <Text size="sm" c="dimmed" className="ms-prose">{o.instructions || t("Sin instrucciones.")}</Text>
          </>)}
      </Stack>

      <Modal opened={dlg?.kind === "rel"} onClose={() => setDlg(null)} title={dlg?.kind === "rel" && dlg.item ? t("Editar {{name}}", { name: dlg.item.name }) : t("Añadir tipo de relación")}>
        <Stack>
          <TextField label={t("Nombre")} description={t("PascalCase, sin espacios (p. ej. RunsOn)")} value={name} disabled={dlg?.kind === "rel" && !!dlg.item} onChange={(e) => setName(e.currentTarget.value)} />
          <TextArea label={t("Descripción")} description={t("Cuándo se usa esta relación; guía al ingestor")} minRows={3} autosize value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
          <Check label={t("Un solo valor a la vez")} checked={functional && !isGeneric(name)} disabled={isGeneric(name)} onChange={(e) => setFunctional(e.currentTarget.checked)}
            description={isGeneric(name) ? t("Es una relación genérica: puede unir cualquier cosa, así que no puede ser de un solo valor.")
              : t("Márcalo solo si un sujeto no puede tener dos destinos vigentes a la vez (por ejemplo, dónde está un equipo físico). Dos destinos aparecerán en Contradicciones. Muchas relaciones parecen de un solo valor y no lo son: mide antes en Contradicciones → Medir en todas las relaciones.")} />
          <MutationError error={saveRel.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setDlg(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" disabled={!name || desc.trim().length < 3} loading={saveRel.isPending} onClick={() => saveRel.mutate()}>{t("Guardar")}</Btn></Group>
        </Stack>
      </Modal>

      <ConfirmDialog opened={dlg?.kind === "rel-del"} onClose={() => setDlg(null)} title={t("Quitar {{v}}", { v: dlg?.kind === "rel-del" ? dlg.item.name : "" })} action={t("Quitar relación")}
        warning={`${dlg?.kind === "rel-del" && usedBy(dlg.item.name) > 0 ? t("Se quita también de {{name}} regla(s) del mapa; las que se queden sin relaciones desaparecen. ", { name: usedBy(dlg.item.name) }) : ""}Los hechos que ya están en el grafo con esta relación no se tocan. Se puede deshacer justo después.`}
        onConfirm={() => delRel.mutateAsync()} />

      <Modal opened={dlg?.kind === "rule"} onClose={() => setDlg(null)} title={dlg?.kind === "rule" && dlg.item ? t("Editar regla del mapa") : t("Añadir regla del mapa")}>
        <Stack>
          <Group grow>
            <SelectField label={t("Origen")} data={entityNames} value={src} disabled={dlg?.kind === "rule" && !!dlg.item} onChange={setSrc} searchable />
            <SelectField label={t("Destino")} data={entityNames} value={tgt} disabled={dlg?.kind === "rule" && !!dlg.item} onChange={setTgt} searchable />
          </Group>
          <Text size="sm" fw={500}>{t("Relaciones permitidas entre esos dos tipos")}</Text>
          <Stack gap={6} mah={260} className="ms-scroll">{(o?.edge_types ?? []).map((t) => <Check key={t.name} label={t.name} checked={edges.includes(t.name)} onChange={(e) => toggle(t.name, e.currentTarget.checked)} />)}</Stack>
          <MutationError error={saveRule.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setDlg(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" disabled={!src || !tgt || edges.length === 0} loading={saveRule.isPending} onClick={() => saveRule.mutate()}>{t("Guardar")}</Btn></Group>
        </Stack>
      </Modal>

      <ConfirmDialog opened={dlg?.kind === "rule-del"} onClose={() => setDlg(null)} title={t("Quitar regla del mapa")} action={t("Quitar regla")}
        warning={`${dlg?.kind === "rule-del" ? t("Se quita la regla {{source}} → {{target}}. ", { source: dlg.item.source, target: dlg.item.target }) : ""}Sin regla, el ingestor no tiene restricción para ese par de tipos. Se puede deshacer justo después.`}
        onConfirm={() => delRule.mutateAsync()} />

      <Modal opened={dlg?.kind === "instr"} onClose={() => setDlg(null)} title={t("Instrucciones de extracción")} size="lg">
        <Stack>
          <TextArea label={t("Instrucciones")} description={t("Guía libre para el ingestor (máximo 4.000 caracteres): qué es importante y cómo clasificar")} minRows={8} autosize maxLength={4000} value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
          <MutationError error={saveInstr.error} />
          <Group justify="flex-end"><Btn kind="ghost" onClick={() => setDlg(null)}>{t("Cancelar")}</Btn><Btn kind="primary" icon="check" loading={saveInstr.isPending} onClick={() => saveInstr.mutate()}>{t("Guardar")}</Btn></Group>
        </Stack>
      </Modal>
    </FillArea>
  );
}
