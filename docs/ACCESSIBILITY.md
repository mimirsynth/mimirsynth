**English** · [Español](es/ACCESSIBILITY.md)

# Accessibility

MimirSynth aims at **WCAG 2.2 level AA**. This page records what has been checked, how to repeat it and what is still open.

## What is checked

| Check | How | Result (0.6.x) |
|---|---|---|
| Automated rules (WCAG 2.0/2.1/2.2 A and AA, plus axe best practices, with target size enabled) | [axe-core](https://github.com/dequelabs/axe-core) injected with Playwright on **28 screens × light and dark theme**, plus the sign-in screen | No violations |
| Colour contrast | The axe `color-contrast` rule on every screen in both themes | No violations |
| Keyboard | Tabbing through My account: every focusable element shows a focus indicator; rows that open on click also open with Enter/Space; radio-style selectors (`Segments`) use arrow keys | OK |
| Reflow (WCAG 1.4.10) | 320 px wide viewport on ten screens, looking for horizontal scrolling | No horizontal scroll |
| Landmarks and headings | Every screen has one `main` landmark and one `h1` (the page title), sections are `h2` | OK |

Fixed in this pass: pages had no level-one heading and the sign-in/setup screens no `main` landmark; action columns in tables had an empty header (now a visually hidden «Actions»); the pager overflowed at 320 px; one heading skipped a level.

## What is still open

- **Manual test with a screen reader (NVDA, VoiceOver)** on the main screens. Automated tools find a minority of the problems; reading order, announcements of changes (toasts, loading states) and the graph canvas need a person with the tool. The graph view is a canvas: its facts are also available as a table in Facts, which is the accessible route.
- Zoom to 200 % / 400 % in a real browser and Windows high-contrast mode have not been tried.

If you use assistive technology and find a barrier, please [open an issue](https://github.com/MimirSynth/mimirsynth/issues).

## Repeating the audit

```bash
# serve the build with a throwaway database and an administrator, then, with Playwright:
npm i axe-core
#   page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' })
#   await page.evaluate(() => axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa','wcag22aa','best-practice'] }, rules: { 'target-size': { enabled: true } } }))
```
Run it on every route (with `?brain=<slug>`) in both `prefers-color-scheme` values. Screens that need the graph database can be stubbed with empty responses.

## Rules for new screens

Use the components in `web/src/ui` (they already carry labels, roles and focus styles); give icon-only buttons an `aria-label`; never convey meaning by colour alone (pills carry text); keep one `h1` per screen (`PageHeader`) and do not skip heading levels; give empty table headers a visually hidden label (`DataTable.ActionsHead`).
