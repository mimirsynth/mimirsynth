import { T, translateServer } from "../i18n";
import { useTranslation } from "react-i18next";
import { Group, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Brain, get, send } from "../api";
import { Btn, CodeBlock, ComboField, DataState, MutationError, Notice, Page, PageHeader, PasswordField, Pill, ProgressBar, Radio, RadioGroup, SelectField, SettingsBody, SettingsGroup, SettingsLayout, SubNav, TextField } from "../ui";
import AdminGraph from "./AdminGraph";
import ConnectAgent from "./ConnectAgent";

type StepKey = "admin" | "graph" | "embedding" | "llm" | "decider" | "brain" | "token" | "agent";
export type Wizard = {
  finished: boolean; current: StepKey; brain: string | null; token_id: number | null; agent_connected: boolean;
  steps: { key: StepKey; status: "done" | "skipped" | "todo"; blocking: boolean; skippable: boolean }[];
  embedding: { model: string; base_url: string; dim: number; index_dim: number };
  llm: { configured: boolean; name: string | null }; decider: { configured: boolean; name: string | null };
};
type Ollama = { found: string | null; openai_base: string | null; models: string[]; suggested: string; has_suggested: boolean; tried?: string[] };
type JobOut = { status: string; done?: number | null; total?: number | null; message?: string | null; error?: string | null };
type Extra = { brain?: string; token_id?: number };

const TITLE: Record<StepKey, string> = {
  admin: T("Tu cuenta"), graph: T("Base de datos del grafo"), embedding: T("Embeddings"), llm: T("Modelo LLM"), decider: T("Decisor"),
  brain: T("Tu primer brain"), token: T("Token de API"), agent: T("Conecta tu agente"),
};
/** What each step is for, for someone who has never set up an AI memory. */
const INTRO: Record<StepKey, string> = {
  admin: T("Ya tienes la cuenta de administrador: con ella configuras la instancia. En los pasos siguientes la dejas lista para que tu agente recuerde lo que aprende."),
  graph: T("La memoria se guarda como un grafo: entidades (personas, servidores, proyectos) unidas por hechos. Aquí eliges dónde vive ese grafo y compruebas que se puede usar. Si ya tienes datos de Graphiti, puedes adoptarlos."),
  embedding: T("Un modelo de embeddings convierte cada texto en números para encontrar lo que se parece por su significado, no solo por sus palabras. Sin él, el recall no encuentra nada."),
  llm: T("Un modelo de lenguaje lee lo que tu agente propone y saca de ahí entidades y hechos. Sin él, las propuestas aprobadas esperan sin entrar en la memoria."),
  decider: T("Un decisor aprueba solo, con un umbral de confianza, las propuestas claramente factuales; lo dudoso sigue esperando a una persona. Es opcional."),
  brain: T("Un brain es una memoria separada, con su propio grafo, sus miembros y sus tokens: por ejemplo, una por equipo o por proyecto."),
  token: T("Tu agente se identifica con un token. Con el rol Colaborador lee la memoria y propone hechos nuevos, que esperan a que alguien los apruebe."),
  agent: T("Elige tu agente y copia lo que necesita. El paso se pone en verde cuando el agente hace su primer recall, y entonces el panel te deja probar qué recibe."),
};
const STATUS: Record<string, string> = { done: T("completado"), skipped: T("saltado") };

/** The setup wizard (issue 361): a guided first run, from the administrator's account to the agent's first recall. Each step is kept on the
 *  server as it is passed, so closing the browser resumes on the same step; the graph and embedding steps are checked by the server and
 *  cannot be skipped. */
export default function SetupWizard() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["setup"], queryFn: () => get<Wizard>("setup"),
    refetchInterval: (query) => (query.state.data?.current === "agent" && !query.state.data.agent_connected ? 5000 : false) });
  const [open, setOpen] = useState<StepKey | null>(null);
  const [extra, setExtra] = useState<Extra>({});
  const [secret, setSecret] = useState("");
  const done = (w: Wizard) => { qc.setQueryData(["setup"], w); setOpen(null); setExtra({}); qc.invalidateQueries({ queryKey: ["me"] }); qc.invalidateQueries({ queryKey: ["ai-status"] });
    if (w.finished) { qc.invalidateQueries({ queryKey: ["brains"] }); navigate("/"); } };
  const mark = useMutation({ mutationFn: ({ key, action }: { key: StepKey; action: "done" | "skip" }) => send<Wizard>("POST", `setup/steps/${key}`, { action, ...extra }), onSuccess: done });
  const close = useMutation({ mutationFn: () => send<Wizard>("POST", "setup/close"), onSuccess: done });
  const w = q.data;
  if (!w) return <Page><DataState query={q} /></Page>;
  const step = open ?? w.current;
  const at = w.steps.findIndex((s) => s.key === step);
  const reach = w.steps.findIndex((s) => s.key === w.current);
  const meta = w.steps[at];
  const body: Record<StepKey, ReactNode> = {
    admin: null,
    graph: <AdminGraph />,
    embedding: <EmbeddingStep w={w} />,
    llm: <LlmStep key="llm" w={w} kind="llm" />,
    // its own key: the same component as the LLM step, which would otherwise keep that step's endpoint and model filled in (issue 421)
    decider: <LlmStep key="decider" w={w} kind="decision" />,
    brain: <BrainStep w={w} pick={(brain) => setExtra({ brain })} />,
    token: <TokenStep w={w} brain={extra.brain ?? w.brain} pick={(token_id, s) => { setExtra({ token_id }); setSecret(s); }} />,
    agent: <AgentStep w={w} secret={secret} />,
  };
  const ready = step === "brain" ? !!(extra.brain ?? w.brain) : step === "token" ? !!(extra.token_id ?? w.token_id) : true;
  return (
    <Page>
      <PageHeader title={t("Configuración inicial")} description={t("De la cuenta de administrador a la primera vez que tu agente recuerda algo, en unos minutos. Puedes dejarlo en cualquier paso: al volver, sigue donde lo dejaste.")}
        actions={<Btn kind="ghost" loading={close.isPending} onClick={() => close.mutate()}>{t("Configurar a mano")}</Btn>} />
      <SettingsLayout nav={<SubNav label={t("Pasos de la configuración")} value={step} onChange={(v) => setOpen(v as StepKey)}
        items={w.steps.slice(0, reach + 1).map((s, i) => ({ value: s.key, label: `${i + 1}. ${t(TITLE[s.key])}${STATUS[s.status] ? ` · ${t(STATUS[s.status])}` : ""}` }))} />}>
        <SettingsGroup title={`${at + 1}/${w.steps.length} · ${t(TITLE[step])}`} description={t(INTRO[step])}>
          <SettingsBody><Stack gap="md">
            {body[step]}
            {meta.blocking && <Text size="xs" c="dimmed" className="ms-measure">{t("Este paso no se puede saltar: al pulsar «Siguiente», el servidor lo comprueba.")}</Text>}
            <MutationError error={mark.error ?? close.error} />
            <Group justify="space-between">
              <Btn kind="ghost" disabled={at === 0} onClick={() => { setOpen(w.steps[at - 1].key); mark.reset(); }}>{t("Atrás")}</Btn>
              <Group gap="xs">
                {meta.skippable && step !== "agent" && <Btn loading={mark.isPending && mark.variables?.action === "skip"} onClick={() => mark.mutate({ key: step, action: "skip" })}>{t("Saltar")}</Btn>}
                <Btn kind="primary" disabled={!ready} loading={mark.isPending && mark.variables?.action === "done"} onClick={() => mark.mutate({ key: step, action: "done" })}>
                  {step === "agent" ? t("Terminar") : t("Siguiente")}</Btn>
              </Group>
            </Group>
          </Stack></SettingsBody>
        </SettingsGroup>
      </SettingsLayout>
    </Page>
  );
}

function EmbeddingStep({ w }: { w: Wizard }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [kind, setKind] = useState("ollama");
  const ollama = useMutation({ mutationFn: () => get<Ollama>("setup/ollama") });
  const [job, setJob] = useState<number | null>(null);
  const pull = useMutation({ mutationFn: (o: Ollama) => send<{ job_id: number }>("POST", "setup/ollama/pull", { base: o.found, model: o.suggested }), onSuccess: (r) => setJob(r.job_id) });
  const jq = useQuery({ queryKey: ["setup-job", job], enabled: job !== null, queryFn: () => get<JobOut>(`setup/jobs/${job}`),
    refetchInterval: (query) => (["queued", "running"].includes(query.state.data?.status ?? "queued") ? 1500 : false) });
  const [base, setBase] = useState("https://api.openai.com/v1"); const [key, setKey] = useState(""); const [model, setModel] = useState("");
  const create = useMutation({ mutationFn: (b: { base_url: string; model: string; api_key?: string }) => send<{ is_default: boolean; dim: number; model: string }>("POST", "embedding-engines", { name: `${b.model} · ${new URL(b.base_url).host}`, ...b }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["setup"] }); qc.invalidateQueries({ queryKey: ["embedding-engines"] }); } });
  const o = ollama.data;
  const pulled = jq.data?.status === "done";
  return (
    <Stack gap="sm">
      <Notice tone="info" title={t("En uso ahora")}>{t("{{model}} en {{url}}, {{dim}} dimensiones. Si ya responde, pulsa «Siguiente».", { model: w.embedding.model, url: w.embedding.base_url, dim: w.embedding.dim })}</Notice>
      <RadioGroup label={t("O elige otro")} value={kind} onChange={setKind}>
        <Stack gap="xs" mt={4}>
          <Radio value="ollama" label={t("Ollama en local")} description={t("Gratis y privado: los textos no salen de tu equipo. Recomendado para empezar.")} />
          <Radio value="openai" label={t("Un servicio compatible con OpenAI")} description={t("OpenAI, OpenRouter u otro proveedor, con su clave de API.")} />
        </Stack>
      </RadioGroup>
      {kind === "ollama" ? <Stack gap="xs">
        <Group gap="xs"><Btn icon="search" loading={ollama.isPending} onClick={() => ollama.mutate()}>{t("Buscar Ollama")}</Btn>
          {o && (o.found ? <Pill tone="success">{t("Encontrado en {{url}}", { url: o.found })}</Pill> : <Pill tone="warn">{t("No se encuentra")}</Pill>)}</Group>
        {o && !o.found && <Text size="sm" className="ms-measure">{t("No responde ninguna de estas direcciones: {{tried}}. Instálalo desde ollama.com o vuelve a ejecutar el instalador y elige el Ollama incluido.", { tried: (o.tried ?? []).join(", ") })}</Text>}
        {o?.found && !o.has_suggested && !pulled && <Group gap="xs">
          <Btn icon="download" loading={pull.isPending || jq.data?.status === "running"} onClick={() => pull.mutate(o)}>{t("Descargar {{model}}", { model: o.suggested })}</Btn>
          {jq.data?.total ? <ProgressBar done={jq.data.done ?? 0} total={jq.data.total} text={jq.data.message ?? ""} /> : jq.data && <Text size="xs" c="dimmed">{jq.data.message ?? jq.data.status}</Text>}
        </Group>}
        {jq.data?.status === "failed" && <Notice tone="danger">{jq.data.error}</Notice>}
        {o?.found && (o.has_suggested || pulled) && !create.data && <Btn icon="check" loading={create.isPending}
          onClick={() => create.mutate({ base_url: o.openai_base!, model: o.suggested })}>{t("Usar {{model}}", { model: o.suggested })}</Btn>}
      </Stack> : <Stack gap="xs">
        <TextField label={t("Endpoint (base URL)")} value={base} onChange={(e) => setBase(e.currentTarget.value)} />
        <PasswordField label={t("Clave de API")} value={key} onChange={(e) => setKey(e.currentTarget.value)} autoComplete="off" />
        <TextField label={t("Modelo")} placeholder={t("nombre del modelo de embeddings")} value={model} onChange={(e) => setModel(e.currentTarget.value)}
          description={t("El índice de esta instancia es de {{dim}} dimensiones: elige un modelo de ese tamaño. Con otro, tendrás que reindexar.", { dim: w.embedding.index_dim })} />
        <Group><Btn icon="check" disabled={!base || !model} loading={create.isPending} onClick={() => create.mutate({ base_url: base, model, api_key: key || undefined })}>{t("Probar y usar")}</Btn></Group>
      </Stack>}
      {create.data && (create.data.is_default
        ? <Notice tone="success">{t("{{model}} responde con {{dim}} dimensiones y ya es el motor en uso.", { model: create.data.model, dim: create.data.dim })}</Notice>
        : <Notice tone="warn" title={t("Añadido, pero no en uso")}>{t("{{model}} da {{dim}} dimensiones y el índice es de {{index}}. Para usarlo, pásate a él con «Reindexar» en Administración → Embeddings; con la memoria aún vacía tarda segundos.", { model: create.data.model, dim: create.data.dim, index: w.embedding.index_dim })}
          <Group mt={6}><Btn size="row" component={Link} to="/admin?seccion=embedding" icon="admin">{t("Embeddings")}</Btn></Group></Notice>)}
      <MutationError error={ollama.error ?? pull.error ?? create.error} />
    </Stack>
  );
}

/** The LLM that extracts facts, or the decider: a local Ollama or an OpenAI-compatible service, its model picked from the provider's list. */
function LlmStep({ w, kind }: { w: Wizard; kind: "llm" | "decision" }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const cur = kind === "llm" ? w.llm : w.decider;
  const [base, setBase] = useState(""); const [key, setKey] = useState(""); const [model, setModel] = useState("");
  const ollama = useMutation({ mutationFn: () => get<Ollama>("setup/ollama"), onSuccess: (o) => { if (o.openai_base) { setBase(o.openai_base); setModel(""); models.mutate(o.openai_base); } } });
  const models = useMutation({ mutationFn: (b: string) => send<{ models: string[]; error: string | null }>("POST", "llm-engines/models", { base_url: b, api_key: key || undefined }) });
  const path = kind === "llm" ? "llm-engines" : "decision-engines";
  // Added, then tested at once (issue 420): the LLM must return the structured output ingestion needs, the decider a letter with logprobs.
  // An engine that fails is kept, with the warning; «Next» runs the same check and does not pass the step.
  // One that passes becomes the engine in use, so a second try after a model that failed is the one «Next» checks.
  const check = useMutation({ mutationFn: async (e: { id: number; is_default: boolean }) => {
    const r = await send<EngineCheck>("POST", `${path}/${e.id}/test`);
    if (r.ok && !e.is_default) await send("POST", `${path}/${e.id}/default`);
    return r;
  }, onSettled: () => { qc.invalidateQueries({ queryKey: ["setup"] }); qc.invalidateQueries({ queryKey: [path] }); } });
  const create = useMutation({ mutationFn: () => send<{ id: number; is_default: boolean }>("POST", path, { name: `${model} · ${new URL(base).host}`, base_url: base, model, api_key: key || undefined, ...(kind === "llm" ? { small_model: "" } : { threshold: 0.8 }) }),
    onSuccess: (e) => { qc.invalidateQueries({ queryKey: ["setup"] }); qc.invalidateQueries({ queryKey: [path] }); check.mutate(e); } });
  let valid = false;
  try { valid = /^https?:/.test(new URL(base).protocol); } catch { /* not a URL yet */ }
  return (
    <Stack gap="sm">
      {cur.configured ? <Notice tone="success" title={t("En uso ahora")}>{cur.name ?? t("el de las variables de entorno")}</Notice>
        : <Notice tone={kind === "llm" ? "warn" : "info"}>{kind === "llm" ? t("Todavía no hay ninguno. Puedes saltar este paso, pero hasta que añadas uno las propuestas aprobadas no entrarán en la memoria, y el inicio te lo recordará.")
          : t("Todavía no hay ninguno. Sin decisor, cada propuesta espera a que la revise un curador.")}</Notice>}
      <Group gap="xs"><Btn icon="search" loading={ollama.isPending} onClick={() => ollama.mutate()}>{t("Usar Ollama en local")}</Btn>
        {ollama.data && !ollama.data.found && <Pill tone="warn">{t("No se encuentra")}</Pill>}</Group>
      <TextField label={t("Endpoint (base URL)")} placeholder="https://openrouter.ai/api/v1" /* i18n-ok: a URL */ value={base} onChange={(e) => setBase(e.currentTarget.value)} onBlur={() => valid && models.mutate(base)} />
      <PasswordField label={t("Clave de API")} description={t("Vacía para Ollama.")} value={key} onChange={(e) => setKey(e.currentTarget.value)} onBlur={() => valid && models.mutate(base)} autoComplete="off" />
      <ComboField label={t("Modelo")} data={models.data?.models ?? []} limit={50} value={model} onChange={setModel} placeholder={t("Elige uno o escribe el nombre")}
        description={kind === "llm" ? t("Para una memoria que vas a conservar, un modelo instruct de unos 14B o más (en Ollama, qwen2.5:14b-instruct) o uno pequeño y barato de un proveedor.") : undefined} />
      {models.data?.error && <Text size="xs" c="dimmed">{models.data.error}</Text>}
      <Group><Btn icon="plus" disabled={!valid || !model} loading={create.isPending || check.isPending} onClick={() => create.mutate()}>{t("Añadir")}</Btn>
        {check.isPending && <Text size="xs" c="dimmed">{t("Probando el modelo con una extracción de ejemplo…")}</Text>}</Group>
      {check.data && <EngineCheckNotice r={check.data} kind={kind} />}
      <MutationError error={ollama.error ?? create.error ?? check.error} />
    </Stack>
  );
}

type EngineCheck = { ok: boolean; ms: number; reply?: string; error?: string; warning?: string };

/** What the test of a just-added LLM or decider found: it works, it works with a warning, or it is kept but ingestion would fail. */
function EngineCheckNotice({ r, kind }: { r: EngineCheck; kind: "llm" | "decision" }) {
  const { t } = useTranslation();
  if (!r.ok) return <Notice tone="warn" title={t("Añadido, pero no pasa la prueba")}>{translateServer(r.error ?? "")}{" "}
    {kind === "llm" ? t("Puedes probar con otro modelo o saltar este paso; con este, «Siguiente» no lo da por hecho.") : t("Puedes probar con otro modelo o saltar este paso.")}</Notice>;
  if (r.warning) return <Notice tone="warn" title={t("Funciona, con un aviso")}>{translateServer(r.warning)}</Notice>;
  return <Notice tone="success">{kind === "llm" ? translateServer(r.reply ?? "") : t("Responde con una opción y su probabilidad: {{reply}}", { reply: r.reply })}</Notice>;
}

const slugOf =(name: string) => name.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 41);

function BrainStep({ w, pick }: { w: Wizard; pick: (slug: string) => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const [chosen, setChosen] = useState(w.brain ?? "");
  const [name, setName] = useState("");
  const create = useMutation({ mutationFn: () => send<Brain>("POST", "brains", { slug: slugOf(name), name: name.trim() }),
    onSuccess: (b) => { qc.invalidateQueries({ queryKey: ["brains"] }); setChosen(b.slug); pick(b.slug); setName(""); } });
  const list = brains.data ?? [];
  return (
    <Stack gap="sm">
      {list.length > 0 && <SelectField label={t("Usar un brain que ya existe")} data={list.map((b) => ({ value: b.slug, label: `${b.name}${b.read_only ? ` · ${t("solo lectura")}` : ""}` }))}
        value={chosen || null} onChange={(v) => { if (v) { setChosen(v); pick(v); } }} placeholder={t("Elige uno")} />}
      <Group align="flex-end" gap="xs">
        <TextField label={list.length ? t("O crea uno nuevo") : t("Nombre del brain")} placeholder={t("Infraestructura")} value={name} onChange={(e) => setName(e.currentTarget.value)}
          description={name ? t("Su identificador será «{{slug}}».", { slug: slugOf(name) }) : undefined} />
        <Btn icon="plus" disabled={slugOf(name).length < 2} loading={create.isPending} onClick={() => create.mutate()}>{t("Crear")}</Btn>
      </Group>
      {chosen && <Pill tone="success">{t("Brain del asistente: {{slug}}", { slug: chosen })}</Pill>}
      {list.find((b) => b.slug === chosen)?.read_only && <Notice tone="warn">{t("Es de solo lectura: tu agente podrá consultarlo, pero no proponer nada en él.")}</Notice>}
      <MutationError error={create.error} />
    </Stack>
  );
}

function TokenStep({ w, brain, pick }: { w: Wizard; brain: string | null; pick: (id: number, secret: string) => void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(t("Mi agente"));
  const [made, setMade] = useState<{ id: number; token: string } | null>(null);
  const create = useMutation({ mutationFn: () => send<{ id: number; token: string }>("POST", `brains/${brain}/tokens`, { name: name.trim(), role: "contributor", days: 90 }),
    onSuccess: (r) => { setMade(r); pick(r.id, r.token); } });
  if (!brain) return <Notice tone="warn">{t("Vuelve al paso anterior y elige un brain.")}</Notice>;
  return (
    <Stack gap="sm">
      {w.token_id && !made && <Notice tone="success">{t("El asistente ya creó un token para este brain. Puedes seguir con él, o crear otro.")}</Notice>}
      {!made ? <Group align="flex-end" gap="xs">
        <TextField label={t("Nombre del token")} description={t("Para reconocerlo después: el agente o el equipo que lo usa.")} value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Btn icon="plus" disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>{t("Crear token")}</Btn>
      </Group> : <Stack gap="xs">
        <Notice tone="warn" title={t("Cópialo ahora: es la única vez que se muestra.")}>{t("Rol Colaborador, válido 90 días. El paso siguiente ya lo lleva puesto en lo que copies.")}</Notice>
        <CodeBlock copy label={t("Token de API")}>{made.token}</CodeBlock>
      </Stack>}
      <MutationError error={create.error} />
    </Stack>
  );
}

function AgentStep({ w, secret }: { w: Wizard; secret: string }) {
  const { t } = useTranslation();
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const b = brains.data?.find((x) => x.slug === w.brain);
  if (!b) return <DataState query={brains} />;
  return (
    <Stack gap="sm">
      {w.agent_connected ? <Notice tone="success" title={t("La memoria está lista")}>{t("Tu agente ya ha hecho su primer recall. Pulsa «Terminar» para ir al inicio.")}</Notice>
        : <Text size="sm" c="dimmed" className="ms-measure">{t("Cuando tu agente haga su primer recall, este paso se pondrá en verde. Si prefieres conectarlo más tarde, pulsa «Terminar»: lo tienes en Administración → Conectar un agente.")}</Text>}
      <ConnectAgent brain={b} token={w.token_id ? { id: w.token_id, secret: secret || undefined } : undefined} untilRecall />
    </Stack>
  );
}
