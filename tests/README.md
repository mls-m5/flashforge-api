# Local checks and test ownership

From the repository root (the wrapper also works from another working directory):

```sh
./tools/check.sh
# Or: python3 tools/check.py
# Python + trace integrity only, with explicit Node/UI skip:
./tools/check.sh --python-only
# Single family or individual UI check:
python3 -m unittest discover -s tests -p 'test_web_jobs.py' -v
node tests/test_start_after_upload_ui.js
```

Full checks require Python3.11+ and Node.js18+, no pip/npm installation. Runner
sets project-local TMPDIR, uses the same Python interpreter for the suite and
trace exporter, discovers sorted `tests/test_*.js`, and stops on the first
failing check. Missing/old Node fails before the suite; Python-only mode must
be explicitly selected and is never labelled a full UI pass. `git diff --check`
is a separate pre-commit review check, not a runtime/container/hardware test.

## HTTP/workbench families

The original `test_web.py` scenarios now belong to these modules; test method
bodies/assertions were moved unchanged in R1, not replaced by weaker mocks.
Existing access/storage *unit* tests are separate from HTTP integration families.

| Module | Contract |
| --- | --- |
| `test_web.py` | Core HTTP parsing/config/assets, receipt limits, owned-dummy boundary and config/names |
| `test_web_http.py` | Direct in-memory wire parsing/body/response/deadline/error contracts |
| `test_web_http_integration.py` | Raw HTTP/error/access ordering and body limits through owned-loopback WebServer |
| `test_web_routes.py` | Direct route delegation/guards/file streams using memory writers and synthetic local files |
| `test_web_route_access.py` | Common gate precedes route construction on every protected route/asset; config is request-bound |
| `test_web_monitoring.py` | HTTP monitor lifecycle, ownership handoff, recording failures and passive reads |
| `test_web_manual.py` | Owned-dummy counter/light rehearsal; physical controls stay locked |
| `test_web_lan.py` | Auth/peer/Host/Origin/token and shared-workflow behavior on ephemeral loopback |
| `test_web_cli.py` | CLI refusal and clean SIGINT/SIGTERM shutdown |
| `test_web_jobs.py` | Exact save/start/cancel, combined intent, finalized records, unknown results/no retries |
| `test_web_admission.py` | HTTP quota/reservation/archive/locking; no GET-triggered archive |
| `test_web_files.py` | Slot owner byte I/O/cache/cleanup/selection and workbench owner/admission boundary |
| `test_web_models.py` | Single/multiple source identities, transforms, bounded STL/core3MF preview and cancellation |
| `test_web_slicing.py` | Fake Orca, quality/snapshot/guard/publication and cancellation |
| `test_web_gx.py` | Explicit GX source/format/hash/export, errors and generated-upload gate |
| `test_web_access.py`, `test_web_storage.py` | Independent access/archival policy unit tests |
| `test_web_password.py`, `test_web_password_http.py` | Salted persistence/cache/atomic errors, restart/change/access/busy/cancel/reset without hardware |

`web_helpers.py::WebTestCase` holds only common setup/teardown, split-header HTTP
requests, file/JSON helpers, operation completion and fake-Orca configuration.
It contains **no test methods**, so importing it cannot duplicate scenarios.
Local feature helpers stay in their family. Avoid importing one concrete test
class into another module: unittest can discover/re-run imported test classes.
Keep assertions that prove no connection/command visible in each scenario.

Each HTTP test retains a fresh mock/server on ephemeral loopback and project-local
scratch. Authenticated LAN tests never bind to a real LAN interface. Test fixture
G-code is synthetic and dummy jobs execute nothing. Configured targets/native
Orca/actual containers and browser/GPU rendering are not part of these checks.
Do not convert a test to using an existing proxy just because it is on localhost.

R2a extracted production wire parsing/responses; R2b extracts routes/file streams,
keeping common access gates/error mapping/socket/task cleanup on WebServer. Its
direct tests use memory writers/synthetic local files and its integration tests
retain the same owned-loopback fixture. Existing tests/assertions are preserved.
R2c extracts file ownership/I/O/cache into SlotFiles while Workbench keeps the
single state, identities, admission/busy and operation policy. Its direct tests
use synthetic files/readers/fake converters. The existing preview killpg patch
now targets web_files, the actual converter owner; assertions remain unchanged.
`test_password_ui.js` independently checks explicit password form intent, capability
visibility, matching new values, clearing, no retry/double-submit and no printer
routes. Salted record/reset tests use project-local private files; reset CLI uses
only the existing workspace lock. No actual credential or hardware target is a
fixture. Browser Basic-auth caching/reauthentication remains host acceptance.

## Optional parallel Python checks

`./tools/check.sh --jobs 4` shards the same flat test files across isolated
subprocesses (bounded1–8); serial remains default. Each module runs once, full
failure output is retained and failures are never retried. Mock state is not
shared between threads. Web and slicer fixtures patch only the slicer scratch
root into their private temporary directories; actual mutex/resource/job guards
remain enabled. The lock test proves same-workspace exclusion and separate-root
independence. No new native/container/LAN/hardware launch is introduced.
`test_parallel_checks.py` tests worker overlap, distinct PIDs/local TMPDIR,
complete failure reports, bounded workers and refusal to omit nested tests.
`test_server_shutdown.py` verifies active handler drain before listener wait for
proxy/mock/web, client/upstream closure and server_shutdown without a watchdog wait.
An intentionally aborted incomplete web request may close with either EOF or RST;
handler-drain ordering and no-FinderClient assertions remain required.
The Python3.12 listener-drain contract is enforced portably on Python3.11 too.
Quick source packaging runs no tests and records not_run; `--check` is explicit.

HTTP negative-access tests must keep their status/body and route/client assertions.
A peer rejection before consuming a request can reset TCP. The user's full3.12.3
log showed that ignoring cleanup alone is insufficient: the EOF-based response
read can raise the same reset, whose traceback is then extended by wait_closed.
Both fixtures now read one Content-Length message (4s total,16KiB headers/64MiB
body), not TCP EOF. Missing/duplicate/invalid/oversized lengths, truncated bodies
and resets before completion still fail; close_http_writer tolerates only reset
from cleanup. No response-read exception is blindly swallowed. Existing status /
body/auth/no-route/no-client assertions remain. Linux SO_LINGER tests reproduce
an actual reset after a complete403 in both helpers and reject a reset before the
body completes, with separate header/body writes and no timing sleeps. Production
access/HTTP/wire code is unchanged. Native3.12 acceptance remains host-run.

Node fixture consolidation, internal state and shared process refactors remain
later stages in
[docs/REFACTORING.md](../docs/REFACTORING.md), not already complete.
