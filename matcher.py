"""Name matching between IPTV playlist channels and XMLTV EPG channels.

Shared by the one-shot CLI and the container service. Standard library only.
"""
import collections
import difflib
import re
import unicodedata

# Provider abbreviations no string metric can bridge. Both sides normalized.
# Every entry below was verified against the EPG: the target channel exists and
# is the same channel, not merely a similar string.
ALIASES = {
    # Champions League, spelled out upstream
    "m lcampeones": "m liga de campeones",
    **{f"m lcampeones {n}": f"m liga de campeones {n}" for n in range(2, 14)},
    "m lcampeon2": "m liga de campeones2",
    "m lcampeon3": "m liga de campeones 3",
    # Spacing and glued words
    "tele madrid": "telemadrid",
    "la sexta": "lasexta",
    "cazaypesca": "caza y pesca",
    "bemad tv": "be mad",
    # Abbreviations
    "disney jr": "disney junior",
    "disney ch": "disney channel",
    "disney 1": "disney channel 1",
    "a3series": "atreseries",
    "nat geo": "national geographic",
    "m ellas v": "movistar ellas vamos",
    # Provider prefix differences (M+ vs Movistar)
    "m cine espanol": "movistar cine espanol",
    "m cine espagnol": "movistar cine espanol",
    # Extra or missing qualifier words
    "sundance tv": "sundance",
    "extremadura": "canal extremadura",
    "canal odisea": "odisea",
    "mtv espana": "mtv",
    "paramount network": "paramount channel",
    "paramount": "paramount channel",
    # Renamed upstream: the playlist keeps the M+ prefix, the EPG dropped it
    "m vamos 2": "vamos 2",
    # Mojibake in the playlist: 'CL.SICOS' is a mangled 'Clásicos'
    "m cl sicos": "m clasicos",
    # Provider suffixes that survive normalization and block the match
    **{f"m deportes{n} solo eventos": f"m deportes {n}" for n in range(2, 7)},
    "m deportes2hd solo eventos": "m deportes 2",
    # Playlist keeps the channel NUMBER in the name (235 is a dial position)
    "m laligatvhd 235": "m laligatv",
    "dazn laliga 235": "dazn laliga",
    # 'TV' present on one side only
    "m laliga 2": "m laligatv 2",
    "m laliga 3": "m laligatv 3",
    # Shortened or prefixed variants of the same channel
    "canal alquiler 1": "alquiler 1",
    "new alquiler 1": "alquiler 1",
    "bom": "bom cine",
    "gol play": "gol",
    "m ellas": "movistar ellas vamos",
}

QUALITY = r"(?:uhd|4k|fhd|full\s*hd|hd|sd|1080p?|720p?|hevc|h265|multi|vip|backup|alt)"


def normalize(name):
    s = unicodedata.normalize("NFKD", name.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"^\s*\[[^\]]*\]\s*", "", s)
    s = re.sub(r"^\s*(?:es|esp|spain|espana)\s*[-:|]\s*", "", s)
    s = re.sub(rf"{QUALITY}\s*\+?\s*$", " ", s)
    s = re.sub(rf"\b{QUALITY}\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def digit_key(norm_name):
    """Digits carry channel identity: 'Canal Sur 2' is not 'Canal Sur'.

    Fuzzy distance treats digits as ordinary characters and silently collapses
    distinct channels. Requiring identical digit runs blocks that whole class
    of false positive. A wrong guide misleads; an empty one is merely empty.
    """
    return tuple(re.findall(r"\d+", norm_name))


def build_index(epg_channels):
    index = collections.defaultdict(list)
    for cid, display in epg_channels:
        index[normalize(display)].append((cid, display))
    return index


def match_name(name, index, keys, cutoff=0.92):
    """Return (tier, epg_id, epg_name). Tier is exact, fuzzy, or none."""
    key = normalize(name)
    key = ALIASES.get(key, key)
    if not key:
        return "none", "", ""
    if key in index:
        cid, display = index[key][0]
        return "exact", cid, display
    safe = [k for k in keys if digit_key(k) == digit_key(key)]
    close = difflib.get_close_matches(key, safe, n=1, cutoff=cutoff)
    if close:
        cid, display = index[close[0]][0]
        return "fuzzy", cid, display
    return "none", "", ""
