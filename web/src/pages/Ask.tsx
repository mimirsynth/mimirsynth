
import { useTranslation } from "react-i18next";
import { Group, Stack, Text, Title } from "@mantine/core";
import { Btn, NumberField, Pill, Segments, TextArea, Toggle, MutationError, Page, PageHeader, FillArea, ListCard, CodeBlock, CopyBtn, Tabs, useTabParam, CardLink } from "../ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { Brain, fmtDay, fmtNum, get, send } from "../api";
import RefQueries, { RefQueryForm, type Item, type RefQuery } from "./RefQueries";
import RecallQuality from "./RecallQuality";
import AskAnswer from "./AskAnswer";
import AskAllBrains, { type AllBrainsResult } from "./AskAllBrains";
import { EmptyState, EntityChip, Form, humanRelation, Toolbar } from "../ui";
import { askParams, loadAsk, saveAsk } from "./askSession";

type Fact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; name: string; source: string; target: string; source_uuid: string; target_uuid: string; source_type?: string | null; target_type?: string | null; score?: number; similarity?: number | null; origin?: string; replaces?: string };
/** Entity page of a fact's end; a lent fact opens it in the brain that lends it. */
const entityLink = (uuid: string, origin?: string) => `/entidad/${uuid}${origin ? `?origen=${origin}` : ""}`;
type Superseded = { uuid: string; fact: string; invalid_at: string | null; replaced_by: { uuid: string; fact: string }[] }[];
type Chunk = { id: number; origin?: string; name: string; text: string; valid_at: string | null; score: number; similarity?: number | null; rrf: number; superseded?: Superseded };
type Passage = { document_id: number; chunk_idx: number; title: string; text: string; similarity: number; origin?: string; superseded?: Superseded;
  source_updated_at?: string | null; last_seen_at?: string | null; heading_path?: string | null; page?: number | null };
/** A passage's place in its document: the title, the heading it sits under and its page, so two passages of one document are told apart.
 *  The heading path often starts with the document's own title (its first heading), which is not repeated. */
const passageTitle = (p: Passage) => {
  const path = (p.heading_path ?? "").split(" › ").filter((h, i) => h && !(i === 0 && h === p.title)).join(" › ");
  return `${p.title}${path ? ` › ${path}` : ""}${p.page ? ` (p. ${p.page})` : ""}`;
};
type Res = { recall_id?: string; query: string; facts: Fact[]; chunks: Chunk[]; documents?: Passage[]; documents_state?: string; context: string; index: boolean; min_similarity?: number; ms: Record<string, number> };
/** «0.42», or null for what joins the recall by its link to a fact no longer true rather than by its closeness to the question. */
const simValue = (x: { similarity?: number | null; score?: number }) => { const v = x.similarity ?? x.score; return typeof v === "number" ? fmtNum(v, 2) : null; };
type Mark = "expect" | "avoid";
const KEYS = /Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘+Enter" : "Ctrl+Enter";
// A touch screen with no keyboard to hand: the button does not offer a shortcut it cannot use.
const TOUCH = typeof window !== "undefined" && !!window.matchMedia?.("(hover: none) and (pointer: coarse)").matches;
type Rating = "useful" | "irrelevant" | "incorrect";
type Scope = "brain" | "all";
/** What the recall left on screen, kept for this tab so Back restores it: see askSession. */
type Kept = { q: string; facts: number; chunks: number; data: Res; marks: Record<string, { mark: Mark; item: Item }>; rated: Record<string, Rating>; marking: boolean; notes?: Record<string, string> };
const SCOPE_KEY = "mimirsynth.askScope";  // the last scope chosen, per browser; a convenience, Ask works the same without it
const storedScope = (): Scope => { try { return localStorage.getItem(SCOPE_KEY) === "all" ? "all" : "brain"; } catch { return "brain"; } };

export default function Ask({ graph, role }: { graph: string; role: string }) {
  const { t } = useTranslation();
  // The question and its limits come from the address («Open in Ask» from «All my brains», or Back after leaving the page), and a search
  // or an answer writes them there: so Back, a reload or a copied link come back to the same question.
  const [start] = useState(askParams);
  const [q, setQ] = useState(start.q);
  // Scope (issue 186): this brain, or the same search in every brain the person can read. A link may set it (`?alcance=`); the choice
  // is then remembered in the browser. With a single brain there is nothing to choose.
  const [params, setParams] = useSearchParams();
  const brains = useQuery({ queryKey: ["brains"], queryFn: () => get<Brain[]>("brains") });
  const several = (brains.data?.length ?? 0) > 1;
  const asked = params.get("alcance");
  const [chosen, setChosen] = useState<Scope>(() => (asked === "all" || asked === "brain" ? asked : storedScope()));
  const scope: Scope = several ? chosen : "brain";
  const setScope = (v: Scope) => {
    setChosen(v);
    try { localStorage.setItem(SCOPE_KEY, v); } catch { /* sin almacenamiento */ }
    const n = new URLSearchParams(params); n.delete("alcance"); setParams(n, { replace: true });
  };
  useEffect(() => { if (asked === "all" || asked === "brain") setScope(asked); }, [asked]);  // eslint-disable-line react-hooks/exhaustive-deps
  const [nf, setNf] = useState(start.facts); const [nc, setNc] = useState(start.chunks);
  // What this tab last had on screen for this question, if anything: the recall, its ratings and the marks not yet saved.
  const [kept, setKept] = useState<Kept | null>(() => {
    const k = start.q ? loadAsk<Kept>(graph, "context") : null;
    return k && k.q === start.q && k.facts === start.facts && k.chunks === start.chunks ? k : null;
  });
  const [marks, setMarks] = useState<Record<string, { mark: Mark; item: Item }>>(() => kept?.marks ?? {});
  const [save, setSave] = useState<RefQuery | null>(null);
  const [marking, setMarking] = useState(() => kept?.marking ?? false);
  const [answerTrigger, setAnswerTrigger] = useState(0); const [answering, setAnswering] = useState(false);
  const answered = useRef(0);  // the last press AskAnswer acted on: coming back to «Responder» must not write again by itself
  const resultsHead = useRef<HTMLDivElement>(null);  // «Debe salir / Sobra» show only while building a reference query
  const [tab, setTab] = useTabParam("preguntar");
  const [mode, setMode] = useTabParam("contexto", "modo");   // «Responder» writes an answer with citations (issue 126); «Contexto» shows the recall
  const status = useQuery({ queryKey: ["index", graph], queryFn: () => get<{ enabled: boolean; chunks: number; episodes: number }>("index/status", { graph }) });
  const [rated, setRated] = useState<Record<string, Rating>>(() => kept?.rated ?? {});
  const [rateNote, setRateNote] = useState<Record<string, ReactNode>>({});  // what a rating did, said on its own card
  const [notes, setNotes] = useState<Record<string, string>>(() => kept?.notes ?? {});  // what «Incorrecto» said was wrong, shown on its card
  // «Incorrecto» on a fact proposes its correction: first it asks what is wrong, on the card, so the curator has something to decide on.
  const [wrong, setWrong] = useState<{ key: string; note: string } | null>(null);
  const focusWrong = (key: string) => document.getElementById(`ms-wrong-${key}`)?.focus();
  const limits = useRef({ facts: nf, chunks: nc });  // those of the search on screen, kept with it
  const run = useMutation({ mutationFn: () => { limits.current = { facts: nf, chunks: nc }; return send<Res>("POST", `brains/${graph}/recall`, { query: q, facts: nf, chunks: nc }); }, onMutate: () => setKept(null),
    onSuccess: () => { setMarks({}); setRated({}); setRateNote({}); setNotes({}); setWrong(null); } });
  const r = run.data ?? kept?.data;  // the recall on screen: this search's, or the one kept for this question
  /** The question and limits into the address, replacing the entry: the page stays one step of Back. Defaults are left out. */
  const remember = () => setParams((p) => {
    const n = new URLSearchParams(p);
    n.set("q", q.trim());
    if (nf !== 8) n.set("hechos", String(nf)); else n.delete("hechos");
    if (nc !== 4) n.set("fragmentos", String(nc)); else n.delete("fragmentos");
    return n;
  }, { replace: true });
  // The open brain pays for the query's embedding in the AI consumption (issue 176).
  const searchAll = useMutation({ mutationFn: () => send<AllBrainsResult>("POST", "search", { query: q, facts: nf, chunks: nc, brain: graph }) });
  const search = () => { if (!q.trim()) return; if (scope === "all") searchAll.mutate(); else run.mutate(); };
  // The mode as the address has it now, not as this render saw it: the router re-renders in a transition, so Ctrl/⌘+Enter right after
  // choosing «Responder» can still run in a render that shows «Contexto».
  const viewNow = () => scope === "all" ? "contexto" : new URLSearchParams(window.location.search).get("modo") ?? "contexto";
  const primary = () => { if (!q.trim()) return; remember(); if (viewNow() === "contexto") search(); else setAnswerTrigger((n) => n + 1); };
  // The button that had the focus is disabled while it works, so the focus falls to the page: give it to the results instead.
  useEffect(() => {
    if (!run.data) return;
    const head = resultsHead.current;
    if (!document.activeElement || document.activeElement === document.body) head?.focus({ preventScroll: true });
    // when they start low on the screen (a phone, under the controls), the results are brought up to its top
    if (head && head.getBoundingClientRect().top > window.innerHeight * 0.6) {
      head.scrollIntoView({ block: "start", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
  }, [run.data]);
  const shownGraph = useRef(graph);
  useEffect(() => { if (graph !== shownGraph.current) { shownGraph.current = graph; run.reset(); setKept(null); } }, [graph]);  // eslint-disable-line react-hooks/exhaustive-deps -- results of another brain are not this one's
  // Valorar lo que devolvió el recall (útil, irrelevante, incorrecto): alimenta la pestaña Calidad.
  const rate = useMutation({
    mutationFn: (a: { key: string; kind: string; id: string; rating: Rating; note?: string }) => send<{ proposal_id: number | null; recorded_only: boolean; existing?: boolean }>("POST", `brains/${graph}/recall/${r?.recall_id}/ratings`, { kind: a.kind, id: a.id, rating: a.rating, note: a.note ?? "" }),
    onSuccess: (r, a) => {
      setRated((m) => ({ ...m, [a.key]: a.rating }));
      // the note goes with a new correction; one already in the queue keeps the note it was proposed with, so this one is not shown as sent
      setNotes(({ [a.key]: _, ...m }) => (a.rating === "incorrect" && a.note && r.proposal_id && !r.existing ? { ...m, [a.key]: a.note } : m));
      if (a.rating === "incorrect") { setWrong(null); focusWrong(a.key); }
      const said = a.rating === "useful" ? t("Valorado como útil.") : a.rating === "irrelevant" ? t("Valorado como irrelevante.") : t("Valorado como incorrecto.");
      // The proposal a rating «incorrecto» created stays when the rating changes: a curator decides it, and saying otherwise would lie.
      const proposal = r.proposal_id && (canSync ? <Link to="/propuestas?estado=pending&tipo=correction">{t("propuesta #{{id}}", { id: r.proposal_id })}</Link>
        : t("propuesta #{{id}}", { id: r.proposal_id }));
      const then = r.proposal_id
        ? (a.rating === "incorrect" && !r.existing   // rated again: the one already in the queue, not a new one
          ? <>{t("Se ha propuesto su corrección:")} {proposal}.{!canSync && <> {t("La decide un curador.")}</>}</>
          : <>{t("La corrección que se propuso antes sigue en la cola:")} {proposal}.{canSync ? <> {t("Si ya no hace falta, recházala allí.")}</> : <> {t("La decide un curador.")}</>}</>)
        : r.recorded_only ? t("Con tu rol no se propone la corrección: la verá un curador en Calidad.") : null;
      setRateNote((m) => ({ ...m, [a.key]: then ? <>{said} {then}</> : said }));
    } });
  const unrate = useMutation({
    mutationFn: (a: { key: string; kind: string; id: string }) => send<{ removed: boolean; proposal_id: number | null }>("DELETE", `brains/${graph}/recall/${r?.recall_id}/ratings`, undefined, { kind: a.kind, id: a.id }),
    onSuccess: (res, a) => {
      setRated(({ [a.key]: _, ...m }) => m);
      setNotes(({ [a.key]: _, ...m }) => m);
      const proposal = res.proposal_id && (canSync ? <Link to="/propuestas?estado=pending&tipo=correction">{t("propuesta #{{id}}", { id: res.proposal_id })}</Link>
        : t("propuesta #{{id}}", { id: res.proposal_id }));
      setRateNote((m) => ({ ...m, [a.key]: res.proposal_id
        ? <>{t("Valoración retirada.")} {t("La corrección que se propuso antes sigue en la cola:")} {proposal}.{canSync ? <> {t("Si ya no hace falta, recházala allí.")}</> : <> {t("La decide un curador.")}</>}</>
        : t("Valoración retirada.") }));
    } });
  const canPropose = ["contributor", "curator", "admin", "owner"].includes(role);
  const sendWrong = () => {
    if (!wrong?.note.trim()) return;
    const [kind, id] = wrong.key.startsWith("f:") ? ["fact", wrong.key.slice(2)] : ["", ""];
    if (kind) rate.mutate({ key: wrong.key, kind, id, rating: "incorrect", note: wrong.note.trim() });
  };
  // Rating feeds Quality and is saved at once; «Incorrecto» also proposes a correction, so it stands apart, in the danger colour. A word
  // before each group says which one it is: the marks for a reference query look the same and do something else.
  const rateBtns = (key: string, kind: string, id: string, canIncorrect = true) => r?.recall_id && <Group gap={4} role="group" aria-label={t("Valorar")}>
    <Text size="xs" c="dimmed" className="ms-ask-actlabel" aria-hidden="true">{t("Valorar")}</Text>
    {(["useful", "irrelevant"] as Rating[]).map((v) => (
      <Btn key={v} size="row" kind="ghost" aria-pressed={rated[key] === v} icon={rated[key] === v ? "check" : undefined}
        title={rated[key] === v ? t("Pulsa otra vez para retirar la valoración") : undefined}
        onClick={() => (rated[key] === v ? unrate.mutate({ key, kind, id }) : rate.mutate({ key, kind, id, rating: v }))}>
        {v === "useful" ? t("Útil") : t("Irrelevante")}</Btn>))}
    {canIncorrect && <><span className="ms-ask-sep" aria-hidden="true" />
      <Btn size="row" kind="ghost" className="ms-ask-wrong" aria-pressed={rated[key] === "incorrect"} icon={rated[key] === "incorrect" ? "check" : undefined}
        aria-expanded={canPropose && rated[key] !== "incorrect" ? wrong?.key === key : undefined} id={`ms-wrong-${key}`}
        title={rated[key] === "incorrect" ? t("Pulsa otra vez para retirar la valoración") : undefined}
        onClick={() => (rated[key] === "incorrect" ? unrate.mutate({ key, kind, id })
          : canPropose ? setWrong(wrong?.key === key ? null : { key, note: "" }) : rate.mutate({ key, kind, id, rating: "incorrect" }))}>{t("Incorrecto")}</Btn></>}
  </Group>;
  // A card's actions and, under them, what its rating did (a live region there from the start, so the result is announced).
  const cardActions = (what: string, key: string, kind: string, id: string, item: Item, canIncorrect: boolean) => (
    <Stack gap={4}>
      {/* One stop for Tab per card (the arrows move inside): with 13 cards of 3 to 5 buttons each, Tab no longer walks 50 buttons. */}
      <Toolbar className="ms-ask-actions" label={actionsLabel(what)}>{rateBtns(key, kind, id, canIncorrect)}{markBtns(key, item)}</Toolbar>
      {wrong?.key === key && <div className="ms-ask-wrongform"><Form onSubmit={sendWrong}>
        <TextArea label={t("¿Qué está mal?")} description={t("Lo lee el curador que decide la corrección: qué dice mal el hecho y, si lo sabes, qué es lo cierto.")}
          autosize minRows={2} maxLength={500} autoFocus value={wrong.note} onChange={(e) => setWrong({ key, note: e.currentTarget.value })}
          onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); setWrong(null); focusWrong(key); } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendWrong(); } }} />
        <Group gap="xs" mt={6}>
          <Btn size="row" kind="danger" type="submit" disabled={!wrong.note.trim()} loading={rate.isPending}>{t("Proponer corrección")}</Btn>
          <Btn size="row" kind="ghost" onClick={() => { setWrong(null); focusWrong(key); }}>{t("Cancelar")}</Btn>
        </Group>
      </Form></div>}
      {rated[key] === "incorrect" && notes[key] && <Text size="xs" className="ms-ask-sentnote">{t("Tu nota: «{{note}}»", { note: notes[key] })}</Text>}
      {r?.recall_id && <Text size="xs" c="dimmed" role="status">{rateNote[key] ?? ""}</Text>}
    </Stack>);
  const view = scope === "all" ? "contexto" : mode;  // across brains there is no written answer: it needs one brain's recall
  const sync = useMutation({ mutationFn: () => send<any>("POST", `brains/${graph}/index/sync`), onSuccess: () => status.refetch() });
  const canSync = ["curator", "admin", "owner"].includes(role);
  const sim = (x: { similarity?: number | null; score?: number }) => { const v = simValue(x); return v === null ? null : `${t("sim")} ${v}`; };
  // Every card of the result has an anchor, so what replaces what reads as a link between the two cards (issue: critique of Ask).
  const factAnchor = (origin: string | undefined, uuid: string) => `hecho-${origin ?? ""}-${uuid}`;
  const chunkAnchor = (c: Chunk) => `fragmento-${c.origin ?? ""}-${c.id}`;
  const passageAnchor = (p: Passage) => `pasaje-${p.origin ?? ""}-${p.document_id}-${p.chunk_idx}`;
  /** «fact», a link to its card when it is in the result. */
  const factRef = (origin: string | undefined, uuid: string, text: string) => r?.facts.some((x) => x.uuid === uuid && x.origin === origin)
    ? <>«<CardLink to={factAnchor(origin, uuid)}>{text}</CardLink>»</> : <>«{text}»</>;
  /** The fragments and passages of the result that state a fact no longer true. */
  const statedBy = (f: Fact) => [...(r?.chunks ?? []).map((c) => ({ origin: c.origin, name: c.name, anchor: chunkAnchor(c), gone: c.superseded })),
    ...(r?.documents ?? []).map((p) => ({ origin: p.origin, name: p.title, anchor: passageAnchor(p), gone: p.superseded }))]
    .filter((x) => x.origin === f.origin && x.gone?.some((s) => s.uuid === f.uuid));
  const current = r?.facts.filter((f) => f.status !== "invalidated") ?? [];
  const gone = r?.facts.filter((f) => f.status === "invalidated") ?? [];
  /** The sentence under a fact: what it replaces, or, for one no longer true, what replaced it and what in the result states it. */
  const factNote = (f: Fact) => {
    if (f.status !== "invalidated") {
      if (!f.replaces) return undefined;
      const old = gone.find((g) => g.origin === f.origin && g.fact === f.replaces);
      return <>
        <div>{t("Sustituye a")} {old ? factRef(old.origin, old.uuid, old.fact) : <>«{f.replaces}»</>}</div>
        {simValue(f) === null && <div className="ms-ask-why">{t("Está aquí por esa sustitución, no por parecerse a la pregunta.")}</div>}
      </>;
    }
    const now = current.filter((c) => c.origin === f.origin && c.replaces === f.fact);
    const by = statedBy(f);
    if (!now.length && !by.length) return undefined;
    return <>
      {now.length > 0 && <div>{t("Ahora:")} {now.map((c, i) => <Fragment key={c.uuid}>{i ? " · " : ""}{factRef(c.origin, c.uuid, c.fact)}</Fragment>)}</div>}
      {by.length > 0 && <div>{t("Lo dice:")} {by.map((x, i) => <Fragment key={x.anchor}>{i ? " · " : ""}«<CardLink to={x.anchor}>{x.name}</CardLink>»</Fragment>)}</div>}
      {simValue(f) === null && by.length > 0 && <div className="ms-ask-why">{t("Está aquí porque lo afirma ese texto, no por parecerse a la pregunta.")}</div>}
    </>;
  };
  const validity = (f: Fact) => (f.invalid_at ? `${fmtDay(f.valid_at)} → ${fmtDay(f.invalid_at)}` : t("desde {{date}}", { date: fmtDay(f.valid_at) }));
  // Each result's place, as the agent reads them in the injected context: one numbering across the sections, facts first (current,
  // then no longer true), then fragments, then passages. Under each heading, what decides the order inside it.
  const rank = (n: number) => t("n.º {{n}}", { n });
  const pulledIn = (list: Fact[]) => list.some((f) => simValue(f) === null);
  const orderNote = (text: string) => <Text size="xs" c="dimmed" className="ms-ask-order">{text}</Text>;
  // A marked card says so in words at its top, where a list is scanned; its border is left to the focus.
  const markPill = (key: string) => marking && marks[key]
    ? <Pill size="xs" tone={marks[key].mark === "expect" ? "success" : "warn"}>{marks[key].mark === "expect" ? t("Marcado: debe salir") : t("Marcado: sobra")}</Pill> : undefined;
  // a similarity within 0,05 of the threshold: what a small change of threshold would drop
  const edge = (x: { similarity?: number | null; score?: number }) => {
    const v = x.similarity ?? x.score, min = r?.min_similarity;
    return typeof v === "number" && !!min && v < min + 0.05 ? ` · ${t("en el límite del umbral")}` : "";
  };
  const factCard = (f: Fact, i: number, list: Fact[]) => (
    <ListCard key={`${f.origin ?? ""}-${f.uuid}`} anchor={factAnchor(f.origin, f.uuid)} invalid={f.status === "invalidated"} note={factNote(f)} aside={markPill(`f:${f.uuid}`)}
      actions={cardActions(f.fact, `f:${f.uuid}`, "fact", f.uuid, { text: f.fact, kind: "fact" }, !f.origin)}
      tags={<>{f.origin && <Pill size="xs" tone="alt">{f.origin}</Pill>}<EntityChip name={f.source} type={f.source_type} to={entityLink(f.source_uuid, f.origin)} />
        <Text size="xs" c="dimmed" title={f.name}>{humanRelation(f.name)}</Text><EntityChip name={f.target} type={f.target_type} to={entityLink(f.target_uuid, f.origin)} />
        <span className="ms-listcard-meta ms-data ms-ask-inlinemeta">{`${rank(i + 1 + (list === gone ? current.length : 0))} · ${sim(f) ?? t("sin similitud")} · ${validity(f)}`}</span></>}>{f.fact}</ListCard>);
  // Marcar un resultado como «debe salir» o «sobra» para guardarla como consulta de referencia. Se guarda el principio del texto.
  const toggle = (key: string, mark: Mark, item: Item) => setMarks((m) => {
    const n = { ...m };
    if (n[key]?.mark === mark) delete n[key]; else n[key] = { mark, item: { ...item, text: item.text.slice(0, 200) } };
    return n;
  });
  // Marks are kept here until «Guardar como consulta de referencia»; the pressed one shows a check, like a rating.
  const markBtns = (key: string, item: Item) => canSync && marking && <Group gap={4} role="group" aria-label={t("Consulta de referencia")}>
    <Text size="xs" c="dimmed" className="ms-ask-actlabel" aria-hidden="true">{t("Consulta de referencia")}</Text>
    <Btn size="row" kind="ghost" aria-pressed={marks[key]?.mark === "expect"} icon={marks[key]?.mark === "expect" ? "check" : undefined} onClick={() => toggle(key, "expect", item)}>{t("Debe salir")}</Btn>
    <Btn size="row" kind="ghost" aria-pressed={marks[key]?.mark === "avoid"} icon={marks[key]?.mark === "avoid" ? "check" : undefined} onClick={() => toggle(key, "avoid", item)}>{t("Sobra")}</Btn>
  </Group>;
  // A fragment or a passage that states something no longer true (issues 282 and 286): the mark first, then what stopped being true and
  // what is true now, before its text, so it is not read as current.
  const supersededNotice = (origin: string | undefined, sup?: Superseded) => (sup?.length ? <>
    <Pill size="xs" tone="warn">{t("Puede estar superado")}</Pill>
    {sup.map((s) => (
      <div key={s.uuid}>
        <div>{t("Dejó de ser cierto el {{date}}:", { date: fmtDay(s.invalid_at) })} {factRef(origin, s.uuid, s.fact)}</div>
        {s.replaced_by.length > 0 && <div>{t("Ahora:")} {s.replaced_by.map((x, i) => <Fragment key={x.uuid}>{i ? " · " : ""}{factRef(origin, x.uuid, x.fact)}</Fragment>)}</div>}
      </div>))}
  </> : undefined);
  const actionsLabel = (what: string) => t("Acciones sobre «{{what}}»", { what: what.length > 60 ? `${what.slice(0, 60)}…` : what });
  const marked = Object.values(marks);
  // Kept for this tab as it changes, so leaving for an entity and coming back with Back finds it as it was (the notes under the ratings
  // are not kept: the pressed button says the rating).
  useEffect(() => {
    if (run.data) saveAsk(graph, "context", { q: run.data.query, ...limits.current, data: run.data, marks, rated, marking, notes } satisfies Kept);
    else if (kept) saveAsk(graph, "context", { ...kept, marks, rated, marking, notes } satisfies Kept);
  }, [run.data, kept, marks, rated, marking, notes]);  // eslint-disable-line react-hooks/exhaustive-deps
  // Marks not saved as a reference query are kept in this tab; closing it or leaving the app would lose them, so the browser asks first.
  const unsaved = marking && marked.length > 0;
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);
  const toRef = (): RefQuery => ({ query: r?.query ?? q, expect: marked.filter((m) => m.mark === "expect").map((m) => m.item), avoid: marked.filter((m) => m.mark === "avoid").map((m) => m.item),
    docs: null, note: "" });
  const busyNow = view === "contexto" ? run.isPending || searchAll.isPending : answering;
  const ask = (
    <Stack gap="xs">
      <TextArea autosize minRows={2} label={t("Pregunta")} placeholder={t("¿Dónde está Nextcloud ahora?")} value={q} onChange={(e) => setQ(e.currentTarget.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && q.trim()) { e.preventDefault(); primary(); } }} />
      <Group gap="md" align="flex-end">
        {several && <Segments label={t("Alcance")} value={scope} onChange={(v) => setScope(v as Scope)}
          data={[{ value: "brain", label: t("Este brain") }, { value: "all", label: t("Todos mis brains") }]} />}
        {scope === "brain" && <Segments label={t("Modo")} value={mode} onChange={(v) => setMode(v)}
          data={[{ value: "responder", label: t("Responder") }, { value: "contexto", label: t("Contexto") }]} />}
      </Group>
      {scope === "all" && <Text size="xs" c="dimmed">{t("La misma búsqueda en todos los brains que puedes leer, con tu rol en cada uno y sin federación. La respuesta redactada, las valoraciones y guardar como consulta de referencia solo están en «Este brain»: los resultados mezclan brains distintos.")}</Text>}
      <Group align="flex-end">
        <NumberField size="xs" label={t("Hechos")} value={nf} min={0} max={30} onChange={(v) => setNf(Number(v) || 0)} w={80} />
        <NumberField size="xs" label={t("Fragmentos")} value={nc} min={0} max={15} onChange={(v) => setNc(Number(v) || 0)} w={100} />
        {/* while it works the button says so in words, instead of a spinner in place of its label */}
        <Btn kind="primary" disabled={!q.trim() || busyNow} onClick={primary}>
          {busyNow ? (view === "contexto" ? t("Buscando…") : t("Redactando…"))
            : view === "contexto" ? (TOUCH ? t("Buscar") : t("Buscar ({{keys}})", { keys: KEYS })) : (TOUCH ? t("Responder") : t("Responder ({{keys}})", { keys: KEYS }))}</Btn>
      </Group>
      <Group gap="xs">
        {status.data && <Pill tone={status.data.enabled ? "success" : "warn"}>{status.data.enabled ? t("índice: {{chunks}} fragmentos de {{episodes}} episodios", { chunks: status.data.chunks, episodes: status.data.episodes }) : t("índice de texto desactivado (requiere PostgreSQL)")}</Pill>}
        {canSync && status.data?.enabled && <Btn size="row" loading={sync.isPending} onClick={() => sync.mutate()} icon="refresh">{t("Reindexar ahora")}</Btn>}
        {sync.data && <Text size="xs" c="dimmed">{sync.data.reindexed} {t("episodios reindexados")}</Text>}
      </Group>
      {view === "responder" && <AskAnswer graph={graph} query={q} facts={nf} chunks={nc} trigger={answerTrigger} answered={answered} onBusy={setAnswering} />}
      {scope === "all" && <MutationError error={searchAll.error} />}
      {scope === "all" && searchAll.data && <AskAllBrains r={searchAll.data} />}
      {view === "contexto" && scope === "brain" && <MutationError error={run.error ?? rate.error ?? unrate.error} />}
      {/* The live region is there before the first search and only its text changes: a node replaced on every search is not announced. */}
      {view === "contexto" && scope === "brain" && <div ref={resultsHead} tabIndex={-1} className="ms-ask-head">
        <Group gap="xs"><Text size="sm" role="status">{r ? t("Recall de «{{q}}»: hechos {{f}} · fragmentos {{c}} · pasajes {{d}}", { q: r.query, f: r.facts.length, c: r.chunks.length, d: r.documents?.length ?? 0 }) : ""}</Text>
          {r && r.query !== q.trim() && <Pill size="xs" tone="warn">{t("De una pregunta anterior")}</Pill>}</Group>
        {r && <Text size="xs" c="dimmed" className="ms-data">{r.min_similarity ? `${t("umbral {{v}}", { v: fmtNum(r.min_similarity) })} · ` : ""}{t("{{ms}} ms en total: embedding {{e}} ms · hechos {{f}} ms · fragmentos {{c}} ms", { ms: r.ms.total, e: r.ms.embed, f: r.ms.facts, c: r.ms.chunks })}</Text>}
        {r && canSync && <Group gap="md" mt={6} className="ms-ask-marking">
          <Toggle label={t("Marcar para una consulta de referencia")} checked={marking} onChange={(e) => setMarking(e.currentTarget.checked)} />
        </Group>}
      </div>}
      {view === "contexto" && scope === "brain" && r && (
        <div className="ms-ask-wrap"><div className="ms-ask-cols">
          <Stack className="ms-ask-main" gap="xs">
            {/* In one column the context comes after every card: on a phone that is thousands of pixels down. */}
            {(r.facts.length + r.chunks.length + (r.documents?.length ?? 0)) > 1 && <Text size="xs" c="dimmed">{t("Numerados en el orden en que el agente los lee en el contexto inyectado.")}</Text>}
            {r.context && <Text size="sm" className="ms-ask-jump"><CardLink to="ask-context">{t("Ir al contexto inyectado")}</CardLink></Text>}
            {!r.facts.length && !r.chunks.length && !!r.min_similarity && (
              <Text size="xs" c="dimmed">{t("Ningún hecho ni fragmento llega a la similitud mínima ({{v}}, en Administración → Recuerdo).", { v: fmtNum(r.min_similarity) })}</Text>)}
            {!r.facts.length && !r.chunks.length && !r.documents?.length && <EmptyState>{t("El recall no ha traído nada para esta pregunta: ni hechos, ni fragmentos, ni pasajes.")}</EmptyState>}
            {current.length > 0 && <>
              <Title order={2} size="h5">{t("Hechos vigentes ({{n}})", { n: current.length })}</Title>
              {/* the graph's order: closeness, weighed down by shelf life and the source's trust where those apply */}
              {orderNote(pulledIn(current)
                ? t("Primero, los que sustituyen a algo de este resultado; después, por parecido a la pregunta, con menos peso para lo que pasó su vida útil o viene de una fuente menos fiable.")
                : t("Por parecido a la pregunta, con menos peso para lo que pasó su vida útil o viene de una fuente menos fiable."))}
            </>}
            {current.map(factCard)}
            {gone.length > 0 && <>
              <Title order={2} size="h5" mt="xs">{t("Hechos que dejaron de ser ciertos ({{n}})", { n: gone.length })}</Title>
              {orderNote(pulledIn(gone) ? t("Por parecido a la pregunta; al final, los que afirma un fragmento o pasaje de este resultado.") : t("Por parecido a la pregunta."))}
              {gone.map(factCard)}
            </>}
            {r.chunks.length > 0 && <>
              <Title order={2} size="h5" mt="xs">{t("Fragmentos de episodios ({{n}})", { n: r.chunks.length })}</Title>
              {orderNote(t("Por la fusión de dos búsquedas, por parecido y por las palabras de la pregunta, con algo más de peso para lo reciente: por eso la similitud no siempre baja. Lo que puede estar superado va al final."))}
            </>}
            {r.chunks.map((c, i) => (
              <ListCard key={`${c.origin ?? ""}-${c.id}`} anchor={chunkAnchor(c)} title={c.origin ? `${c.name} · ${c.origin}` : c.name} meta={[rank(current.length + gone.length + i + 1), sim(c) ?? t("sin similitud"), fmtDay(c.valid_at)].join(" · ") + edge(c)}
                aside={markPill(`c:${c.origin ?? ""}:${c.id}`)}
                actions={cardActions(c.name, `c:${c.origin ?? ""}:${c.id}`, "chunk", `${c.origin ?? ""}:${c.id}`, { text: c.text, kind: "chunk" }, false)}
                notice={supersededNotice(c.origin, c.superseded)}>{c.text}</ListCard>))}
            {!!r.documents?.length && <>
              <Title order={2} size="h5" mt="xs">{t("Pasajes de documentos ({{n}})", { n: r.documents.length })}</Title>
              {orderNote(t("Por la fusión de dos búsquedas, por parecido y por las palabras de la pregunta. Lo que puede estar superado va al final."))}
              {r.documents.map((p, i) => (
                <ListCard key={`${p.origin ?? ""}-${p.document_id}-${p.chunk_idx}`} anchor={passageAnchor(p)} aside={markPill(`d:${p.origin ?? ""}:${p.document_id}:${p.chunk_idx}`)} title={p.origin ? `${passageTitle(p)} · ${p.origin}` : passageTitle(p)}
                  meta={[rank(current.length + gone.length + r.chunks.length + i + 1), sim(p) ?? t("sin similitud"), t("actualizado el {{date}}", { date: fmtDay(p.source_updated_at ?? p.last_seen_at) })].join(" · ")}
                  notice={supersededNotice(p.origin, p.superseded)}
                  actions={cardActions(p.title, `d:${p.origin ?? ""}:${p.document_id}:${p.chunk_idx}`, "doc", `${p.origin ?? ""}:${p.document_id}:${p.chunk_idx}`, { text: p.text, kind: "doc" }, false)}>{p.text}</ListCard>))}
            </>}
            {/* while marking, how many and «Guardar» at the foot of the results, in reach of the marks however far down they are */}
            {canSync && marking && <div className="ms-ask-markbar" role="region" aria-label={t("Consulta de referencia")}>
              <Text size="sm">{!marked.length ? t("Ninguno marcado todavía") : marked.length === 1 ? t("1 marcado") : t("{{n}} marcados", { n: marked.length })}</Text>
              <Btn size="row" icon="save" onClick={() => setSave(toRef())}>{t("Guardar como consulta de referencia")}</Btn>
            </div>}
          </Stack>
          {/* Beside the cards it stays in view while they scroll, and scrolls inside its own box. «Copiar» sits in its header, not over the text. */}
          <Stack gap="xs" className="ms-ask-side" id="ask-context" tabIndex={-1}>
            <div className="ms-ask-side-head">
              <Title order={2} size="h6">{t("Contexto inyectado")}</Title>
              {r.context && <CopyBtn value={r.context} />}
            </div>
            {r.context ? <CodeBlock label={t("Contexto inyectado")}>{r.context}</CodeBlock>
              : <Text size="sm" c="dimmed">{t("Vacío: con este recall el agente no recibiría nada.")}</Text>}
          </Stack>
        </div></div>)}
      {save && <RefQueryForm graph={graph} initial={save} onClose={() => setSave(null)} />}
    </Stack>
  );
  return (
    <Page>
      <PageHeader title={t("Preguntar")} description={<>{t("Recall híbrido: hechos del grafo (vigentes e invalidados) más fragmentos de los episodios originales. Es el contexto que se inyecta al agente.")} {t("«Responder» redacta con ese mismo recall una respuesta que cita de dónde sale cada afirmación.")}</>} />
      <FillArea>
        {canSync ? <Tabs value={tab} onChange={(v) => setTab(v)}>
          <Tabs.List>
            <Tabs.Tab value="preguntar">{t("Preguntar")}</Tabs.Tab>
            <Tabs.Tab value="referencia">{t("Consultas de referencia")}</Tabs.Tab>
            <Tabs.Tab value="calidad">{t("Calidad")}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="preguntar" pt="sm">{ask}</Tabs.Panel>
          <Tabs.Panel value="referencia" pt="sm"><RefQueries graph={graph} /></Tabs.Panel>
          <Tabs.Panel value="calidad" pt="sm"><RecallQuality graph={graph} canAdmin={["admin", "owner"].includes(role)} /></Tabs.Panel>
        </Tabs> : ask}
      </FillArea>
    </Page>
  );
}
