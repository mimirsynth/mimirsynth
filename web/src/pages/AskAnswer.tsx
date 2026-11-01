import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";
import { Fragment, useRef, useState, type ReactNode } from "react";
import { ApiError, langHeaders } from "../api";
import { translateServer } from "../i18n";
import { Btn, EmptyState, ListCard, MutationError, Notice, Pill } from "../ui";

/** One numbered piece of evidence: what the answer cites as [F1], [E1] or [D1]. */
type Source = { ref: string; kind: "fact" | "episode" | "document"; id: string | number; text: string; title?: string; entity?: string;
  status?: string; origin?: string };
type Done = { citations: string[]; unknown: string[]; called: boolean; ms?: number };
const CITE = /\[([FED])(\d{1,3})\]/g;

/** Where a source leads: the fact's entity page, the episode in the Journal, the passage's document in Knowledge. Lent episodes and
 * documents live in another brain, so they have no link here. */
export function sourceLink(s: Source): string | null {
  if (s.kind === "fact") return s.entity ? `/entidad/${s.entity}${s.origin ? `?origen=${s.origin}` : ""}` : null;
  if (s.origin) return null;
  return s.kind === "episode" ? `/diario?episodio=${s.id}` : `/conocimiento?doc=${s.id}`;
}

/** Reads the NDJSON stream of `POST /answer`: one `sources` line, `delta` lines and a `done` (or `error`) line. */
async function streamAnswer(graph: string, body: unknown, on: (ev: Record<string, unknown>) => void, signal: AbortSignal) {
  const r = await fetch(`/api/brains/${graph}/answer`, { method: "POST", credentials: "include", signal,
    headers: { "Content-Type": "application/json", ...langHeaders() }, body: JSON.stringify(body) });
  if (!r.ok) {
    let m = r.statusText; try { m = (await r.json()).detail ?? m; } catch { /* sin cuerpo */ }
    throw new ApiError(r.status, translateServer(m));
  }
  const reader = r.body!.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n")) >= 0) { const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (line) on(JSON.parse(line)); }
  }
}

/** Ask → Answer (issue 126): a written answer from the recall, every claim cited to its evidence. */
export default function AskAnswer({ graph, query, facts, chunks }: { graph: string; query: string; facts: number; chunks: number }) {
  const { t } = useTranslation();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [text, setText] = useState("");
  const [done, setDone] = useState<Done | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const label = (ref: string) => {
    const n = ref.slice(1);
    return ref[0] === "F" ? t("hecho {{n}}", { n }) : ref[0] === "E" ? t("episodio {{n}}", { n }) : t("doc {{n}}", { n });
  };
  const go = async () => {
    abort.current?.abort();
    const ctl = new AbortController(); abort.current = ctl;
    setSources(null); setText(""); setDone(null); setError(null); setBusy(true);
    try {
      await streamAnswer(graph, { query, facts, chunks }, (ev) => {
        if (ev.type === "sources") setSources(ev.sources as Source[]);
        else if (ev.type === "delta") setText((x) => x + (ev.text as string));
        else if (ev.type === "done") setDone(ev as unknown as Done);
        else if (ev.type === "error") setError(new Error(translateServer(ev.detail as string)));
      }, ctl.signal);
    } catch (e) { if (!(e instanceof DOMException && e.name === "AbortError")) setError(e); }
    finally { setBusy(false); }
  };
  const byRef = new Map((sources ?? []).map((s) => [s.ref, s]));
  // The answer with each [F1]/[E1]/[D1] turned into a link to its source; a label that was not in the evidence is marked, not linked.
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CITE)) {
    const ref = `${m[1]}${Number(m[2])}`, s = byRef.get(ref), to = s && sourceLink(s);
    parts.push(<Fragment key={`t${m.index}`}>{text.slice(last, m.index)}</Fragment>);
    parts.push(!s ? <Pill key={`c${m.index}`} size="xs" tone="danger" title={t("Esta cita no estaba entre las pruebas: no lleva a ningún sitio.")}>{t("cita sin origen")}</Pill>
      : to ? <Link key={`c${m.index}`} to={to} className="ms-nolink" title={s.text}><Pill size="xs" tone="alt">{label(ref)}</Pill></Link>
      : <Pill key={`c${m.index}`} size="xs" tone="alt" title={`${s.text}${s.origin ? ` · ${s.origin}` : ""}`}>{label(ref)}</Pill>);
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(<Fragment key="end">{text.slice(last)}</Fragment>);
  const cited = new Set(done?.citations ?? []);
  return (
    <Stack gap="xs">
      <Group gap="xs">
        <Btn kind="primary" disabled={!query} loading={busy} onClick={() => void go()}>{t("Responder")}</Btn>
        {busy && <Btn kind="ghost" onClick={() => abort.current?.abort()}>{t("Parar")}</Btn>}
        {done?.ms !== undefined && <Text size="xs" c="dimmed">{t("{{ms}} ms", { ms: done.ms })}</Text>}
      </Group>
      <Text size="xs" c="dimmed">{t("Redacta una respuesta solo con lo que devuelve el recall y cita de dónde sale cada afirmación. Si no hay información, lo dice sin preguntar al modelo. Revisa las citas: el modelo puede equivocarse al resumir.")}</Text>
      <MutationError error={error} />
      {sources && (text ? <Notice tone="info" title={t("Respuesta")}><Text size="sm" className="ms-prose">{parts}</Text></Notice>
        : busy && <EmptyState>{t("Redactando…")}</EmptyState>)}
      {!!done?.unknown.length && <Text size="xs" c="dimmed">{t("El modelo citó {{refs}}, que no estaban entre las pruebas: esas citas no llevan a ningún sitio.", { refs: done.unknown.join(", ") })}</Text>}
      {!!sources?.length && <>
        <Title order={6} mt="xs">{t("Pruebas ({{n}})", { n: sources.length })}</Title>
        {sources.map((s) => {
          const to = sourceLink(s);
          return (
            <ListCard key={s.ref} invalid={s.status === "invalidated"}
              tags={<>{to ? <Link to={to} className="ms-nolink"><Pill size="xs" tone={cited.has(s.ref) ? "alt" : undefined}>{label(s.ref)}</Pill></Link>
                : <Pill size="xs" tone={cited.has(s.ref) ? "alt" : undefined}>{label(s.ref)}</Pill>}
                {s.origin && <Pill size="xs">{s.origin}</Pill>}{s.title && <Text size="xs" c="dimmed">{s.title}</Text>}</>}>{s.text}</ListCard>);
        })}
      </>}
    </Stack>
  );
}
