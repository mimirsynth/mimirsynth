# Server texts added since the last release

The same as `../en/README.md`, for the messages the API shows (`../en.server.json`): a pull request adds a new file here, sorted alphabetically, instead of editing `en.server.json`. `python -m mimirsynth.i18n_extract --missing` lists the texts that still need a translation, and `node scripts/i18n.mjs --consolidate` merges these files into `en.server.json` in the version PR. The Docker image copies this folder next to the API, so the server answers with these texts too.
