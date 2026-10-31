**English** · [Español](Preguntas-frecuentes)

# Frequently asked questions

## General
**What is the difference with an ordinary vector database?**
A vector database returns similar texts. MimirSynth also extracts **facts with validity dates**, so it knows something *stopped being true* and does not hand you the old data as if it were current. And it keeps the original texts and the documents for detail.

**Do I need an LLM?**
To **ingest** (extract facts), yes. To **search**, no: recall uses no LLM. Embeddings do need an embedding model.

**Does it work with local models?**
Yes. Any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio…) works for LLM, embeddings and decider. Larger models extract better.

**Can I use it without the bundled FalkorDB?**
Yes, point `MIMIRSYNTH_FALKOR_HOST` at your FalkorDB. See [[Installation]].

**What is a brain and how many do I need?**
An isolated domain. One is enough to start; create more to separate teams, projects or people. See [[Concepts]].

## Writing
**My agent writes but I see nothing new.**
If it uses a contributor token, the proposal is **pending**: review it in [[Proposals]]. A proposal in which the secret detector flagged something also waits for a curator, whoever sent it. If it is already approved, check [[Jobs]] in case ingestion failed or no LLM is configured.

**Can I edit an episode?**
No, they are immutable. Correct the **fact** ([[Facts]]) or add a new episode that contradicts it.

**How do I delete something stored by mistake?**
Delete or invalidate the fact in [[Facts]]. If it was a secret, also consider **rotating the secret**: the original text remains in the episode and may have been sent to the extraction LLM. To prevent it, the secret detector masks or blocks credentials before a proposal is stored, depending on the brain's policy (see [[Proposals]]).

**Two facts that cannot both be true are current at the same time.**
Mark the relation as single-valued in the [[Ontology]] and resolve the case in [[Contradictions]], which also helps you measure which relations to mark.

**The system creates duplicate entities or odd relations.**
It is normal at the start. Define an [[Ontology]], unify with [[Relations and aliases]] and [[Merge duplicates]].

## Documents
**What formats are supported?** Markdown, text, HTML, PDF with text, and Office documents (`.docx`, `.pptx`, `.xlsx`, `.odt`). See [[Knowledge]].

**Can my wikis be indexed?** Yes, read-only: Outline, Confluence (Cloud and Data Center) and Notion. The Confluence and Notion adapters have not yet been validated against a live instance; Docmost is not supported yet. An Obsidian vault is indexed as a folder. See [[Document memory]].

**The same document is in two sources. Is it indexed twice?** No: the copy is marked as a duplicate and only the oldest one is indexed. **Find duplicates** in [[Knowledge]] checks documents indexed before this existed.

**Is a document turned into facts?** No; it is cited. To convert a passage, **promote it to memory**.

## Users and security
**How do I invite someone?** [[Administer users]]. With SMTP configured they receive an email; without it, you hand them the link.

**I lost my two-factor phone.** Use a recovery code or a passkey, or ask an administrator to reset it ([[My account]]).

**Can I use my identity provider (Google, Entra, Keycloak…)?** Yes, see [[OIDC identity]]. An account or invitation (or automatic sign-up by domain) is still needed.

**Does my data leave the server?** The texts of proposals are sent to the configured **LLM** to extract facts, and the texts to index go to the **embedding** model. With local models, nothing leaves. The secret detector masks or blocks credentials in proposals and documents before they are stored or indexed, but do not rely on it: keep secrets out of memory and store only where they are.

**What if I lose `MIMIRSYNTH_SESSION_SECRET`?** The secrets stored encrypted in the database can no longer be decrypted and must be entered again: provider keys, SMTP password, OIDC secrets, wiki keys and notification channel secrets. The authenticator-app secrets of two-factor are encrypted with it too, so those codes stop being accepted. Sessions are invalidated. The rest of the data is unaffected.

## Operation
**How do I upgrade?** [[Upgrade and backups]].

**How many resources does it need?** About 2 GB of RAM for the application, PostgreSQL and FalkorDB with moderate use. The LLM and embeddings are separate.

**Where is the installation code?** In the container log, while there is no administrator: `docker compose logs mimirsynth | grep -A3 "FIRST START"`.

**Is there an API?** Yes: the [[REST API]], and an MCP server with the `recall` and `remember` tools for agents ([[Connect agents]]).
