import { useTranslation } from "react-i18next";
import { Group, Text } from "@mantine/core";
import { Link } from "react-router-dom";
import { Fragment, useEffect, useRef, useState, type MutableRefObject, type ReactNode } from "react";
import { ApiError, fmtDay, langHeaders } from "../api";
import { translateServer } from "../i18n";
import { Block, Btn, CardLink, EmptyState, EntityChip, RelationWord, ListCard, Loading, MutationError, Notice, Pill, ViewBar } from "../ui";
import { loadAsk, saveAsk } from "./askSession";

/** One numbered piece of evidence: what the answer cites as [F1], [E1] or [D1]. */
type Superseded = { fact: string; invalid_at: string | null; replaced_by: { fact: string }[] }[];
type Source = { ref: string; kind: "fact" | "episode" | "document"; id: string | number; text: string; title?: string; entity?: string;
  status?: string; origin?: string; valid_at?: string | null; invalid_at?: string | null; replaces?: string; superseded?: Superseded;
  /** A fact's two ends and its relation, shown as Context shows them. */
  source?: string; target?: string; source_type?: string | null; target_type?: string | null; target_entity?: string; name?: string };
type Done = { citations: string[]; unknown: string[]; called: boolean; ms?: number };
const CITE = /\[([FED])(\d{1,3})\]/g;
type Kept = { asked: string; sources: Source[] | null; text: string; done: Done };

/** Where a source leads: the fact's entity page, the episode in the Journal, the passage's document in Knowledge. Lent episodes and
 * documents live in another brain, so they have no link here. */
const entityPage = (uuid: string, origin?: string) => `/entidad/${uuid}${origin ? `?origen=${origin}` : ""}`;
export function sourceLink(s: Source): string | null {
  if (s.kind === "fact") return s.entity ? entityPage(s.entity, s.origin) : null;
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

/** Ask → Answer (issue 126): a written answer from the recall, every claim cited to its evidence. Its view: a bar with what the mode
 *  does behind its «i» and the answer's status, the answer, then the evidence as blocks in the order Context shows them. */
/** `trigger`: each increment writes an answer to `query` (Ask owns the button and Ctrl/⌘+Enter, in the same place as «Buscar»).
 *  `answered`: the last increment acted on, kept by Ask so it outlives this view. Coming back to «Responder» mounts this again with a count
 *  already answered, which must not write by itself; a press made just before it mounted (Ctrl/⌘+Enter right after choosing the mode) must.
 *  `onBusy` tells Ask when it is writing. An answer to an earlier question says so. */
export default function AskAnswer({ graph, query, facts, chunks, trigger, answered, onBusy }:
  { graph: string; query: string; facts: number; chunks: number; trigger: number; answered: MutableRefObject<number>; onBusy?: (busy: boolean) => void }) {
  const { t } = useTranslation();
  // The last answer this tab wrote for this question, back on screen after leaving the page (or the mode) and coming back: see askSession.
  const [kept] = useState(() => { const k = loadAsk<Kept>(graph, "answer"); return k && query.trim() && k.asked === query.trim() ? k : null; });
  const [sources, setSources] = useState<Source[] | null>(() => kept?.sources ?? null);
  const [text, setText] = useState(() => kept?.text ?? "");
  const [done, setDone] = useState<Done | null>(() => kept?.done ?? null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const head = useRef<HTMLDivElement>(null);
  // When it finishes, the button that started it may have lost the focus (it was busy): give it to the answer's line, as Context does.
  useEffect(() => { if (!busy && asked !== null && (!document.activeElement || document.activeElement === document.body)) head.current?.focus(); }, [busy]);  // eslint-disable-line react-hooks/exhaustive-deps
  const [asked, setAsked] = useState<string | null>(() => kept?.asked ?? null);
  const abort = useRef<AbortController | null>(null);
  // A finished answer is kept for this tab; one cut short or failed is not.
  useEffect(() => { if (!busy && asked !== null && done && !error) saveAsk(graph, "answer", { asked, sources, text, done } satisfies Kept); }, [busy, done]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { onBusy?.(busy); }, [busy]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (trigger !== answered.current) { answered.current = trigger; if (query.trim()) void go(); } }, [trigger]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { abort.current?.abort(); onBusy?.(false); }, []);  // eslint-disable-line react-hooks/exhaustive-deps
  const evAnchor = (ref: string) => `ev-${ref}`;
  const citeAnchor = (ref: string) => `cita-${ref}`;
  const label = (ref: string) => {
    const n = ref.slice(1);
    return ref[0] === "F" ? t("hecho {{n}}", { n }) : ref[0] === "E" ? t("episodio {{n}}", { n }) : t("doc {{n}}", { n });
  };
  const go = async () => {
    abort.current?.abort();
    const ctl = new AbortController(); abort.current = ctl;
    setSources(null); setText(""); setDone(null); setError(null); setBusy(true); setAsked(query.trim());
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
  const first = new Set<string>();  // the sources whose first citation has been placed: that one carries the id «Volver a la cita» goes to
  for (const m of text.matchAll(CITE)) {
    const ref = `${m[1]}${Number(m[2])}`, s = byRef.get(ref);
    const id = s && !first.has(ref) ? (first.add(ref), citeAnchor(ref)) : undefined;
    parts.push(<Fragment key={`t${m.index}`}>{text.slice(last, m.index)}</Fragment>);
    parts.push(!s ? <Pill key={`c${m.index}`} tone="danger" title={t("Esta cita no estaba entre las pruebas: no lleva a ningún sitio.")}>{t("cita sin origen")}</Pill>
      : <CardLink key={`c${m.index}`} id={id} to={evAnchor(ref)} className="ms-cite" title={`${s.text}${s.origin ? ` · ${s.origin}` : ""}`}>{label(ref)}</CardLink>);
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(<Fragment key="end">{text.slice(last)}</Fragment>);
  const cited = new Set(done?.citations ?? []);
  const help = t("Redacta una respuesta solo con lo que devuelve el recall y cita de dónde sale cada afirmación. Si no hay información, lo dice sin preguntar al modelo. Revisa las citas: el modelo puede equivocarse al resumir.");
  // The evidence as Context shows the recall: current facts, then those no longer true, then fragments and passages, with the same
  // warning on a fragment or passage that states something no longer true. The answer cites them by the same labels either way.
  const all = sources ?? [];
  const groups: [string, Source[]][] = [
    [t("Hechos vigentes"), all.filter((s) => s.kind === "fact" && s.status !== "invalidated")],
    [t("Hechos que dejaron de ser ciertos"), all.filter((s) => s.kind === "fact" && s.status === "invalidated")],
    [t("Fragmentos de episodios"), all.filter((s) => s.kind === "episode")],
    [t("Pasajes de documentos"), all.filter((s) => s.kind === "document")],
  ];
  const notice = (sup?: Superseded) => (sup?.length ? <>
    <Pill tone="warn">{t("Puede estar superado")}</Pill>
    {sup.map((x, i) => (
      <div key={i}>
        <div>{t("Dejó de ser cierto el {{date}}:", { date: fmtDay(x.invalid_at) })} «{x.fact}»</div>
        {x.replaced_by.length > 0 && <div>{t("Ahora:")} {x.replaced_by.map((r) => `«${r.fact}»`).join(" · ")}</div>}
      </div>))}
  </> : undefined);
  const when = (s: Source) => (s.kind !== "fact" ? undefined : s.invalid_at ? `${fmtDay(s.valid_at)} → ${fmtDay(s.invalid_at)}` : s.valid_at ? t("desde {{date}}", { date: fmtDay(s.valid_at) }) : undefined);
  return (
    <>
      {/* The status is a live region there from the start and only its text changes, so each answer is announced: said while writing and
          again when done (the answer itself is not a live region). The bar takes the focus when it finishes. */}
      <div ref={head} tabIndex={-1} className="ms-ask-head">
        <ViewBar title={t("Responder")} help={help}
          meta={<><span role="status">{asked === null ? "" : busy ? t("Redactando la respuesta a «{{q}}»…", { q: asked }) : t("Respuesta a «{{q}}» lista.", { q: asked })}</span>
            {done?.ms !== undefined && <span className="ms-data">{` · ${t("{{ms}} ms", { ms: done.ms })}`}</span>}
            {asked !== null && asked !== query.trim() && <> <Pill tone="warn">{t("De una pregunta anterior")}</Pill></>}</>}
          actions={busy && <Btn kind="ghost" onClick={() => abort.current?.abort()}>{t("Dejar de redactar")}</Btn>} />
      </div>
      {/* before the first answer, what this mode does */}
      {asked === null && !busy && <EmptyState>{help}</EmptyState>}
      <MutationError error={error} />
      {sources && text ? <section aria-label={t("Respuesta")} className="ms-answer"><ListCard title={t("Respuesta")}><span className="ms-answer-prose">{parts}</span></ListCard></section>
        : busy && <Loading label={t("Redactando…")} />}
      {!!done?.unknown.length && <Notice tone="warn">{t("El modelo citó {{refs}}, que no estaban entre las pruebas: esas citas no llevan a ningún sitio.", { refs: done.unknown.join(", ") })}</Notice>}
      {!!sources?.length && <Block title={t("Pruebas")} count={sources.length}>
        {groups.filter(([, list]) => list.length).map(([head, list]) => (
          <Block key={head} title={head} count={list.length}>
            {list.map((s) => {
              const ends = s.kind === "fact" && !!s.source && !!s.target;  // with its ends, a fact leads to their pages through the chips
              const to = ends ? null : sourceLink(s);
              const isCited = cited.has(s.ref);
              const back = isCited && first.has(s.ref);
              return (
                <ListCard key={s.ref} anchor={evAnchor(s.ref)} invalid={s.status === "invalidated"} notice={notice(s.superseded)} meta={when(s)}
                  title={ends ? undefined : s.title} note={s.replaces ? <>{t("Sustituye a")} «{s.replaces}»</> : undefined}
                  tags={<>
                    <Pill tone={isCited ? "alt" : undefined}>{isCited ? t("{{ref}} · citado", { ref: label(s.ref) }) : label(s.ref)}</Pill>
                    {s.origin && <Pill>{s.origin}</Pill>}
                    {ends && <>
                      <EntityChip name={s.source ?? ""} type={s.source_type} to={s.entity ? entityPage(s.entity, s.origin) : undefined} />
                      {s.name && <RelationWord name={s.name} />}
                      <EntityChip name={s.target ?? ""} type={s.target_type} to={s.target_entity ? entityPage(s.target_entity, s.origin) : undefined} />
                    </>}</>}
                  actions={(to || back) ? <Group gap="md">
                    {back && <CardLink to={citeAnchor(s.ref)}>{t("Volver a la cita")}</CardLink>}
                    {to && <Link to={to} className="ms-cardlink">{s.kind === "episode" ? t("Abrir el episodio en el Diario") : s.kind === "document" ? t("Abrir el documento en Conocimiento") : t("Abrir la entidad")}</Link>}
                  </Group> : undefined}>{s.text}</ListCard>);
            })}
          </Block>))}
      </Block>}
    </>
  );
}
