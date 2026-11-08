import { useTranslation } from "react-i18next";
import { useMediaQuery } from "@mantine/hooks";
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Btn } from "./Btn";
import { move, onScreen, placeCard, type Rect, type Size, type TourMove } from "./tourLogic";

/** A step of a guided tour: what it explains and, in `target`, the `data-tour` value of the element it points at (none: a card in the
 *  middle of the window). */
export type TourStep = { id: string; title: string; body: ReactNode; target?: string };

const same = (a: Rect | null, b: Rect | null) => a === b || (!!a && !!b && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height);
const SETTLE_MS = 600;  // a phone's navigation slides in when a step opens it: the spotlight follows it until it stops

/**
 * Guided tour: a card per step beside the element it explains, which is lit up while the rest of the window is dimmed.
 * It is a modal dialog: the application underneath is inert while it is open, the focus goes to the card at each step (its title and text
 * are read out with «Paso 2 de 8») and comes back where it was at the end. Tab stays inside the card; the arrows move between steps and
 * Escape skips the tour. On a phone the card is docked full width at the edge away from the target. Movement only with
 * `prefers-reduced-motion: no-preference` (theme.css). `onStep` lets the screen show a step's target (open the phone's menu);
 * `onClose(persist)` is called when it is finished or skipped.
 */
export function Tour({ steps, opened, onClose, onStep, returnTo }: {
  steps: TourStep[]; opened: boolean; onClose: (persist: boolean) => void; onStep?: (step: TourStep) => void;
  /** The `data-tour` of the element that gets the focus back when the one that opened the tour is no longer there. */ returnTo?: string;
}) {
  const { t } = useTranslation();
  const ids = useId();
  const narrow = useMediaQuery("(max-width: 48em)") ?? false;
  const [index, setIndex] = useState(0);
  const [target, setTarget] = useState<Rect | null>(null);
  const [card, setCard] = useState<Size>({ width: 360, height: 220 });
  const [view, setView] = useState<Size>({ width: 1024, height: 768 });
  const cardRef = useRef<HTMLDivElement>(null);
  const step = opened ? steps[index] : undefined;

  useEffect(() => {
    if (!opened) return;
    const back = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = document.getElementById("root");
    setIndex(0);
    root?.setAttribute("inert", "");  // the tour is portalled outside it
    return () => {
      root?.removeAttribute("inert");
      // what opened it may be gone (an entry of a menu that has closed): then the focus goes to `returnTo`
      (back?.isConnected ? back : returnTo ? document.querySelector<HTMLElement>(`[data-tour="${returnTo}"]`) : null)?.focus();
    };
  }, [opened]);

  useEffect(() => { if (step) onStep?.(step); }, [step?.id]);  // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (step) cardRef.current?.focus(); }, [step?.id]);

  useLayoutEffect(() => {
    if (!step) return;
    const el = step.target ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`) : null;
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
    const measure = () => {
      const v = { width: window.innerWidth, height: window.innerHeight };
      const r = el?.getBoundingClientRect();
      const next = onScreen(r ? { top: r.top, left: r.left, width: r.width, height: r.height } : null, v);
      setView((p) => (p.width === v.width && p.height === v.height ? p : v));
      setTarget((p) => (same(p, next) ? p : next));
      const c = cardRef.current?.getBoundingClientRect();
      if (c) setCard((p) => (p.width === c.width && p.height === c.height ? p : { width: c.width, height: c.height }));
    };
    const until = performance.now() + SETTLE_MS;
    let frame = 0;
    const tick = () => { measure(); if (performance.now() < until) frame = requestAnimationFrame(tick); else el?.scrollIntoView({ block: "nearest", inline: "nearest" }); };
    tick();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("resize", measure); window.removeEventListener("scroll", measure, true); };
  }, [step?.id, step?.target]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!step) return null;
  const go = (how: TourMove) => {
    const r = move(index, steps.length, how);
    if (r.index === null) { setIndex(0); onClose(r.persist); } else setIndex(r.index);
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") { e.preventDefault(); go("skip"); return; }
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); go(e.key === "ArrowRight" ? "next" : "back"); return; }
    if (e.key !== "Tab") return;
    const all = [...(cardRef.current?.querySelectorAll<HTMLElement>("button:not([disabled])") ?? [])];
    if (!all.length) return;
    const first = all[0], last = all[all.length - 1];
    if (e.shiftKey && (document.activeElement === first || document.activeElement === cardRef.current)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  const place = placeCard(target, card, view, narrow);
  const last = index + 1 >= steps.length;
  return createPortal(
    <div className="ms-tour">
      {target
        ? <div className="ms-tour-spot" aria-hidden style={{ top: target.top - 4, left: target.left - 4, width: target.width + 8, height: target.height + 8 }} />
        : <div className="ms-tour-shade" aria-hidden />}
      <div key={step.id} ref={cardRef} role="dialog" aria-modal="true" aria-labelledby={`${ids}-t`} aria-describedby={`${ids}-n ${ids}-b`} tabIndex={-1}
        className="ms-tour-card" data-mode={place.mode} data-edge={place.mode === "dock" ? place.edge : undefined}
        style={place.mode === "float" ? { top: place.top, left: place.left } : undefined} onKeyDown={onKey}>
        <div id={`${ids}-n`} className="ms-tour-count">{t("Paso {{n}} de {{total}}", { n: index + 1, total: steps.length })}</div>
        <h2 id={`${ids}-t`} className="ms-tour-title">{step.title}</h2>
        <div id={`${ids}-b`} className="ms-tour-body">{step.body}</div>
        <div className="ms-tour-dots" aria-hidden>{steps.map((s, i) => <span key={s.id} data-on={i === index ? "" : undefined} />)}</div>
        <div className="ms-tour-actions">
          <Btn kind="ghost" onClick={() => go("skip")}>{t("Saltar recorrido")}</Btn>
          <div className="ms-tour-nav">
            {index > 0 && <Btn icon="chevronLeft" onClick={() => go("back")}>{t("Atrás")}</Btn>}
            <Btn kind="primary" onClick={() => go("next")}>{last ? t("Terminar") : t("Siguiente")}</Btn>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
