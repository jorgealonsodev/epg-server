"""HTTP service: fetch upstream EPG, rewrite it, serve the result.

Standard library only, so the image needs no pip install.
Never contacts the IPTV provider — channel names come from a local file.
"""
import logging
import os
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from epg_rewrite import load_channel_names, parse_sources, rewrite, to_gzip

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("server")

SOURCES = [u.strip() for u in os.environ.get(
    "EPG_SOURCES", "https://iptv-epg.org/files/epg-es.xml.gz").split(",") if u.strip()]
CHANNELS_FILE = os.environ.get("CHANNELS_FILE", "/data/channels.txt")
PORT = int(os.environ.get("PORT", "8080"))
REFRESH_HOURS = float(os.environ.get("REFRESH_HOURS", "12"))
CUTOFF = float(os.environ.get("FUZZY_CUTOFF", "0.92"))
CACHE_FILE = os.environ.get("CACHE_FILE", "/data/cache/epg.xml.gz")
# Shipped inside the image. A bind mount or a fresh named volume arrives empty,
# and Docker creates a missing bind source silently instead of failing, so the
# configured path cannot be relied on to exist on a first deploy.
BUNDLED_CHANNELS = os.environ.get("BUNDLED_CHANNELS", "/app/channels.txt")


class State:
    """Last good build. Kept in memory and mirrored to disk.

    A failed refresh must never replace a working guide, so the previous
    payload is retained and served until a rebuild actually succeeds.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.xml = None
        self.gz = None
        self.stats = {}
        self.unmatched = []
        self.built_at = None
        self.last_error = None

    def store(self, xml, gz, stats, unmatched):
        with self.lock:
            self.xml, self.gz = xml, gz
            self.stats, self.unmatched = stats, unmatched
            self.built_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self.last_error = None
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "wb") as fh:
                fh.write(gz)
        except OSError as exc:
            log.warning("cache write failed: %s", exc)

    def load_cache(self):
        try:
            with open(CACHE_FILE, "rb") as fh:
                with self.lock:
                    self.gz = fh.read()
                    self.built_at = "from cache"
            log.info("served stale cache until first refresh (%d bytes)", len(self.gz))
        except OSError:
            pass


STATE = State()


def resolve_channels_file():
    """Return a readable channel list, seeding the volume on first run.

    Order: the configured path, else the copy bundled in the image. When the
    configured path is missing but writable, the bundled copy is written there
    so the file becomes editable and survives restarts.
    """
    if os.path.exists(CHANNELS_FILE):
        return CHANNELS_FILE
    if not os.path.exists(BUNDLED_CHANNELS):
        raise RuntimeError(
            f"no channel list: {CHANNELS_FILE} is missing and no bundled copy "
            f"at {BUNDLED_CHANNELS}")
    try:
        os.makedirs(os.path.dirname(CHANNELS_FILE), exist_ok=True)
        shutil.copyfile(BUNDLED_CHANNELS, CHANNELS_FILE)
        log.warning("%s was missing; seeded it from the bundled list. "
                    "Edit that file to customise, it persists in the volume.",
                    CHANNELS_FILE)
        return CHANNELS_FILE
    except OSError as exc:
        log.warning("%s is missing and not writable (%s); using the bundled "
                    "list read-only. Mount a writable volume to customise it.",
                    CHANNELS_FILE, exc)
        return BUNDLED_CHANNELS


def build():
    path = resolve_channels_file()
    names = load_channel_names(path)
    if not names:
        raise RuntimeError(f"no channel names in {path}")
    channels, programmes = parse_sources(SOURCES)
    if not channels:
        raise RuntimeError("no EPG source could be read")
    root, stats, unmatched = rewrite(channels, programmes, names, CUTOFF)
    xml, gz = to_gzip(root)
    STATE.store(xml, gz, stats, unmatched)
    log.info("built: %s | %d bytes gz", stats, len(gz))


def refresher():
    while True:
        try:
            build()
        except Exception as exc:
            STATE.last_error = str(exc)
            with STATE.lock:
                had_guide = STATE.gz is not None
            if had_guide:
                log.error("refresh failed, keeping previous guide: %s", exc)
            else:
                # Nothing to fall back on: the service is up but serving 503.
                log.error("refresh failed and NO guide is available, "
                          "so /epg.xml.gz will return 503: %s", exc)
        time.sleep(REFRESH_HOURS * 3600)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        log.info("%s %s", self.address_string(), fmt % a)

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"

        if path in ("/", "/status"):
            with STATE.lock:
                lines = [
                    "epg-rewriter",
                    f"built      : {STATE.built_at}",
                    f"sources    : {', '.join(SOURCES)}",
                    f"last error : {STATE.last_error or 'none'}",
                    "",
                    "stats:",
                    *[f"  {k:18}: {v}" for k, v in STATE.stats.items()],
                    "",
                    f"unmatched ({len(STATE.unmatched)}):",
                    *[f"  {n}" for n in STATE.unmatched],
                ]
            self._send(200, "\n".join(lines).encode(), "text/plain; charset=utf-8")
            return

        if path in ("/epg.xml.gz", "/epg.gz", "/guide.xml.gz"):
            with STATE.lock:
                gz = STATE.gz
            if not gz:
                self._send(503, b"guide not built yet", "text/plain")
                return
            self._send(200, gz, "application/gzip",
                       {"Content-Disposition": 'attachment; filename="epg.xml.gz"'})
            return

        if path in ("/epg.xml", "/guide.xml"):
            with STATE.lock:
                xml = STATE.xml
            if not xml:
                self._send(503, b"guide not built yet", "text/plain")
                return
            self._send(200, xml, "application/xml; charset=utf-8")
            return

        if path == "/health":
            with STATE.lock:
                ok = STATE.gz is not None
            self._send(200 if ok else 503, b"ok" if ok else b"no guide", "text/plain")
            return

        if path == "/refresh":
            threading.Thread(target=build, daemon=True).start()
            self._send(202, b"refresh started", "text/plain")
            return

        self._send(404, b"not found", "text/plain")


def main():
    STATE.load_cache()
    threading.Thread(target=refresher, daemon=True).start()
    log.info("listening on :%d  -> /epg.xml.gz", PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
