import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fmt, get, send } from "../api";
import { Block, Btn, CodeBlock, EmptyState, Form, MutationError, Notice, Pill, Radio, RadioGroup, Segments, SelectField, Step, Steps, TextField, ViewBar } from "../ui";
import { T } from "../i18n";
import { AGENTS, AGENT_NAME, CONFIG_PATH, connectedSince, snippets, type AgentId, type Block as Snippet, type BlockKind } from "./connectSnippets";

/** A token the panel already has: one it created, or the one a previous step of the setup wizard made (issue 361). Its secret is known only
 *  right after it was created; a token made before is used without it, and the snippets carry a placeholder. */
export type GivenToken = { id: number; secret?: string; name?: string };
type BrainRef = { slug: string; name: string; role: string; description?: string };
type Tok = { id: number; name: string; prefix: string; mine: boolean; expired: boolean; replaced_by: number | null; scopes: string[] };
type Activity = { id: number; name: string; connected: boolean; last_used_at: string | null; recalls: number; last_recall_at: string | null };
type Probe = { context?: string; facts?: unknown[]; chunks?: unknown[]; documents?: unknown[] };

const OTHER = T("Otro cliente MCP");
/** What each block is, said above it. */
const BLOCK: Record<BlockKind, { title: string; text: string }> = {
  config: { title: T("Guarda la configuración"), text: T("Todos los plugins de MimirSynth leen este fichero, en cualquier sistema (en Windows, dentro de tu carpeta de usuario). Si ya tienes uno, cambia solo estas claves. Guárdalo legible solo por ti: lleva el token.") },
  install: { title: T("Instala el plugin"), text: T("Una línea, en un terminal. Si después pregunta la URL, el brain o el token, ya los encuentra en el fichero: pulsa Intro para quedarte con cada uno.") },
  mcp: { title: T("Opcional: el servidor MCP del brain"), text: T("Da al modelo las herramientas de MimirSynth (recall, remember, facts_about…) además de lo que hace el plugin.") },
  "mcp-json": { title: T("Añade el servidor a tu cliente"), text: T("La forma «mcpServers» que leen la mayoría de clientes MCP. Transporte HTTP «streamable», sin estado; solo hace falta poder enviar una cabecera.") },
  "mcp-raw": { title: T("O configúralo a mano"), text: T("La dirección del servidor MCP del brain y la cabecera de cada petición.") },
};
/** What only one agent needs to know, after its blocks. */
const AFTER: Partial<Record<AgentId, string>> = {
  codex: T("Codex solo ejecuta los hooks de un plugin cuando confías en ellos: abre /hooks en Codex y confía en los tres de «mimirsynth». Para el servidor MCP, exporta antes MIMIRSYNTH_TOKEN con el token."),
  hermes: T("Además de instalarlo, «hermes memory setup» hace de MimirSynth el proveedor de memoria de ese perfil."),
  openclaw: T("OpenClaw pide aceptar las capacidades del plugin, y el setup ofrece darle el acceso a la conversación que necesita su recall."),
};

/** «Connect your agent» (issue 362): pick the agent, get its one-line install or its MCP configuration already filled in with this server, the
 *  brain and a token, and see it turn green when the agent makes its first call; then a test recall shows what the agent receives.
 *  It lives on the brain's page (Administration → Brain → Connect an agent); the setup wizard (issue 361) embeds it with the token its previous
 *  step created, through `token`. A view inside the settings group (or the wizard's step) that titles it: the bar picks the agent, then the
 *  token and the steps. */
export default function ConnectAgent({ brain, token: given, onConnected, untilRecall }: { brain: BrainRef; token?: GivenToken; onConnected?: (tokenId: number) => void;
  /** Turn green with the agent's first recall, not its first call: the setup wizard's step, which that same recall ticks (issue 421). */
  untilRecall?: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [agent, setAgent] = useState<AgentId>("claude-code");
  const [mode, setMode] = useState<"new" | "existing">("new");
  const [made, setMade] = useState<GivenToken | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const writer = ["contributor", "curator", "admin", "owner"].includes(brain.role);
  const [role, setRole] = useState<string | null>(writer ? "contributor" : "reader");
  const cfg = useQuery({ queryKey: ["config"], queryFn: () => get<{ token_max_days?: number }>("config"), staleTime: Infinity });
  const list = useQuery({ queryKey: ["tokens", brain.slug], enabled: !given, queryFn: () => get<Tok[]>(`brains/${brain.slug}/tokens`) });
  const usable = (list.data ?? []).filter((x) => x.mine && !x.expired && !x.replaced_by);
  const chosen = usable.find((x) => String(x.id) === picked);
  // the token being watched: the wizard's, the one made here, or one picked from the list (without its secret)
  const tok: GivenToken | null = given ?? (mode === "new" ? made : chosen ? { id: chosen.id, name: chosen.name } : null);
  const create = useMutation({
    mutationFn: () => {
      const cap = cfg.data?.token_max_days ?? 0;
      return send<{ id: number; name: string; token: string }>("POST", `brains/${brain.slug}/tokens`, { name: agent === "mcp" ? t(OTHER) : AGENT_NAME[agent], role, days: cap && cap < 90 ? cap : 90 });
    },
    onSuccess: (r) => { setMade({ id: r.id, secret: r.token, name: r.name }); qc.invalidateQueries({ queryKey: ["tokens", brain.slug] }); },
  });
  const conn = { url: window.location.origin, brain: brain.slug, token: tok?.secret ?? "" };
  const roleOptions = [{ value: "reader", label: t("Lector: solo consulta") }, ...(writer ? [{ value: "contributor", label: t("Colaborador: consulta y propone (recomendado)") }] : [])];
  return (
    <>
      <ViewBar title={t("Conectar un agente")}>
        <Segments label={t("¿Qué agente usas?")} value={agent} onChange={(v) => setAgent(v as AgentId)} data={AGENTS.map((a) => ({ value: a, label: a === "mcp" ? t(OTHER) : AGENT_NAME[a] }))} />
      </ViewBar>
      {!given && (
        <Stack gap="xs">
          <RadioGroup label={t("Token de API")} value={mode} onChange={(v) => setMode(v as "new" | "existing")}>
            <Group gap="md">
              <Radio value="new" label={t("Crear uno para este agente")} />
              <Radio value="existing" label={t("Usar uno que ya tengo")} disabled={!usable.length} />
            </Group>
          </RadioGroup>
          {mode === "new" && !made && (
            <>
              <SelectField label={t("Rol")} data={roleOptions} value={role} onChange={setRole} allowDeselect={false} />
              <Group><Btn kind="primary" icon="plus" loading={create.isPending} disabled={!role} onClick={() => create.mutate()}>{t("Crear token")}</Btn></Group>
            </>)}
          {mode === "new" && made && <Notice tone="warn">{t("Token «{{name}}» creado. Ya va en los fragmentos de abajo: cópialos ahora, porque no se vuelve a mostrar.", { name: made.name })}</Notice>}
          {mode === "existing" && <>
            <SelectField label={t("Token")} placeholder={t("Elige uno de tus tokens")} value={picked} onChange={setPicked}
              description={t("El secreto de un token solo se muestra al crearlo: los fragmentos llevan «mst_…» donde va el tuyo.")}
              data={usable.map((x) => ({ value: String(x.id), label: `${x.name} · ${x.prefix}…` }))} />
          </>}
          <MutationError error={create.error} />
        </Stack>)}
      <Steps label={t("Conectar {{agent}}", { agent: agent === "mcp" ? t(OTHER) : AGENT_NAME[agent] })}>
        {snippets(agent, conn).map((b) => <SnippetStep key={b.kind} block={b} />)}
        <Step title={t("Arranca el agente")}>
          {AFTER[agent] && <Text size="sm">{t(AFTER[agent]!)}</Text>}
          {tok ? <LiveCheck key={tok.id} brain={brain} token={tok} fresh={!!tok.secret || !!given} onConnected={onConnected} untilRecall={untilRecall} />
            : <Text size="sm" c="dimmed">{untilRecall ? t("Crea o elige un token y aquí verás cuándo hace el agente su primer recall.")
              : t("Crea o elige un token y aquí verás cuándo llega la primera llamada del agente.")}</Text>}
        </Step>
      </Steps>
    </>
  );
}

function SnippetStep({ block }: { block: Snippet }) {
  const { t } = useTranslation();
  const b = BLOCK[block.kind];
  return (
    <Step title={t(b.title)}>
      <Stack gap={6}>
        <Text size="sm">{t(b.text)}</Text>
        {block.kind === "config" && <Text size="sm" className="ms-data">{CONFIG_PATH}</Text>}
        <CodeBlock copy label={t(b.title)}>{block.code}</CodeBlock>
      </Stack>
    </Step>
  );
}

/** Waits for the agent's first authenticated call with the token (with `untilRecall`, its first recall), asking the server every two
 *  seconds, then runs a test recall with what that token may see. `fresh`: a token just created, so any call counts; for an older one, a
 *  call (or a recall) after the ones first seen. */
function LiveCheck({ brain, token, fresh, onConnected, untilRecall }: { brain: BrainRef; token: GivenToken; fresh: boolean; onConnected?: (id: number) => void;
  untilRecall?: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  // the last call before watching: none for a fresh token; for an older one, what the server says the first time it is asked
  const [base, setBase] = useState<{ at: string | null; recalls: number } | null>(fresh ? { at: null, recalls: 0 } : null);
  const [seen, setSeen] = useState(false);
  const act = useQuery({ queryKey: ["token-activity", brain.slug, token.id], queryFn: () => get<Activity>(`brains/${brain.slug}/tokens/${token.id}/activity`),
    refetchInterval: () => (seen ? false : 2000), refetchIntervalInBackground: true, gcTime: 0 });
  useEffect(() => { if (act.data && !base) setBase({ at: act.data.last_used_at, recalls: act.data.recalls }); }, [act.data, base]);
  const connected = !!base && !!act.data && (untilRecall ? act.data.recalls > base.recalls : connectedSince(base.at, act.data.last_used_at));
  const name = act.data?.name ?? token.name ?? "";
  const [query, setQuery] = useState((brain.description?.trim() || brain.name).slice(0, 300));
  const probe = useMutation({ mutationFn: (q: string) => send<Probe>("POST", `brains/${brain.slug}/tokens/${token.id}/test-recall`, { query: q }) });
  useEffect(() => {
    if (!connected || seen) return;
    setSeen(true);
    qc.invalidateQueries({ queryKey: ["onboarding"] });  // the getting-started checklist reads the same records
    onConnected?.(token.id);
    probe.mutate(query);
  }, [connected]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (act.error) return <MutationError error={act.error} />;
  if (!connected) {
    return (
      untilRecall
        ? <Notice tone="info" title={t("Esperando el primer recall del agente…")} role="status">
          <Text size="sm">{t("Ábrelo en cuanto esté instalado y escríbele un primer mensaje; con un cliente MCP sin plugin, pregúntale algo que deba buscar en MimirSynth. Esto se pone en verde unos segundos después de su primer recall.")}</Text>
        </Notice>
        : <Notice tone="info" title={t("Esperando la primera llamada del agente…")} role="status">
          <Text size="sm">{t("Ábrelo (o ejecuta su comando de estado) en cuanto esté instalado. Esto se pone en verde unos segundos después de que use el token.")}</Text>
        </Notice>);
  }
  const p = probe.data;
  const n = (x?: unknown[]) => x?.length ?? 0;
  return (
    <Stack gap="xs">
      <Notice tone="success" title={untilRecall ? t("Tu agente ya ha hecho su primer recall") : t("Tu agente está conectado")} role="status">
        <Text size="sm">{untilRecall
          ? t("Recalls hechos con «{{name}}» hasta ahora: {{n}}; el último, el {{at}}.", { name, n: act.data?.recalls ?? 0, at: fmt(act.data?.last_recall_at) })
          : act.data?.recalls
            ? t("Primera llamada con «{{name}}» el {{at}}. Recalls hechos con él hasta ahora: {{n}}.", { name, at: fmt(act.data?.last_used_at), n: act.data.recalls })
            : t("Primera llamada con «{{name}}» el {{at}}.", { name, at: fmt(act.data?.last_used_at) })}</Text>
      </Notice>
      <Block title={t("Un recall de prueba: lo que recibe el agente")} help={t("Una vista previa: no cuenta como un recall del agente ni queda registrada.")}>
        <Form onSubmit={() => { if (query.trim()) probe.mutate(query.trim()); }}>
          <TextField label={t("Pregunta")} value={query} onChange={(e) => setQuery(e.currentTarget.value)} />
          <Group><Btn type="submit" icon="ask" loading={probe.isPending} disabled={!query.trim()}>{t("Probar recall")}</Btn></Group>
        </Form>
        <MutationError error={probe.error} />
        {p && <>
          <Group gap={6}>
            <Pill>{t("{{n}} hechos", { n: n(p.facts) })}</Pill>
            <Pill>{t("{{n}} fragmentos", { n: n(p.chunks) })}</Pill>
            <Pill>{t("{{n}} pasajes", { n: n(p.documents) })}</Pill>
          </Group>
          {p.context?.trim() ? <CodeBlock label={t("Contexto del recall de prueba")}>{p.context}</CodeBlock>
            : <EmptyState>{t("El brain ha respondido, pero nada de lo que sabe se parece lo bastante a esta pregunta. En un brain nuevo es lo normal: prueba otra, o vuelve cuando haya memoria.")}</EmptyState>}
        </>}
      </Block>
    </Stack>
  );
}
