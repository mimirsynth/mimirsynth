# Changelog

All notable changes to MimirSynth. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/) (0.x: the API and the schema may change between minor versions).

Releases publish a container image to `ghcr.io/mimirsynth/mimirsynth` (tags `X.Y.Z`, `X.Y`, `X` and `latest`; `linux/amd64` and `linux/arm64`).

## [Unreleased]

## [0.4.0] - 2026-10-25
### Changed
- Web toolchain moved to current majors: Vite 8, React 19, Mantine 9 and TypeScript 7. Node 26 for the web build stage.
- The i18n guard (`npm run i18n`) parses the sources with `oxc-parser` instead of the TypeScript compiler API.
- Release workflow actions updated (Docker buildx/QEMU/metadata/build-push v4–v7, build-provenance v4).
- Dependabot now proposes major updates, one pull request each; `graphiti-core` stays pinned.

## [0.3.1] - 2026-10-25
### Changed
- Installation uses only the official artefacts: each release attaches `docker-compose.yml` and `env.example`, and the Compose file no longer builds (`docker-compose.build.yml` is the contributor override). Documentation is written for users; building from source lives in `CONTRIBUTING.md`.

## [0.3.0] - 2026-10-25
First public release.

### Added
- Own user accounts (argon2id passwords, invitations and recovery by single-use link, lockout, first-start wizard), TOTP two-factor with recovery codes (optionally mandatory), optional SMTP email.
- OIDC sign-in as an optional, linked identity, with automatic sign-up by allowed domain and roles granted from provider groups.
- Administration reorganised into sectioned cards with side navigation; settings stored in the database and editable without a restart (secrets encrypted).
- Interface and server messages in English and Spanish, per-person and per-instance language, translated emails.
- Document memory: uploads, read-only folders and Outline wikis, hybrid search, recall integration and "promote to memory".
- Job queue with progress, cancel and retry; grouped scheduled rescans and automatic retention.
- Brains with per-brain roles, proposal quarantine with an optional decider, ontology packages, vocabulary tools (aliases, duplicates, type corrector).
- Hybrid recall (facts, episode text, documents) and API tokens for agents; Claude Code integration.
- Container image published to GHCR; Docker Compose uses it by default.

### Changed
- Documentation rewritten for users: README, `docs/` and a bilingual wiki.

### Security
- Sessions, secrets and credentials hardened (see `SECURITY.md`); the application refuses to start with the default session secret when sign-in is enabled.
