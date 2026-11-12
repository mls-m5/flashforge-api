# FlashForge Finder 2 protocol lab

Reverse-engineer the Finder 2 network protocol, build a realistic offline simulator, and eventually offer a small local drag-and-drop upload interface. **Uploading must not automatically start a print.**

## Current status

Implemented:

- An **offline TCP printer mock**, using Python 3.11+ and the standard library only. Its default `finder-v1.5` profile supports captured-style idle replies and framed upload, plus explicit virtual start/cancel. Earlier profiles remain selectable.
- Identity/status replies, control ownership, bounded RAM-only virtual upload storage and a mock file listing.
- **Persistent traffic logs and connection history** for mock, proxy and client commands, with exact request/reply streams.
- A **recording TCP proxy** for comparing FlashPrint traffic with the real printer's responses.
- A **GX upload CLI and reusable async client**, with exact block ACKs/CRC32, upload-only defaults, and separately confirmed start/stop actions.
- Automated localhost tests, including the existing uploader, recording failures and proxy transport behavior.
- The original experimental [`upload.py`](upload.py), unchanged.

Not implemented: UDP discovery, replay/standalone analysis tooling, physical job dynamics, or the web interface. **FlashPrint connection, upload and explicit virtual start/stop have now been observed against the dummy.** The new client has also uploaded the user's 3.67 MB GX to a fresh dummy with an exact byte match and no job started. A subsequent user-run host/proxy trial confirmed the new client's real-printer upload-only flow: all blocks, final save and release acknowledged, no start/stop sent. Other firmware, errors/retries and physical job-control actions remain separately bounded; mock success alone is not hardware evidence.

## Upload a GX file (dummy first)

Terminal 1:

```sh
python3 -m finderlab mock
```

Terminal 2:

```sh
python3 -m finderlab upload upload/test1.gx
```

The client defaults to `127.0.0.1:8899`. Confirm this is the **dummy**, not a proxy to hardware. It preserves all GX bytes/embedded thumbnails, validates block ACKs and final save, and sends **no start or stop**. Use `--port` for a different endpoint and `--remote-name "client sample.gx"` for an ASCII destination basename. Only observed Finder firmware `V1.5 20170419` is enabled.

Read [docs/CLIENT.md](docs/CLIENT.md) for proxy/direct hardware trials, safety confirmations, status/start/stop commands, errors and persistent client logs. A hardware trial requires physical supervision and explicit approval; non-loopback targets also require `--allow-hardware`. Slicing/GX/thumbnail generation is deferred—use a known-working FlashPrint file first. The old `upload.py` remains unchanged and is not the new client.

## Run the dummy printer

From the project directory, no installation required:

```sh
python3 -m finderlab mock --verbose
```

It listens on **127.0.0.1:8899** by default. Connect FlashPrint manually to that address. The mock saves only after `M29`, starts a virtual job only after `M23`, and cancels only after an explicit `M26`. It never heats, moves, executes G-code or connects to hardware.

The original `upload.py` uses raw bytes and **does not implement the observed block/CRC/ACK protocol**. To test that old script locally, explicitly run the legacy profile instead of the default:

```sh
python3 -m finderlab mock --profile synthetic-v1
# In another terminal:
python3 upload.py 127.0.0.1 path/to/model.gx
```

That legacy test does not validate a model or prove hardware compatibility. Virtual files disappear when the mock exits, but **recorded payload bytes persist on disk**. Every run prints its capture directory under `captures/`: start with `traffic.log` for timestamped requests/replies and connection history. Raw streams preserve bytes beyond the log's bounded previews. Recording is enabled even without `--verbose`; Ctrl+C finalizes the manifest.

Logs in this workspace can be inspected directly by the assistant when you provide their path. Logs on another computer must be copied here deliberately. See [docs/CAPTURES.md](docs/CAPTURES.md) for privacy and storage limits.

For a different local port:

```sh
python3 -m finderlab mock --port 9000
```

The old uploader still has a hardcoded port of 8899. Use a TCP test client for other ports. See [docs/MOCK.md](docs/MOCK.md) for commands, limits, troubleshooting and manual FlashPrint testing.

## Record actual printer responses

For an approved, supervised hardware experiment, stop the mock and replace the documentation IP below with the printer's actual address:

```sh
python3 -m finderlab proxy --target-host 192.0.2.10 --target-port 8899
```

Connect FlashPrint manually to **127.0.0.1** on the proxy computer. Begin with connection/status only. The proxy forwards **all** commands unchanged, including print-start and heating; it is not a safety filter. No discovery is implemented. See [docs/PROXY.md](docs/PROXY.md) for a local-only trial, network configuration and diagnosis of the current disconnect.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use ephemeral loopback ports and never connect to a physical printer. Generated test files use the ignored project-local `.tmp/` directory and are cleaned up; do not use the system temporary directory for project work. No third-party dependencies are required. One integration test retains the uploader's existing three-second pause.

## Components and next steps

| Component | Purpose |
| --- | --- |
| Recording proxy (implemented; localhost-tested) | FlashPrint → proxy → explicit target, preserving both byte streams. |
| Evidence-based simulator | Reproduce observed Finder 2 identity, sessions, status, transfer and discovery. |
| Analysis and replay | Inspect captures, compare experiments and generate regression fixtures. |
| Upload client and web UI | Use the verified protocol for local drag-and-drop transfer, without print-start. |

A real-printer connection/status capture now supplies independent regression fixtures, with private identity fields anonymized. The user's subsequent mock recording confirms sustained FlashPrint idle polling. A second capture now establishes the observed upload framing and start/cancel reply formats. Dynamic job behavior, error/retry handling and discovery still need evidence. Small regression fixtures are retained; a broader systematic log corpus/replay system is future work.

## Documentation

New documentation is English; older Swedish sections will be translated incrementally.

- [DESIGN.md](DESIGN.md): architecture, realism goals and safety boundaries.
- [AGENTS.md](AGENTS.md): contributor/agent rules, including milestone commits.
- [docs/CLIENT.md](docs/CLIENT.md): upload program, manual printer trials and separate job controls.
- [docs/MOCK.md](docs/MOCK.md): implemented mock behavior and usage.
- [docs/PROXY.md](docs/PROXY.md): recording proxy and real-response comparison.
- [docs/PROTOCOL.md](docs/PROTOCOL.md): evidence, hypotheses and open protocol questions.
- [docs/CAPTURES.md](docs/CAPTURES.md): implemented logs, history, recording format and privacy.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md): reverse-engineering procedures.
- [docs/ROADMAP.md](docs/ROADMAP.md): milestones and acceptance criteria.
- [docs/QUESTIONS.md](docs/QUESTIONS.md): environment and product decisions still needed.

## Safety

The mock has no outgoing printer connection and never executes G-code. Bind to loopback by default; use an explicit host address only when deliberately exposing the mock on a trusted LAN. Do not expose any project service or the real printer to the internet.

Hardware experiments require explicit approval and physical supervision. The old uploader is incompatible with the observed framing. The new client's upload-only workflow is dummy-tested and now has one successful user-run physical-printer trial; other firmware, physical job controls and failure cases require their own verification. Uploading does not validate G-code safety or fix incompatible slicer output. The implemented transparent proxy forwards dangerous commands too; it is not a safety filter.
