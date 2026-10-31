**English** · [Español](Importar-un-brain)

# Import a brain

Creates a **new brain** from a package made with [[Export a brain]], from this instance or another one. The other brains are not touched.

## How
**Administration → Brain access → Import a brain.** It needs the **instance administrator** (an API token can never import), and it is recorded in the [[Audit log]].

1. Click **Choose package** and pick the `.mimirsynth.tar.gz` (or `.tar.gz.enc`) file. It is uploaded in parts, so a proxy's size limit does not get in the way.
2. If the package is not encrypted, the card shows what its manifest says: the original brain, when and with which version it was exported, its counts, and what will happen with the graph and the vectors here.
3. Fill in the **slug** and the **name** of the new brain. Its graph gets the same name as the slug, so neither can exist already.
4. Choose what to import:
   - **Full:** the graph, the ontology and the vocabulary with their history, the type corrections, the reference queries, the proposals and the documents.
   - **Structure only:** the ontology and the aliases, as a template for a new brain. No graph, proposals or documents.
5. For a full import, **Fast restore (use the exact copy)** is off by default. Tick it only for a package you exported yourself (see [The graph](#the-graph)).
6. For an encrypted package, type its **password**.
7. Click **Import**. It runs as a job ([[Jobs]]) and the card shows its progress. When it is done, **Open** switches to the new brain.

Only one import runs at a time. An uploaded package that nobody imports is deleted after 24 hours.

## Checked before writing anything
The package comes from outside, so it is read in full and checked before anything is created:
- It holds only regular files (no links or folders), each one listed in the manifest, under the paths an export writes. A path with `..`, an absolute path or one that is not on that list rejects the package.
- Each file has the size and the `sha256` the manifest says, and every listed file is there.
- The manifest is a MimirSynth package with a format version this instance can read.
- The graph's labels and relation types are plain names, every relation joins two nodes of the package, and the number of nodes and relations matches the manifest.
- Each document only points to its own files, and the reused vectors have the dimension of the embedding model in use.

A package that fails any check is rejected with the reason, and nothing is written.

**The importer trusts nothing in the package except what it validated.** The checksums in the manifest come from the package itself, so they only catch a damaged file, not a tampered one; and encrypting a package does not make it trusted, because anyone with the password can make one. That is why the graph comes in through its JSON copy, which goes through every check above, and not through the exact copy, unless you ask for it.

## The graph
- By default the **JSON copy** goes in, in batches, and Graphiti's indices are created. It is the copy that was validated.
- **Fast restore** uses the **exact copy** (the dump) instead. It is faster on a large graph and keeps everything, indices included, but an exact copy is a FalkorDB payload that goes in as it is: it cannot be validated like the JSON copy. So it is only for packages you exported yourself, and even then what it restored is compared with the JSON copy: the labels and relation types with their counts, the property names and the uuids. If anything differs, the restored graph is dropped and the JSON copy goes in, and the card says so with the differences.
- Fast restore also falls back to the JSON copy when the package has no exact copy (it was left out because of a secret), when FalkorDB here is another version, or when the original graph exists in this instance (the exact copy carries its graph's name and can only be restored under it). The card says which.
- The `group_id` of every node and relation is set to the new brain's graph, as when a brain's graph is renamed in [[Brains and members]].

Agents that wrote to the original graph with Graphiti's `group_id` have to be pointed to the new one.

## The vectors
- **Same embedding model** and dimension as where it was exported: the vectors the package brings are reused (those of the graph and, if it was exported with **Include the vectors**, those of the search index). Only the missing ones are computed.
- **Another model:** all of them are computed again in the same job: Graphiti's in the graph, the episodes' index and the documents'. This calls the embedding engine for the whole brain, so it takes time.

## What the new brain gets
- **You are its owner.** Members, API tokens, AI engines and notification channels are not in the package: set them up here.
- **Proposals** keep their text and their review. Their author is you, and the names of the original author and reviewer stay in the proposal. One that was approved but not yet ingested goes back to **pending**: a curator decides again.
- **Documents** keep their metadata, their normalized text and, when the package brings it, their original. One without text is left with an error to reindex it. **Upload** sources come enabled; **folder and wiki** sources come **disabled** and without their credentials. Review their settings (the folder root must exist here) and enable them.
- The secrets policy and its exceptions are the original brain's.
- If the brain has [[Reference queries]], they are run once the import finishes. Compare the result with the last run of the original brain (it is in the package) to check that the recall is the same.

## If something fails
A failure at any point removes everything the import created: the brain, its graph, its rows, its files and its index. The job says why.

- **Wrong password:** the package stays uploaded, and **Try another password** on the card imports it again.
- **The service restarts in the middle:** the job fails saying so, and the next start removes what it had created. Upload the package again. The password, if there was one, only lived in memory.

## Limits
- The largest package is `MIMIRSYNTH_IMPORT_MAX_MB` (20,480 MB). The document store needs room for the package and for what it unpacks to.

## API
All instance administrator routes, under `/api/brain-imports`:
- `POST /uploads` (`{"filename", "size"}`) starts an upload; `PUT /uploads/{id}/parts/{n}` sends each part; `POST /uploads/{id}/complete` joins them and returns the manifest's summary (`null` for an encrypted package); `DELETE /uploads/{id}` discards it.
- `POST /api/brain-imports` (`{"upload_id", "slug", "name", "mode": "full" | "structure", "password", "dump": false}`) starts the import and returns the job; `dump: true` is fast restore.
- `GET /api/brain-imports` lists the last ones with their state, the graph's method and the counts.

See [[REST API]].
