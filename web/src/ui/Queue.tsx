import { useTranslation } from "react-i18next";
import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { Check } from "./Fields";

export type QueueItem = { id: number; title: ReactNode; preview?: string; meta?: ReactNode; tags?: ReactNode;
  /** The title as plain text, for the checkbox's name («Seleccionar #3 · …»); without it the checkbox says only the number. */ label?: string };

/** A review queue: one item is open (the detail beside it), several can be checked for a decision on all of them. Each item is a list
 *  entry with a real button to open it and its own checkbox, so screen readers keep the list structure and the open one is announced
 *  (`aria-current`). The queue is one Tab stop (the open item, or the first): Up/Down, Home/End open the next item and take the focus to
 *  it (`onMove`; the open item and the focus are always the same one), and the page's J/K shortcuts do the same (`useShortcuts`). The checkboxes stay out of the Tab
 *  order: the page's X checks the item with the focus, and a checked item says so to a screen reader. */
export function QueueList({ items, activeId, focusKey, onActivate, onMove, checked, onCheck, label }: {
  items: QueueItem[]; activeId: number | null; onActivate: (id: number) => void; checked: Set<number>; onCheck: (id: number, on: boolean) => void; label: string;
  /** Opens an item reached with the arrow keys, without leaving the queue (on a narrow screen the detail stays hidden). */ onMove?: (id: number) => void;
  /** Bumped to move the focus to the open item (after an undo, for example), so it is not lost when the control that had it goes away. */
  focusKey?: number;
}) {
  const { t } = useTranslation();
  const refs = useRef(new Map<number, HTMLButtonElement>());
  const list = useRef<HTMLUListElement>(null);
  useEffect(() => {  // the open item stays in view when J/K move it, and takes the focus when the queue had it
    if (activeId === null) return;
    const el = refs.current.get(activeId);
    el?.scrollIntoView({ block: "nearest" });
    if (el && list.current?.contains(document.activeElement) && document.activeElement !== el) el.focus();
  }, [activeId]);
  useEffect(() => {
    if (focusKey && activeId !== null) refs.current.get(activeId)?.focus();
  }, [focusKey]);  // eslint-disable-line react-hooks/exhaustive-deps
  const keys: Record<string, (i: number) => number> = { ArrowDown: (i) => i + 1, ArrowUp: (i) => i - 1, Home: () => 0, End: () => items.length - 1 };
  const move = (from: number, key: string) => {
    const next = items[keys[key](items.findIndex((it) => it.id === from))];
    if (!next) return;
    onMove?.(next.id);
    refs.current.get(next.id)?.focus();
  };
  const stop = items.some((it) => it.id === activeId) ? activeId : items[0]?.id;  // the queue's one Tab stop
  return (
    <ul className="ms-queue" aria-label={label} ref={list}>
      {items.map((it) => (
        <li key={it.id} className="ms-queue-item" data-qid={it.id} data-active={it.id === activeId ? "" : undefined} data-checked={checked.has(it.id) ? "" : undefined}>
          <label className="ms-queue-check">{/* a touch anywhere around the box checks it */}
            <Check checked={checked.has(it.id)} tabIndex={-1} onChange={(e) => onCheck(it.id, e.currentTarget.checked)} aria-label={it.label ? t("Seleccionar #{{id}} · {{title}}", { id: it.id, title: it.label }) : t("Seleccionar #{{id}}", { id: it.id })} />
          </label>
          <button type="button" className="ms-queue-open" aria-current={it.id === activeId ? "true" : undefined} tabIndex={it.id === stop ? 0 : -1}
            aria-labelledby={`ms-q-${it.id}-t`} aria-describedby={`ms-q-${it.id}-d`}
            ref={(el) => { if (el) refs.current.set(it.id, el); else refs.current.delete(it.id); }}
            onClick={() => onActivate(it.id)}
            onKeyDown={(e) => { if (keys[e.key]) { e.preventDefault(); move(it.id, e.key); } }}>
            <span className="ms-queue-title" id={`ms-q-${it.id}-t`}>{it.title}</span>
            <span className="ms-queue-desc" id={`ms-q-${it.id}-d`}>
              {checked.has(it.id) && <span className="ms-sr">{t("Seleccionada.")} </span>}
              {it.preview && <span className="ms-queue-preview">{it.preview}</span>}
              {(it.meta || it.tags) && <span className="ms-queue-meta">{it.tags}{it.meta}</span>}
            </span>
          </button>
        </li>))}
    </ul>
  );
}

/** Single-key shortcuts for a screen (J/K, A/R…). They never fire while the person types in a field or with a modifier held, and only
 *  while `enabled` (for instance, not with a dialog open). With `scope`, only while the focus is inside it (WCAG 2.1.4): a key typed or
 *  dictated anywhere else on the page never decides anything. */
export function useShortcuts(map: Record<string, () => void>, enabled = true, scope?: RefObject<HTMLElement | null>) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return;
    const on = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      const el = e.target instanceof HTMLElement ? e.target : null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.closest("[role=dialog]"))) return;
      if (scope && !(scope.current && document.activeElement && scope.current.contains(document.activeElement))) return;
      const fn = ref.current[e.key.toLowerCase()];
      if (fn) { e.preventDefault(); fn(); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [enabled]);
}

/** The two-pane layout of a review screen: the queue and the open item side by side; on a narrow content area (below about 760px) one at a
 *  time, the detail when `showDetail`, with its own way back. Measured on the content width, like Ask and Query. */
/** The queue item the focus is on, if it is in a `QueueList`: the page's X checks that one rather than the open one. */
export function focusedQueueItem(): number | null {
  const li = document.activeElement instanceof HTMLElement ? document.activeElement.closest<HTMLElement>("[data-qid]") : null;
  return li ? Number(li.dataset.qid) : null;
}

export function InboxLayout({ list, detail, showDetail, detailLabelledBy, listLabelledBy, scopeRef, skip }: { list: ReactNode; detail: ReactNode; showDetail: boolean;
  /** A link at the top of the queue, shown when it has the focus, straight to the open item («Ir a la propuesta abierta»). */
  skip?: { label: string; onSkip: () => void };
  /** The area a screen's shortcuts act in (`useShortcuts`' scope): a click anywhere in it, even on plain text, puts the focus there. */ scopeRef?: RefObject<HTMLDivElement | null>;
  /** The id of the open item's heading, which names the detail region for screen readers. */ detailLabelledBy?: string;
  /** The id of the queue's heading, which names the queue region. */ listLabelledBy?: string }) {
  return (
    <div className="ms-inbox-wrap">
      <div className="ms-inbox" data-detail={showDetail ? "" : undefined} ref={scopeRef} tabIndex={scopeRef ? -1 : undefined}>
        <section className="ms-inbox-list" aria-labelledby={listLabelledBy}>
          {skip && <button type="button" className="ms-skip" onClick={skip.onSkip}>{skip.label}</button>}
          {list}
        </section>
        <section className="ms-inbox-detail" aria-labelledby={detailLabelledBy}>{detail}</section>
      </div>
    </div>
  );
}
