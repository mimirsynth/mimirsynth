import { useEffect, useRef, type FocusEvent, type KeyboardEvent, type ReactNode } from "react";

/** A row of actions that is one stop for Tab: the arrows (and Home/End) move between its buttons, and Tab leaves it. The last button used
 *  keeps the stop, so coming back lands where you were. For lists where every item repeats the same actions (a card per result), so the
 *  keyboard does not have to walk through all of them to reach the next item. */
export function Toolbar({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const active = useRef(0);
  const items = () => [...(ref.current?.querySelectorAll<HTMLElement>("button:not([disabled]), a[href]") ?? [])];
  const settle = (focus = false) => {
    const all = items();
    if (!all.length) return;
    active.current = Math.min(active.current, all.length - 1);
    all.forEach((el, i) => { el.tabIndex = i === active.current ? 0 : -1; });
    if (focus) all[active.current].focus();
  };
  // after every render: buttons come and go (the marks show only while marking), and the stop must stay on one of them
  useEffect(() => settle());
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const all = items();
    const i = all.indexOf(e.target as HTMLElement);
    if (i < 0) return;
    const to = e.key === "ArrowRight" || e.key === "ArrowDown" ? (i + 1) % all.length
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? (i - 1 + all.length) % all.length
      : e.key === "Home" ? 0 : e.key === "End" ? all.length - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    active.current = to;
    settle(true);
  };
  const onFocus = (e: FocusEvent<HTMLDivElement>) => {
    const i = items().indexOf(e.target as HTMLElement);
    if (i >= 0 && i !== active.current) { active.current = i; settle(); }
  };
  return <div ref={ref} role="toolbar" aria-label={label} className={className} onKeyDown={onKeyDown} onFocus={onFocus}>{children}</div>;
}
