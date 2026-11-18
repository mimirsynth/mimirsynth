# Working on MimirSynth with a coding agent

This file is for coding agents (and the people who drive them). It adds a workflow on top of [CONTRIBUTING.md](CONTRIBUTING.md), which stays the source for the project rules. If the two disagree, CONTRIBUTING.md wins.

## Rule zero: no AI attribution

Nothing in this repository credits an AI or an agent: no co-author trailers, no "generated with" footers, no mention of an assistant in code, comments, commit messages, PR or issue bodies, changelog entries or docs. This applies even if your tool adds such lines by default; remove them.

## 1. Classify the change

| Tier | When | Required |
|---|---|---|
| T0 trivial | typo, docs wording, one-line config | the checks in section 4 |
| T1 logic | new or changed behaviour in `api/`, `integrations/` or `scripts/` | T0 + plan + tests + independent review + QA |
| T2 interface | anything in `web/` that users see | T1 + interface plan + screenshots + interface critique |
| T3 sensitive | auth, roles, tokens, brain isolation, webhooks, file uploads, installer, deletion of data | T1 + security review, done before merge |

Tiers add up: a change to the login screen is both T2 and T3. If you are unsure, pick the higher one.

## 2. Plan before code (T1+)

Write down, in the PR description or before you start:

- **Acceptance criteria** that can be checked, each with how it will be verified (test name, command, UI state). Include at least one failure path.
- **Touch list**: every file the change must reach: callers, tests, Alembic migration, translations (`web/src/i18n/en/…`), wiki pages in both languages, generated reference tables.
- **Out of scope**, in one line each.

For T2, also plan the states (empty, loading, error, no permission, long content), the layout on phone, tablet and desktop, and which components from `web/src/ui/` you reuse. New components need a reason.

## 3. Build

Make the smallest change that fully solves the problem. Reuse existing helpers and components. Don't add options or abstractions nobody asked for. Every behaviour change ships with its test.

## 4. Checks (all must pass before you ask for review)

```bash
cd api && .venv/bin/pytest -q                                # API (PostgreSQL/FalkorDB tests skip themselves without services)
cd web && npm run build && npm test                          # types, build, check:ui, i18n, tooling tests
ruff check --select E9,F63,F7,F82 api/                       # syntax errors and undefined names
shellcheck -S error install.sh update.sh                     # if you touched them
gitleaks detect --no-git -s <changed paths>                  # no secrets
semgrep scan --config p/default --severity ERROR <changed>   # static security, errors only
```

For T2, also open the changed screens in a real browser at 390, 820 and 1440 px wide, take screenshots, run an accessibility check (axe-core), and **look at the screenshots** yourself. Check for overlap, clipping, horizontal scroll, contrast, missing states, and texts that are not translated.

## 5. Independent review

The author does not review their own change in the same context. Run each review below with a fresh context (a sub-agent, or a new session) and give it only the acceptance criteria and the diff. The reviewer reports findings and does not edit code.

- **Code review (T1+):** correctness against each criterion, broken callers, data safety, missing tests, unrequested code. Each finding gives a `file:line`, a concrete failure scenario and a suggested fix.
- **QA (T1+):** turn every criterion into test cases (happy path, failure path, boundaries) and run them. Report a table of case, command, expected, actual and PASS/FAIL. A case that was not run is *not tested*, never PASS.
- **Interface critique (T2):** read the screenshots against `DESIGN.md` and the existing screens: hierarchy, spacing, consistency with `web/src/ui/`, states, accessibility.
- **Security (T3):** secrets, authorization on every new route (can one brain or user reach another's data?), untrusted input, exposure and destructive paths.

The author answers every finding with *fixed* (how) or *not applicable* (why) before marking the PR ready.

## 6. Report

Fill in the PR template honestly. Under *How it was tested*, list the commands you ran and their results, and also what you did **not** test.
