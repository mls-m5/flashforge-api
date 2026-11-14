# Standalone web workbench, no OctoPrint and no third-party Python dependencies.
FROM docker.io/python:3.11-slim-bookworm
WORKDIR /app
COPY finderlab /app/finderlab
RUN useradd --create-home --uid 1000 finder \
    && mkdir -p /app/web-data /app/.tmp \
    && chown -R finder:finder /app/web-data /app/.tmp
USER finder
# Linux host networking lets this loopback-only page reach a host dummy/proxy.
# Orca/native libraries/profiles are NOT bundled into this initial image.
ENTRYPOINT ["python3", "-m", "finderlab", "web"]
