**English** · [Español](Actualizaci%C3%B3n-y-copias-de-seguridad)

# Upgrade and backups

## Upgrading with `update.sh`
Every release attaches an update script that **backs up, updates and checks** in one step. Download it once into the folder that holds your `docker-compose.yml` and `.env`:
```bash
cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/update.sh && chmod +x update.sh
```
| Command | What it does |
|---|---|
| `./update.sh` | Updates to the latest stable release |
| `./update.sh --check` | Only reports what is running, what is configured and what the latest release is. Changes nothing |
| `./update.sh --version 0.8.0` | Updates (or goes) to a specific version; release candidates such as `0.8.0-rc.1` work too |
| `./update.sh --rollback` | Goes back to the version of the last backup. Add `--with-db` to restore the database too |

An update runs in this order:
1. **Download.** It pulls the new image first, so a wrong version or no network stops everything **before touching anything**, and the existing backup stays intact.
2. **Backup** into `./backup`: PostgreSQL, the documents volume, the bundled FalkorDB (if you use `--profile bundled`), your `docker-compose.yml` and your `.env`. **Only one backup is kept**: the previous one is replaced only once the new one has been written and checked, so backups never pile up.
3. **Update.** It pins `MIMIRSYNTH_VERSION` in `.env` and recreates only the application; database **migrations** run on start. It adopts the release's `docker-compose.yml` **only if yours is the unmodified one** of the version you were running; otherwise it keeps yours and tells you.
4. **Check.** It waits until the application answers with the new version and is healthy, shows the database revision and warns if the log has errors in the last minutes. If it does not verify, it tells you how to go back.

Other options: `--update-compose` always adopts the release's compose file, `--keep-compose` never touches it, `--no-files` skips the documents volume, `--backup-dir DIR` saves the backup elsewhere, `--yes` skips the confirmation of a rollback and `--force` reinstalls the same version. The script speaks Spanish when your `LANG` is Spanish.

> **If your `.env` says `MIMIRSYNTH_VERSION=latest`**, the script cannot tell which compose file you started from, so it keeps yours: compare it with the release's and use `--update-compose` if you have not changed it. If you keep your own compose file, check the release notes for lines to add by hand (for example, since 0.8.0 the `mimirsynth` service needs `extra_hosts: ["host.docker.internal:host-gateway"]` to reach Ollama on a Linux host).

### Going back
`./update.sh --rollback` puts back the `docker-compose.yml` and `.env` of the backup (so the previous image version) and checks that it answers. The files of the failed version are kept as `*.rolledback`. With `--with-db` it also **restores the database** from the backup: anything written since the backup is lost. The documents volume and FalkorDB are not restored automatically: their copies are in `./backup` if you need them (see [Restoring](#restoring)).

### Without the script
Take a backup (below) and then:
```bash
docker compose pull
docker compose --profile bundled up -d
```
Check it is still healthy: `docker compose ps` and `curl -s http://localhost:8000/api/health`. Read the [releases](https://github.com/MimirSynth/mimirsynth/releases) first in case one needs a manual step.

## What to save
Three things, which must be consistent with each other (take them at the same moment); `update.sh` saves all of them except an external FalkorDB:

| What | Contains | How |
|---|---|---|
| **PostgreSQL** | users, brains, members, proposals, audit log, settings, alerts, text and document indexes | `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql` |
| **`docstore` volume** | originals of the uploaded documents | copy of the volume (e.g. `docker run --rm -v mimirsynth_docstore:/d -v $PWD:/b busybox tar czf /b/docstore.tgz -C /d .`) |
| **FalkorDB** (`graphdata`) | the knowledge (episodes, entities, facts) | copy of the volume, or an RDB dump with `redis-cli` |

Also save your **`.env`**, and in particular `MIMIRSYNTH_SESSION_SECRET`: without it the provider keys, the SMTP password, the OIDC secrets and the notification channel secrets stored in the database cannot be decrypted (you would have to enter them again).

Volume names carry the Compose project prefix (normally the folder name); see them with `docker volume ls`.

## What can be rebuilt
- The **episode text index** is regenerated from the graph ("Reindex now" in [[Ask]]).
- The **document index** is regenerated from the originals in the store (reindex the document).
- It cannot be rebuilt: the graph itself, users and permissions, or uploaded files.

## Restoring
1. Install the same version (or a later one) with the same `.env`.
2. Start only the database: `docker compose up -d postgres`.
3. Restore the dump: `docker compose exec -T postgres psql -U mimirsynth mimirsynth < mimirsynth.sql` (from an `update.sh` backup: `gunzip -c backup/mimirsynth.sql.gz | docker compose exec -T postgres psql -U mimirsynth mimirsynth`).
4. Put the `docstore` and `graphdata` volumes back (`update.sh` leaves them as `docstore.tar.gz` and `falkordb-dump.rdb`).
5. Start everything: `docker compose --profile bundled up -d`.

## Good practices
- Automate the backup (cron or your system's scheduler) and **test a restore** from time to time.
- `update.sh` keeps only the last backup, inside the installation folder: **copy it off the server** if you need history.
- Always take a backup before upgrading, and before changing the embedding model ([[AI providers]]).
