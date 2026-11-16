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
| `test_web_monitoring.py` | HTTP monitor lifecycle, ownership handoff, recording failures and passive reads |
| `test_web_manual.py` | Owned-dummy counter/light rehearsal; physical controls stay locked |
| `test_web_lan.py` | Auth/peer/Host/Origin/token and shared-workflow behavior on ephemeral loopback |
| `test_web_cli.py` | CLI refusal and clean SIGINT/SIGTERM shutdown |
| `test_web_jobs.py` | Exact save/start/cancel, combined intent, finalized records, unknown results/no retries |
| `test_web_admission.py` | HTTP quota/reservation/archive/locking; no GET-triggered archive |
| `test_web_models.py` | Single/multiple source identities, transforms, bounded STL/core3MF preview and cancellation |
| `test_web_slicing.py` | Fake Orca, quality/snapshot/guard/publication and cancellation |
| `test_web_gx.py` | Explicit GX source/format/hash/export, errors and generated-upload gate |
| `test_web_access.py`, `test_web_storage.py` | Independent access/archival policy unit tests |

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

R2a extracted production wire parsing/responses only, keeping all common access
gates, routes and socket/task cleanup on WebServer. Its direct tests use memory
streams/writers; its integration tests retain the same owned-loopback fixture.
Node fixture consolidation, route/source ownership, internal state and shared
process refactors remain later stages in
[docs/REFACTORING.md](../docs/REFACTORING.md), not already complete.
