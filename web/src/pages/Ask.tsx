import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, NumberField, Panel, Pill, TextArea, MutationError, Page, PageHeader, FillArea, ListCard, CodeBlock } from "../ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fmt, get, send } from "../api";

type Fact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; name: string; source: string; target: string; score: number };
type Chunk = { id: number; name: string; text: string; valid_at: string | null; score: number; rrf: number };
type Res = { facts: Fact[]; chunks: Chunk[]; context: string; index: boolean; ms: Record<string, number> };

export default function Ask({ graph, role }: { graph: string; role: string }) {
  const [q, setQ] = useState("");
  const [nf, setNf] = useState(8); const [nc, setNc] = useState(4);
  const status = useQuery({ queryKey: ["index", graph], queryFn: () => get<{ enabled: boolean; chunks: number; episodes: number }>("index/status", { graph }) });
  const run = useMutation({ mutationFn: () => send<Res>("POST", `brains/${graph}/recall`, { query: q, facts: nf, chunks: nc }) });
  const sync = useMutation({ mutationFn: () => send<any>("POST", `brains/${graph}/index/sync`), onSuccess: () => status.refetch() });
  const canSync = ["curator", "admin", "owner"].includes(role);
  const r = run.data;
  return (
    <Page>
      <PageHeader title="Preguntar" description={<>Recall híbrido: hechos del grafo (vigentes e invalidados) más fragmentos de los episodios originales. Es el contexto que se inyecta al agente.</>} />
      <FillArea><Stack gap="xs">
      <Group gap="xs">
        {status.data && <Pill tone={status.data.enabled ? "success" : "warn"}>{status.data.enabled ? `índice: ${status.data.chunks} fragmentos de ${status.data.episodes} episodios` : "índice de texto desactivado (requiere PostgreSQL)"}</Pill>}
        {canSync && status.data?.enabled && <Btn size="row" loading={sync.isPending} onClick={() => sync.mutate()} icon="refresh">Reindexar ahora</Btn>}
        {sync.data && <Text size="xs" c="dimmed">{sync.data.reindexed} episodios reindexados</Text>}
      </Group>
      <TextArea autosize minRows={2} placeholder="¿Dónde está Nextcloud ahora?" value={q} onChange={(e) => setQ(e.currentTarget.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && q) run.mutate(); }} />
      <Group align="flex-end">
        <NumberField size="xs" label="Hechos" value={nf} min={0} max={30} onChange={(v) => setNf(Number(v) || 0)} w={80} />
        <NumberField size="xs" label="Fragmentos" value={nc} min={0} max={15} onChange={(v) => setNc(Number(v) || 0)} w={100} />
        <Btn kind="primary" disabled={!q} loading={run.isPending} onClick={() => run.mutate()}>Buscar (Ctrl+Enter)</Btn>
        {r && <Text size="xs" c="dimmed">{r.ms.total} ms (embedding {r.ms.embed} · hechos {r.ms.facts} · fragmentos {r.ms.chunks})</Text>}
      </Group>
      <MutationError error={run.error} />
      {r && (
        <Group align="flex-start" wrap="nowrap" gap="md">
          <Stack className="ms-ask-main" gap="xs">
            <Title order={5}>Hechos ({r.facts.length})</Title>
            {r.facts.map((f) => (
              <ListCard key={f.uuid} invalid={f.status === "invalidated"}
                tags={<><Pill size="xs">{f.source}</Pill><Text size="xs" className="ms-data">{f.name}</Text><Pill size="xs">{f.target}</Pill></>}
                meta={<>sim {f.score} · {fmt(f.valid_at)}{f.invalid_at ? ` → ${fmt(f.invalid_at)}` : ""}</>}>{f.fact}</ListCard>))}
            <Title order={5} mt="xs">Fragmentos de episodios ({r.chunks.length})</Title>
            {r.chunks.map((c) => (
              <ListCard key={c.id} title={c.name} aside={`${fmt(c.valid_at)} · sim ${c.score}`}>{c.text}</ListCard>))}
          </Stack>
          <Stack gap="xs" className="ms-ask-side">
            <Title order={6}>Contexto inyectado</Title>
            <CodeBlock copy>{r.context}</CodeBlock>
          </Stack>
        </Group>)}
      </Stack></FillArea>
    </Page>
  );
}
