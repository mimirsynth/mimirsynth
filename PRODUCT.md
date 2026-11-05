# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

People open the web interface; agents never do. Agents reach MimirSynth through MCP (`recall`, `remember`) or the REST API with a token scoped to one brain. The web UI serves three audiences equally, and no screen may assume only one of them:

- **Curators** of a shared team or organisation memory. They review what agents propose, fix types and duplicates, resolve contradictions and watch recall quality.
- **Individual users** with a memory of their own, for example a developer whose coding agents write to a personal brain. They act as curator and administrator at the same time.
- **Instance administrators**. They install and operate the instance: AI engines, users and roles, OIDC, document sources, notifications, backups and updates.

Roles are per brain (reader, contributor, curator, owner), plus instance administrator.

## Product Purpose

MimirSynth is memory for AI agents, built on the CoALA cognitive framework and on a temporal knowledge graph (Graphiti on FalkorDB). Agents recall facts, episode text and document passages before they answer, and propose new knowledge as they work. Success means that what an agent recalls is true, current and traceable to where it came from, and that the people responsible for the memory can keep it that way without heavy effort.

## Positioning

All four points below hold together. A neighbouring product may offer one of them, but not the combination:

- **Human review:** anything an agent writes waits in quarantine until a curator approves it, or until the decider approves it against the brain's scope. The decider never rejects on its own. The memory is trustworthy because it is reviewed.
- **Bitemporal history:** facts are invalidated, never overwritten. You can ask what was known at any point in time.
- **Self-hosted and open:** it runs with Docker on your own infrastructure, with your own OpenAI-compatible models. It is licensed Apache-2.0 and there is no cloud service.
- **Isolated brains:** each knowledge domain has its own graph, ontology, members and tokens. A brain can lend read access to another (federation), with an expiry date and revocable at any time.

## Operating Context

- **Install:** `docker compose` with the published image. FalkorDB is bundled or external. PostgreSQL is the control plane in production and SQLite in development. A first-start setup code leads to creating the administrator account. `update.sh` backs up, updates and rolls back in one step.
- **Configuration:** the environment holds only what is needed to start and connect. Everything else is set in Administration and applies without a restart.
- **Inputs:** agent proposals; uploaded files; folders, wikis (Outline, Confluence, Notion) and Git repositories as document sources.
- **Main UI areas:** Overview, Ask (recall and answers), Graph (2D, radial, tree, 3D), Facts, Journal, Proposals, Knowledge (documents), Vocabulary and ontology maintenance, Quality (reference queries), Jobs, Notifications, My account (tokens, 2FA, passkeys) and Administration.
- **Outbound channels:** in-app notifications, plus Telegram, ntfy, Gotify, webhooks and email, as configured by the administrator.
- **Development:** the project works in English. Issues may be opened in Spanish.

## Capabilities and Constraints

- **Nothing leaves the instance unless the administrator configured it.** No third-party fonts, analytics, CDNs or other outbound calls. The reasons are privacy, GDPR and air-gapped installs. The web fonts ship with the app (Fontsource, OFL-1.1).
- **Two languages, Spanish and English, for the whole interface.** Translation keys are the Spanish strings (`web/src/i18n`). Text in CSS `content` and in `aria-label` templates must also go through translation.
- **Two themes, light (Superficie) and dark (Pozo), equally finished.**
- **Status:** 0.x, under active development. The API and the schema may change between versions.
- **Terminology** (the UI action verbs are fixed):
  - *Añadir* (add) brings something that already exists into a collection.
  - *Crear* (create) makes something new.
  - *Borrar* (delete) destroys data.
  - *Quitar* (remove) unlinks something without destroying it.
  - *Revocar* (revoke) invalidates a credential.
  - *Cancelar* (cancel) dismisses a dialog.
  - *Cerrar* (close) hides a panel.
  - *Deshacer* (undo) reverts the last operation.
  - *Buscar* (search) runs a query.
  - *Ejecutar* (run) starts a task.

  Domain terms: brain, fact, episode, proposal, curator, decider, ontology, federation, recall.
- **Open decisions:**
  - Right to be forgotten, meaning a real deletion of a person or entity (#134). It needs design first.
  - Further integrations (#105, #111, #112).

## Brand Commitments

- **Name:** MimirSynth. Mímir is the guardian of the well of knowledge in Norse mythology, a memory you consult. "Synth" stands for synthetic memory and for synthesis, the consolidation of episodes into knowledge. It has no relation to Grafana Mimir.
- **Mark:** `web/public/mimirsynth-mark.svg`, plus the mono ink and mono light variants.
- **Identity source:** `web/src/theme.css` and `web/src/ui/DESIGN.md`. Screens are built only from the `web/src/ui` kit, which `npm run check:ui` enforces.
- **Voice:** plain and precise. It says what happens and what to do next, with no marketing tone. User documentation lives in the GitHub wiki, in both languages.

## Evidence on Hand

- README (English and Spanish), technical docs in `docs/` and `docs/es/`, and a user guide in the wiki.
- Accessibility record in `docs/ACCESSIBILITY.md`: axe on 28 screens in both themes, with keyboard and reflow checks.
- CHANGELOG with the release history.
- There are no public testimonials, customer names, case studies or published benchmarks. Do not invent any.

## Product Principles

1. **Trust before volume.** Agent writes go through review. The UI makes reviewing fast and never hides what is pending.
2. **History is never lost.** Invalidate, don't overwrite. Every fact shows where it came from and when it was valid.
3. **Your infrastructure, your models.** Nothing depends on a hosted service or reaches a third party on its own.
4. **One interface for curators, individuals and administrators.** Shared patterns everywhere, and depth revealed by role rather than by separate products.
5. **Operational honesty.** Errors, empty states and loading states say what happened and what to do, in the user's language.

## Accessibility & Inclusion

The target is WCAG 2.2 AA, with axe in both themes as the minimum check. Still open: a manual screen-reader pass with NVDA and VoiceOver (#9), 200–400% zoom, and Windows high-contrast mode. The graph canvas has an accessible route: the same facts as a table in Facts.
