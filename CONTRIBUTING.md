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
- **Translations:** every visible text goes through `t("…")`. The source language is Spanish (the text itself is the key) and the English catalogue is `web/src/i18n/en.json`; messages the server shows go in `web/src/i18n/en.server.json`, which the API also uses to answer in the caller's language (texts for agents that are not an `HTTPException` are marked with `i18n.tr("…", lang)`). `npm run i18n` checks that nothing is untranslated and that `en.json` is in alphabetical order (`node scripts/i18n.mjs --sort` puts it in order, so the keys two PRs add do not collide at the end of the file), and `python -m mimirsynth.i18n_extract --missing` lists missing server texts. To add a language, add its catalogue and an entry in `LANGUAGES` (`web/src/i18n/index.ts`).
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

## Pull requests
One PR, one purpose. Describe the why, link the issue and tick the template's checklist. Continuous integration must pass.

**Changelog.** A PR does not edit `CHANGELOG.md`. Its entry goes in the `## Changelog` section of its description, one line per entry: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` or `Security`, a colon and the text in English, as it should read in the changelog (a line that does not start with a type continues the entry above). The *PR* check fails without one; a change that needs no entry (CI, docs only, a dependency bump) takes the label `no-changelog` instead, and Dependabot's PRs are exempt. The entries are written into `CHANGELOG.md` when a version is released, so `[Unreleased]` in the file is not up to date between releases: the merged PRs are the source, and `python scripts/changelog.py --preview` shows what the next version would say.

## License
By contributing you agree that your contribution is published under [Apache-2.0](LICENSE).

## Releasing (maintainers)
1. Set the new version in `api/pyproject.toml` (the single source of truth: the app, the image labels and the release check read it) and run `python scripts/changelog.py --release X.Y.Z`: it reads the `## Changelog` sections of the PRs merged since the last tag (through the GitHub API, with `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`) and writes them under a new `## [X.Y.Z] - date` heading, in their sub-sections and with their PR numbers. It warns about merged PRs that should have had an entry. Review the result; this all goes in the version PR.
2. Commit, then tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`. A pre-release uses `vX.Y.Z-rc.N` (it does not move `latest`).
3. The *Release* workflow checks that the tag matches the version, builds the image for `linux/amd64` and `linux/arm64`, pushes it to `ghcr.io/mimirsynth/mimirsynth` and creates the GitHub release from the changelog.
