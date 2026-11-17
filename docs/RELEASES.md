# Copyable server source releases

## Package on the development machine

```sh
./tools/package_release.sh                   # Quick archive, no tests
# Optional alternative: run every check, then package only on success:
./tools/package_release.sh --check --jobs 4
# Python equivalent: python3 tools/package_release.py [--check --jobs 4]
```

Ordinary packaging requires Git and Python3.11+, but no Node. It exports
**committed HEAD** using `git archive` without running tests and prints
**Tests NOT RUN**. `release.json` records checks.result=not_run/command=null:
an archive is not a passing release validation. Choose `--check` to run the full
`tools/check.py` suite (Python, all Node scripts and trace integrity; Node18+
required) and publish only after success. `--jobs 1–8` requires `--check`; default1
retains serial tests. Tests can also run separately via `./tools/check.sh --jobs 4`.
Do not use quick packaging to describe known failed source as validated. Commit/review tracked edits first. Untracked `result.json`,
ignored .env, runtime data and local tooling are not prerequisites and never
enter this archive. No tag, push, network discovery, printer connection,
container build/start, deletion of evidence or automatic deployment occurs.

Output under ignored `dist/releases/finderlab-COMMIT/`:

- `finderlab-COMMIT.tar.gz`: complete standalone server source rooted at `finderlab/`;
- `SHA256SUMS`: SHA256 of that archive;
- `release.json`: exact source commit/tree/date, hash/size/count and check result.

Orca downloader, full Compose/live preset, Python/UI/local Three assets, tracked
Finder2 profiles and their upstream source/license/provenance are included.
**No .env/passwords, user models, captures, web workspace, private drafts,
AppImages or container images**. Tracked private roots/env files/auth.json/verifier temporary files cause refusal,
not silent publication. Required runtime source/config/license files are checked;
links/devices/unsafe paths and excessive sizes/counts fail review. Limits:10000
entries,64MiB source/unpacked and32MiB compressed. Same commit has reproducible
archive bytes; an existing release directory is never overwritten. Packaging
checks current clean source again after tests and pins the original commit.

The paused OctoPrint Git submodule contents are not included/needed for the
standalone server release. This is not an OctoPrint plugin installation bundle.
Git metadata is not in the archive, so use a new release instead of `git pull`
on an unpacked deployment. Keep source/licenses with any distributed copy.

## Copy, verify, unpack and start

Copy the entire output directory to your server using your usual file transfer
or e.g. `scp -r dist/releases/finderlab-COMMIT user@SERVER:~/releases/`. Replace
COMMIT/user/SERVER with the actual values; do not publish your private .env.
On the server, in that copied release directory:

```sh
sha256sum -c SHA256SUMS
tar -xzf finderlab-COMMIT.tar.gz
cd finderlab
```

**If this server already works, copy its existing private .env into this new
finderlab directory**, keeping the verified printer IP, server LAN IP and live
Compose settings. Do not replace a working config with a blank example.
For a new deployment only:

```sh
cp .env.example.live .env
# Set FINDER_PRINTER_HOST to your verified printer IP.
# Other-computer access: FINDER_LISTEN_HOST is this server's192.168 interface IP.
```

When no operation is active, stop/replace the old instance deliberately, then:

```sh
podman compose up --build -d
podman compose logs finder-web
```

Docker Compose is equivalent. **For an existing deployment preserve the existing
Compose project name** (use the same `-p NAME`, COMPOSE_PROJECT_NAME, or deployment
folder name). Otherwise a new folder can select new named volumes, and old
records/files will not appear in the new instance. For a fresh server you can
choose a stable name, e.g. `podman compose -p finderlab up --build -d`, and reuse
that name on future updates. Never use `down -v` as ordinary update cleanup.
Do not run old/new web/proxy services simultaneously on the same ports or against
one workspace. Do not restart merely to test while an upload/Slice/start is active.

Live config starts its bundled proxy, waits for passive listener readiness and
opens status-only monitoring. It does not start a print on startup. With job
controls enabled, the later **Save + start** initiating click may heat/move;
uncheck for save only. Physical manual controls remain locked. HTTP on your
specific LAN IP:8000 is unencrypted; trusted home network only, no router
forwarding/public tunnel. Port9000 is the TCP proxy, not a browser URL.
See [DEPLOYMENT.md](DEPLOYMENT.md) for access/login/readiness/provider limits.

This is a **source release**: the server needs Linux x86_64 and Docker/Podman
with compatible Compose/.env/health dependencies. First build still needs
Internet/disk space to fetch base image, apt packages and the pinned official
Orca asset. No Git/Python/Node host installation is required merely to run
Compose; the image supplies the runtime. A packaged passing suite is not an
actual provider/container/browser/hardware acceptance claim.

## Parallel test isolation and shutdown regression

`./tools/check.sh --jobs 4` runs the same flat Python test files in at most four
separate Python processes, not multiple unittest cases sharing mock/global state.
Output is grouped by module, all failed modules retain their complete diagnostics,
and no module is retried. Node/trace checks still follow Python success. Serial
mode remains the default; use fewer workers on constrained machines. Nested test
packages fail visibly in parallel mode until supported, never silently disappear.
Test workspaces/ports are private and ephemeral; fake-slicer fixtures retain the
real workspace mutex but now select separate scratch roots. No production lock
is removed to permit parallel tests.

The reported Python3.12 proxy shutdown failure exposed listener wait preceding
active-session cancellation. Python's Server.wait_closed waits for active
connections too; proxy/mock/web now stop accepting, close/cancel/join owned
handlers, then await listener closure. Wire bytes/timeouts/job guards are unchanged.
Portable loopback regression tests enforce this ordering even under Python3.11;
the original shutdown test also has a bounded wait instead of waiting60 seconds.
The user's three other error tracebacks were not supplied; they are not diagnosed
from the one displayed failure. Python3.12 execution remains a host verification.

## Validation

Local Python3.11 validation:379 Python tests,17 Node scripts and reviewed-trace
integrity passed both serially and with --jobs 4. Test-identity multisets matched
exactly (379, no omissions/duplicates introduced). The same staged source passed
all checks in a clean checkout without local tools/private profiles. Measured
full-run wall time here was about49s serial vs20s parallel; host CPU/load affects
these numbers. All three new drain-order regressions failed on original HEAD,
then passed with the fix. Python3.12, rendered-browser/container/hardware trials
were not run; the supplied traceback only diagnoses the one shutdown failure.

Tests use fresh project-local Git fixtures and fake check scripts, not recursive
production suites or hardware. They cover clean/staged/untracked boundaries,
private paths, required files, failed checks, archive/hash/source metadata,
no overwrite, reproducibility and unsafe links/size refusal. Actual project packaging always reviews the resulting archive; only `--check`
runs the real full suite. A checked run does not cache/reuse earlier test results.
For the same commit, quick and checked packaging use the same destination; an
existing output is refused before running tests. Run checks separately if that
archive already exists, rather than deleting evidence to force publication.
Extraction smoke tests should use a fresh project-local scratch directory,
verify no private .env/model/log/Git files and check the unpacked source without
starting containers or configured printer targets.
