#!/usr/bin/env python3
"""Regenerate data/channels.txt from the IPTV playlist.

Run this BY HAND, on a workstation, when the provider adds or renames
channels. It is deliberately not part of the service and not copied into the
image: the container must never hold the subscription URL nor open a
connection to the provider.

What it does: downloads the playlist (or reads one already on disk), keeps the
live channels, writes their names — names only, no URLs and no credentials —
and reports what the provider changed since the last run, which is the list of
names worth checking against the guide.

    ./extract_channels.py                 # uses PLAYLIST_URL from .env
    ./extract_channels.py --dry-run       # report the changes, write nothing
    ./extract_channels.py --file list.m3u # from a playlist already downloaded

Standard library only, like the rest of the repo.
"""
import argparse
import os
import re
import sys
import urllib.request

HEADER = (
    "# Canales en vivo de la playlist IPTV — SOLO NOMBRES.\n"
    "# Sin URLs ni credenciales: este archivo es seguro de compartir/commitear.\n"
    "# Regeneralo cuando tu proveedor agregue o renombre canales.\n"
    "\n"
)
# Live channels sit in the provider's '[ES] ' groups; everything else in the
# playlist is VOD and series, which have no place in a channel list.
GROUP_PREFIX = "[ES] "
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "data", "channels.txt")
DEFAULT_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
# A playlist is large and the provider is slow; a player waits this long too.
TIMEOUT = 180
# Asking as a player keeps the request indistinguishable from ordinary use.
USER_AGENT = "VLC/3.0.20 LibVLC/3.0.20"


class Report:
    """What changed, for the caller to print or assert on."""

    def __init__(self):
        self.added = []
        self.removed = []
        self.total = 0
        self.written = False


def read_env_file(path):
    """Parse KEY=VALUE lines the way compose does. Missing file is not an error.

    The subscription URL belongs here: .env is gitignored, so the URL survives
    between runs without ever reaching the repository. It went unrecorded once
    and regenerating the list stalled until it could be asked for again.
    """
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def parse_names(text, group_prefix=GROUP_PREFIX):
    """Channel names from an M3U, deduplicated and sorted case-insensitively.

    The visible name follows the comma after the LAST quoted attribute. Titles
    contain commas, so splitting on the first one mangles them.
    """
    names, seen = [], set()
    for line in text.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        group = re.search(r'group-title="([^"]*)"', line)
        if not (group and group.group(1).startswith(group_prefix)):
            continue
        last_quote = line.rfind('"')
        comma = line.find(",", last_quote if last_quote != -1 else 0)
        if comma == -1:
            continue
        name = line[comma + 1:].strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    names.sort(key=str.lower)
    return names


def render(names):
    """The channels.txt body. Refuses to emit anything that leaks credentials."""
    for name in names:
        if re.search(r"https?://|[?&](?:username|password|user|pass)=", name):
            raise ValueError(
                f"refusing to write a name that looks like a URL: {name!r}")
    return HEADER + "\n".join(names) + "\n"


def load_names(path):
    """Read back a channels.txt. A comment is '#' followed by whitespace."""
    try:
        with open(path, encoding="utf-8") as fh:
            return [l.strip() for l in fh
                    if l.strip() and not l.startswith("# ")]
    except OSError:
        return []


def diff(old, new):
    before, after = set(old), set(new)
    return (sorted(after - before, key=str.lower),
            sorted(before - after, key=str.lower))


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8", errors="replace")


def main(argv=None, report=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="subscription URL (default: PLAYLIST_URL)")
    parser.add_argument("--file", help="a playlist already downloaded")
    parser.add_argument("--out", default=DEFAULT_OUT, help="list to write")
    parser.add_argument("--env", default=DEFAULT_ENV, help="file holding PLAYLIST_URL")
    parser.add_argument("--group-prefix", default=GROUP_PREFIX,
                        help=f"playlist groups to keep (default: {GROUP_PREFIX!r})")
    parser.add_argument("--dry-run", action="store_true",
                        help="report the changes without writing")
    args = parser.parse_args(argv)
    report = report or Report()

    url = args.url or os.environ.get("PLAYLIST_URL") or \
        read_env_file(args.env).get("PLAYLIST_URL")
    try:
        if args.file:
            with open(args.file, encoding="utf-8") as fh:
                text = fh.read()
        elif url:
            text = fetch(url)
        else:
            print("no playlist source: pass --file, or --url, or set "
                  f"PLAYLIST_URL in {args.env}", file=sys.stderr)
            return 2
    except (OSError, ValueError) as exc:
        print(f"could not read the playlist: {exc}", file=sys.stderr)
        return 1

    names = parse_names(text, args.group_prefix)
    if not names:
        print(f"no channel matched group prefix {args.group_prefix!r}",
              file=sys.stderr)
        return 1

    previous = load_names(args.out)
    report.added, report.removed = diff(previous, names)
    report.total = len(names)

    try:
        body = render(names)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"{len(previous)} -> {len(names)} channels "
          f"(+{len(report.added)} -{len(report.removed)})")
    for name in report.removed:
        print(f"  - {name}")
    for name in report.added:
        print(f"  + {name}")

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(body)
    report.written = True
    print(f"wrote {args.out}")
    if report.added:
        print("check the added names against the guide before trusting "
              "coverage: matcher.py may need an alias for some of them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
