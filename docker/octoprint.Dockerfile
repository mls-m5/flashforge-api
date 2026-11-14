# Official multi-architecture OctoPrint 1.11.8 image; observed Python 3.10.18.
ARG OCTOPRINT_IMAGE=docker.io/octoprint/octoprint:1.11.8@sha256:5ea0181e476597faa2800c991af4ce16903005f46b4c16666a4080ad606310bb
FROM ${OCTOPRINT_IMAGE}
USER root
COPY plugins/octoprint-flashforge-finder2 /opt/finder2-plugin
# Install globally, NOT into /octoprint/plugins, which is hidden by the volume.
RUN PIP_USER=false python -m pip install --no-cache-dir --no-deps /opt/finder2-plugin \
    && python -c "from importlib.metadata import version; assert version('OctoPrint-FlashForge-Finder2') == '0.1.0'" \
    && useradd --create-home --uid 1000 finder2 \
    && mkdir -p /octoprint/octoprint /octoprint/plugins \
    && chown -R finder2:finder2 /octoprint
USER finder2
WORKDIR /octoprint
# Bypass the official image's root S6/HAProxy/webcam startup for host networking.
ENTRYPOINT ["/usr/local/bin/octoprint"]
CMD ["--basedir", "/octoprint/octoprint", "serve", "--host", "127.0.0.1", "--port", "5000"]
