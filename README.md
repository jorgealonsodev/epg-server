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
| `/status` | Match counts and the full unmatched list. |
| `/health` | 200 once a guide is available. |
| `/refresh` | Trigger a rebuild without restarting. |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `EPG_SOURCES` | iptv-epg.org ES | Comma-separated. More sources lift the ceiling. |
| `REFRESH_HOURS` | `3` | Matches the upstream regeneration cycle. Reading faster gains nothing; slower lags behind schedule corrections. Accepts fractions. |
| `FUZZY_CUTOFF` | `0.92` | Raise it for stricter matching. |
| `CHANNELS_FILE` | `/data/channels.txt` | Names only, one per line. |

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
