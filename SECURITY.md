**English** · [Español](docs/es/SECURITY.md)

# Security

## Supported versions
MimirSynth is in 0.x development: only the latest published version is fixed.

## Reporting a vulnerability
**Do not open a public issue.** Use GitHub's private advisory: *Security → Report a vulnerability* tab of this repository.

Include the steps to reproduce, the affected version and the impact you estimate. We will reply as soon as possible and coordinate disclosure with you.

## Deployment good practices
- Set a long, random `MIMIRSYNTH_SESSION_SECRET`; it signs sessions and encrypts stored secrets.
- Serve the application behind HTTPS and set `MIMIRSYNTH_COOKIE_SECURE=true`.
- Do not use `MIMIRSYNTH_AUTH_MODE=off` outside development: it disables sign-in.
- Require two-factor under Administration → Security.
- Do not expose FalkorDB or PostgreSQL outside the deployment network.
