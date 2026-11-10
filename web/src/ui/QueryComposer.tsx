import { useTranslation } from "react-i18next";
import { Menu as MMenu } from "@mantine/core";
import type { ReactNode } from "react";
import { Btn } from "./Btn";
import { TextArea } from "./Fields";
import { Icon, type IconName } from "./Icon";

const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);
// A touch screen with no keyboard to hand: no shortcut is offered that cannot be used.
const TOUCH = typeof window !== "undefined" && !!window.matchMedia?.("(hover: none) and (pointer: coarse)").matches;

/** How a screen puts a question to the brain, the same in Ask and in the Cypher query: the field under its label, full width; under it,
 *  one row with the options that shape the run (`options`: segments, limits), then the run button, always in the same place, the
 *  shortcut beside it as small keycaps, and the secondary tools (`tools`: examples, history). Ctrl/⌘+Enter runs from the field. `code`
 *  sets the field in the monospace, without spelling correction. `status`, when given, is the one line that says what the last run
 *  returned, right under the field, in a live region that is there from the start so a screen reader announces each result. */
export function QueryComposer({ label, value, onChange, onRun, runLabel, busy, busyLabel, disabled, code, placeholder, description, options, tools, status, autoFocus }: {
  label: string; value: string; onChange: (v: string) => void; onRun: () => void; runLabel: string; busy?: boolean; busyLabel?: string;
  disabled?: boolean; code?: boolean; placeholder?: string; description?: ReactNode; options?: ReactNode; tools?: ReactNode; status?: ReactNode; autoFocus?: boolean;
}) {
  const { t } = useTranslation();
  const can = !!value.trim() && !busy && !disabled;
  return (
    <div className="ms-composer">
      <TextArea label={label} description={description} value={value} onChange={(e) => onChange(e.currentTarget.value)} autosize minRows={code ? 3 : 2} maxRows={code ? 12 : 8}
        placeholder={placeholder} autoFocus={autoFocus} className={code ? "ms-mono-input" : undefined} spellCheck={!code} autoCapitalize={code ? "off" : undefined} autoCorrect={code ? "off" : undefined}
        aria-keyshortcuts={TOUCH ? undefined : MAC ? "Meta+Enter" : "Control+Enter"}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (can) onRun(); } }} />
      <div className="ms-composer-bar">
        {options && <div className="ms-composer-options">{options}</div>}
        <div className="ms-composer-run">
          {/* while it works the button says so in words, instead of a spinner in place of its label */}
          <Btn kind="primary" disabled={!can} onClick={onRun}>{busy ? (busyLabel ?? runLabel) : runLabel}</Btn>
          {!TOUCH && <span className="ms-composer-keys" aria-hidden="true"><kbd>{MAC ? "⌘" : t("Ctrl")}</kbd>+<kbd>{t("Intro")}</kbd></span>}{/* i18n-ok: the Mac key's symbol */}
          {tools}
        </div>
      </div>
      {status !== undefined && <div className="ms-composer-status ms-data" role="status">{status}</div>}
    </div>
  );
}

/** A secondary button that opens a short menu of choices (examples, recent queries). Mantine's menu: arrows move between entries, Escape
 *  closes it and gives the focus back. With no entries it is disabled. */
export function MenuButton({ label, icon, items }: { label: string; icon?: IconName; items: { key: string; label: string; onClick: () => void }[] }) {
  return (
    <MMenu position="bottom-start" withinPortal classNames={{ dropdown: "ms-menu" }}>
      <MMenu.Target>
        <Btn icon={icon} disabled={!items.length} rightSection={<Icon name="chevronDown" size={14} />}>{label}</Btn>
      </MMenu.Target>
      <MMenu.Dropdown>
        {items.map((it) => <MMenu.Item key={it.key} onClick={it.onClick} className="ms-menubtn-item">{it.label}</MMenu.Item>)}
      </MMenu.Dropdown>
    </MMenu>
  );
}
