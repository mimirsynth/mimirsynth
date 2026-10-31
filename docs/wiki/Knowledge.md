**English** · [Español](Conocimiento)

# Knowledge

The **document memory**: files and wiki pages that the brain keeps, splits into chunks and lets you search **by meaning and by text**. Unlike episodes, documents are **not turned into facts**: they are cited with their provenance. To understand the design, see [[Document memory]].

The screen has two tabs: **Documents** and **Sources**.

## Documents tab

### Searching
The search bar at the top accepts a natural-language sentence or keywords. Results are **passages** with their citation (document › section), a similarity indicator and three actions:
- **View context:** the neighbouring chunks of the same document.
- **Original:** downloads the file.
- **Promote to memory:** turns the passage into a [proposal](Proposals) (see below).

With no search you see the **table of documents**.

### Uploading files
Drag files into the upload area or press **Choose files**. Formats: **Markdown, text (`.md`, `.markdown`, `.txt`, `.rst`, `.log`), HTML (`.html`, `.htm`), PDF and Office (`.docx`, `.pptx`, `.xlsx`, `.odt`)**: Word and OpenDocument headings become headings, each slide starts with its title, each sheet with its name, and each table row goes on one line. You need at least the **contributor** role.
- Uploads are sent **in parts** and you can upload several at once; you see the state of each one and a **Clear list** button.
- The maximum size of a file and of each part is set by the administrator ([[Folders and limits]]).
- If you upload a file **identical** to one already uploaded, it is not stored again.

### The documents table
Columns: **Document** (title and file name), **Source**, **Size**, **Chunks**, **State** and **Updated**. You can sort by title, size, chunks and date, filter by title or file name, and filter by source (and, for a folder or wiki, by **Folder**). Above the table, the **State** selector has a counter per state:

| State | Meaning |
|---|---|
| Indexed | Ready to search |
| Indexing | Being chunked and embedded |
| Queued | Waiting its turn |
| Error | It failed (the reason appears in the detail) |
| Duplicate | Same text as another document of the brain: not indexed again (see below) |

### Duplicate documents
The same note can arrive twice: from two folders, from a folder and a wiki, or uploaded under another name. When a document's extracted text matches one already indexed in the brain (ignoring case and spacing), it is marked **Duplicate**: it is neither chunked nor embedded, and recall uses the original.
- The **Duplicate** state filter lists them, and the detail of a duplicate has **View the original**.
- If the original is deleted, leaves its source, changes or cannot be indexed, the **oldest duplicate** is indexed in its place. When two copies are indexed at the same time, the oldest always wins.
- **Find duplicates** (brain administrators), next to the filters, checks the documents indexed before this check existed and takes the repeated ones out of the index. It runs as a job with progress ([[Jobs]]) and says how many it took out. **Nothing is deleted at the source.**

### A document's detail
Clicking a document opens its panel:
- State, size and number of chunks; file name, hash (sha256) and upload date.
- **Secrets detected**, if the secret detector found credentials when indexing (see below).
- **Download original**, **View full text** (up to the first megabyte) and, for wikis, **Open in the wiki**.
- **Mentioned entities**: the graph entities whose name appears in the text. Each one opens the [[Graph]] focused on it.
- **Relations**: the graph facts that connect those entities («A —relation→ B», with the fact and the date it holds from). Only current facts by default; **Include facts that are no longer true** adds the invalidated ones, marked «no longer true». **Show more** loads more.
- The list of **chunks** (`#0`, `#1`…), each with its section and a button to **promote it to memory**.
- **Reindex** (brain administrators): re-chunks and recomputes the vectors.
- **Delete** (brain administrators, or the person who uploaded it): removes the original, the text and the chunks; it cannot be undone. Only uploaded documents can be deleted here: documents from a folder or a wiki are removed at their origin and disappear on the next scan.

### Secrets in documents
Before a document is chunked, the **secret detector** looks for credentials in its text (cloud and AI provider keys, tokens, private keys, passwords in URLs…). What happens depends on the brain's policy (Administration → Brain access → **Secrets**):
- **Mask** (the default): certain secrets are replaced in the indexed text, so they never reach the chunks, the vectors or recall.
- **Block**: the document is not indexed and stays in **Error**, saying which type of secret it contains.
- **Only warn**: nothing is changed, the findings are only reported.

The detail panel lists what was found. **The downloadable original is never modified**: it keeps the value as it was.

### Promote to memory
A relevant passage of a document can become **graph knowledge**:
1. Press **Promote to memory** on a chunk.
2. Edit the **text to remember**: it should be a **self-contained** statement.
3. Optional: give it a title.
4. **Send proposal.** If you are a curator, it is approved and the facts are extracted into the graph; otherwise it goes into quarantine.
The document does not change; the proposal carries the provenance (document and section).

## Sources tab
A **source** is where documents come from. There are three types: **Uploads** (the automatic source of the files you upload), **Folder** and **Wiki**. Each source shows its type, origin, its documents by state, its state and its last sync, with actions depending on your role.

### Folders (brain administrator)
A folder is a server directory, mounted **read-only**, whose files are indexed without copying them.
1. **Add folder.**
2. Choose the **authorised root**. Roots are registered by the instance administrator ([[Folders and limits]]); if there are none, the button is disabled and you will see a notice.
3. Optional: a **subfolder** inside the root. It is walked entirely, subfolders included; hidden files are ignored.
4. **Rescan every (minutes):** minimum 5; empty = only when you press **Scan**.
What a scan does: it detects **new, changed** (by size, date and hash) and **disappeared** files, and indexes only what is needed. A *scheduled* scan that finds the folder empty **fails without deleting anything** (in case the volume was unmounted); a *manual* one does empty the index.

An Obsidian vault is a folder of Markdown: add it as a folder. Its conventions (frontmatter, internal links, embeds, comments) are understood.

### Wikis (instance administrator)
Connect a wiki through its API, **read-only**, and its pages are indexed with a snapshot and a link to the original page.
1. **Add wiki.**
2. Choose the **Wiki type**:
   - **Outline:** the wiki URL and a **read-only API key**. Collections are Outline's collections.
   - **Confluence** (Cloud and Data Center): the Confluence URL (in Cloud it ends in `/wiki`), the email of the account that created the token (Cloud only; leave it empty in Data Center) and an **API token** (Cloud) or a **personal access token** with read permission (Data Center). Collections are **spaces**.
   - **Notion:** the token of an **internal integration** with read-only content access, shared with the pages or databases to index. Collections are the **databases** shared with the integration, plus one for **loose pages** that are not in a database.
3. Keys and tokens are stored **encrypted** and not shown again.
4. **Connect**: the connection is checked and the list of collections appears.
5. Tick the collections to index (at least one), give it a name and a **resync** interval (empty = manual).

> The Confluence and Notion adapters follow each API's documented format and are covered by tests, but **have not yet been validated against a live instance**. If you use one, check the result of the first scan and report any problem. Docmost is not supported yet.

On each sync only what changed is reindexed: pages are compared by modification date, and only new or changed ones are **downloaded** (this matters for Notion, where each page costs one request). Deleted or archived pages, and those in collections you untick, are removed. If the wiki fails halfway (expired key, outage, rate limit), the scan **stops without deleting anything**.

### Actions on a source
- **Scan**: now.
- **Edit**: name and interval; the subfolder of a folder. For a wiki, an instance administrator can also change **which collections are indexed** (the list is fetched with the stored credentials; at least one) and replace the key (empty = keep the stored one; a new one is checked before saving).
- **Pause** / **Resume**: stops and restarts scheduled scans.
- **Remove**: deletes the source and its indexed documents; the files of a folder and the pages of a wiki are not touched.

## How it shows up in recall
If a passage is really relevant (sufficient similarity), [[Ask]] and the API include up to **2 cited passages** in a "Documents" section, capped in size and time. Repeated text counts once, so the passages are always **different** ones. It can be disabled per request. See [[Recall and ingestion]].

> Document content is **data, not instructions**. A document may contain text that looks like an order to the agent; recall marks it as a quote from a source and your agent must treat it as such.
