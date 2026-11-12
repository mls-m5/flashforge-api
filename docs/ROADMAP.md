# Roadmap and acceptance criteria

Everything below is planned unless explicitly marked complete.

## Implementation update: initial dummy printer

At the user's request, a synthetic TCP mock has been implemented ahead of the recording proxy and real-printer captures. It provides the first offline-testable server, control ownership, fixed identity/status replies, bounded RAM uploads, commit/discard semantics and a mock listing. See [MOCK.md](MOCK.md). Run it with `python3 -m finderlab mock`; run tests with `python3 -m unittest discover -s tests -v`.

## Implementation update: recording and proxy

Both CLI modes now write persistent per-run logs, structured events, per-session binary streams and final hashes/manifests. A byte-preserving TCP proxy supports explicit IP/port targets, bidirectional backpressure, half-close, connection/idle timeouts and fail-closed recording. Tests cover binary streams, concurrent sessions, active one-way transfer, recording limits/I/O failure and CLI restart history. Temporary test data stays inside ignored `.tmp/`.

This delivers the main M1 transport/recording foundation, but a standalone capture validator remains missing. The package is flat (`finderlab/`) and uses standard-library tests without installation. See [PROXY.md](PROXY.md) and [CAPTURES.md](CAPTURES.md).

## Implementation update: captured idle profile

A user-collected real-printer proxy capture establishes the `V1.5 20170419` connection/status baseline. Default `finder-v1.5-idle` replies match a reviewed fixture with name/serial anonymized. Independent byte-for-byte tests cover the initial connection/polling sequence and repeated/reordered queries. The user's subsequent finalized mock capture confirms FlashPrint connection and idle polling. `synthetic-v1` remains selectable.

This advances M2/M3, not completion: client version remains unknown; upload, printing, errors, discovery and the remaining acceptance criteria still need evidence and implementation.

## M0 — Agree on the test setup

- Confirm the model, firmware, FlashPrint version, host OS and GitHub reference.
- Decide whether hardware is available for a supervised baseline capture.
- Check whether FlashPrint supports manual IP connection and upload without print-start.
- Confirm Python 3.11+ availability or revise the proposed runtime.

**Done when:** the environment and safety limits are recorded. Unknown details may remain explicit blockers rather than guessed defaults. Offline transport development does not need to wait for every hardware answer.

## M1 — Project skeleton and byte-preserving proxy

Implement packaging, CLI/configuration, recording format and TCP proxy. Include a local fake server, tests and documented actual commands. No discovery emulation or protocol rewriting is required yet.

**Acceptance:**

- Listen address/port, target address/port and capture directory are configurable; loopback is the default bind.
- Bidirectional binary traffic remains byte-identical under fragmentation, coalescing and simultaneous traffic.
- Independent sessions, backpressure, half-close, refused connections, timeouts and cancellation are handled.
- Recording offsets, timestamps, hashes and complete/incomplete markers can be validated.
- Disk/logging failure is visible and never produces a supposedly complete capture.
- Tests run without printer access and verify that no configured hardware target is contacted accidentally.

**First useful deliverable:** a proxy tested against a fake printer, plus a procedure for an approved FlashPrint capture. This is not yet Finder 2 protocol compatibility.

## M2 — Capture inspection and reference behavior

Implement session summaries, hex/text views and byte-range extraction. Obtain and document a direct/proxied baseline (when hardware access is approved). Extract reviewed, shareable fixtures where possible.

**Acceptance:**

- Identify the request/response sequence for connect, identity, status and disconnect.
- Determine actual upload framing from a successful FlashPrint transfer, or explicitly record why this remains blocked.
- Determine whether discovery support is required before FlashPrint can use our endpoints.
- Attach model/firmware/client versions and capture references to protocol findings.
- Source bytes and captured payload can be compared without lossy decoding.

Synthetic fixtures can support tooling tests but must not be labeled captured Finder behavior.

## M3 — Stateful simulator, direct connection first

Implement versioned identity/status profiles, session ownership, the verified upload state machine, virtual files and capture output. A synthetic profile may precede captured profiles, with clear limitations.

**Acceptance:**

- A specified FlashPrint version accepts a Finder 2 profile and remains connected through repeated status polls.
- Two files of different sizes/names can be transferred; the simulator stores the expected exact bytes and reports consistent state.
- Fragmented commands, command-like payload bytes, final payload plus next command in one read, invalid lengths, limits and interrupted uploads have tests.
- Unknown commands are visible and do not silently succeed.
- No physical printer connection or executable G-code path exists in simulator mode.
- Compatibility claims list the validated profile and tested workflow, not just “works with FlashPrint.”

**Blocked without reference data:** realistic identity/error/upload behavior cannot be claimed from a self-consistent simulator/client pair alone.

## M4 — Discovery and broader FlashPrint compatibility

Move this milestone earlier if manual endpoint selection is unavailable. Implement only the discovery variant established by captures, with explicit network-interface selection.

**Acceptance:**

- FlashPrint discovers the simulator on the documented LAN setup and connects to it rather than the real printer.
- Advertised identity and endpoint match subsequent TCP responses.
- Raw discovery queries/replies are available as fixtures with documented field interpretations.
- Restart, reconnect, altered polling order and control conflicts have defined behavior.
- Unsupported versions/topologies are listed, not hidden behind fabricated replies.

## M5 — Verified upload-only client

Replace or wrap the experimental script only after the upload protocol is evidenced. Add configurable port, robust response buffering, cancellation and explicit success/unknown-result semantics.

**Acceptance:**

- Works against the simulator and independent reference fixtures.
- An explicitly approved real Finder 2 trial confirms file acceptance and no print-start.
- No generic retry of partially completed uploads; loss of final acknowledgement is reported as uncertain.
- Errors and cleanup are tested, including disconnect while the printer might still own a temporary file.
- Any removal of the existing fixed delay is validated, not merely assumed safe.

## M6 — Minimal web interface

Implement local drag-and-drop/file selection, explicit upload confirmation, configured printer target and honest progress/error reporting. No slicing, automatic print-start, arbitrary command console or cloud access.

**Acceptance:**

- Dropped files do not trigger transfer until the user confirms.
- Browser upload and printer transfer are distinguishable; sent bytes are not presented as printer confirmation.
- File/path limits, temporary-file cleanup, operation locking and cancellation are covered by tests.
- Target address comes from trusted server configuration, not arbitrary browser input.
- End-to-end tests use the simulator; physical-printer tests remain opt-in.
- Loopback is the default; LAN serving is documented as a separate security configuration.

## Deferred work

Virtual print-progress simulation, additional firmware/client profiles, richer fault injection, exportable reports and optional separate print controls can follow. Print controls require a new safety/design decision rather than being added as a side effect of upload support.

## Definition of done for each milestone

Include executable tests, documented actual commands, implementation status, known gaps and evidence references. Keep `README.md`, `DESIGN.md` and protocol notes consistent. New documentation is in English; existing Swedish text is translated incrementally when edited.
