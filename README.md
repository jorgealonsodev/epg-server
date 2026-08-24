# epg-rewriter

Downloads a public XMLTV guide, rewrites its channel names to match an IPTV
playlist, and serves the result over HTTP.

**It never contacts the IPTV provider.** Channel names are read from a local
`channels.txt`, so no credentials ever enter the container and the provider
sees no extra connections.

## Why it rewrites instead of renaming

The relation between guide and playlist is 1:N, not 1:1. One guide channel
typically backs several playlist variants:

```
M+LaLigaTV.es  ->  M+ LaLigaTV, M+ LaLigaTV 4K, M+ LaLigaTV FULL HD,
                   M+ LaLigaTVHD, M+ LaLigaTVHD+, M+ LaLigaTVSD
```

A `<channel>` can hold only one id, so renaming fixes one variant and orphans
the rest. Each matched channel is therefore duplicated once per variant, with
its programmes copied along.

## Quick start

```bash
docker compose up -d --build
curl -o guide.xml.gz http://localhost:29956/epg.xml.gz
```

Point the player's guide URL at `http://<host>:29956/epg.xml.gz` and leave the
playlist URL exactly as it is.

## Endpoints

| Path | Purpose |
|---|---|
| `/epg.xml.gz` | The rewritten guide (gzip). Use this one. |
| `/epg.xml` | Same, uncompressed. |
| `/status` | Match counts and the full unmatched list. Restricted. |
| `/health` | 200 once a guide is available. |
| `/refresh` | Trigger a rebuild without restarting. Restricted. |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `EPG_SOURCES` | iptv-epg.org ES | Comma-separated. More sources lift the ceiling. |
| `REFRESH_HOURS` | `3` | Matches the upstream regeneration cycle. Reading faster gains nothing; slower lags behind schedule corrections. Accepts fractions. |
| `FUZZY_CUTOFF` | `0.92` | Raise it for stricter matching. |
| `CHANNELS_FILE` | `/data/channels.txt` | Names only, one per line. |
| `GUIDE_TOKEN` | unset | Gates the guide URL. Carried in the URL, not a header. |
| `ADMIN_TOKEN` | unset | Gates `/status` and `/refresh`. Sent as a header. |

## Exposing this publicly

Scanning is unavoidable: any reachable address is probed continuously by
automated traffic. What matters is that a probe gains nothing.

`/epg.xml.gz` and `/health` are open. `/status` is not — it lists every channel
name — and neither is `/refresh`, which would let an anonymous caller trigger
downloads in a loop. Both answer 404 rather than 403, since a refusal confirms
the endpoint exists. `/` returns three lines and no inventory.

### Gating the guide URL

An IPTV player accepts a bare URL and cannot send headers, so the guide can only
be gated by something the URL itself carries. Set `GUIDE_TOKEN` and use either
form — they are equivalent:

```
https://<host>/<GUIDE_TOKEN>/epg.xml.gz
https://<host>/epg.xml.gz?token=<GUIDE_TOKEN>
```

Everything else then answers 404 without it, including `/`, so a scanner learns
nothing. `/health` stays exempt: the container healthcheck calls it with no
token and it reveals only whether a guide exists.

Serve this over TLS. The token sits in the URL, so plain HTTP exposes it to
anyone on the path, and URLs leak through logs, history and `Referer` headers.
Treat it as a bearer secret: whoever holds the URL has the guide.

### Gating /status and /refresh

By default the restricted endpoints accept private and loopback callers only.
Behind a reverse proxy that check is useless, because every request then carries
the proxy's own private address — so set `ADMIN_TOKEN`, which switches the check
to the token alone and ignores the source address:

```bash
curl -H "X-Admin-Token: $ADMIN_TOKEN" http://<host>:29956/status
```

If the player lives on the same LAN, the stronger option is not to publish the
port to the internet at all.

## channels.txt

One channel name per line, exactly as the playlist spells it. A comment is `#`
followed by a space — a bare `#` starts a real channel name in the wild
(`#DAZN 1 FULL HD`) and is preserved.

Regenerate it when the provider adds or renames channels. Names only: keep URLs
and credentials out of this file.

The list lives in the `epg-data` named volume. A copy is baked into the image,
and the service seeds the volume from it on first run, so a fresh deployment
works with no manual file placement. Edit the copy in the volume to customise:

```bash
docker exec -it epg-rewriter vi /data/channels.txt
docker exec epg-rewriter kill -HUP 1   # or: curl .../refresh
```

Do not use a relative bind mount such as `./data:/data` here. Docker creates a
missing bind source as an empty root-owned directory instead of failing, which
leaves the service running with no channel list and only a 503 to show for it.

## Coverage

Matching runs in tiers, and prefers leaving a channel unmatched over guessing:
a wrong guide misleads, an empty one is merely empty.

- `exact` — matched after normalization. Reliable.
- `fuzzy` — similarity above the cutoff, with identical digit runs. Digits carry
  identity (`Canal Sur 2` is not `Canal Sur`), so a differing digit blocks the
  match outright. Worth reviewing via `/status`.
- `none` — no correspondence.

Coverage is capped by the source, not the algorithm: channels absent from the
upstream guide can never match. Add sources to `EPG_SOURCES` to raise the cap.

Pure abbreviations no string metric can bridge (`M+ LCAMPEONES` ->
`M+ Liga de Campeones`) belong in `ALIASES` in `matcher.py`.

## Resilience

A failed refresh never replaces a working guide: the previous payload is kept
in memory, mirrored to disk, and served until a rebuild succeeds. `/status`
reports the last error.
