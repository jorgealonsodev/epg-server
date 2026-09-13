# epg-rewriter

Your IPTV playlist and your guide source name the same channels differently, so
the player shows no programme information. This service downloads a public
XMLTV guide, rewrites its channel names to match the playlist, and serves the
result over HTTP. The player keeps pointing at the provider; only the guide URL
points here.

**It never contacts the IPTV provider.** Channel names come from a local
`channels.txt`, so no credentials enter the container and the provider sees no
extra connections.

## Quick start

```bash
docker compose up -d --build
curl -s http://localhost:29956/health    # "no guide" (503) -> "ok" (200)
```

The first build downloads and rewrites the guide, which takes a moment. A 503
means it is still building, not that something is broken. Once it answers `ok`:

```
http://<host>:29956/epg.xml.gz
```

Set that as the player's guide URL and leave the playlist URL exactly as it is.

> Publishing beyond your LAN? Read [Exposing this publicly](#exposing-this-publicly)
> first — the guide token travels in the URL and needs TLS.

## Common tasks

| I want to… | Go to |
|---|---|
| Fix channels that lost their guide | [Updating the channel list](#updating-the-channel-list) |
| Understand why coverage is not 100% | [Coverage](#coverage) |
| Put this on the internet safely | [Exposing this publicly](#exposing-this-publicly) |
| Change refresh rate, sources, tokens | [Configuration](#configuration) |
| Run the tests | [Development](#development) |

## Updating the channel list

Run this when the provider adds or renames channels — renamed ones silently
lose their guide, and unknown names showing up in `/status` is the signal.

### 1. Record the subscription URL (once)

Put it in `.env`, which is gitignored, so it survives between runs:

```
PLAYLIST_URL=http://<panel>/get.php?username=<user>&password=<pass>&type=m3u_plus
```

Do this even if you regenerate by hand. The URL went unrecorded once and the
refresh stalled outright: it cannot be reconstructed from a saved playlist,
whose hostnames are streaming edges with token-proxied links.

### 2. Extract the names

```bash
./extract_channels.py --dry-run   # report what the provider changed
./extract_channels.py             # write data/channels.txt
```

Run it on a workstation, never in the container. The tool is deliberately not
copied into the image, so the container holds no subscription URL and opens no
connection to the provider.

It keeps the playlist's `[ES] ` groups (the rest is VOD and series), drops
duplicates, sorts case-insensitively, and refuses to write a name that looks
like a URL.

### 3. Check what it reports

```
471 -> 501 channels (+46 -16)
  - DAZN ACB 1
  + DAZN EVENTOS 1
```

The added names are the actionable part. A new name often needs an alias in
`matcher.py` before it matches — see [Coverage](#coverage). Removed names may
leave dead aliases behind, which are harmless but worth a look.

### 4. Commit and redeploy

The list ships inside the image, so the change reaches the service through an
ordinary redeploy.

- [ ] `data/channels.txt` contains names only — no URLs, no credentials
- [ ] Added names checked against the guide, aliases added where needed
- [ ] Redeployed, and the log shows `channels.txt replaced with the list shipped in the image`
- [ ] `/status` reports the channel count you expect

## channels.txt

One channel name per line, exactly as the playlist spells it.

A comment is `#` **followed by a space**. A bare `#` starts a real channel name
in the wild (`#DAZN 1 FULL HD`) and is preserved.

### How the list reaches the container

The live copy lives in the `epg-data` named volume. A copy is baked into the
image, and the service seeds the volume from it on first run, so a fresh
deployment needs no manual file placement.

| Situation | What the service does |
|---|---|
| Volume empty | Seeds it from the image |
| Image ships a newer list | Replaces the volume copy — a stale list silently orphans renamed channels |
| You edited the list in the volume | Leaves it alone, and logs why |
| Volume predates the seed stamp | Adopts the shipped list once, keeping `channels.txt.bak` |

It tells those apart with `.channels-seed`, which records the digest of the
shipped list the file was seeded from. To edit the live copy instead:

```bash
docker exec -it epg-rewriter vi /data/channels.txt
docker exec epg-rewriter kill -HUP 1   # or: curl .../refresh
```

Deleting that file makes the service adopt the shipped list again.

> Do not use a relative bind mount such as `./data:/data`. Docker creates a
> missing bind source as an empty root-owned directory instead of failing,
> leaving the service with no channel list and only a 503 to show for it.

## Endpoints

| Path | Purpose |
|---|---|
| `/epg.xml.gz` | The rewritten guide (gzip). Use this one. |
| `/epg.xml` | Same, uncompressed. |
| `/status` | Match counts and the full unmatched list. Restricted. |
| `/health` | 200 once a guide is available. |
| `/refresh` | Trigger a rebuild without restarting. Restricted. |

## Configuration

Copy `.env.example` to `.env` and fill in the tokens. Every setting also has a
default in `docker-compose.yml`, so the stack runs with no `.env` at all — an
absent or blank value falls back rather than breaking the deployment. In
Portainer, set the same names as stack environment variables.

| Variable | Default | Notes |
|---|---|---|
| `EPG_SOURCES` | iptv-epg.org ES | Comma-separated. More sources lift the ceiling. |
| `REFRESH_HOURS` | `3` | Matches the upstream regeneration cycle. Faster gains nothing; slower lags behind schedule corrections. Accepts fractions. |
| `FUZZY_CUTOFF` | `0.92` | Raise it for stricter matching. |
| `CHANNELS_FILE` | `/data/channels.txt` | Names only, one per line. |
| `GUIDE_TOKEN` | unset | Gates the guide URL. Carried in the URL, not a header. |
| `ADMIN_TOKEN` | unset | Gates `/status` and `/refresh`. Sent as a header. |

`PLAYLIST_URL` is read by `extract_channels.py` only. The service never sees it.

## Exposing this publicly

Scanning is unavoidable: any reachable address is probed continuously. What
matters is that a probe gains nothing.

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

**Serve this over TLS.** The token sits in the URL, so plain HTTP exposes it to
anyone on the path, and URLs leak through logs, history and `Referer` headers.
Treat it as a bearer secret: whoever holds the URL has the guide.

### Gating /status and /refresh

By default the restricted endpoints accept private and loopback callers only.
Behind a reverse proxy that check is useless, because every request then carries
the proxy's own private address. Set `ADMIN_TOKEN`, which switches the check to
the token alone and ignores the source address:

```bash
curl -H "X-Admin-Token: $ADMIN_TOKEN" http://<host>:29956/status
```

If the player lives on the same LAN, the stronger option is not to publish the
port to the internet at all.

## Coverage

Matching prefers leaving a channel unmatched over guessing: a wrong guide
misleads, an empty one is merely empty.

| Tier | Meaning |
|---|---|
| `exact` | Matched after normalization. Reliable. |
| `fuzzy` | Similarity above the cutoff, with identical digit runs. Worth reviewing via `/status`. |
| `none` | No correspondence. |

Digits carry identity, so a differing digit blocks a fuzzy match outright:
`Canal Sur 2` is not `Canal Sur`. Abbreviations no string metric can bridge
(`M+ LCAMPEONES` → `M+ Liga de Campeones`) belong in `ALIASES` in `matcher.py`.
Verify every alias against the guide before adding it — the target must exist
and be the same channel.

**Coverage is capped by the source, not the algorithm.** Channels absent from
the upstream guide can never match, and neither can `24/7` loop channels or
rotating event channels, which have no schedule to publish. Add sources to
`EPG_SOURCES` to raise the cap.

### Why it duplicates instead of renaming

Guide and playlist relate 1:N. One guide channel typically backs several
playlist variants:

```
M+LaLigaTV.es  ->  M+ LaLigaTV, M+ LaLigaTV 4K, M+ LaLigaTV FULL HD,
                   M+ LaLigaTVHD, M+ LaLigaTVHD+, M+ LaLigaTVSD
```

A `<channel>` holds one id, so renaming fixes one variant and orphans the rest.
Each matched channel is emitted once per variant, with its programmes copied.

## Logs

The container log is capped at 3 files of 10 MB by the compose file. Every
request is logged and a reachable host is probed continuously, so an uncapped
`json-file` driver would grow until it filled the disk.

Both tokens are redacted from the request line before it is written, so the
guide token does not end up readable in `docker logs`. A reverse proxy in front
keeps its own access log and needs the same treatment — with
nginx-proxy-manager, `access_log off;` in the host's advanced configuration is
enough, since this service already logs the same requests safely.

## Resilience

A failed refresh never replaces a working guide: the previous payload is kept in
memory, mirrored to disk, and served until a rebuild succeeds. `/status` reports
the last error.

## Development

Standard library only — no dependencies, so the image needs no `pip install`.

```bash
python3 -m unittest discover -v
```

| File | Role |
|---|---|
| `server.py` | HTTP service, refresh loop, volume seeding |
| `epg_rewrite.py` | XMLTV parsing and rewriting |
| `matcher.py` | Name normalization, aliases, matching tiers |
| `extract_channels.py` | Regenerates `channels.txt`. Not shipped in the image. |
