/** What Ask shows, kept for this browser tab (sessionStorage), so that leaving the page to open an entity or a source and coming back
 *  with Back puts the same recall, ratings, marks and answer on screen. The address says which question it was (`?q=`); what is kept is
 *  only shown when it was for that question. A convenience: without storage Ask works the same, from an empty page. */
const key = (graph: string, part: string) => `mimirsynth.ask.${graph}.${part}`;

export function loadAsk<T>(graph: string, part: string): T | null {
  try { const s = sessionStorage.getItem(key(graph, part)); return s ? (JSON.parse(s) as T) : null; } catch { return null; }
}

export function saveAsk(graph: string, part: string, value: unknown) {
  try { sessionStorage.setItem(key(graph, part), JSON.stringify(value)); } catch { /* sin almacenamiento, o lleno: no se conserva */ }
}

/** The question and limits in the address, as Ask writes them after a search or an answer. */
export function askParams() {
  const p = new URLSearchParams(window.location.search);
  const num = (name: string, fallback: number, max: number) => {
    const v = Number(p.get(name));
    return p.has(name) && Number.isInteger(v) && v >= 0 && v <= max ? v : fallback;
  };
  return { q: p.get("q") ?? "", facts: num("hechos", 8, 30), chunks: num("fragmentos", 4, 15) };
}
