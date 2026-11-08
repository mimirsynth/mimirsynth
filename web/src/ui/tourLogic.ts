// The guided tour's decisions, without React or the DOM, so `node --test` covers them (scripts/tour.test.mjs): when it starts on its own,
// where each step goes, and where the card sits next to what it explains. Only erasable TypeScript here: Node strips the types to run it.

export type Rect = { top: number; left: number; width: number; height: number };
export type Size = { width: number; height: number };

/** It starts on its own once: for a person who has not finished or skipped it (kept on the server, so on any device) and who already
 *  has a brain to look at (an administrator on a new instance first creates one, and the tour talks about it). */
export function shouldAutoStart({ tourSeen, hasBrain, startedHere }: { tourSeen: boolean | undefined; hasBrain: boolean; startedHere: boolean }): boolean {
  return tourSeen === false && hasBrain && !startedHere;
}

export type TourMove = "next" | "back" | "skip";
/** Where a move leads: the next or the previous step, or the end (`index` null). Finishing and skipping both mark the tour seen
 *  (`persist`): whoever skips it does not want it again, and can replay it from the help menu. */
export function move(index: number, total: number, how: TourMove): { index: number | null; persist: boolean } {
  if (how === "skip") return { index: null, persist: true };
  if (how === "back") return { index: Math.max(0, index - 1), persist: false };
  return index + 1 >= total ? { index: null, persist: true } : { index: index + 1, persist: false };
}

/** A target that is not on screen (the navigation of a phone still closed, an element scrolled away) is no target: the card goes to
 *  the middle instead of pointing at nothing. */
export function onScreen(r: Rect | null, view: Size): Rect | null {
  if (!r || r.width <= 0 || r.height <= 0) return null;
  return r.left + r.width > 0 && r.top + r.height > 0 && r.left < view.width && r.top < view.height ? r : null;
}

export type Placement = { mode: "center" } | { mode: "dock"; edge: "top" | "bottom" } | { mode: "float"; top: number; left: number };
const GAP = 12;
const EDGE = 16;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, Math.max(lo, hi)));

/** Where the card goes. On a phone (`narrow`) it is docked full width at the edge away from the target, so it never covers it; on a
 *  wide screen it floats beside the target (right, then below, then above), kept inside the window. */
export function placeCard(target: Rect | null, card: Size, view: Size, narrow: boolean): Placement {
  if (!target) return { mode: "center" };
  if (narrow) return { mode: "dock", edge: target.top + target.height / 2 > view.height / 2 ? "top" : "bottom" };
  const right = target.left + target.width + GAP;
  if (right + card.width <= view.width - EDGE)
    return { mode: "float", left: right, top: clamp(target.top + target.height / 2 - card.height / 2, EDGE, view.height - card.height - EDGE) };
  const left = clamp(target.left, EDGE, view.width - card.width - EDGE);
  const below = target.top + target.height + GAP;
  if (below + card.height <= view.height - EDGE) return { mode: "float", left, top: below };
  const above = target.top - GAP - card.height;
  if (above >= EDGE) return { mode: "float", left, top: above };
  return { mode: "center" };
}
