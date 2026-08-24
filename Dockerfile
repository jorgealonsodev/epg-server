FROM python:3.12-slim

# Standard library only: no requirements.txt, no pip install, small image.
WORKDIR /app
COPY matcher.py epg_rewrite.py server.py ./

# Default channel list, baked in. A bind mount or a fresh named volume starts
# empty, and Docker creates a missing bind source silently rather than failing,
# so the service must be able to run with no volume content at all. On first
# run it seeds /data/channels.txt from this copy.
COPY data/channels.txt /app/channels.txt

RUN useradd --create-home --uid 1000 epg \
    && mkdir -p /data/cache \
    && chown -R epg:epg /data
USER epg

ENV CHANNELS_FILE=/data/channels.txt \
    BUNDLED_CHANNELS=/app/channels.txt \
    CACHE_FILE=/data/cache/epg.xml.gz \
    PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=90s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=4).status==200 else 1)"

CMD ["python3", "-u", "server.py"]
