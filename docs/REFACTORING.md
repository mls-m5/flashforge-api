# Maintainability refactoring plan

## Scope and decision

The user approved the read-only maintainability review and requested a written
plan followed by incremental implementation. This is a **behavior-preserving
maintenance track**, not new printer capabilities, a framework migration or
hardware authorization. Commit each coherent stage with checks and explicit
remaining work. Do not combine a structural move with a protocol/policy change.

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
  from route dispatch. All routes, including assets/model/thumbnail, must retain
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

### R1 completed — next implementation stage is R2

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

Continue with R2's HTTP/workbench boundary in a separate coherent milestone;
do not silently expand this commit into state-machine/process/frontend changes.
