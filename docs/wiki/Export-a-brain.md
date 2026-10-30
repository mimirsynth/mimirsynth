**English** · [Español](Exportar-un-brain)

# Export a brain

A copy of **one brain** in a single package, without touching the others. Use it to keep a brain apart, or to take it to another instance. The backup in [[Upgrade and backups]] covers the whole instance; this covers one brain.

Importing a package is a separate step that is not available yet.

## How
**Administration → Brain access → Export.** It needs **brain administrator** (an API token can never export), and it is recorded in the [[Audit log]].

1. Choose the options:
   - **Include the vectors:** the embeddings of the search index, and those of the graph in its JSON copy. They save recomputing them when importing with the same embedding model, but the package grows a lot.
   - **Encrypt with a password** (at least 12 characters).
2. Click **Export**. The package is prepared as a job ([[Jobs]]) and the card shows its progress.
3. When it is ready, click **Download**.

The package can be downloaded **once**: it is deleted from the server when it is sent. If nobody downloads it, it **expires** after 24 hours (`MIMIRSYNTH_EXPORT_TTL_HOURS`). If a download fails halfway, export again.

## What is in the package
A `.tar.gz` file (`<slug>-<date>.mimirsynth.tar.gz`) with a versioned **`manifest.json`** first. The manifest records the MimirSynth version, the FalkorDB version, the embedding model, the options, the counts, what the secret detector found and every file with its size and `sha256`.

| Path | Contents |
|---|---|
| `graph/graph.dump` | The graph's `DUMP`: exact and fast to restore on the **same FalkorDB version** |
| `graph/nodes.jsonl`, `graph/edges.jsonl` | The same graph as JSON (labels, properties, relations), for another FalkorDB version. Graphiti's vectors only with the vectors option |
| `brain.json` | Name, description, slug, graph and secrets policy |
| `ontology.json`, `vocabulary.json` | The [[Ontology]], the relation aliases, the history of vocabulary changes and the type corrections |
| `proposals.jsonl` | Every proposal with its review. Authors and reviewers go by name only |
| `documents/` | The sources (without their secrets), each document's metadata, its normalized text and its original |
| `ref_queries.json` | The [[Reference queries]] and the summary of their last run, to check after importing that the recall is the same |
| `vectors/` | Only with the vectors option: the chunks of the search index with their embeddings |

**What never goes in:** members, API tokens, AI engines, notification channels, federation grants, jobs and the graph's snapshots. Engines and channels carry secrets sealed with this instance's key and would not work in another one.

> **Exporting while ingesting:** the dump is taken in one go, but the JSON copy of the graph is read in pages. If something is ingested meanwhile, the JSON can miss the newest facts or have an edge whose node is not in it. For an exact copy, export when nothing is being ingested (see [[Jobs]]), or rely on the dump.

> **Restoring the dump:** the `DUMP` payload carries the graph's name. Restore it under that same name (`manifest.json` → `graph.name`) in an instance that does not have that graph, and then copy it to another name if needed. Restoring it under a different name while the original graph is loaded gives wrong counts and can hang FalkorDB.

## Secrets
Everything goes through the [[Secrets]] detector before it is packaged, **whatever the brain's policy**. A package leaves the instance, so the detector is applied here even when the brain is set to only warn.
- A **certain** secret is masked as `[secret removed: type]`. A **possible** one is only counted.
- A graph with a certain secret goes **without its dump**, which cannot be edited, and only as masked JSON.
- A document goes **without its original** when the original had or has a certain secret, or when its text was never checked (a document that was never indexed). Its masked text still goes.
- The card and the manifest show how many secrets were masked and how many originals were left out. Never the value.

## Encryption
With a password, the package is encrypted with AES-256-GCM in 1 MiB chunks, with the key derived from the password with scrypt. Without the password it cannot be read, and a modified or incomplete package is detected. The password is not stored anywhere: it stays in memory until the job starts, so if the service restarts before the export is done, the job fails saying so and you have to export again. **If you lose it, the package cannot be recovered.**

The file ends in `.mimirsynth.tar.gz.enc`. To decrypt it outside the app, run the image itself from the folder that holds the package (the password is read from the environment, so it never appears in the command):
```bash
read -rs MIMIRSYNTH_PACK_PASSWORD && export MIMIRSYNTH_PACK_PASSWORD
docker compose run --rm --no-deps -T -e MIMIRSYNTH_PACK_PASSWORD -v "$PWD:/work:ro" mimirsynth   python -m mimirsynth.packcrypt decrypt /work/package.mimirsynth.tar.gz.enc - > package.mimirsynth.tar.gz
```
A wrong password, or a modified or incomplete package, ends with an error and no output.

## API
`POST /api/brains/{slug}/exports` (`{"vectors": false, "password": "…"}`, optional password) starts the export and returns the job. `GET /api/brains/{slug}/exports` lists the last ones with their state (`queued`, `running`, `failed`, `ready`, `downloaded`, `expired`). `GET /api/brains/{slug}/exports/{id}/download` gives the package once; after that, or once it expires, it answers 410. See [[REST API]].
