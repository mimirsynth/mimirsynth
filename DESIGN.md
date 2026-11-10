---
name: MimirSynth
description: Memory for AI agents, reviewed by people. A calm, flat operating interface in two themes, Superficie (light) and Pozo (dark).
colors:
  pozo: "#0d1f26"
  mimir: "#1e6b73"
  mimir-bright: "#5fb8bf"
  hidromiel: "#d4a03a"
  espuma: "#cfe4e1"
  pizarra: "#7f93a8"
  superficie: "#e9efee"
  superficie-raised: "#ffffff"
  superficie-line: "#b4c6c3"
  superficie-field-line: "#718c8a"
  superficie-stripe: "#d9e5e3"
  superficie-thead: "#dbe6e4"
  superficie-chip: "#d6e8e6"
  superficie-chip-ink: "#12474e"
  superficie-chip-line: "#9cc3c0"
  superficie-ink: "#0d1f26"
  superficie-muted: "#4d6168"
  superficie-invalidado: "#a8461f"
  pozo-surface: "#0b171c"
  pozo-raised: "#12242b"
  pozo-line: "#24404a"
  pozo-field-line: "#527a86"
  pozo-stripe: "#0f2128"
  pozo-thead: "#0f2027"
  pozo-chip-ink: "#9fdde1"
  pozo-ink: "#e6efed"
  pozo-muted: "#9db2b3"
  pozo-invalidado: "#e88a62"
  graph-canvas: "#101113"
typography:
  display:
    fontFamily: "Oxanium, Segoe UI, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "Oxanium, Segoe UI, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.35
  stat:
    fontFamily: "Oxanium, Segoe UI, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 600
    lineHeight: "38px"
  card-label:
    fontFamily: "Oxanium, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    letterSpacing: "0.06em"
  body:
    fontFamily: "Instrument Sans, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Instrument Sans, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "0.08em"
  data:
    fontFamily: "JetBrains Mono, ui-monospace, Cascadia Code, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  counter: "4px"
  base: "6px"
  large: "10px"
  switch: "9999px"
spacing:
  hair: "4px"
  tight: "8px"
  base: "12px"
  roomy: "16px"
  section: "20px"
  wide: "32px"
components:
  button-primary:
    backgroundColor: "{colors.hidromiel}"
    textColor: "{colors.pozo}"
    rounded: "{rounded.base}"
    height: "36px"
    padding: "0 14px"
  button-secondary:
    backgroundColor: "{colors.superficie-raised}"
    textColor: "{colors.superficie-ink}"
    rounded: "{rounded.base}"
    height: "36px"
    padding: "0 14px"
  button-ghost:
    textColor: "{colors.superficie-ink}"
    rounded: "{rounded.base}"
    height: "36px"
    padding: "0 14px"
  button-danger:
    textColor: "{colors.superficie-invalidado}"
    rounded: "{rounded.base}"
    height: "36px"
    padding: "0 14px"
  button-row:
    rounded: "{rounded.base}"
    height: "28px"
    padding: "0 10px"
  input:
    backgroundColor: "{colors.superficie-raised}"
    textColor: "{colors.superficie-ink}"
    rounded: "{rounded.base}"
    height: "36px"
  pill:
    backgroundColor: "{colors.superficie-chip}"
    textColor: "{colors.superficie-chip-ink}"
    rounded: "{rounded.base}"
    height: "24px"
  segment:
    backgroundColor: "{colors.superficie-chip}"
    textColor: "{colors.superficie-chip-ink}"
    rounded: "{rounded.base}"
    height: "36px"
    padding: "0 14px"
  segment-active:
    backgroundColor: "{colors.mimir}"
    textColor: "{colors.superficie-raised}"
  panel:
    backgroundColor: "{colors.superficie-raised}"
    rounded: "{rounded.base}"
    padding: "16px"
  settings-group:
    backgroundColor: "{colors.superficie-raised}"
    rounded: "{rounded.large}"
    padding: "16px 20px"
  modal:
    backgroundColor: "{colors.superficie-raised}"
    rounded: "{rounded.large}"
  table-head:
    backgroundColor: "{colors.superficie-thead}"
    textColor: "{colors.superficie-muted}"
    typography: "{typography.label}"
---

# Design System: MimirSynth

## Overview

**Creative North Star: "The Well of Mímir"**

In the myth, Mímir guards a well of knowledge that Odin consults. The interface is that well: deep and still, read from the surface. The two themes take their names from it. **Superficie** is the light surface of the water, a pale teal-grey. **Pozo** is the well itself, a deep blue-green that is never pure black. **Mimir** teal marks where you are and where you can go. **Hidromiel**, the mead gold, is kept for the single action that matters on each zone, so it reads as an offering rather than decoration. Nothing in the system floats or glows. Depth comes from tone and from the 1px rule at the edge of each surface.

This is an operating interface. Curators, individual users and administrators come to review, query and maintain a memory, so density and scanability come first. Every control in a row has the same height. Tables are striped in solid colour. Dates and identifiers are set in a monospace with tabular figures, so columns of history line up. Personality lives in a few precise places: Oxanium on titles and figures, the gold primary button, the entity chips coloured by type, and the dark graph canvas that never turns light.

Components are sober and precise: flat, with a 1px rule and one corner radius, and fixed heights. Colour belongs to state (active, success, warning, danger, invalidated) and to the one primary action per zone. It is never there for decoration.

**Key Characteristics:**
- Two themes of equal standing, Superficie and Pozo, built from the same tokens.
- Flat surfaces separated by 1px rules. No shadows.
- One corner (6px) for every control, chip and panel. 10px only for dialogs, side panels and settings groups.
- One control height (36px). Table row actions are 28px and pills 24px.
- Oxanium for display and figures, Instrument Sans for everything you read, and JetBrains Mono for data.
- Hidromiel gold appears on one primary action per zone and nowhere else as a fill.

## Colors

The palette is a narrow teal-grey family drawn from water and stone, with a single warm mead gold and a rust tone that is reserved for what is no longer true.

### Primary
- **Mimir Teal** (light theme `mimir`, dark theme `mimir-bright`): the accent. Use it for the active state (current tab, selected nav item, active segment), for links, for the focus ring in the light theme, for checked controls, and for the success tone of notices and timeline dots. It never fills a large area.
- **Hidromiel Gold** (`hidromiel`): the primary button fill, with Pozo ink on top (7.2:1). It is also the slider thumb, the progress fill, the warning notice edge and the focus ring in the dark theme, where teal would sink into the background.

### Secondary
- **Rust, «Invalidado»** (light `superficie-invalidado`, dark `pozo-invalidado`): the colour of facts that are no longer valid and of the danger button and danger notice. Invalidated text is also struck through, so the meaning never depends on colour alone.

### Tertiary
- **Pizarra Slate** (`pizarra`): the fourth chart series, after teal, gold and rust. Charts use only these four.
- **Espuma Foam** (`espuma`): the theme toggle's thumb in dark mode.

### Neutral
- **Superficie / Pozo surface** (`superficie`, `pozo-surface`): the page background.
- **Raised** (`superficie-raised`, `pozo-raised`): panels, cards, tables, inputs, modals and the navbar, one step up from the surface.
- **Line** (`superficie-line`, `pozo-line`): every 1px rule and border, and the slider and progress track.
- **Field line** (`superficie-field-line`, `pozo-field-line`): the edge of fields, checkboxes and radios, and the track of an off switch. A field is told apart by its edge alone, so this line keeps 3:1 against both the raised fill and the surface (WCAG 1.4.11). The quieter Line would not.
- **Stripe and table head** (`superficie-stripe`/`superficie-thead`, `pozo-stripe`/`pozo-thead`): striped rows and table headers.
- **Chip** (`superficie-chip`, `superficie-chip-ink`, `superficie-chip-line`, and `pozo-chip-ink` on a 14% teal wash in the dark theme): pills, segments, notices, the selected sub-nav item and avatars.
- **Ink and muted** (`superficie-ink`/`superficie-muted`, `pozo-ink`/`pozo-muted`): body text and secondary text. Muted text stays above 5:1 on every surface.
- **Graph canvas** (`graph-canvas`): the background of every graph view, dark in both themes, so entity-type colours read the same everywhere.

Pills carry four status tones (success, warn, danger, alt), defined per theme as a soft fill, a darker ink and a mid-tone border.

### Named Rules
**The One Mead Rule.** A zone has at most one Hidromiel fill: its primary action. If two buttons in a zone both want to be gold, one of them is secondary.

**The Accent Is a Signpost Rule.** Teal marks state, links and focus. It never colours body text or decoration, and text on a surface is always ink or muted.

**The Word Before Colour Rule.** Every state carries a word or a date (invalidated, success, warn, danger). Colour only reinforces it.

**The Same Type, Same Colour Rule.** An entity type takes its colour from a hash of its name (`typeColor` in `web/src/ui/palette.ts`), so a Host is the same colour on every screen and in both themes.

## Typography

**Display Font:** Oxanium (with Segoe UI, system-ui)
**Body Font:** Instrument Sans (with system-ui, -apple-system, Segoe UI)
**Label/Mono Font:** JetBrains Mono (with ui-monospace, Cascadia Code, Consolas)

**Character:** Oxanium's squared, engineered letterforms give titles and figures the feel of an instrument. Instrument Sans is calm and plain, so the content stays in front. The monospace is reserved for data whose alignment matters.

### Hierarchy
- **Display** (Oxanium 600, 26px, 1.3): the page title. There is one per screen and it is the only `h1`.
- **Title** (Oxanium 600, 20px): dialog titles. Section headings inside a page use the Mantine heading scale in Oxanium 600.
- **Stat** (Oxanium 600, 32px / 38px; 28px when inline): key figures on stat cards.
- **Card label** (Oxanium 600, 13px, 0.06em, uppercase): chart and card titles.
- **Body** (Instrument Sans 400, 14px, 1.55): list cards, prose and form text. A screen's help is not printed under its title: it opens from the «i» beside the title, in a popover at the measure (see Layout).
- **Label** (Instrument Sans 600, 12px, 0.08em, uppercase): table headers, settings-group headings and nav section headings (11px, 0.1em).
- **Data** (JetBrains Mono 400, 13px, tabular figures): dates, identifiers, scores, commands and code.

### Named Rules
**The Two Weights Rule.** Instrument Sans ships in 400 and 600, and Oxanium in 500 and 600. Do not ask for 700 or 800: the browser would fake the bold. `b` and `strong` are set to 600 for the same reason. Do not ask for 500 either: it renders as 400, so the emphasis is lost. Emphasis is 600; secondary text is 400 in the muted colour.

**The Tabular Truth Rule.** Any column of dates or numbers is set in the data style, so the digits line up and history can be compared at a glance.

## Layout

A screen is one of two kinds of page. A **document** (Overview, Ask, an entity, the Journal, settings) grows with its content and the window scrolls, with its bar at the window's edge, as on any web page. A **data surface** (a table, the review queue, a canvas) fills the window, and only its data area scrolls inside, so the title, tabs and filters stay in view while the rows move. No screen sets heights in `vh`.

A screen reads top to bottom: the title, the tabs, then each view's bar on a single row (its «i», search, the status segments, its actions), then the data (the Screen Anatomy Rule below). What the screen is for is not printed under the title, where it took two to six lines of every screen for something read once: it sits behind an «i» beside the title and opens in a popover, by click, tap or keyboard, or by resting the pointer on it. It says in a few sentences what the screen shows and what can be done there; anything longer goes to the wiki. Details open in a side panel for reading or a modal for acting. Settings and Administration share one scheme: a 220px sub-navigation in groups on the left, and on the right one settings group per section, with one row per setting. Each row has the name and help on the left and the control on the right, in a 240–340px column. A Save button appears only when something changed.

Spacing follows a small rhythm: 4px inside chips, 8px between related controls, 12px between blocks of a page, 16px inside panels, 20px inside settings groups, and 32px between major columns. The widest reading blocks stop at about 1100px (settings body).

**Breakpoints:** 36em, 48em (phone: the navbar becomes a menu button and tables become cards), 62em, 75em (wide charts span two columns) and 88em. The split view puts its side panel underneath below 1000px.

**Phone (<48em):** every table row becomes a card. Each cell takes its label from its column header, and action cells are right-aligned. The sortable column headers stay above the cards as a strip of «Sort and filter» pills. Settings rows stack. The whole page scrolls.

### Named Rules
**The One Height Rule.** Controls in a row are all 36px: buttons, fields, selects, segments and icon buttons.

**The Measure Rule.** Running text, the kind that is read line after line (prose, a proposal, facts, notes, a screen's help in its popover), stops at about 72 characters (`--ms-measure`): past that the eye loses the start of the next line. Wider panels use the room for a second column, such as a record's sheet, not for longer lines. The token is `33em`, not `72ch`: `ch` is the width of «0», which Instrument Sans draws about one and a half characters wide, so `72ch` ran to some 107. The kit applies it to its own running text (a list card's body and note, prose, the help behind an «i»); a screen never sets a measure itself, so nothing else is cut short. The interface's own short texts are not running text: an empty state, a section's hint, a settings description, a field's description and a notice's message stop at a wider `60em` (`--ms-measure-ui`), so they no longer break after a few words into stacks of short lines, and still do not cross a wide screen. Both wrap evenly (`text-wrap: pretty`), never leaving one word alone on the last line. Tables, code, charts and data grids keep their full width.

**The Screen Anatomy Rule.** Every screen is built from the same parts in the same order, and each kind of thing has one place. A page is its header (title, its «i», page-wide actions), then on a hub its stat cards, then its tabs, then the view. A view, the content of a page or of one of its tabs, is:
1. **The view bar** (`ViewBar`), one row: first the «i» with what the view is for, then its filters (status segments, search, fields under their label) and a short status in the data style; on the right its actions, at most one primary. The bar is the same height as a control and wraps on a narrow screen.
2. **The content**, exactly one of: a data table for records that share fields (the default, also for histories, runs and logs); list cards for records that are mainly text to read and decide on (proposals, summaries, search hits); settings groups with one row per setting for anything that is switched on or set (passes, verifiers, alerts); a comparison in equal columns (`Compare`) for two versions of the same thing; or the empty state. While it loads, `Loading` takes the empty state's place.
3. **Blocks** (`Block`) for the secondary parts below (recent merges, what was set aside, the last runs): a heading in the label style with its count, its own «i» and actions on the right, then content of the same kinds at the full width. Never a card around them.

What the interface says about itself goes behind an «i» (`HelpTip`): beside the title, at the start of a view bar or beside a block heading. It is never a paragraph, an info notice or a footnote on the page. A field explains itself in its description, a record's secondary data goes in its card's meta line or its cell's second line (`CellText`), and a short status goes in the bar. Notices are states, and a state has a name: a warning, an error, a success with its Undo, or an informative state such as «read only» or «as of a date», always titled. Dialogs end with `DialogActions`: Cancel, then the action. Screens set no widths or heights: the bar, the form, the dialog and the table size their fields. A screen with tabs whose views differ (settings beside tables) is a document; only a single data surface fills the window. `npm run check:ui` enforces this: headings, bold text, small muted text, hand-set measures, fixed widths, untitled info notices, hand-made dialog footers, `Panel` and empty states used as loaders all fail the build in a screen.

**The Page Owns the Height Rule.** A data surface (`<Page fill>`) fills the window and its data area scrolls; a document (`<Page>`, the default) grows and the window scrolls. Screens never size themselves against the viewport.

**The Scroll Rule.** A scrollbar never covers or crowds the content. Every bar is thin and drawn in the theme's field line on no track. A data area that scrolls inside the page reaches into the page's right gutter, so its bar sits at the window's edge and the content keeps the same right edge as the title and filters above it; its space is kept whether or not it overflows (`scrollbar-gutter: stable`), so nothing jumps sideways when the bar appears. Where bars overlay the content (macOS, phones, Windows 11's overlay scrollbars) they are drawn over that gutter, never over a button: the kit measures the bar (`--ms-sb`) and keeps the gutter's full width when it is 0.

## Elevation & Depth

The system is flat. Depth is tonal: the page sits on the surface colour, and panels, tables, inputs and dialogs sit one step up on the raised colour, edged with a 1px line. Table headers take a tinted band and a 2px bottom rule. The only things that sit above content are overlays (popovers, tooltips, dialogs), and they too rely on the raised colour and a 1px line rather than a shadow. Mantine's shadow tokens are set to `none`.

### Named Rules
**The No-Shadow Rule.** Relief comes from the 1px rule and the surface colour, never from `box-shadow`, tooltips and popovers included.

**The Inset Marker Exception.** A 3px inset edge marks a selected item (the active sub-nav entry, a table sub-row). It is a position marker, not elevation.

## Shapes

One corner rules the system: a gentle 6px radius on buttons, fields, selects, segments, pills, panels, tables, notices, list cards and tabs. Dialogs, side panels, settings groups, the document drop zone and the graph canvas take 10px. Counters inside a segment or pill take 4px. Switches keep their full pill shape, because that shape is what identifies them as switches. Round shapes are kept for dots: the entity-type dot, timeline points, step markers and legend swatches.

Borders are always 1px solid in the line colour. The drop zone is the one dashed border (1.5px), and it turns teal while a file hovers over it.

## Components

### Buttons
Every action is a button, and it is secondary by default.
- **Shape:** gentle corner (6px), 36px tall, 14px horizontal padding, 14px semibold text. With a leading icon when the verb has one.
- **Primary:** Hidromiel fill with Pozo ink and a faint dark edge. At most one per zone, for example the submit of a dialog or Search. On hover it brightens a little (brightness 1.07). When disabled it stays visible but greyed (opacity 0.7, partly desaturated).
- **Secondary:** raised fill, ink text and a 1px line. On hover it takes the teal wash and a teal border.
- **Ghost:** no fill and no border, with ink text. It is used for Cancel, which always sits to the left of the primary, and for clearing filters.
- **Danger:** transparent, with a rust border and text. On hover it takes a 14% rust wash. Anything that deletes, removes or revokes passes through a confirmation dialog that names the item and repeats the verb.
- **Link:** underlined teal text, only inside a sentence.
- **Row:** a 28px version with 10px padding and 12px text, only for actions inside a table row or a list card.
- **Icon button:** a square 36px button with a 1px line and a tooltip. It turns teal on hover.

### Chips
- **Pill:** a 24px label with a 6px corner, uppercase, 0.06em tracking and semibold, on the chip wash with chip ink. Tones: neutral, success, warn, danger and alt. The strong variant is filled teal. Pills are not interactive.
- **Entity chip:** a named entity with a dot and a 3px left edge in its type colour. The name keeps the theme's ink, so contrast never depends on the type colour. It is a link unless it is the entity of the current page, which draws its whole edge in the type colour instead.

### Segments
The options of a status filter, shaped like pills but interactive and 36px tall. The active option is filled teal, and each option may carry a count in a 4px-corner counter. They move with the arrow keys. The status of an inbox (proposals, jobs, documents) is always a segment row with its counts and «All» first, never a dropdown. A row with a single option is not drawn: one option is no choice, and a lone «All 0» says nothing the list does not.

### Cards / Containers
- **Corner Style:** gentle (6px). Settings groups are 10px.
- **Background:** the raised colour on the surface.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px line.
- **Internal Padding:** 16px for panels and stat cards, 14px × 16px for list cards and 16px × 20px for settings groups.
- **List card:** a title with a muted aside on the right, a body in 14/1.55 text, then tags and actions. An invalidated card shows its body in rust and struck through. A clickable card turns teal at the edge on hover and opens with Enter or Space. What must be read before the body (that it may be superseded) sits above it as a notice, set off by a 1px rule; a sentence about the body (what it replaces, what replaced it) sits under it in 13px muted text. Those sentences link to the cards they name with `CardLink`, a real link that wraps with the text; the card it lands on takes the focus and a teal edge.

### Query Composer
How a screen puts a question to the brain, the same in Ask and in the Cypher query: the field under its label at full width; under it one row with the options that shape the run (scope, mode, limits), then the run button (the zone's primary, always in the same place), the shortcut beside it as small keycaps (hidden on touch screens) and the secondary tools (examples, history, as menu buttons). Ctrl/⌘+Enter runs from the field. A field for code (Cypher) is set in the monospace without spelling correction. What the last run returned is said in one line right under it, in a live region. Choosing an example or a past query replaces the field and offers «Undo».

### Inputs / Fields
- **Style:** raised fill, a 1px field line, 6px corner and 36px height. Labels are 13px semibold ink and descriptions 12px muted. All fields share one size; a size requested at the call site is ignored.
- **Focus:** the border turns teal, and a 2px focus ring sits 2px outside the field (teal in light, gold in dark).
- **Errors:** a mutation error appears as a danger notice under the form, never as loose red text. What the server wrote for people is shown as it is. A request that never reached the server, or an unexpected server failure, says in words what happened and what to do, with the server's own text folded under «Technical detail». A service the instance depends on that does not answer (the embedding engine) is named, with where to fix it.

### Navigation
- **Sidebar:** 240px on the raised colour with a 1px right rule. The logo sits at the top, nav items are grouped under 11px uppercase muted section headings, and session controls sit at the bottom. The active item takes the teal wash, teal text, semibold weight and a 3px teal left edge.
- **Tabs:** always underlined, at both first and second level. Tabs are semibold muted, and the active tab is teal with a 2px teal underline. The open tab lives in the URL.
- **Phone:** the sidebar collapses behind a menu button in a 52px top bar.

### Data Table
The signature of an operating screen. A 1px outer line, a tinted header band with 12px uppercase muted labels and a 2px rule underneath, solid striped rows (marked in Superficie, subtle in Pozo) and the teal wash on hover. Each column header sorts when you press its name, and its funnel opens a filter. The header exposes `aria-sort`. A table scrolls horizontally inside its own box and becomes cards on a phone.

### Review Queue
The curator's inbox (Proposals → To review): the queue and the open item side by side in two 1px-ruled raised panels, the queue about two fifths of the width. On a narrow content area (below about 760px) one shows at a time, with «Back to the queue».
- **Queue entry:** a checkbox for a batch decision, then the title (14px semibold), one muted line of the text, and a meta line with the markers that matter (correction, secret to review, low confidence) and how long it has waited, in the data style. Entries are separated by a 1px rule; the open one takes the chip wash and the 3px inset accent edge.
- **Header bar:** the order it follows, «Select all», and, once something is checked, the batch actions as row-size buttons (approve secondary, reject danger). The detail's Approve stays the zone's only primary.
- **Detail:** the proposal scrolls; the note, the consequence lines, Reject / Approve and the shortcut hint (J/K, A, R, X as small keycaps) stay pinned at the bottom.
- **Rhythm:** deciding opens the next one; the decision notice with Undo sits above, so the curator never goes back to the list.

### Graph Canvas
A dark canvas in both themes, with a 10px corner. Nodes take their entity-type colour. Halos show which source contributed a node and use their own palette, distinct from the type colours. Links are a cool blue and invalid links grey. The canvas colours are tokens of their own (`--ms-canvas`, `--ms-canvas-ink`, `--ms-canvas-rule`, `--ms-canvas-link`), mirrored by `CANVAS` in `web/src/ui/palette.ts` for the renderers; the tooltip and the busy overlay over the canvas use them too. Nothing moves at rest, and with reduced motion nothing moves on its own at all.

## Do's and Don'ts

### Do:
- **Do** build every view as a view bar, one kind of content and blocks below (the Screen Anatomy Rule), and put every explanation behind its «i».
- **Do** build every screen from the kit in `web/src/ui`. `npm run check:ui` fails the build when a screen uses a Mantine primitive the kit wraps, an inline style, a native element, a colour literal, `vh`, or a loose loading or empty text.
- **Do** keep controls in a row at 36px. Use 28px only for row actions and 24px for pills.
- **Do** use the 6px corner everywhere, and 10px only for dialogs, side panels and settings groups.
- **Do** give every state a word or a date as well as its tone, and strike invalidated facts through as well as colouring them rust.
- **Do** set dates, identifiers and scores in the data style with tabular figures.
- **Do** take colours from the tokens (`var(--ms-…)`) or from `web/src/ui/palette.ts`, and check both themes.
- **Do** use the fixed action verbs and their icons: Add, Create, Delete, Remove, Revoke, Cancel, Close, Undo, Search, Run.

### Don't:
- **Don't** use `box-shadow` for depth. Use the raised colour and a 1px line.
- **Don't** put more than one Hidromiel button in a zone.
- **Don't** use teal for body text or decoration.
- **Don't** use emoji or text characters as icons. Icons are Tabler icons registered in `web/src/ui/Icon.tsx`.
- **Don't** convey a state through colour alone.
- **Don't** lighten the graph canvas in the light theme. Type colours are tuned against the dark canvas.
- **Don't** use weights the fonts do not ship: 500, 700 or 800 in Instrument Sans.
- **Don't** load fonts or any other asset from a third-party host. Serve them from the instance (see PRODUCT.md).
