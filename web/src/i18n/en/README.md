# Interface texts added since the last release

A pull request that adds texts to the interface puts their English translation **here**, in a new file named after its topic (for example `entity-type.json`), sorted alphabetically, and does not edit `../en.json`. Two pull requests then never touch the same lines.

`npm run i18n` reads `en.json` plus every file here and fails if a key is in two files or a file is out of order (`node scripts/i18n.mjs --sort` puts them in order). The version PR moves everything into `en.json` with `node scripts/i18n.mjs --consolidate`, which removes the files and leaves this README.
