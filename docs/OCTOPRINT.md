# OctoPrint plugin experiment — checkpoint

Plugin submodule: `plugins/octoprint-flashforge-finder2`, remote
`git@github.com:mls-m5/octoprint-flashforge-finder2.git`.
Research remote: https://github.com/mls-m5/flashforge-api.

This is an early upload-only plugin, not a complete native printer driver.
Its README/SOURCE describe the admin-only API/tab, bounded worker, firmware
gate, GPLv3 transport provenance and remaining live-server/browser acceptance.
No start/stop/heat/discovery or serial emulation is exposed.

## Local Docker test (Linux)

```sh
git submodule update --init --recursive
# Separate terminal, own fresh dummy, not a hardware proxy:
python3 -m finderlab mock --port 9000
# Experimental root:
docker compose config
docker compose up --build
```

Visit http://127.0.0.1:5000 and complete OctoPrint's first-run/admin setup. The
Finder plugin is installed from the local submodule at image build time, not
fetched from a moving Git branch. It is disabled by default. Set its target to
`127.0.0.1:9000`, enable uploads, then use its separate Save to Finder tab with
an OctoPrint local file. Do not use core print/terminal controls for Finder.
Use a new test volume, not a production OctoPrint configuration.

Linux host networking deliberately reaches a dummy/proxy listening on the
host's loopback. The web server itself binds only 127.0.0.1:5000. No serial/USB,
camera, privileged mode or Docker socket is passed through. TCP access to a
physical printer is possible by explicit configuration, including through a
loopback proxy; it is not a safety filter. No agent hardware trial was run.
Docker Desktop may need explicit host-network support; this setup targets Linux.

The Compose layout is adapted from the official GPLv3 example at
https://github.com/OctoPrint/octoprint-docker/blob/32fdd6eae2a9a2c1f97f26cf4c7d3802cb0559db/docker-compose.yml.
The pinned official 1.11.8 image reports Python 3.10.18; the plugin compatibility
floor was adapted accordingly. Its ordinary S6/HAProxy entrypoint is replaced
with a non-root, explicitly loopback-bound OctoPrint command for host networking.
Docker context is allowlisted to plugin source/packaging only; no models,
captures, local profiles, account configuration or Git metadata should enter it.

## Validation at checkpoint

- Real OctoPrint 1.11.8 mixins/permissions and Flask context tests on Python 3.11;
  independent scripted ephemeral-loopback transport/service tests.
- Actual plugin worker uploaded the provided 3668165-byte GX to a fresh dummy,
  byte-identical, 896 ACKed blocks. Commands: M601, M115, M119, M28, M29, M602;
  no M23/M26, no virtual print. Private capture:
  `captures/plugin-dummy-validation/captures/20261114T122940Z-d5187521bf32`.
- Docker/Podman is unavailable in this agent environment: image build, Compose
  runtime, Python 3.10 runtime and browser acceptance are **not yet verified**.
- Research trace derivatives under `docs/traces/` are generated only from pinned,
  already reviewed fixtures, not raw captures. Exporter: `tools/export_reviewed_traces.py`.

Follow-up validation: the research suite (106 tests), plugin SDK suite and
separate Node viewmodel checks pass. New plugin fault tests exercise ACK/save/
overall deadlines, recording quotas/finalization failure, paused/busy guards and
release warnings. The tab coalesces status polls, rejects duplicate submissions,
ignores obsolete replies after logout, and requires a result refresh before a
retry after a lost HTTP submission response. Captures and snapshot hashes are
shown only in the admin tab. These remain context/viewmodel tests, not a live
browser deployment.

Pending: inspect the Docker build/runtime on the host and complete live browser
acceptance against a fresh dummy. The research commit `3ab0401` was successfully
pushed through host approval; later changes and the plugin remote need separate
publication verification. Do not infer push success from a request alone. Do not
claim GitHub publication until the push approval reports success. Raw captures,
models, private profiles, volumes and the pre-existing result.json stay untracked.
