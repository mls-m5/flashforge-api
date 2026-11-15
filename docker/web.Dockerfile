# Default web target has no native slicer or private profiles. Optional slicer
# target downloads a pinned upstream AppImage; see docs/DEPLOYMENT.md.
FROM docker.io/python:3.11-slim-bookworm AS web
LABEL org.opencontainers.image.source="https://github.com/mls-m5/flashforge-api"
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TMPDIR=/app/.tmp
COPY finderlab /app/finderlab
COPY docker/entrypoint.py /app/docker/entrypoint.py
COPY LICENCE /app/LICENCE
RUN useradd --create-home --uid 1000 finder \
    && mkdir -p /app/web-data /app/.tmp /app/proxy-captures \
    && chown -R finder:finder /app/web-data /app/.tmp /app/proxy-captures
USER finder
ENTRYPOINT ["python3", "/app/docker/entrypoint.py"]

FROM web AS slicer
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libwebkit2gtk-4.0-37 libgl1 libegl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY tools/download_orca.py /app/tools/download_orca.py
# The downloader verifies exact size and SHA256 before execution/extraction.
# 2.3.0 x86_64 is deliberate: it matches bookworm and our native offline evidence.
RUN python3 /app/tools/download_orca.py --version 2.3.0 \
    && cd /app/.tmp \
    && /app/.local-tools/OrcaSlicer_Linux_AppImage_V2.3.0.AppImage --appimage-extract > extract.log \
    && mv squashfs-root /opt/orca \
    && printf '%s\n' 'Unmodified OrcaSlicer official v2.3.0 Linux x86_64 AppImage contents.' \
       'Asset SHA256: 73079d88ec36f0615db7919d00aa26fe301e348ba6e051862a7cfc4040150c03' \
       'Release/source: https://github.com/OrcaSlicer/OrcaSlicer/tree/v2.3.0' \
       'Source archive: https://github.com/OrcaSlicer/OrcaSlicer/archive/refs/tags/v2.3.0.tar.gz' \
       'Upstream license: AGPL-3.0; retain upstream attribution/licenses and corresponding source obligations when distributing images.' \
       > /opt/orca/FINDERLAB-PROVENANCE.txt \
    && chmod -R a+rX /opt/orca \
    && rm -rf /app/.local-tools /app/.tmp/* \
    && chown -R finder:finder /app/.tmp
USER finder
# Build-time help probe only: no printer or model commands. Fresh per-job help
# and default validity/resource checks still run through the normal adapter.
RUN mkdir -p /app/.tmp/probe/data /app/.tmp/probe/config /app/.tmp/probe/cache \
    && cd /app/.tmp/probe \
    && XDG_CONFIG_HOME=$PWD/config XDG_CACHE_HOME=$PWD/cache XDG_DATA_HOME=$PWD/data \
       python3 -c 'import subprocess; r=subprocess.run(["/opt/orca/AppRun","--help","--datadir","/app/.tmp/probe/data"],capture_output=True,timeout=20); print(r.stdout.decode("utf8","replace")); print(r.stderr.decode("utf8","replace")); assert r.returncode == 0 and b"--slice" in r.stdout+r.stderr, "Orca help/capability probe failed"' \
    && rm -rf /app/.tmp/probe
