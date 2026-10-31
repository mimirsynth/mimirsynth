**English** · [Español](Carpetas-y-l%C3%ADmites)

# Folders and limits

Two sections of the **Documents** group of administration (instance administrator only).

## Folders (authorised roots)
Brain administrators can connect **server folders** as document sources ([[Knowledge]]). To keep it safe, they do not type free paths: they choose among the **authorised roots** you register here.

A root is a directory **under `/sources`**, which is the host folder Docker mounts **read-only** in the container (`MIMIRSYNTH_SOURCES_DIR`, `./sources` by default). MimirSynth **never writes** to them.

### Mounting the folders
In `.env`: `MIMIRSYNTH_SOURCES_DIR=/srv/documents` (the host folder). Inside it, each subfolder can be a root: `/sources/manuals`, `/sources/wiki-export`… What you mount **later** under that folder on the host (an NFS share, for example) **appears inside without a restart**.

### Registering a root
Add button:
- **Name:** short identifier (lowercase letters, digits, `_` and `-`, up to 40 characters). It is what brain administrators will see.
- **Path:** the path **inside the container**, under `/sources` (e.g. `/sources/manuals`).
- **Description:** optional.
The table shows for each root whether it is **available** (whether the directory exists) and how many **sources** use it. A root with sources cannot be deleted.

> **For safety**, the path must be under `/sources`: arbitrary paths are not accepted. An empty or unmounted folder in a *scheduled* scan **fails without deleting anything** (in case the volume was unmounted).

## Limits
Three settings that bound the size of what is uploaded or indexed:
| Setting | Default | Range | What it does |
|---|---|---|---|
| **Maximum file size** | 2048 MB | 1–20480 | Larger files are rejected when uploaded or when scanning folders |
| **Size of each upload part** | 64 MB | 1–64 | Uploads are sent in parts of this size. **Lower it if your proxy limits request size** |
| **Maximum text extracted per document** | 100 MB | 1–2048 | A document whose text exceeds this size is not indexed |

## Supported formats
Text and Markdown (`.md`, `.markdown`, `.txt`, `.rst`, `.log`), HTML (`.html`, `.htm`), PDF (`.pdf`) and Office (`.docx`, `.pptx`, `.xlsx` and `.odt`; not the old binary formats `.doc`, `.ppt` or `.xls`). A **scanned** PDF (image only, no text) contains no text to index.
- **Markdown and Obsidian:** a vault is just a folder of Markdown, so it is connected as a folder source. The YAML frontmatter is removed (its `title:` is used), wiki-style links (between double square brackets) keep their text, and embeds, `%%comments%%` and `^block` marks are dropped, also in files saved with Windows line endings. Hidden folders such as `.obsidian/` are ignored.
- **Repeated files:** a document whose text matches one already indexed in the brain (ignoring case and spacing), for example the same note in two folders, is marked **duplicate** and not indexed twice ([[Knowledge]]).
- **Secrets:** the brain's secret policy also applies to documents: with **Mask**, credentials are removed from the indexed text; with **Block**, a document that contains a certain one is not indexed. The original file is never modified ([[Connect agents]] explains the policies).
