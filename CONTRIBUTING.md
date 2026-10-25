**English** · [Español](docs/es/CONTRIBUTING.md)

# Contributing to MimirSynth

Thanks for wanting to help! MimirSynth is under active development: before starting on a large change, open an *issue* or a *discussion* to talk it over.

## Set up the environment
```bash
git clone https://github.com/MimirSynth/mimirsynth.git && cd mimirsynth
cd api && uv venv && uv pip install -e . pytest && .venv/bin/pytest -q     # API: tests use SQLite; those needing PostgreSQL or FalkorDB skip themselves
cd ../web && npm install && npm run build                                   # web: includes the interface guardians (check:ui and i18n)
```
For hot reload: `uvicorn mimirsynth.main:app --port 8010` (with `MIMIRSYNTH_AUTH_MODE=off`, development only) and `npm run dev` in `web/`.

## Rules
- **Tests:** every behaviour change comes with its test. A schema change comes with its Alembic migration.
- **Interface:** screens are built only with the components in `web/src/ui/` (read its `README.md`). `npm run check:ui` fails if you use inline styles, native HTML elements or literal colours.
- **Translations:** every visible text goes through `t("…")`. The source language is Spanish (the text itself is the key) and the English catalogue is `web/src/i18n/en.json`; messages the server shows go in `web/src/i18n/en.server.json`. `npm run i18n` checks that nothing is untranslated, and `python -m mimirsynth.i18n_extract --missing` lists missing server texts. To add a language, add its catalogue and an entry in `LANGUAGES` (`web/src/i18n/index.ts`).
- **Text and data:** do not introduce names, addresses or data from your own infrastructure in code, tests or documentation: use generic examples.
- **Secrets:** never commit them. Sensitive values live encrypted in the database, not in the repository.
- **Commits:** English messages in the style `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`.

## Pull requests
One PR, one purpose. Describe the why, link the issue and tick the template's checklist. Continuous integration must pass.

## License
By contributing you agree that your contribution is published under [Apache-2.0](LICENSE).
