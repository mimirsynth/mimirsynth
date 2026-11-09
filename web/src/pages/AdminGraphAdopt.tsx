import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Brain, fmtNum, get, send } from "../api";
import { Btn, DataState, DataTable, EmptyState, Modal, MutationError, Notice, Pill, Radio, RadioGroup, SettingsBody, SettingsGroup, TextArea, TextField } from "../ui";

type Part = {
  name: string; nodes: number; edges: number; entities: number; episodes: number; dim: number | null; graphiti: boolean; group_ids: string[];
  brain: string | null; read_only: boolean | null; valid_name: boolean; dim_ok: boolean; error?: string;
};
type Inventory = { backend: "falkordb" | "neo4j"; engine_dim: number; graphs: Part[]; truncated: boolean };

/** A brain slug from a graph's name: lower case, letters, digits and dashes, 2 to 41 characters. */
const slugOf = (name: string) => name.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 41) || "brain";

function Adopt({ part, inv, onClose, onDone }: { part: Part; inv: Inventory; onClose: () => void; onDone: (b: Brain) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(part.name);
  const [slug, setSlug] = useState(slugOf(part.name));
  const [desc, setDesc] = useState("");
  const [mode, setMode] = useState(part.dim_ok ? "full" : "read_only");
  const adopt = useMutation({ mutationFn: () => send<Brain>("POST", "admin/graph/adopt", { graph: part.name, slug, name, description: desc, read_only: mode === "read_only" }),
    onSuccess: onDone });
  const otherGroups = inv.backend === "falkordb" && part.group_ids.some((g) => g !== part.name);
  return (
    <Modal opened onClose={onClose} title={t("Adoptar «{{graph}}» como brain", { graph: part.name })} centered>
      <Stack gap="sm">
        <Text size="sm" className="ms-measure">{t("El grafo pasa a ser un brain tal como está: no se cambia nada de él, ni de ningún otro grafo de la base de datos.")}</Text>
        <TextField label={t("Nombre")} value={name} onChange={(e) => setName(e.currentTarget.value)} data-autofocus />
        <TextField label={t("Slug")} description={t("Identificador permanente (minúsculas, números y guiones)")} value={slug} onChange={(e) => setSlug(e.currentTarget.value)} />
        <TextArea label={t("Descripción")} description={t("De qué trata este brain. El decisor la usa para juzgar si una propuesta encaja en él.")} autosize minRows={2} value={desc} onChange={(e) => setDesc(e.currentTarget.value)} />
        <RadioGroup label={t("Cómo se usa")} value={mode} onChange={setMode}>
          <Stack gap="xs" mt={4}>
            <Radio value="full" disabled={!part.dim_ok} label={t("Completo")} description={t("Se consulta y aprende: propuestas, ingesta y curación lo escriben.")} />
            <Radio value="read_only" label={t("Solo lectura")} description={t("Se consulta, pero nada lo escribe: ni propuestas, ni curación, ni un cambio de modelo de embeddings.")} />
          </Stack>
        </RadioGroup>
        {!part.dim_ok && <Notice tone="warn" title={t("Sus vectores no son los del motor de embeddings")}>
          {t("Tienen {{dim}} dimensiones y el motor por defecto, {{engine}}: la búsqueda por similitud no los compararía. Se puede adoptar de solo lectura (hechos, línea temporal y entidades funcionan); para adoptarlo completo, cambia antes el motor por uno de {{dim}} dimensiones.", { dim: part.dim, engine: inv.engine_dim })}
        </Notice>}
        {otherGroups && <Notice tone="info" title={t("Escrito con otro group_id")}>
          {t("Graphiti guardó estos datos con group_id {{ids}}. El brain los lee igual, pero lo que aprenda después se escribirá con «{{graph}}» y no se fusionará con ellos.", { ids: part.group_ids.join(", "), graph: part.name })}
        </Notice>}
        <MutationError error={adopt.error} />
        <Group justify="flex-end" gap="xs">
          <Btn kind="ghost" onClick={onClose}>{t("Cancelar")}</Btn>
          <Btn kind="primary" icon="plus" disabled={!name.trim() || !slug} loading={adopt.isPending} onClick={() => adopt.mutate()}>{t("Adoptar")}</Btn>
        </Group>
      </Stack>
    </Modal>
  );
}

/** The graphs the database already holds (issue 359): what each one is and whose brain it is, adopting one as a brain, full or read-only,
 *  and switching an adopted brain between the two. Nothing that is not adopted is ever touched. Also used by the setup wizard. */
export default function ExistingGraphs({ onAdopted }: { onAdopted?: (b: Brain) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-graph-inventory"], queryFn: () => get<Inventory>("admin/graph/inventory"), refetchOnWindowFocus: false });
  const [adopting, setAdopting] = useState<Part | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin-graph-inventory"] }); qc.invalidateQueries({ queryKey: ["brains"] }); };
  const mode = useMutation({ mutationFn: (p: Part) => send<Brain>("PATCH", `admin/graph/brains/${p.brain}`, { read_only: !p.read_only }), onSuccess: refresh });
  const inv = q.data;
  return (
    <SettingsGroup title={t("Grafos de la base de datos")}
      description={t("Lo que ya hay en la base de datos en uso. Un grafo que no es de ningún brain se puede adoptar tal cual; el que no adoptes no se toca.")}
      action={<Btn icon="refresh" loading={q.isFetching} onClick={() => q.refetch()}>{t("Volver a leer")}</Btn>}>
      <SettingsBody>
        {!inv ? <DataState query={q} /> : inv.graphs.length === 0 ? <EmptyState>{t("La base de datos no tiene grafos todavía: cada brain nuevo creará el suyo.")}</EmptyState> : <Stack gap="xs">
          <DataTable fz="sm">
            <DataTable.Thead><DataTable.Tr>
              <DataTable.Th>{t("Grafo")}</DataTable.Th><DataTable.Th>{t("Brain")}</DataTable.Th><DataTable.ActionsHead />
            </DataTable.Tr></DataTable.Thead>
            <DataTable.Tbody>{inv.graphs.map((p) => (
              <DataTable.Tr key={p.name}>
                <DataTable.Td><Stack gap={2}>
                  <Group gap={6}><Text size="sm" className="ms-data ms-breakall">{p.name}</Text>
                    {p.dim != null && <Pill size="sm" tone={p.dim_ok ? "neutral" : "warn"}>{t("{{dim}} dimensiones", { dim: p.dim })}</Pill>}</Group>
                  {p.error ? <Text size="xs" className="ms-text-danger">{p.error}</Text>
                    : <Text size="xs" c="dimmed">{p.graphiti ? t("{{entities}} entidades · {{edges}} aristas · {{episodes}} episodios", { entities: fmtNum(p.entities), edges: fmtNum(p.edges), episodes: fmtNum(p.episodes) })
                      : t("sin entidades ni episodios de Graphiti")}</Text>}
                </Stack></DataTable.Td>
                <DataTable.Td>{p.brain
                  ? <Group gap={4}><Pill size="sm" tone="success">{p.brain}</Pill>{p.read_only && <Pill size="sm">{t("solo lectura")}</Pill>}</Group>
                  : <Text size="xs" c="dimmed">{t("sin adoptar")}</Text>}</DataTable.Td>
                <DataTable.Td>{p.brain
                  ? <Btn size="row" loading={mode.isPending && mode.variables?.name === p.name} onClick={() => mode.mutate(p)}>{p.read_only ? t("Pasar a completo") : t("Pasar a solo lectura")}</Btn>
                  : !p.error && p.valid_name && <Btn size="row" icon="plus" onClick={() => setAdopting(p)}>{t("Adoptar")}</Btn>}</DataTable.Td>
              </DataTable.Tr>))}
            </DataTable.Tbody>
          </DataTable>
          {inv.truncated && <Text size="xs" c="dimmed">{t("Hay más grafos de los que se listan aquí.")}</Text>}
          {inv.graphs.some((p) => !p.brain && !p.valid_name) && <Text size="xs" c="dimmed" className="ms-measure">{t("Un grafo cuyo nombre lleva otros caracteres que letras, números, - y _ no se puede adoptar.")}</Text>}
          <MutationError error={mode.error} />
        </Stack>}
        {adopting && inv && <Adopt part={adopting} inv={inv} onClose={() => setAdopting(null)} onDone={(b) => { setAdopting(null); refresh(); onAdopted?.(b); }} />}
      </SettingsBody>
    </SettingsGroup>
  );
}
