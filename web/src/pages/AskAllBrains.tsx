import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { fmt } from "../api";
import { Block, Btn, EmptyState, ListCard, MutationError, Pill, ViewBar } from "../ui";
import { ROLE } from "./TokensPanel";

type Fact = { uuid: string; fact: string; status: string; valid_at: string | null; invalid_at: string | null; name: string; source: string; target: string; source_uuid: string; target_uuid: string };
type Chunk = { id: number; episode_uuid?: string; name: string; text: string; valid_at: string | null };
type Passage = { document_id: number; chunk_idx: number; title: string; text: string };
type BrainHits = { slug: string; name: string; role: string; state: "ok" | "timeout" | "error"; facts: Fact[]; chunks: Chunk[]; documents: Passage[] };
export type AllBrainsResult = { query: string; brains: BrainHits[]; ms: number };

/** A page of a brain, opened on that brain: the app switches to it from `?brain=` (the link of the email summary does the same). */
const inBrain = (path: string, slug: string) => `${path}${path.includes("?") ? "&" : "?"}brain=${slug}`;

/** What «All my brains» in Ask shows (issues 129 and 186): one search over every brain the person can read, grouped by brain, each
 *  result opening in its own brain. «Open in Ask» goes back to Ask on that brain, with the scope on «This brain» and the query filled in.
 *  Its view: a bar with what this scope does behind its «i», the brains that failed and those with nothing; then a block per brain with
 *  results. `r` is absent before the first search (the bar shows already); `error` is the search's. */
export default function AskAllBrains({ r, error }: { r?: AllBrainsResult; error?: unknown }) {
  const { t } = useTranslation();
  const brains = r?.brains ?? [];
  const found = brains.filter((b) => b.facts.length || b.chunks.length || b.documents.length);
  const quiet = brains.filter((b) => b.state === "ok" && !b.facts.length && !b.chunks.length && !b.documents.length);
  const failed = brains.filter((b) => b.state !== "ok");
  return (
    <>
      <ViewBar title={t("Todos mis brains")}
        help={t("La misma búsqueda en todos los brains que puedes leer, con tu rol en cada uno y sin federación. La respuesta redactada, las valoraciones y guardar como consulta de referencia solo están en «Este brain»: los resultados mezclan brains distintos.")}
        meta={quiet.length > 0 && t("Sin resultados en: {{names}}", { names: quiet.map((b) => b.name).join(", ") })}>
        {failed.map((b) => <Pill key={b.slug} tone={b.state === "timeout" ? "warn" : "danger"}>{b.name} · {b.state === "timeout" ? t("no respondió a tiempo") : t("falló")}</Pill>)}
      </ViewBar>
      <MutationError error={error} />
      {r && !found.length && <EmptyState>{t("Nada encontrado en tus brains.")}</EmptyState>}
      {found.map((b) => (
        <Block key={b.slug} title={b.name} count={b.facts.length + b.chunks.length + b.documents.length}
          actions={<><Pill>{t(ROLE[b.role] ?? b.role)}</Pill>
            <Btn kind="link" component={Link} to={inBrain(`/preguntar?alcance=brain&q=${encodeURIComponent(r?.query ?? "")}`, b.slug)}>{t("Abrir en Preguntar")}</Btn></>}>
          {b.facts.map((f) => (
            <ListCard key={f.uuid} invalid={f.status === "invalidated"}
              tags={<><Link to={inBrain(`/entidad/${f.source_uuid}`, b.slug)} className="ms-nolink"><Pill>{f.source}</Pill></Link>
                <span className="ms-data">{f.name}</span><Link to={inBrain(`/entidad/${f.target_uuid}`, b.slug)} className="ms-nolink"><Pill>{f.target}</Pill></Link></>}
              meta={<>{fmt(f.valid_at)}{f.invalid_at ? ` → ${fmt(f.invalid_at)}` : ""}</>}>{f.fact}</ListCard>))}
          {b.chunks.map((c) => (
            <ListCard key={`c-${c.id}`} title={c.episode_uuid ? <Link to={inBrain(`/diario?episodio=${c.episode_uuid}`, b.slug)}>{c.name}</Link> : c.name}
              aside={fmt(c.valid_at)}>{c.text}</ListCard>))}
          {b.documents.map((p) => (
            <ListCard key={`d-${p.document_id}-${p.chunk_idx}`} title={<Link to={inBrain(`/conocimiento?doc=${p.document_id}`, b.slug)}>{p.title}</Link>}>{p.text}</ListCard>))}
        </Block>))}
    </>
  );
}
