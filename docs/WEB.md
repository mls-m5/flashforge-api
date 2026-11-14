# Standalone local Finder workbench

OctoPrint development is **paused**. The main page is now independent of
OctoPrint: `python3 -m finderlab web`. Python 3.11+ and the standard library are
sufficient for the page and printer transfer. No pip installation is needed.

## Start with a fresh dummy

Terminal 1, from this repository root:

```sh
python3 -m finderlab mock --port 9000
```

Terminal 2:

```sh
python3 -m finderlab web --enable-upload --target-port 9000
```

Open **http://127.0.0.1:8000**, using the exact URL printed by the server.
Use `--listen-port 8001` if occupied. No printer connection or status polling
occurs on startup or page refresh. Uploads are disabled without `--enable-upload`.
The HTTP listener is restricted to loopback IPs; LAN binding is deliberately
rejected in this experimental version.

1. Drop one `.gx`, `.gcode`, `.g` or `.stl` file. This only stores it locally.
2. A print file can be downloaded/reviewed immediately. An STL requires the
   separately configured Orca stage below; clicking Slice never connects to a
   printer. The page has no model/toolpath preview yet.
3. Review the output and choose an unused ASCII remote basename. Confirm
   **Save to Finder · no start**. It opens a printer connection only after
   confirmation and can overwrite an existing remote file. Optional job controls
   below are separate actions and never appended to Save.
4. Wait for **Final save confirmed**, not just all block bytes acknowledged.
   On unknown result, inspect logs and physical state, not a blind retry.
5. Discard removes current input/generated files, not the saved printer file
   or private captures. It does not cancel a print. Only one slot/job exists;
   choose another file after explicitly discarding the current one.

There are no discovery, pause/resume, direct heater/motion or arbitrary-command
endpoints. Explicit Start/Cancel endpoints are disabled by default as below. Existing GX bytes/previews remain unchanged; plain G-code is neither
wrapped in GX nor safety-validated. The fingerprint gate remains Finder
`V1.5 20170419`. Other firmware support is not inferred.

**Confirm port 9000 really belongs to your new dummy.** A loopback proxy can
reach hardware. To deliberately configure a non-loopback target, use
`--target-host IP --target-port PORT --allow-hardware --enable-upload` only for
an approved supervised trial. No agent hardware trial is part of this work.

## Optional explicit Start and Cancel

To enable the separate buttons, first test with the new dummy:

```sh
python3 -m finderlab web --enable-upload --enable-job-controls --target-port 9000
```

In Podman, append `--enable-job-controls` to the arguments after the image name.
It is independent of `--enable-upload`; neither flag overrides the non-loopback
hardware guard or experiment approval. Buttons still require their own browser
confirmation. **Start may heat/move a physical printer behind a proxy.** No new
agent hardware trial is authorized or performed by adding these controls.

- **Start saved file** uses only the exact server-recorded basename from this
  slot's confirmed save. A per-save ID binds confirmation to that save so another
  tab cannot silently replace the reference. Editing the remote-name input after
  Save cannot redirect Start. A new firmware-gated session rechecks READY before
  M23. There is at most one Start attempt per slot; failed/uncertain attempts are
  not retried. Discard/restart loses the reference rather than guessing it.
- Save IDs do not lock or read back remote contents: another client can overwrite
  a filename on the printer. Close competing clients and start only reviewed,
  known-safe files. A successful save or slice is not a motion-safety certificate.
- **Request cancel** sends a separately confirmed M26 to the configured target,
  including jobs started outside this page; no local file is required. This is
  **not an emergency stop** and an ACK does not prove READY, stopped motion or
  cooled heaters. Check the physical printer. A deliberate new confirmation may
  send another cancel; the server/browser never automatically retries it.
- All operations share the single-job lock. Cancel is unavailable while another
  local operation is active; it is not injected into an upload's binary stream.
  Shutdown and failures never send automatic M26. Physical controls remain
  necessary for emergencies. No live printer polling/job monitoring is added.
- Start/cancel result and original save confirmation are separate facts. Lost
  replies report UNKNOWN; a failed start does not erase the confirmed save.
  Subsequent release/logging failures are shown separately. Context/loopback
  tests validate wiring, not physical start/cancel dynamics or safety.

## Orca is optional; native experimental slicing is not print approval

The page uses the existing resource-limited, shell-free Orca adapter. It does
not bundle a printer profile, edit the existing local draft, substitute Marlin,
turn off validity checks or pretend the Sailfish incompatibility is fixed.
Installed Orca 2.3.0 rejects the current draft's `gcode_flavor=sailfish`;
2.5.0 source also excludes it from accepted values. See
[ORCA_FINDER_DRAFT_01.md](ORCA_FINDER_DRAFT_01.md). A separate offline dialect/
profile decision is still needed before a useful native Finder slice can be
claimed. **The initial page is usable with existing FlashPrint GX files now;
STL → safe Finder toolpaths is not yet solved.**

The user subsequently authorized a separate **offline Marlin-emission draft 02**.
Native 2.3.0 now slices a generated cube and the supplied holder and the native
HTTP Slice/download path was checked, with uploads/job controls disabled.
Extrusion resets, final retraction and a slow Z layer-change hook address the
identified numeric issues, but G21/M82/M118 behavior and physical homing/clip
clearance remain unresolved. See [ORCA_FINDER_DRAFT_02.md](ORCA_FINDER_DRAFT_02.md)
for private artifact paths and a **read-only slicing-page invocation**. On this
workspace, `python3 tools/start_offline_web.py` is the short launcher for that
native experiment; it never enables uploads or job controls. Original
profiles are unchanged. Do not enable generated-output upload/start just because
this candidate slices successfully.

With your own trusted, self-contained and separately reviewed JSON profiles:

```sh
python3 -m finderlab web \
  --orca /absolute/path/to/orca-slicer \
  --machine local-profiles/reviewed-machine.json \
  --process local-profiles/reviewed-process.json \
  --filament local-profiles/reviewed-filament.json
```

The paths above are placeholders, not provided working profiles. See
[SLICING.md](SLICING.md) for required profile fields, CLI/native runtime setup,
limits and provenance. No path/executable/profile or arbitrary Orca argument is
accepted through HTTP. Drop STL (millimetres), explicitly Slice, then download
its generated plain `.gcode` for offline inspection. Native diagnostic excerpts
are bounded and displayed as text; private captures retain original output.
Slicing success never triggers an automatic save or print.

Saving generated output is **blocked by default** even when regular print-file
uploads are enabled. Only after separate profile/output review may an operator
also supply `--allow-sliced-upload` and `--enable-upload`. This is an explicit
policy opt-in, not a toolpath safety certificate. The browser still requires a
separate confirmed Save; a GX remote-name override for generated G-code is
rejected. Native code/profiles are trusted, not sandboxed: the resource wrapper
limits jobs but cannot deny arbitrary filesystem/network access to a malicious
slicer. Use only trusted local models on this experimental page.

## Podman on Linux

No OctoPrint setup or printer profile wizard is involved:

```sh
podman build -f docker/web.Dockerfile -t localhost/finderlab-web .
podman volume create finderlab-web-data
podman volume create finderlab-web-scratch
podman run --rm --name finderlab-web --network host \
  --cap-drop=all --security-opt=no-new-privileges \
  -v finderlab-web-data:/app/web-data:U \
  -v finderlab-web-scratch:/app/.tmp:U \
  localhost/finderlab-web --enable-upload --target-port 9000
```

Start the host dummy separately as above. Host networking makes its loopback
port reachable; the page itself binds only `127.0.0.1:8000`. `:U` changes
ownership inside these dedicated named volumes; do not substitute production
volumes/directories. Stop with `podman stop finderlab-web`; private data persists.
Rebuild the image after code changes.

The image contains **no Orca executable/native GUI libraries/profiles**. Use the
native Python invocation for initial Orca experiments. A pinned, tested slicer
container requires further work; mounting an executable alone is not sufficient
if its shared libraries are missing. Podman/Docker is unavailable in the agent
environment, so image build/runtime remain unverified.

The default `docker-compose.yml` now runs the standalone page (uploads disabled).
For a Compose provider, use `podman compose up --build` or
`docker compose up --build`. To enable transfers, deliberately add the desired
`--enable-upload --target-port PORT` command to that service. The old OctoPrint
example is preserved separately at `compose.octoprint.yml`; do not start it as
part of the standalone workflow.

## Storage, HTTP and failure boundaries

- `web-data/` is private and Git-ignored. Use a dedicated folder; `--data-dir`
  selects it; if changed, keep that location out of Git/build contexts yourself.
  One process holds its workspace lock. State is in-memory only;
  restart does **not** resume jobs or infer remote state. Interrupted files/logs
  remain on disk and count against quota; inspect/archive them locally.
- One resident file, one operation, no queue. STL ≤64 MiB; print/generated file
  ≤8 MiB; incoming file deadline 60 s. Header/JSON deadlines 10 s, headers
  ≤16 KiB, JSON ≤2048 bytes, at most 16 HTTP clients. Connections close after
  one request; no chunked upload, multipart, pipelining or Expect support.
- Workspace admission is conservatively bounded to 256 MiB and 4096 entries:
  each operation reserves a worst-case capture/output budget before starting.
  This includes stored files/captures, not the Orca adapter's separate bounded
  scratch workspace under project `.tmp/` or unrelated writers. Capture streams
  are capped at 64 MiB per operation; no automatic log deletion/rotation.
- Save has an overall 900-second deadline plus transport timeouts. Shutdown
  cancels local tasks/process groups and closes sockets, never sends a printer
  cancel. Partial/unknown remote files may remain. An unknown save cannot be
  repeated in the same slot; inspect first, then explicitly discard/reset.
- Raw captures and generated output can contain model bytes and identifiers.
  Do not publish them or whole runtime volumes. `complete` describes recording,
  not save/slice success. Save confirmation and later release/log failure are
  distinct facts; a confirmed save is not erased by a later error.
- Strict Host matching resists DNS rebinding; mutating requests require exact
  same Origin plus a per-run token fetched by the page. No CORS permission is
  emitted. CSP restricts scripts/styles/connections to this origin and rejects
  framing. No browser-supplied target paths, addresses or native options.
- This is a small HTTP/1.1 loopback workbench, **not a production web server**.
  It has no accounts/TLS; other local processes and browser extensions remain
  trusted. Never forward its port, put it on a public reverse proxy, or expose
  it to LAN/internet. No security-sandbox claim is made for native STL parsing.

## Narrow local API

All POSTs require `Origin: http://<exact printed authority>` and
`X-Finder-Token` from GET `/api/config`. Files use `application/octet-stream`;
other POSTs use `application/json`. Target/executable/profile/path overrides
are never accepted. GET config/state are local-only cached reads, not printer
queries. A successful action response means accepted/current state, not final
save or slice success; poll `/api/state` while `busy`.

| Method/path | Meaning |
| --- | --- |
| GET `/api/config` | Per-run token, fixed endpoint, capabilities and limits |
| GET `/api/state` | Current slot/job state and bounded private diagnostic excerpt |
| POST `/api/file?name=NAME` | Bounded raw bytes into empty slot; no slicing/printer connection |
| POST `/api/slice` | `{"confirm":true}`; offline Orca only |
| GET `/api/artifact` | Idle-slot print file download, fixed safe attachment name |
| POST `/api/save` | `{"confirm":true,"remote_name":"sample.gx"}`; upload only |
| POST `/api/discard` | `{"confirm":true}`; remove idle slot files, retain logs |
| POST `/api/start` | `{"confirm":true,"save_id":"ID from cached state"}`; gated exact saved file, fresh READY check |
| POST `/api/stop` | `{"confirm":true}`; gated cancel request, not emergency stop |

There is no general filesystem browser or raw capture download endpoint. The
printed private capture path is for deliberate local inspection.

## Local application trials (not hardware evidence)

Actual stdlib HTTP-client trials against freshly started ephemeral services:

- Supplied 3668165-byte GX → HTTP file endpoint → explicit Save → new dummy:
  exact byte equality, 896 frames, only M601/M115/M119/M28/M29/M602 and no
  virtual print. Private capture:
  `web-data/manual-gx/captures/20261114T132526Z-4112e567c689`.
- Native installed Orca 2.3.0, unchanged private Finder draft, generated binary
  review cube → HTTP Slice: expected Sailfish validation failure, bounded native
  diagnostic visible through cached state, no output artifact or printer
  sessions. Private capture:
  `web-data/native-profile-check/captures/20261114T132526Z-fe43872dc961`.
  An initial one-triangle ASCII sample failed model loading first (capture
  `20261114T132451Z-3249c3aae033`); it was replaced with the generated binary
  cube for the profile check. Neither run changed the profiles or contacted a
  printer. This is a failure-path trial, not successful native slicing.

Raw files/geometry and captures remain ignored. These trials exercise HTTP and
native adapter behavior, not a real browser rendering or physical compatibility.

## Checks and remaining acceptance

```sh
python3 -m unittest discover -s tests -v
node tests/test_web_ui.js
```

Tests use fresh ephemeral HTTP/TCP loopback endpoints, generated bytes and a fake
Orca executable. They exercise browser/server transfer separately from save,
exact payload/hash/command order, save without start/stop, separate confirmed
job controls with stale-ID/repeat/unknown guards, explicit gates, origin/token/
Host checks, truncated/oversized files, busy/quota/locking and slicing outcomes.
Node checks use a minimal DOM model, not a rendered browser. Native experimental generation has a separate recorded trial; a print-approved
Finder profile, actual browser drag/drop and container acceptance still need
manual validation. No physical printer is used or authorized by these checks.
