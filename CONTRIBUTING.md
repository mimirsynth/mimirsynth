**English** · [Español](docs/es/CONTRIBUTING.md)

# Contributing to MimirSynth

Thanks for wanting to help! MimirSynth is under active development: before starting on a large change, open an *issue* or a *discussion* to talk it over.

## Language
MimirSynth is **English-first** and **Spanish-friendly**: English is the working language so that anyone can take part, and most of the people around the project speak Spanish, so Spanish stays a first-class language for users.

- **In English:** commit messages, pull request titles and descriptions, issue titles, labels, code (identifiers, comments, docstrings, log messages) and the source version of every document.
- **Spanish is welcome** in issues, discussions and comments. If you are not comfortable writing in English, write in Spanish: a maintainer will add an English title or summary, and the original stays as it is. Conversations can carry on in either language.
- **Existing Spanish comments** in the code are translated when you touch that code, not in sweeping translation-only PRs that conflict with everyone else's work.
- **Documentation** is written in English first and kept translated into Spanish (see [Documentation](#documentation)).
- **The interface** is fully available in English and Spanish. For now its translation catalogues still use the Spanish text as the key (see *Translations* below); moving the source to English is planned.

¿Prefieres leer esto en castellano? [docs/es/CONTRIBUTING.md](docs/es/CONTRIBUTING.md).

## Set up the environment
```bash
git clone https://github.com/MimirSynth/mimirsynth.git && cd mimirsynth
cd api && uv venv && uv pip install -e . pytest && .venv/bin/pytest -q     # API: tests use SQLite; those needing PostgreSQL or FalkorDB skip themselves
cd ../web && npm install && npm run build                                   # web: includes the interface guardians (check:ui and i18n)
```
To run the API tests as CI does, start FalkorDB (`docker run -d -p 6379:6379 falkordb/falkordb:v4.22.0`) and set `MIMIRSYNTH_TEST_FALKOR=localhost`. On Windows the interpreter is `.venv\Scripts\python` (`.venv/Scripts/python -m pytest -q`) and the suite passes there too. When a test writes a text file, give it `encoding="utf-8"` (and `newline=""` if the exact bytes matter): otherwise Windows writes it in its own code page and with CRLF.

To run the full stack from your checkout (builds the image locally instead of pulling the official one):
```bash
cp .env.example .env     # set POSTGRES_PASSWORD and MIMIRSYNTH_SESSION_SECRET
docker compose -f docker-compose.yml -f docker-compose.build.yml --profile bundled up -d --build
```
For hot reload: `uvicorn mimirsynth.main:app --port 8010` (with `MIMIRSYNTH_AUTH_MODE=off`, development only) and `npm run dev` in `web/`.

## Rules
- **Tests:** every behaviour change comes with its test. A schema change comes with its Alembic migration, which revises the latest one: a test fails if there are two heads, so the second of two PRs with a migration renumbers its own.
- **Interface:** screens are built only with the components in `web/src/ui/` (read its `README.md`). `npm run check:ui` fails if you use inline styles, native HTML elements or literal colours.
- **Translations:** every visible text goes through `t("…")`. The source language is Spanish (the text itself is the key) and the English catalogue is `web/src/i18n/en.json`; messages the server shows go in `web/src/i18n/en.server.json`, which the API also uses to answer in the caller's language (texts for agents that are not an `HTTPException` are marked with `i18n.tr("…", lang)`). **A PR does not edit `en.json` or `en.server.json`:** it adds its new translations in a new file of its own, sorted alphabetically, under `web/src/i18n/en/` (for example `en/webhooks.json`), or under `web/src/i18n/en.server/` for server texts. Two PRs that add texts then never touch the same lines and merge in any order. The interface, the API and the Docker image read each catalogue together with its fragments. `npm run i18n` checks that nothing is untranslated, that no key is in two files and that every file is in alphabetical order (`node scripts/i18n.mjs --sort` puts them in order). `python -m mimirsynth.i18n_extract --missing` lists missing server texts. The fragments are merged into the catalogues when a version is released (see below). To add a language, add its catalogue and an entry in `LANGUAGES` (`web/src/i18n/index.ts`).
- **Text and data:** do not introduce names, addresses or data from your own infrastructure in code, tests or documentation: use generic examples.
- **Secrets:** never commit them. Sensitive values live encrypted in the database, not in the repository.
- **Commits:** English messages in the style `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`. PR titles follow the same style, because PRs are squash-merged and the title becomes the commit on `main`.

## Documentation
| Where | What | Languages |
|---|---|---|
| `README.md` / `README.es.md` | What MimirSynth is and the quick start | English and Spanish |
| `docs/` / `docs/es/` | Technical documentation that accompanies the code | English and Spanish |
| `docs/wiki/` | The user guide, published to the [wiki](https://github.com/MimirSynth/mimirsynth/wiki) | English and Spanish pages, in pairs |
| `CHANGELOG.md` | Release notes, written when a version is released (see below) | English |

- A change in behaviour updates the documentation it affects **in the same PR**, in both languages. If you cannot write the Spanish part, say so in the PR and a maintainer will add it before merging.
- **The wiki is edited here, not on GitHub.** Every page in `docs/wiki/` is published to the wiki when it reaches `main`, and the publication overwrites anything edited directly on the wiki. English pages have English names (`Quick-start.md`) and Spanish pages Spanish names (`Guía-rápida.md`); each starts with a link to its counterpart, and links between pages use `[[Page name]]`. A new page goes into `docs/wiki/_index.yml`: in a section of the sidebar (and in the lists of the home page if it is a main entry point), or under `unlisted`. `_Sidebar.md` and the page lists of `Home.md` and `Inicio.md` are generated from it with `python scripts/wiki_index.py` and never edited by hand; a test fails if they are not up to date or if a page is missing from the index.
- **Reference tables are generated from the code.** The table of events on Notifications comes from `notify.EVENTS` and `notify.EVENT_DOCS`, where each event has its wiki description and guide. The settings tables on Settings reference come from `appsettings.REGISTRY`. The route tables on REST API come from the app's routes, by area (`BRAIN_AREAS` and `INSTANCE_AREAS` in the script) and by the minimum role their dependencies require. All are written in both languages by `scripts/wiki_reference.py`, run with the API's interpreter (`api/.venv/bin/python scripts/wiki_reference.py`), between the `<!-- generated:start … -->` and `<!-- generated:end -->` markers; the text around them is still written by hand. A new event or setting needs its Spanish text in the code and its English translation in the catalogue, and then the generator, not an edit of the pages. A new route needs nothing more, unless its path starts a new area. A test fails if the pages are out of date, if an entry has no description or translation, or if a route has no area.

## Pull requests
One PR, one purpose. Describe the why, link the issue and tick the template's checklist. Continuous integration must pass.

**Changelog.** A PR does not edit `CHANGELOG.md`. Its entry goes in the `## Changelog` section of its description, one line per entry: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` or `Security`, a colon and the text in English, as it should read in the changelog (a line that does not start with a type continues the entry above). The *PR* check fails without one; a change that needs no entry (CI, docs only, a dependency bump) takes the label `no-changelog` instead, and Dependabot's PRs are exempt. The entries are written into `CHANGELOG.md` when a version is released, so `[Unreleased]` in the file is not up to date between releases: the merged PRs are the source, and `python scripts/changelog.py --preview` shows what the next version would say.

## License
By contributing you agree that your contribution is published under [Apache-2.0](LICENSE).

## Releasing (maintainers)
1. Set the new version in `api/pyproject.toml` (the single source of truth: the app, the image labels and the release check read it) and run `python scripts/changelog.py --release X.Y.Z`: it reads the `## Changelog` sections of the PRs merged since the last tag (through the GitHub API, with `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`) and writes them under a new `## [X.Y.Z] - date` heading, in their sub-sections and with their PR numbers. It warns about merged PRs that should have had an entry. Review the result; this all goes in the version PR.
2. Run `node scripts/i18n.mjs --consolidate` in `web/`: it merges the translation fragments into `en.json` and `en.server.json`, sorted, and removes them. It also goes in the version PR.
3. Commit, then tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`. A pre-release uses `vX.Y.Z-rc.N` (it does not move `latest`).
4. The *Release* workflow checks that the tag matches the version, builds the image for `linux/amd64` and `linux/arm64`, pushes it to `ghcr.io/mimirsynth/mimirsynth` and creates the GitHub release from the changelog. It also publishes the OpenCode and OpenClaw plugins to npm (`@mimirsynth/opencode`, `@mimirsynth/openclaw`) when their version is not on npm yet, with provenance and the repository secret `NPM_TOKEN`; a pre-release tag publishes them under the dist-tag `next`. Each plugin keeps its own version, so a release whose plugins did not change publishes nothing to npm.

### Public beta release checklist
The first public beta (milestone *Public beta*, #356) is released with the steps above plus these checks. Each item says what CI already guarantees and what is left to check by hand. `STAGE` in `api/mimirsynth/brand.py` is what labels the release as a beta: the interface shows it beside the version and the *Release* workflow puts a banner at the top of the notes; set it to `""` for 1.0.

- [ ] **Every other issue in the milestone is closed.**
- [ ] **A normal version tag, not `-rc`.** The installation guide and the wiki download from `releases/latest/download/…`, and GitHub's *latest* skips pre-releases, so a `vX.Y.Z-rc.N` would leave every install command on the previous version. Try the candidate with an `-rc` first if you want, then tag the same commit as `vX.Y.Z`.
- [ ] **Multi-arch images.** *Automated on release:* the *Release* workflow builds the application and the OCR service for `linux/amd64` and `linux/arm64`, with provenance, SBOM and an attestation. *Not covered by pull requests:* CI's `docker` job builds `linux/amd64` only, so before tagging run *Release* by hand on `main` (Actions → Release → Run workflow): it builds both architectures and publishes nothing. After the release: `docker buildx imagetools inspect ghcr.io/mimirsynth/mimirsynth:X.Y.Z` lists both platforms (same for `-ocr`).
- [ ] **Installer published with checksums.** *Automated on release:* `install.sh`, `install.ps1`, `update.sh`, `docker-compose.yml` and `env.example` are attached with `SHA256SUMS`, and the notes list the hashes and the one-line install commands. *Covered by CI:* `install.sh` installs from scratch with the bundled FalkorDB and detects a second run, connects to an existing FalkorDB, and stops when the graph database does not answer; `shellcheck` on `install.sh` and `update.sh`; `install.ps1` parses, is plain ASCII and passes PSScriptAnalyzer. *By hand after the release:* CI runs the installer from the checkout with a locally built image, never from the release assets, and never runs `install.ps1`, an existing Neo4j or macOS. Install once with `curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash` on Linux or macOS and with `irm …/install.ps1 | iex` on Windows, check `sha256sum -c SHA256SUMS --ignore-missing`, and finish the first-start wizard.
- [ ] **Wiki up to date.** *Automated:* every push to `main` that touches `docs/wiki/` republishes the whole wiki (*Wiki* workflow), and the tests fail if the sidebar, the home page lists or the generated reference tables are out of date. *By hand:* the last *Wiki* run on `main` succeeded, and the getting-started guide and quick start describe the installer and the wizard of this release.
- [ ] **Native plugins installable.** The Claude Code, Codex and Hermes Agent plugins install straight from this repository and need nothing more. The OpenCode and OpenClaw plugins install from npm (`@mimirsynth/opencode`, `@mimirsynth/openclaw`): their packages are built and tested in CI, but no workflow publishes them, so they are published by hand.
- [ ] **Feedback channels.** The issue templates (bug, beta feedback, installer problem, agent integration problem) and the links in `.github/ISSUE_TEMPLATE/config.yml` work, and Discussions has its Q&A category. Pin an announcement in Discussions when the release is out.
