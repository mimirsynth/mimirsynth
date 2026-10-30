**English** · [Español](HTTPS-y-proxy-inverso)

# HTTPS and reverse proxy

Do not publish MimirSynth's port directly to the Internet without TLS: passwords, session cookies and API tokens would travel in clear. Put a **reverse proxy** (Caddy, Traefik, nginx, a tunnel…) in front that terminates HTTPS. HTTPS is also **required for passkeys**: browsers only offer them on a secure origin.

## MimirSynth settings
In `.env`:
```bash
MIMIRSYNTH_PUBLIC_URL=https://mimirsynth.example.com
MIMIRSYNTH_COOKIE_SECURE=true
```
- `PUBLIC_URL` is used to build the OIDC sign-in return URL and the invitation and recovery links. Its domain is also the **passkeys' relying-party ID**: a passkey only works on the domain it was created on, so set the final address before anyone registers one; changing the domain later invalidates them (people keep their password as a fallback). It can also be set under *Administration → Identity*.
- `COOKIE_SECURE=true` makes the session cookie travel only over HTTPS.

## Example with Caddy
```
mimirsynth.example.com {
    reverse_proxy localhost:8000
}
```
Caddy obtains and renews the certificate by itself.

## Example with nginx
```nginx
server {
    server_name mimirsynth.example.com;
    client_max_body_size 100m;          # see the note on uploads
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    # listen 443 ssl; ssl_certificate ...; (certificate of your choice)
}
```

## Uploading large files
The interface uploads files **in parts** (64 MB at most by default) so proxies with a request-size limit do not reject them. If your proxy limits requests to less than that, lower "Size of each upload part" under *Administration → Limits* (see [[Folders and limits]]). The maximum file size is adjusted there too.

## Forwarding headers
MimirSynth uses `X-Forwarded-For` to limit sign-in attempts per IP address (password, two-factor and passkeys). Make sure your proxy sends it and that you do **not** accept that header from external clients without going through the proxy.

## Agents and monitors
- Agents connect to the public address: `https://mimirsynth.example.com/api/brains/<slug>/mcp` for MCP, `…/recall` and `…/proposals` for HTTP ([[Connect agents]]). The MCP server refuses requests that a browser sends from another origin; agent clients do not send one, so nothing needs configuring.
- An external monitor on another machine should check `https://mimirsynth.example.com/api/health` through the proxy ([Monitoring the instance](Installation#monitoring-the-instance)).

## What not to expose
- **FalkorDB** and **PostgreSQL** must not be reachable from outside the deployment network. The included Compose does not publish their ports: leave it that way.
- The API's interactive documentation (`/docs`) is reachable by anyone who reaches the application; the data is still protected by authentication.
