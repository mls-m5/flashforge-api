# Maintainability refactoring plan

## Scope and decision

The user approved the read-only maintainability review and requested a written
plan followed by incremental implementation. This is a **behavior-preserving
maintenance track**, not new printer capabilities, a framework migration or
hardware authorization. Commit each coherent stage with checks and explicit
remaining work. Do not combine a structural move with a protocol/policy change.

## Handoff: start here in a new agent session

### Checkpoint and authorization

- R1 implementation checkpoint: **`0d9454c`**. **R2a is now complete** (see its
  progress log below); the next bounded milestone is **R2b route separation**.
  Use current Git HEAD/status rather than assuming the older handoff commit.
  Earlier relevant
  commits: `b4b7145` (tracked Finder2 profiles/default slicer Compose) and
  `74b6f21` (container packaging). The original handoff was documentation only;
  the later R2a implementation and its limits are recorded below.
- The user approved continuing the incremental refactoring plan, not replacing
  the application or adding functionality. **Continue with R2b below**, commit and
  report that bounded milestone, then continue through the checklist.
- At handoff, tracked working tree was clean; unrelated untracked `result.json`
  remained. Recheck Git status first; never overwrite another agent/user's work.
  No push was performed in this session. Do not assume the remote includes these
  local commits; verify availability before using a different machine/clone.
- R1's production changes were confined to the container argv builder. R2a now
  extracts HTTP wire primitives into `finderlab/web_http.py`, keeping common
  access gates, routes, file streams and lifecycle on WebServer. Workbench/state /
  operation/storage code is unchanged. R2b/R2c and R3–R6 are not implemented.

### Read before implementation

Read `AGENTS.md`, `README.md`, `DESIGN.md`, `docs/PROTOCOL.md`, current maintenance
section of `docs/ROADMAP.md`, this plan and `docs/WEB.md`. Read `docs/LAN.md` for
access behavior and `docs/CAPTURES.md` before capture/fixture changes. Additional
source/plate/preview/storage/GX changes require their respective docs listed in
AGENTS.md; avoid pulling those changes into the first HTTP extraction.

Then inspect `finderlab/web.py`, `finderlab/web_access.py`,
`tests/web_helpers.py`, `tests/README.md` and the relevant `test_web*.py` families.
The plan's review metrics describe the original checkpoint, not a target size.

### R2a — completed first bounded implementation (acceptance retained)

1. Run `./tools/check.sh` for a fresh baseline. R1 reported291 Python tests and16
   Node scripts plus trace integrity. Preserve every existing scenario; additional
   focused tests are welcome. The scratch comparison scripts mentioned below are
   historical aids, **not required files**: reproduce any baseline from Git if
   needed, not from ignored local data.
2. Extract the narrow HTTP request/header parser and response-writing primitives
   from `WebServer.handle/head/reply/problem` into a small explicit module (for
   example `finderlab/web_http.py`; the name is not a prescribed architecture).
   Use named request data, explicit inputs/dependencies and no import cycle back
   to `finderlab.web`. A small shared exception can live at this boundary, with
   an explicit re-export if preserving `from finderlab.web import WebError`.
3. Keep connection/task/writer lifecycle and application dispatch clearly owned
   by `WebServer`. Keep all common peer/Host/Basic/method/Origin/token gates
   before any route side effect. Preserve current validation order/status codes,
   byte/body/deadline limits, CRLF/duplicate-header behavior, authentication
   challenge, security headers and connection-close behavior. Do not silently
   broaden HTTP support or mix a parser fix into the extraction.
4. Add direct parser/response boundary tests (split/incomplete/oversized input,
   duplicate headers, unsupported transfer/Expect, malformed length, exact
   response/security headers), retaining HTTP integration coverage. Access tests
   must still prove every asset/API is protected and no target connection occurs
   on rejection or cached GETs. Use only owned ephemeral loopback/fake streams.
5. Leave Workbench state, `start`, `_operation`, printer-session/monitor handoff,
   file/plate/cache ownership and profile/process code **unchanged in R2a**.
   This makes the first production move reviewable. Update real import/patch
   points when necessary; do not add dynamic forwarding merely to hide coupling.
6. Run full checks plus `git diff --check`, review changed behavior/imports and
   tests, update this log and commit with an English message. Report actual
   acceptance and gaps; a clean suite is not a browser/container/hardware trial.

### R2b and R2c — after R2a

- **R2b:** split route handlers/dispatch from transport while retaining one common
  access gate. Keep public WebServer/CLI entry points stable where practical.
  Model/artifact/thumbnail streaming must retain token/identity/busy semantics.
- **R2c:** give source/plate/artifact storage a narrow owner/interface. Preserve
  hashes/receipt identities, immutable snapshots, quota/archive protection,
  no GET-triggered archive and cleanup after cancellation. Read the related
  model/plate/storage docs first. Do not introduce competing state dictionaries.
- Only mark the main R2 checklist complete after all of its boundaries are done.
  Then R3 handles explicit state; R4 shared process runtime; R5 frontend/test
  fixtures; R6 remaining readability/documentation. Do not pre-emptively tackle
  all stages in one diff or commit.

### If worker agents are available in the next session

The user explicitly requested using workers for suitable writing/review work
when available; this preference is also recorded in AGENTS.md. Worker availability
is harness/session-dependent. In the handoff and R2a sessions no subagent launch
tool was exposed (R2a could read the skill documentation only); no worker ran. Useful independent assignments are **read-only** parser/access
contract review and test-gap review, while one owner performs the extraction.
Agree file ownership before parallel edits; R2/R3 both touching web.py are not
independent tasks. Run the integrated suite after merging/reviewing results.
No worker receives permission for hardware/LAN/proxy actions or private-data
publication. Do not claim parallel implementation unless agents actually ran.

### Do not accidentally turn this into deployment work

Docker/Podman build/runtime, rendered-browser/GPU and user-supervised physical
acceptance remain separate outstanding checks. Default Compose includes pinned
Orca2.3.0 and tracked `profiles/finder2`; do not reintroduce manual private-profile
copying or change network/job defaults as part of refactoring. No public
listener, dependency/framework migration, new manual printer controls, tuning,
wire/parser interpretation change, automatic retry, push or service restart is
needed/authorized for this handoff. Leave existing services and recordings alone.

## Findings from the review

- `finderlab/web.py` is932 lines: HTTP/access/routing, source/artifact storage,
  validation/admission, model preview, background work, printer operations and
  monitor ownership share one module. `handle` is169 lines, `start`97 and
  `_operation`109 at this checkpoint. The most important coupling is finalized
  save/release -> exact identity -> fresh READY/start, not the raw file size.
- Workbench's mutable dictionary mixes source/model, artifact, saved identity,
  operation progress and error/job outcomes. Changes require reasoning about
  combinations of fields and phases across many branches.
- Some recent code, especially `docker/entrypoint.py`, plate logic and browser
  handlers, packs multiple decisions/statements onto single lines. Reading and
  reviewing safety-sensitive predicates is harder than necessary.
- `slice_model` is175 lines; GX imports private `_run`/`_copy_bounded` from the
  slicer. Process/resource/capture lifecycle is useful beyond slicing but is
  currently named/owned as slicer internals.
- `tests/test_web.py` is1247 lines. The same HTTP/loopback/fake-Orca helpers serve
  unrelated feature families. Several Node checks separately recreate similar
  DOM/events/timer/fetch stubs. The16 Node commands are manually enumerated.
- Browser controllers coordinate through custom events and separate polling /
  cancellation loops. They encode important stale-response and uncertain-result
  vetoes; consolidation must preserve these, not merely reduce line count.

These are code-review observations, not a measured development-time benchmark.
A shorter module alone is not the acceptance criterion: clearer ownership and
unchanged observable behavior are.

## Ordered stages

### R1 — Readability and a reliable test entry point (first milestone)

- [x] Split HTTP/workbench tests by behavior with a shared, test-free fixture
  class; retain every existing assertion/scenario and ephemeral owned endpoints.
- [x] Make container environment parsing / proxy / web / slicing / capability
  construction separate named functions with conventional multi-line code.
  Preserve defaults, validation order/messages and exact generated CLI argv.
- [x] Add one dependency-free command for Python, discovered Node checks and
  reviewed-trace integrity. Missing Node must not masquerade as a full pass;
  explicit Python-only mode must report what it skips. Never run launchers,
  native tools, containers or configured printer targets as part of this command.
- [x] Check baseline test inventory and moved method bodies; run full suite /
  Node / trace integrity / diff checks and commit the milestone.

This stage builds a safer base for the larger web changes below. No shared
production workbench state or HTTP behavior changes in R1.

### R2 — Separate HTTP from workbench behavior

- [ ] Separate bounded request parsing/response writing and shared access checks
  from route dispatch. **Partial: R2a extracted parsing/response primitives;
  common access checks and routes remain in WebServer until R2b.** All routes,
  including assets/model/thumbnail, must retain
  the same peer/Host/Basic/Origin/token/body/deadline/CSP checks and error behavior.
- [ ] Leave `finderlab.web` as the public CLI/server entry point where practical;
  use explicit imports and update patch points deliberately, not a broad registry
  or catch-all proxy layer to keep old tests artificially passing.
- [ ] Extract source/plate/artifact storage behind a narrow interface. Preserve
  immutable identities, cache/quota/discard cleanup and no GET-triggered archive.
- [ ] Keep operation orchestration and Save->Start finalization gates together.
  Avoid cyclic imports or callbacks that obscure who owns busy/network locks.

### R3 — Explicit internal state and transitions

- [ ] Introduce small named source/artifact/saved-identity/operation data objects
  and transition methods, not a generic state-machine dependency.
- [ ] Keep current public JSON/API shape via an explicit snapshot serializer.
- [ ] Make confirmed save independent of start/release/logging failure; represent
  unknown/not-sent/acknowledged results and one-attempt intent explicitly.
- [ ] Test transitions directly as well as through HTTP, including two tabs,
  stale identity, cancellation and recording failures. Avoid retaining both a
  mutable dictionary and independent object as competing sources of truth.

### R4 — Process runtime and a readable slicing pipeline

- [ ] Extract bounded subprocess/file snapshot primitives into a small explicit
  runtime module shared by slicer/GX, with public names rather than private imports.
- [ ] Preserve resource caps, process creation/cancellation race handling, group
  reap, stdout/stderr bytes/quota, workspace lock and complete capture semantics.
- [ ] Break slicing into named prepare/model/process/probe/slice/review/publish
  steps. Keep no-overwrite publication, exact hashes and no permission fallback.
- [ ] Regression-test fake workers first; a labelled native offline recheck can
  follow if useful. A new helper module is not a security-sandbox claim.

### R5 — Frontend coordination and shared test fixtures

- [ ] Introduce a small explicit API/state boundary for configuration, cached
  snapshots, pending/uncertain actions and event ownership.
- [ ] Preserve abort/generation/ETag/source-slot guards, server snapshot locks,
  direct initiating clicks, no blind retry and no auto Slice/GX/Save/Start.
- [ ] Extract reusable DOM/events/timer/fetch fixtures incrementally, keeping
  feature-specific assertions visible; pure predicates can be tested separately.
- [ ] No React, TypeScript migration, bundler, CDN or new npm dependency merely
  for refactoring. Browser/GPU acceptance remains separate from Node fixtures.

### R6 — Follow-through and documentation

- [ ] Apply readability improvements to plate/preview code one module at a time,
  without changing numerical limits or parser interpretation.
- [ ] Keep current setup/architecture concise and link historical experiment
  records rather than duplicating changing instructions. Do not erase evidence
  or revive a resolved physical blocker as an unqualified current claim.
- [ ] Update this checklist and links after each stage; reassess priority based
  on the next real feature rather than extracting abstractions speculatively.

## Invariants throughout all stages

- No agent hardware/proxy connection, scanning, public/LAN listener or hardware
  trial. Tests use project-local scratch and fresh ephemeral loopback fakes.
- Preserve wire frames/CRC/ACK/final save/release, firmware gate, no retry/stop;
  loopback is not a hardware-safety guarantee. Preserve exact save/start identity,
  READY check, continuous busy ownership and finalized-capture-before-start gate.
- Keep job-capability and generated-output flags, checked-by-default web combined
  intent, unchecked/legacy API and ordinary CLI save-only behavior unchanged.
- Tracked profile/start/end/retraction/skirt bytes, mandatory priming check,
  unsupported-data failures and geometry/resource/storage limits stay unchanged.
- Do not merge G-code interpreters just because they look similar: preview,
  diagnostics and admission deliberately have different scopes/strictness.
- Keep raw captures, user models, ignored drafts, .env and unrelated result.json
  untouched/unstaged. No history rewriting or push without explicit authorization.

## Validation and progress log

Baseline before R1:280 Python tests,16 Node checks and reviewed trace integrity
passed at the prior milestone. Actual container builds, browser/GPU and physical
acceptance are not supplied by this refactoring's automated checks.

### R1 completed

- Split the65 existing HTTP/config scenarios into feature modules plus a shared
  test-free fixture. The old1247-line test_web.py is now156 lines; largest moved
  family is255 lines. All79 original methods (tests + helpers) retain identical
  ASTs and occur exactly once; only layout/module/class ownership changed.
  Fixtures retain the same assertions, partial-header/body behavior and endpoints.
- Container entrypoint now has explicit proxy/web/slicing/capability helpers,
  ordinary multi-line branches, descriptive locals and environment type hints.
  Compared383 pre-refactor argv/error outcomes using project-local synthetic
  profile/executable placeholders: exact argv, exception types/messages unchanged.
  All tracked runtime/profile provenance hashes remained unchanged.
- Added tools/check.py and short executable tools/check.sh wrapper;16 Node files
  are discovered rather than enumerated. Added8 stub-process runner contracts
  and3 container parser/exec-boundary checks. No native/container/printer launcher
  is invoked by the runner. The existing tests still use fake workers/endpoints.
- `./tools/check.sh`:291 Python tests, all16 Node checks and reviewed-trace
  integrity passed. `../tools/check.sh --python-only` from project .tmp also ran
  all291 Python tests + trace integrity, explicitly reporting UI checks skipped.
  A fresh staged `git checkout-index` copy, without ignored local profiles/tools,
  also passed the full runner (291 Python +16 Node + trace integrity).
  `git diff --check` and `bash -n tools/check.sh` passed; profile/HTTP/operation
  production code is unchanged.
- Baseline comparison scripts/output stay ignored in .tmp; they are not a new
  runtime prerequisite or private fixture in Git. Permanent regression tests
  cover parser boundaries, argv gates and runner discovery/failure/skip behavior.
- Container build/browser/GPU/hardware acceptance remains unverified here. No
  agent printer/proxy/LAN listener or native Orca trial was performed in R1.

### R2a completed — next implementation stage is R2b

- `finderlab/web_http.py` now owns Request header data, bounded CRLF/ASCII header
  parsing, strict POST Content-Length, bounded JSON object reads, shared WebError
  and exact head/reply/problem wire writing. WebError remains available through
  an explicit import from finderlab.web; there is no cyclic workbench import.
- WebServer retains common peer/Host/Basic/method/Origin/token gates, URL/route
  interpretation, model/artifact/thumbnail streaming, connection/task cleanup
  and explicit response entry methods. Its response entry points delegate to
  wire helpers, not a dynamic compatibility registry or forwarding object.
  Body reads remain after access/type/query validation; URL/method checks have
  not been moved ahead of authentication.
- Workbench, WebConfig and WebCapture class ASTs match pre-R2a exactly; all tracked
  profile JSON bytes are unchanged. Client/protocol/monitor/source/cache/storage /
  slicer/frontend code and existing test methods were not changed.
- Added18 direct in-memory request/response tests and4 owned-loopback integration
  tests: split CRLF/surplus, malformed/incomplete/duplicate/oversized headers,
  exact size limits, strict POST length, JSON object errors, deadlines, response
  bytes/CSP/Basic challenge, write failure/cancellation and access-validation
  ordering before side effects. No test uses configured targets/native Orca.
- An offline old/new comparison exercised555 synthetic raw HTTP responses and
  writer close/abort outcomes with identical bytes/results; no sockets/targets
  were opened by that comparison. Its script is an ignored scratch aid, not a
  new deployment/test prerequisite. Existing authenticated-all-routes, saved
  identity/start failure, archive and model-preview integration tests remain.
- Baseline `./tools/check.sh`:291 Python tests +16 Node + trace integrity passed.
  After extraction:313 Python tests +16 Node + trace integrity passed; focused
  HTTP tests22/22 passed. Full diff whitespace check passed. A fresh staged
  git checkout-index copy without ignored local profiles/tools also passed all
  313 Python tests +16 Node scripts + trace integrity.
- No worker agent was launched because no launch tool was exposed; no hardware,
  LAN listener, service restart, native or container trial was performed.

Continue R2b (routes) and R2c (source/artifact owner) as separate milestones.
Do not mark all R2 complete or expand into state/process/frontend changes.
