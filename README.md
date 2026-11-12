# FlashForge Finder 2 protocol lab

Reverse-engineer the Finder 2 network protocol, build a realistic offline simulator, and eventually offer a small local drag-and-drop upload interface. **Uploading must not automatically start a print.**

## Current status

Implemented:

- A **synthetic TCP printer mock**, using Python 3.11+ and the standard library only.
- Identity/status replies, control ownership, bounded RAM-only upload storage and a mock file listing.
- Automated localhost tests, including the existing uploader against the mock.
- The original experimental [`upload.py`](upload.py), unchanged.

Not implemented: UDP discovery, recording proxy, capture/replay tooling, capture-derived Finder profiles, virtual printing, or the web interface. **Finder 2 and FlashPrint compatibility remain unverified.** The mock's response syntax and raw-upload framing are hypotheses, not captured printer behavior.

## Run the dummy printer

From the project directory, no installation required:

```sh
python3 -m finderlab mock --verbose
```

It listens on **127.0.0.1:8899** by default. In another terminal, test the existing uploader against this local mock:

```sh
python3 upload.py 127.0.0.1 path/to/model.gx
```

This tests the synthetic protocol only; it does not validate a model or prove hardware compatibility. Files disappear when the mock exits. Verbose logging shows commands and committed file sizes, not binary payload contents. Stop with Ctrl+C.

For a different local port:

```sh
python3 -m finderlab mock --port 9000
```

The old uploader still has a hardcoded port of 8899. Use a TCP test client for other ports. See [docs/MOCK.md](docs/MOCK.md) for commands, limits, troubleshooting and manual FlashPrint testing.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use ephemeral loopback ports and never connect to a physical printer. No third-party dependencies are required. One integration test retains the uploader's existing three-second pause.

## Planned components

| Component | Purpose |
| --- | --- |
| Recording proxy | FlashPrint → proxy → real printer, preserving both byte streams. |
| Evidence-based simulator | Reproduce observed Finder 2 identity, sessions, status, transfer and discovery. |
| Analysis and replay | Inspect captures, compare experiments and generate regression fixtures. |
| Upload client and web UI | Use the verified protocol for local drag-and-drop transfer, without print-start. |

The synthetic mock is being implemented before reference captures at the user's request. A reference capture is still required to make it a trustworthy substitute for the physical printer.

## Documentation

New documentation is English; older Swedish sections will be translated incrementally.

- [DESIGN.md](DESIGN.md): architecture, realism goals and safety boundaries.
- [AGENTS.md](AGENTS.md): contributor/agent rules, including milestone commits.
- [docs/MOCK.md](docs/MOCK.md): implemented mock behavior and usage.
- [docs/PROTOCOL.md](docs/PROTOCOL.md): evidence, hypotheses and open protocol questions.
- [docs/CAPTURES.md](docs/CAPTURES.md): proposed capture format and privacy.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md): reverse-engineering procedures.
- [docs/ROADMAP.md](docs/ROADMAP.md): milestones and acceptance criteria.
- [docs/QUESTIONS.md](docs/QUESTIONS.md): environment and product decisions still needed.

## Safety

The mock has no outgoing printer connection and never executes G-code. Bind to loopback by default; use an explicit host address only when deliberately exposing the mock on a trusted LAN. Do not expose any project service or the real printer to the internet.

Hardware experiments require explicit approval and physical supervision. The existing uploader is experimental and is not a verified Finder 2 client. A future transparent proxy will forward dangerous commands too; it will not be a safety filter.
