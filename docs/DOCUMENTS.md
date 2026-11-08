**English** · [Español](es/DOCUMENTS.md)

# Document memory (design)

Status: **implemented** (uploads, folders, wikis and Git repositories; phases D1 to D5, see «Phases»). This page started as the design of the document memory and still records the decisions taken and the alternatives discarded; where the implementation ended up differing from the first design, the text describes what the code does today and says so.

## What it is and what it is not

MimirSynth has **episodic and semantic** memory (the temporal graph) and a text index of the episodes. The document memory adds memory of **what documents say**: manuals, wiki pages, notes, policies, READMEs. It is the *knowledge* of the CoALA model, queried by retrieval (RAG), not distilled into facts.

Principles:

1. **The document is the source of truth.** It is indexed and cited; it is not turned into graph facts. This avoids noise, duplicates and the cost of running an LLM over text that is already curated.
2. **Always with provenance.** Every returned passage carries source, title, link or path, section and last sync date. No citation, no answer.
3. **Per brain.** Documents belong to a brain just like facts: same roles, same isolation, same audit log.
4. **Content is data, not instructions.** A document may contain text that looks like an order to the agent; recall marks it as a quote from a source and never as an instruction.
5. **Environment-agnostic.** No specific names, addresses or systems in the code: sources are configured.

## Sources

A source is a connector that can **list** documents (with a stable identifier and a change marker) and **fetch their content**. There are four kinds:

| Kind | What it is | Configuration |
|---|---|---|
| **Wiki through its API** | Any wiki with a read API. Outline, Confluence and Notion are implemented (see «Wikis»); the connector is an adapter with a small interface, so others can be added without touching the rest | Depends on the adapter (usually a URL and a token, with the secrets encrypted with `secretbox`) plus the collections to index |
| **Folder of files** | A folder mounted **read-only** with `.md`, `.markdown`, `.txt`, `.rst`, `.log`, `.html`, `.htm`, `.pdf`, `.docx`, `.pptx`, `.xlsx` and `.odt` files (and `.png`, `.jpg` and `.jpeg` when OCR is configured), in subfolders. Originals are **referenced where they are**, not copied | An authorised root and a subfolder inside it (see «Folders and job queue») |
| **Git repository** | The documents of a repository (README, `docs/`, ADRs, changelog), synced by commit (see «Git repositories») | The address, the branch (empty = the default one), the paths to include and, for a private repository, a read-only token (encrypted with `secretbox`) |
| **Upload from the UI** | Files dragged into the browser, of any size (chunked upload) | None; each brain has one «Uploads» source and the original goes to the file store |

Possible later, without changing the design: crawling a URL, object storage.

## Data model

Control plane (PostgreSQL, Alembic migrations):

- `doc_sources`: `id`, `brain_id`, `kind` (`wiki` | `directory` | `git` | `upload`), `name` (unique per brain), `config` (JSON; secrets encrypted), `enabled` (a source can be paused), `sync_interval` (minutes, empty = manual only), `status`, `last_sync_at`, `last_error`, `created_by`.
- `documents`: `id`, `brain_id`, `source_id`, `external_id` (the relative path in a folder or a repository, the page id in a wiki), `title`, `filename`, `url`, `mime`, `size`, `sha256`, `norm_hash` (fingerprint of the extracted text, used to detect duplicates), `storage_ref` (where the original is, see «File store»), `text_ref` (the normalised text the chunks point into), `source_updated_at`, `status` (`pending` | `indexing` | `active` | `duplicate` | `error`), `error`, `chunks`, `meta` (collection, detected secrets, the original of a duplicate…), `first_seen_at`, `last_seen_at`. Unique on `(source_id, external_id)`.
- Background work goes to the general `jobs` table (see «Folders and job queue»). *The `doc_jobs` table of the first design was never created.*

Index (like `episode_chunks`: pgvector tables created by the index module, with the same embedding dimension):

- `doc_chunks`: `document_id`, `brain_id`, `chunk_idx`, `heading_path` (the path of headings, e.g. «Installation › Requirements»), `char_start` and `char_end` (the chunk's position in the normalised text), `page` (when the source has pages, as a PDF does), `text`, `content_hash`, `embedding`, `tsv` (full text). GIN and HNSW indexes.

**The database does not hold the files.** It keeps the reference to the original, the chunked text and its vectors, and every chunk points by position into the full document. Whoever receives a passage can ask for the surrounding context or the whole file.

## File store

Originals live on a **stack volume** mounted by the application (`MIMIRSYNTH_DOC_STORE`, `/data/documents` by default), not in PostgreSQL. That way there is no practical size limit and the database stays small.

```
<store>/<brain>/<source>/<document>/
    <sha256>.<ext>        the original file (uploads) or the snapshot (wiki page, file of a repository at a commit), immutable
    <sha256>.norm.txt     the normalised text that char_start/char_end point into
```

- **Paths are generated by the server** from ids, never from a user-supplied name: the original name is only kept as metadata.
- **Chunked upload:** the browser sends the file in parts (at most 64 MB per request, adjustable downwards, because proxies in front of the application often limit the body size) that the server writes to disk as a stream, without loading them into memory. The maximum file size is set under Administration → Limits (default `MIMIRSYNTH_DOC_MAX_MB`, 2048 MB). Uploads left half-way are removed after 24 hours. Uploading a file identical (same `sha256`) to one already in the brain returns the existing document instead of storing it twice.
- **Folder:** nothing is copied. The original is read from its path inside the read-only mounted root; only the normalised text is written to the store. If the file disappears, the next scan removes the document from the index.
- **Wiki:** a snapshot of each page (Markdown, or HTML for wikis that deliver HTML) is stored, so it can be re-chunked without fetching it again and cited even if the wiki is down.
- **Content change:** the new version is written and indexed first; only then is the old one removed, so a document is never left without an original.
- **Integrity:** the `sha256` is computed on upload and whenever a folder file changes. *The first design planned a maintenance job to find orphan files and rows whose file is missing; it does not exist yet.* A document whose original has disappeared answers 404 when downloaded.
- **Rebuildable:** the index (`doc_chunks`) can be regenerated entirely from the store, as the episode index can from the graph. **The volume is the source of truth and goes into backups together with PostgreSQL.**
- **`docker compose`:** a named volume for the store and a single read-only bind for the folders to index (see «Folders and job queue»).

## Ingestion pipeline

1. **Discover:** the connector lists the source's documents.
2. **Compare:** decide what is new, changed, equal or gone. A folder compares size and modification date and only computes the `sha256` of what changed; a wiki compares each page's modification date and title. Equal documents are not touched.
3. **Extract:** Markdown, text, HTML, RST, PDF and Office (`.docx`, `.pptx`, `.xlsx`, `.odt`) to normalised text keeping the heading structure (stored next to the original). Office files are read with the standard library (they are zip files with XML): Word and OpenDocument headings become `#` headings, each slide starts with its title (or its number), each sheet with its name, and a table row goes on one line with its cells separated by « | ». Before reading, a file that declares more than 5,000 entries or 512 MB uncompressed is rejected (a zip bomb), and so is an XML part with a DOCTYPE or an entity declaration. The old binary formats (`.doc`, `.ppt`, `.xls`) are not read. PDF needs `pypdf`, the optional `pdf` extra, which the container image includes. A PDF, PNG or JPEG is recognised by its first bytes, whatever its extension says; the pages of a PDF with no text, and images, are read with OCR (see «OCR»). A document whose text exceeds the configured maximum (100 MB by default, under Administration → Limits) is not indexed.
4. **Secrets:** before chunking, the secret detector masks anything shaped like a credential, or leaves the document unindexed if the brain blocks them (see «Security»).
5. **Chunk:** by headings and paragraphs (~900 characters with a 120-character overlap, like the episodes), recording the heading path and each chunk's position in the text.
   - **Duplicates:** if the extracted text (ignoring case and spacing, the same rule recall uses to skip repeated passages) is already indexed in another document of the brain, the document is marked `duplicate`, points to the oldest one and is neither chunked nor embedded. It is listed in Knowledge with its own status filter and a link to the original. If the original is deleted, leaves its source, its text changes or it cannot be indexed, the oldest duplicate gets indexed in its place. Deduplication is per brain; across brains, federation already labels the origin. When two copies are indexed at the same time, or an older one is reindexed, the oldest always wins. **Find duplicates** (brain administrators) checks documents indexed before this existed, from their normalised text and without extracting them again, as a job with progress; nothing is deleted at the source.
6. **Embed:** in batches, with the configured embedding engine, respecting its rate limit.
7. **Replace:** a changed document's chunks are replaced in a single transaction, so a query never sees a half-indexed document.
8. **Retire:** a document that is no longer in the source is removed from the index and from the database, together with its stored text; the scan's job records how many were removed. *The first design kept the record as `deleted` for history; the implementation removes it.*

It is idempotent and resumable: if it fails half-way, the next run carries on. It runs in the background with visible progress (see «Folders and job queue»). Changing the embedding model requires an explicit reindex (Administration → Embeddings).

## OCR

Scanned PDFs and images (#135). Tesseract runs in a separate service (`ocr/` in the repository, image `mimirsynth-ocr`, the `ocr` profile of the compose file), which MimirSynth calls over HTTP when `MIMIRSYNTH_OCR_URL` is set; the main image does not change.
- **Which pages:** those of a PDF that `pypdf` leaves without text (fewer than 16 letters or digits), so a mixed PDF only sends its scanned pages. At most *OCR pages per document* (50); the rest stay empty and the document says how many.
- **The protocol:** the service answers with one JSON line per page as it reads them. The indexing job shows the progress and, when it is cancelled, closes the connection, which stops the service between pages. A page that fails does not lose the rest.
- **Citations:** each page is one page of the normalised text, and a chunk never spans two pages, so the recall cites the right page.
- **Secrets:** the text read goes through the secret detector like any other.
- **Without OCR:** a scanned PDF or an image fails with an error that says how to enable it; a mixed PDF is indexed with its text pages and says how many it could not read. Folders and repositories only bring images in when OCR is configured, so that a documentation folder's diagrams do not fill the list with errors.
- **Vision model:** a brain can turn on the vision model of an LLM engine (*OCR vision engine*, empty: the default one) instead of Tesseract, with Tesseract taking over the pages the model cannot read. The service still turns PDF pages into images; a lone image goes to the model directly. Its calls count as the brain's AI usage under «Document OCR».

## Retrieval

- **Own search:** `GET /api/brains/{slug}/docs/search?q=…`, hybrid (full text + vectors, RRF fusion) like episode recall. It returns passages with their citation.
- **Recall integration, without making it expensive:** the agent context gains a «Documents» section, but only when it adds value.
  - **Hard budget:** at most 2 passages (adjustable under Administration → Recall) of ~1,000 characters (about 600 tokens in total), always cited.
  - **Only if relevant:** below a similarity threshold (0.66 by default, calibrated for `nomic-embed-text`; it depends on the embedding model) nothing is added, unless the passage comes close and also matches at least two terms of the query. A query unrelated to documents spends no tokens.
  - **No repeats:** a passage whose text matches one already chosen (the same content in two documents, or in a source that lends its documents) is skipped, so the budget goes to different passages.
  - **No slowdown:** the document search runs in parallel with the facts and episodes search, with its own maximum time (0.6 s by default); if it overruns, the section is omitted rather than delaying the answer.
  - **Can be disabled** per request (`docs: 0` in `recall`), and the agent can ask later for the full document or the extended context of a passage, only when it needs it (`GET /docs/{id}/context?chunk=…`, `GET /docs/{id}/file`).
  - Facts, episode fragments and documents are shown separately: they are different kinds of evidence.
- **Kept apart from the graph** except for two optional bridges, both implemented in phase D5 (see «Bridges with the graph»):
  - **Entity links:** which graph entities each document mentions (by name match, no LLM), to navigate from an entity to its documents and back.
  - **Promote to memory:** from a passage, a button creates a **quarantined proposal** (the usual queue) so that, if it deserves to be a fact, it goes through the normal ingestion path.

## Permissions and audit

| Action | Minimum role |
|---|---|
| Search and read documents, download the original, see the jobs | reader |
| Upload files; promote a passage to memory | contributor |
| Delete an uploaded document | whoever uploaded it, or a brain administrator |
| Cancel or retry a job | curator |
| Add, edit, pause, scan or remove sources; reindex a document; find duplicates | brain administrator |
| Register folder roots; connect a wiki or change its connection and collections; connect a Git repository or change its branch, paths or token | instance administrator (not with an API token) |

Only uploaded documents can be deleted one by one: a folder or wiki document would come back on the next scan, so it is removed at its origin or by removing the source. Everything is audited (which source, who, how many documents). Removing a source asks for confirmation and deletes its documents and chunks from the index; the files in the folder and the pages in the wiki are untouched.

**Federation** ([FEDERATION.md](FEDERATION.md)) treats documents as a resource granted separately from the graph («graph only», «documents only», «both»).

## Security

- **Folder:** the instance administrator registers the roots under Administration → Folders, always under the read-only bind `/sources`; a brain administrator only picks a root and a subfolder inside it. Never an arbitrary path, and symbolic links that leave the folder are not followed.
- **Wiki:** only instance administrators set the URL and the credentials, since the server makes requests to the address it is given. Private networks are allowed (normal for self-hosting). *The switch to forbid them that the first design mentioned does not exist.*
- **Git repository:** the same rule as a wiki (instance administrators only), and git runs fenced in: only `https` and `http`, no user or password in the address, the token only over https and in a header passed in the environment, without the system's or the user's git configuration, without hooks, links, submodules or Git LFS. Like a wiki, the server connects to whatever http(s) address the instance administrator gives, internal ones included: that is the intended use, and there is no outbound allow-list. See «Git repositories».
- **Uploads:** size limit; only the supported extensions are accepted, and a text file whose content turns out to be binary is rejected at extraction; HTML is reduced to text. The original is only returned to someone with read permission on the brain, with `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`; nothing is executed or served as a page.
- **Secrets:** encrypted with the same `secretbox` as the engine keys; never returned by the API (it only says which ones are set).
- **Credentials inside a document:** before chunking, the secret detector masks anything shaped like a credential in the indexed text, or leaves the document unindexed (in `error`) if the brain blocks them. The original is not modified. See «Secrets» in [ARCHITECTURE.md](ARCHITECTURE.md).

## Interface

A **Knowledge** tab, built only with the component kit:

- Search bar with results (highlighted passage, citation and link).
- Table of **sources**: kind, status, last scan, number of documents, «Scan», edit, pause, remove.
- Table of **documents**: title, source, updated, chunks, status (duplicates included, with a link to the original) and the error if any; filters by text, source, status and folder.
- **Upload** area (drag and drop) with progress per file.
- Document detail with its chunks and heading path, the full text, the original, the entities it mentions and the relations between them, and «Promote to memory».

## Phases

1. **D1 — Upload and search (done, 2026-10-23).** Schema, upload from the UI, extraction, chunking, embeddings, hybrid search and the minimal tab. The smallest slice that already works end to end, without connectors.
2. **D2 — Recall (done, 2026-10-23).** The «Documents» section in the agents' context and in the hook.
3. **D3 — Folder (done, 2026-10-23).** Folder sources with rescans, and the general job queue (see «Folders and job queue»).
4. **D4 — Wiki (done, 2026-10-23).** The adapter interface (`wikis.py`) and the Outline implementation, with incremental sync by modification date (see «Wikis»). Confluence and Notion came later, in 0.7.0.
5. **D5 — Bridges with the graph (done, 2026-10-23).** Mentioned entities, documents that mention an entity and «promote to memory» (see «Bridges with the graph»).

## Decisions

Taken on 2026-10-23:

1. **Originals:** on a stack volume, never in PostgreSQL. The database keeps the reference, the chunked text and the vectors.
2. **Formats of the first version:** Markdown, text, HTML and RST; PDF as an optional extra. *Today PDF is read whenever `pypdf` is installed, as it is in the container image.*
3. **Documents in recall by default:** yes, with a hard budget, a relevance threshold and a maximum time (see «Retrieval»).
4. **Synchronisation:** manual for now, with an optional per-source interval later. *The interval now exists: 5 minutes or more, or empty for manual only.*
5. **Previous versions of chunks:** not kept; only the current document can be queried.

Studied, not implemented:

6. **Importing the content of an earlier memory service** (for example, another memory service for agents). What such a service holds is usually short agent notes, not documents with a file or URL. It would be treated as one more source of kind «notes» (each note a small document), indexed with embeddings only, without going through LLM extraction, and labelled as an archive with its date so that recall can give it less weight than what is current.

## Folders and job queue

**General queue (`jobs`).** Everything the application does in the background is recorded in a `jobs` table (kind, status, progress, log, result, attempts, who started it) and runs in a pool bounded per kind. Current kinds: `proposal.ingest`, `doc.index`, `doc.scan`, `doc.dedupe`, `retype.scan`, `conflicts.scan`, `refquery.run`, `embedding.reindex` and `embedding.switch`. Statuses: queued, running, done, failed, cancelled. The **Jobs** screen (reader or above) lists, filters and shows the detail; curator or above can cancel and retry. On start, whatever was half-way is marked as interrupted and the idempotent kinds (`doc.index`, `doc.scan`, `embedding.reindex`) are relaunched by themselves. Finished jobs are kept 60 days, and scheduled rescans that ended without incident 7 days (both adjustable under Administration → Ingestion and jobs). Handlers are registered with `@jobs.register(kind, label, limit, resume)` and receive a `JobCtx` (`progress`, `note`, `retrying`, `check` for cancellation). Left out for now: the periodic sync of the episode index (every 10 min, not a user action) and the decider's triage (instant).

**Folder source.** The compose file mounts a single read-only bind (`MIMIRSYNTH_SOURCES_DIR` on the host → `/sources`, with `rslave` propagation: whatever is mounted underneath on the host appears without a restart). The instance administrator registers the roots under Administration → Folders (table `doc_roots`); only paths under `/sources` are valid. Nothing is ever written to them. A source is a root plus a subfolder (which cannot leave the root). Originals **are not copied**: the database keeps the relative path (`external_id`) and the store only the normalised text. Hidden files and folders, symbolic links that leave the folder, empty files and anything that is not a supported format or exceeds the maximum size are ignored. A rescan compares size and date, only computes the `sha256` of what changed, indexes what is new or modified and removes what disappeared.

Protection: if the folder is not available, the scan fails without deleting anything; if it appears empty while the source had documents, a scheduled scan fails too (it could be an unmounted volume) and only a manual one, which is an explicit order, empties the index. A folder document cannot be deleted on its own (it would come back): the source is removed, and the files in the folder are untouched. Automatic rescan with a per-source interval (minimum 5 min) or manual.

## Wikis

A `wiki` source reads a wiki's pages through its API, read-only, and treats them like any other document (chunking, index, recall, job queue). The implementations are Outline (`wikis.Outline`, measured against a live instance), Confluence (Cloud and Data Center) and Notion (`wikis.Confluence`, `wikis.Notion`). The last two are written against each API's documented format and covered by tests with simulated responses, **not yet validated against a live instance**: if you use one, check the first scan and report any problem. Docmost has no documented public API to build on yet and is left unwritten.

- **Connection:** the fields each adapter declares (for Outline, the instance URL and an API key). Secrets are stored encrypted (`secretbox`) and never returned by the API. For Outline, a key limited to `documents.list` and `collections.list` is recommended. The collections to index are chosen after the connection is checked, and can be changed later under Knowledge → Sources → Edit with the stored credentials; leaving a secret field blank keeps the stored one.
- **Only the instance administrator** connects or changes a wiki (never with an API token): the server makes requests to the URL it is given.
- **Incremental sync:** each page's modification date and title are compared; only what changed is fetched, hashed and reindexed. Deleted, archived or unpublished pages are removed. The «original» is a snapshot of the page (with its title as a heading) kept in the store; the document keeps the page's URL so it can be opened in the wiki. An empty page is not indexed.
- **Protection:** if the wiki fails half-way (expired key, outage, rate limit), the exception stops the scan and nothing is deleted. If it returns zero pages while the source has documents, a scheduled scan fails; only a manual one empties the index. Retries on rate limits (429) honour `Retry-After`.
- **Measured against a live Outline instance** (at design time): 170 pages, 527,000 characters (~1,200 chunks), listed in 1.4 s.

### How to add another wiki

An adapter is a class in `wikis.py` registered with `@register`. It describes itself and the interface builds the form from that description: no UI changes are needed.

```python
@register
class Confluence(Adapter):
    id, label, collection_label = "confluence", "Confluence", "Spaces"
    fields = [Field("base_url", "URL"), Field("email", "Email"), Field("token", "API token", secret=True)]
    def collections(self): ...            # [{id, name, description}]
    def documents(self, ids): ...         # yield WikiDoc(id, title, content, updated_at, url, collection, format="markdown"|"html")
```

A `WikiDoc.content` may be a function instead of a string: the scan calls it only for pages that are new or changed, so adapters whose content costs one request per page (Notion) do not download everything on every scan.

Contract rules: read-only; stateless; `updated_at` is the page's last modification date (it decides whether to reindex); `format` is `markdown` or `html` (the extractor reads both, so Confluence can return its HTML as is); a connection or permission error is raised as `WikiError` with a readable message, and cutting the list half-way never deletes anything. Everything else (encryption of `secret` fields, collection selection, incremental sync, snapshot of the original, progress in Jobs, protection against emptying) is common. The configuration is stored as `{adapter, settings, secrets (encrypted), collection_ids}`.

**Adapter status**
- **Outline:** done and tested against a live instance.
- **Obsidian:** needs no adapter. A vault is a folder of Markdown: use it as a folder source. The extractor understands its conventions: it strips the YAML frontmatter (using its `title:`), keeps the text of `[[links]]` and `[[target|alias]]`, and drops `![[embeds]]`, `%%comments%%` and `^block` marks, also with Windows line endings. `.obsidian/` is ignored because it is hidden.
- **Confluence (Cloud and Data Center) and Notion:** written against each API's documented format and covered by tests with simulated responses; **not yet validated against a live instance**. Confluence uses the REST v1 API (`/rest/api`): Cloud with email + API token, Data Center with a personal access token and no email; collections are spaces and pages come as HTML (`body.storage`). Notion has no spaces: the collections are the databases shared with the integration plus «Loose pages»; each page's blocks are converted to Markdown and its content is only fetched when the modification date changed.
- **Docmost:** not written; its public API is not documented in a stable way. It will be added when it is, or when a test instance is available.

## Git repositories

A `git` source (#118) indexes the documents of a repository: by default the `README*` and `CHANGELOG*` at its root, everything under `docs/` and any `adr/` folder. Mounting a clone as a folder and pulling it from cron still works; this source adds what that cannot: sync by commit, a citation that points to the file at the indexed commit, and a read-only token kept by the instance instead of in a cron job.

- **Connection:** the address (https, or http without a token), the branch (empty = the repository's default branch), the paths and, for a private repository, a read-only token (with a user, for the forges that ask for one: Bitbucket, Gitea). The repository is checked with `git ls-remote` before saving. Only the instance administrator connects it or changes its branch, paths or token; a brain administrator can rename it, change its interval, pause it or remove it.
- **What is read:** a shallow, blobless clone (`--depth 1 --filter=blob:none --no-checkout`) kept in the store at `<store>/<brain>/<source>/_git`. The tree is listed **without sizes** (asking for a size downloads the content) and the files are chosen by path; then only the chosen files that are **new or changed** (by their blob) are downloaded, with a sparse checkout of exactly those paths. Measured on this project's own repository: 138 documents, a 1.8 MB clone.
- **Choosing the files:** the paths are patterns from the root where `*` stays inside one folder and `**` crosses folders. A path without `*` or `?` in its last part also takes everything inside it as a folder, as in `.gitignore`: `Fullstack` and `Fullstack/` are `Fullstack/**`. Names are compared without case, and the same accented name matches however it was typed or committed; `Articulos` still does not match `Artículos`. Only the document types the index reads come in; hidden files and folders and the names that hold credentials by nature (`.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `credentials*`, `*.tfstate*`…) never do, whatever the patterns say; links and submodules are skipped. Everything still goes through the secret detector when it is indexed.
- **Sync by commit:** with no new commit, a scheduled scan reads nothing. Otherwise the unchanged files keep their document, the changed ones are reindexed, and the ones gone from the paths leave the index. Each document keeps the repository, the path, the commit and the blob, and its link points to the file at that commit in the forge (GitHub, GitLab, Bitbucket, Gitea, Forgejo and Codeberg are recognised from the address; any other gets the GitHub form).
- **Limits:** at most 2,000 files selected and 200 MB downloaded in one sync (otherwise the scan fails and asks to narrow the paths); a file above the maximum document size is left out.
- **Paths that select nothing:** saving a source refuses them and names the repository's top-level folders, after reading its trees in a throwaway clone (no contents; if that takes more than a minute, saving goes on). A sync whose paths select no file fails with the same message instead of finishing with 0 files, and the edit form shows how many files each path took at the last read.
- **Protection:** if git fails (address, token, network), or the paths select too many files, the scan fails and deletes nothing. If the paths select nothing while the source has documents, a scheduled scan fails too; only a manual one empties the index. Changing the branch or the paths makes the next scan read the whole tree again. Removing the source deletes its clone; the repository itself is never touched.
- **Container image:** it includes `git`.

## Bridges with the graph

The document is still the source of truth; linking is pointing, and nothing is written to the graph.

- **Mentioned entities** (`GET /docs/{id}/entities`): the names and aliases of the graph's live entities are looked for in the document's text (whole word, case-insensitive; merged entities do not count, and their old name works as an alias of the surviving one). No LLM and no new tables: the entity list is cached for a minute and the matches are computed when the document is opened, so they are always up to date. Names shorter than 4 characters (except 3-letter uppercase acronyms) and numeric names are ignored. In Knowledge, each entity in the detail leads to the Graph centred on it (`/grafo?nodo=<uuid>`).
- **Relations between them** (same route): the graph already knows how the mentioned entities relate. With a single query (`MATCH (a)-[r:RELATES_TO]->(b)` between the detected entities, no LLM or embeddings) the viewer shows «A —relation→ B» with the fact and the date it holds from. Only current facts by default; `expired=true` adds the ones that are no longer true (`expired_count` says how many there are) and `relations=N` limits how many are returned (`total` counts those that match the filter). The brain's relation aliases are applied to the name. Only the brain's own graph: what other brains lend (see [FEDERATION.md](FEDERATION.md)) does not come in here. If the graph fails, the viewer still shows the entities.
- **Documents that mention an entity** (`GET /docs/mentions?entity=<uuid>`): a phrase search in the full-text index with the name and aliases; it returns the document, how many passages match and the best highlighted snippet. It appears in an entity's panel on the Graph screen, with a link to the document (`/conocimiento?doc=<id>`).
- **Promote to memory** (`POST /docs/{id}/promote`): turns a passage (as is, or edited by whoever promotes it) into a proposal with its provenance («Source: title, section, URL»), confidence 0.7 and, as reference date, the page's or file's date. It goes through the normal flow: a contributor leaves it in quarantine, a curator approves it and facts are extracted with Graphiti. The same passage cannot be promoted twice (409 with the existing proposal).
