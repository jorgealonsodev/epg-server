"""Rewrite an XMLTV EPG so its channel names match an IPTV playlist.

The playlist and the EPG name channels differently, so players that match by
name find nothing. This rewrites the EPG side only: the playlist, and the
credentials inside it, are never touched or even read.

Relation is 1:N, not 1:1 — one EPG channel typically backs several playlist
variants (HD / FULL HD / 4K / SD). Renaming would fix one and orphan the rest,
so each matched EPG channel is DUPLICATED once per variant.
"""
import gzip
import io
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

from matcher import build_index, match_name

log = logging.getLogger("epg")

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) epg-rewriter/1.0"


def load_channel_names(path):
    """One channel name per line.

    A comment is '#' followed by whitespace. A bare '#' with no space starts a
    real channel name in the wild (e.g. '#DAZN 1 FULL HD'), so it is kept.
    """
    names, seen = [], set()
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n").strip()
            if not line or re.match(r"^#\s", line):
                continue
            if line not in seen:
                seen.add(line)
                names.append(line)
    return names


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def parse_sources(urls):
    """Merge several EPG sources. First source wins on duplicate channel id."""
    channels, programmes, seen = [], [], set()
    for url in urls:
        try:
            root = ET.parse(io.BytesIO(fetch(url))).getroot()
        except Exception as exc:
            log.error("source failed, skipping: %s (%s)", url, exc)
            continue
        added = 0
        for ch in root.findall("channel"):
            cid = ch.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                channels.append(ch)
                added += 1
        programmes.extend(root.findall("programme"))
        log.info("source ok: %s (+%d channels)", url, added)
    return channels, programmes


def rewrite(channels, programmes, playlist_names, cutoff=0.92):
    epg_pairs = []
    for ch in channels:
        node = ch.find("display-name")
        display = (node.text or "").strip() if node is not None else ""
        if display:
            epg_pairs.append((ch.get("id"), display))

    index = build_index(epg_pairs)
    keys = list(index)

    # epg_id -> [playlist names it must appear as]
    targets = defaultdict(list)
    stats = {"exact": 0, "fuzzy": 0, "none": 0}
    unmatched = []
    for name in playlist_names:
        tier, epg_id, _ = match_name(name, index, keys, cutoff)
        stats[tier] += 1
        if epg_id:
            targets[epg_id].append(name)
        else:
            unmatched.append(name)

    by_id = {ch.get("id"): ch for ch in channels}
    progs_by_id = defaultdict(list)
    for prog in programmes:
        progs_by_id[prog.get("channel")].append(prog)

    out = ET.Element("tv", {
        "generator-info-name": "epg-rewriter",
        "source-info-name": "rewritten to match IPTV playlist names",
    })

    emitted_channels = emitted_programmes = 0
    for epg_id, names in targets.items():
        source = by_id.get(epg_id)
        if source is None:
            continue
        for name in names:
            # id and display-name both carry the exact playlist name: players
            # fall back to name matching when the playlist has no tvg-id.
            ch = ET.SubElement(out, "channel", {"id": name})
            ET.SubElement(ch, "display-name").text = name
            icon = source.find("icon")
            if icon is not None:
                ET.SubElement(ch, "icon", dict(icon.attrib))
            emitted_channels += 1

    for epg_id, names in targets.items():
        for prog in progs_by_id.get(epg_id, []):
            for name in names:
                clone = ET.fromstring(ET.tostring(prog))
                clone.set("channel", name)
                out.append(clone)
                emitted_programmes += 1

    stats.update(channels_out=emitted_channels, programmes_out=emitted_programmes,
                 epg_channels_in=len(channels), playlist_channels=len(playlist_names))
    return out, stats, unmatched


def to_gzip(tree_root):
    xml = ET.tostring(tree_root, encoding="utf-8", xml_declaration=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(xml)
    return xml, buf.getvalue()
