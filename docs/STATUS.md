# Printer status: active polling and passive proxy recordings

## Active polling (default in the proxy web launcher)

At the user's request, `./tools/start_proxy_web.sh` now **connects on startup**
to its explicitly configured loopback proxy for status polling. Verify the
proxy's upstream first and **close FlashPrint and other control clients before
launching**. This is a deliberate change from the former no-connect startup.
There is no discovery. The agent's checks use fresh loopback dummies only.
A user-run physical monitoring session is now observed (FINDER-PROGRESS-019
below); broader firmware/error/session-handoff and browser acceptance remain
pending. No agent hardware connection was made.

- One firmware-gated session (M601/M115), then serial M119/M105/M27 batches,
  **one second after each completed batch**. These are requested snapshots,
  not spontaneous events or exact firmware synchronization. No heating, motion,
  upload, print-start or print-cancel commands are sent by the monitor.
- The shared network lock releases the monitor's control/session before local
  Save/Start/Cancel and pauses polling while a local operation is busy. After a
  successful operation it may open a fresh status session. An uncertain printer
  operation, failed release, query/identity/protocol/recording error stops it;
  there is **no automatic error retry/reconnect**. Other processes/FlashPrint
  are not covered by this local lock.
- **Stop status polling** closes only monitoring, not the print. **Start status
  polling** explicitly confirms reconnection. Refresh only reads cached HTTP
  data; opening/reloading a browser tab never restarts polling or retries jobs.
  Stop is allowed during a local operation; cleanup may wait for its lock.
- To leave polling off at startup: `./tools/start_proxy_web.sh --no-monitor`.
  Manual Start remains available. This does not enable upload/job controls in
  the read-only observer. `tools/watch_printer.sh` remains fully passive.
- The offline slicing launcher still never connects. Owned-dummy upload mode
  automatically polls **its owned fresh simulator only**, not existing proxies.
  Low-level `python3 -m finderlab web` remains disconnected by default:
  `--auto-monitor` explicitly enables startup connection; `--enable-monitor`
  permits manual Start only. No Save/Start/Cancel policy flags are implied.
- Active samples are timestamped when the complete batch was parsed/recorded,
  not when physical motion occurred. The UI labels the source/capture/session
  and endpoint. Stopped samples immediately become stale, even if recent.
  No active failure silently falls back to old passive data labelled live.
- Each monitor run records raw bytes and `status_snapshot` events privately
  under its web workspace (64 MiB, at most256 sessions). Quota/entry admission
  reserves space for its remaining capture budget alongside ordinary jobs;
  limits stop monitoring rather than deleting logs/continuing unrecorded.
  Long prints can exhaust the quota: archive logs locally and explicitly restart
  monitoring, never infer that a stopped monitor means a stopped print.

## Passive mode: what is implemented

The web page now shows a **Printer status** panel: observed nozzle/bed actual
and target temperatures, MachineStatus/MoveMode, and M27 reported file-byte
progress. It is read-only and **does not open a printer socket, claim control,
or send any printer command**. It reads the traffic FlashPrint is already
polling through the recording proxy. Browser polling every2 seconds asks only
our local HTTP API, not the printer.

This mode is separate from active polling. Do not start active polling while
FlashPrint is already controlling/polling the printer.
If nobody asks the printer status questions, a transparent proxy cannot invent
updates. The panel never treats missing observations as stopped printing.

## Watch during the current print without restarting other services

Leave FlashPrint and the proxy running, then from the project root:

```sh
./tools/watch_printer.sh
```

Open **http://127.0.0.1:8001**. This separate page has uploads, Start/Cancel and
slicing disabled. It observes existing recordings for proxy listener
`127.0.0.1:9000`; it does not start/restart the proxy, use the printer IP or send
a handshake. Ctrl+C stops only this observer. Optional web port:
`./tools/watch_printer.sh 8002`.

The proxy launcher retains `--status-capture captures`, but now uses active
polling by default. Use the separate observer for passive-only viewing while
FlashPrint is connected. Passive status never enables actions. Do not restart an active save/slice just
to update the UI. The short offline and owned-dummy launchers do not observe
physical-printer logs; owned-dummy mode explicitly disables this status source.

An explicit source can be a run directory or a captures root, using the
server CLI `--status-capture PATH`, or proxy wrapper:

```sh
./tools/start_proxy_web.sh --status-capture captures/REVIEWED_RUN_ID
```

Relative wrapper paths are project-relative. No HTTP argument can choose a
capture path, target or printer command. The page must still use the exact
loopback URL printed at startup. Never expose this private status page to LAN
or forward its port externally.

## Freshness and source identity

- With a capture root, choose the lexically newest valid **proxy** capture
  matching the web target's listener host/port. The printed source run, session
  and captured upstream are shown so the user can verify what is observed. A
  proxy restart can change the upstream behind the same port; the source is not
  a cryptographic printer identity guarantee. Select an explicit run if needed.
- The current view uses one session's replies, not a blend of temperature from
  one session and state from another. Missing metrics are unknown. The latest
  session with complete timestamped recognized replies in the bounded tails is
  selected; its session ID is displayed. New short connections can therefore
  temporarily show incomplete information. It does not silently label such a
  view fully current.
- Each metric shows its own UTC observation time and age. Ages derive from raw
  stream offsets and the corresponding proxy data event, not the time the page
  fetched the log. Last-write time alone is not status freshness.
- More than10 seconds old, future clock skew beyond5 seconds, missing/invalid
  fields or absent metrics mark the observation **stale/incomplete**. Old values
  can be displayed labelled stale, not claimed live. A failed HTTP read clears
  values to unknown instead of leaving a fresh-looking stale display.
- Manifest `complete` describes recording finalization, **not printer/job
  completion**. A non-finalized capture might be running or interrupted; neither
  is automatically inferred. The panel labels it accordingly.
- M27 byte counts are not time remaining, executed motion or a completed-print
  guarantee. Repeated values may be firmware reporting granularity; no stalled
  print is inferred. If the device reports76580/76579 as observed previously,
  preserve both raw numbers, flag the overrun and cap only the displayed percent
  at100. Zero totals yield unknown percent. READY and byte100% are not proof
  of cooled heaters, successful print quality or safe cancellation.

## Data and parser boundaries

GET `/api/printer-status` returns the active monitor's cache when one was
started, otherwise passive observations. It never initiates a printer request.
POST `/api/monitor` with `{"enabled":true,"confirm":true}` starts monitoring
only when the server permits it; false stops it. Exact Origin/token protection
and typed allowlisting apply. No target/command/interval override is accepted.

The status response contains only derived fields, observation metadata and
source labels. No raw G-code, full replies, serial/name, paths supplied by HTTP,
or capture-download endpoint is added. Configuration is trusted local startup
input. Reading logs does not edit raw originals or generate new traffic captures.

`finderlab/passive_status.py` reads at most256KiB of event tail and64KiB of raw
server stream per selected candidate session (at most16 recent session IDs),
with manifests capped at1MiB and capture-root enumeration at1024 entries. Data
is bounded; an older status beyond those windows is unknown rather than found
by unbounded archive scanning. Avoid huge archives in the live capture root;
choose an explicit run directory when needed. Symlink/special stream files are
not followed; local capture directories/writers are trusted, not an OS sandbox.

Only complete echo-framed M105/M119/M27 replies from authoritative raw byte
ranges are parsed. Stream fragments and coalesced replies are handled; an
incomplete final reply is ignored. LF-only manual ACKs are not merged into a
status reply. Error/invalid newer frames invalidate their metric. Partial JSON
records while logging are tolerated, not rewritten. No inference of spontaneity,
request-side execution or physical behavior is added by this parser.

## User-host terminal byte overrun and active monitoring observation

The user reported progress one byte beyond the total. Existing proxy capture
`20261114T214419Z-91f9faa3164d` / host monitor
`web-data/proxy-test/captures/20261114T214811Z-696f28901933`, s0001, show repeated
raw `SD printing byte 428450/428449`. At 21:52:53 UTC the captured state was
READY/READY, actual nozzle 100°C / target 0°C. The discrepancy is already in the
printer reply, not caused by page percentage rounding. Earlier cube observations
showed 76580/76579; its root cause is still unknown. The current UI already caps
percentage at 100% and flags the raw overrun, without inferring completion or
subtracting a byte. No payload/parser/framing/timing change is justified.

The inspected host monitor prefix contains only M601/M115 and repeated
M119/M105/M27; firmware V1.5 20170419 is captured. This is user-run physical
status-session evidence, not a new agent hardware test, end-quality/touch-safety
proof or validation of error/reconnect/control-handoff behavior. The recordings
were ongoing/unfinalized and read without alteration; observations are dated
snapshots, not a promise of present state. See FINDER-PROGRESS-019 for scope.

## Evidence and checks

Initial read-only inspection of the user-run active proxy capture
`20261114T201427Z-97f92a5c0249` showed FlashPrint's M601/M115/M650/M114 prefix
and sustained M105/M119/M27 queries during printing. Responses included
T0:220/220, BUILDING_FROM_SD/MOVING and repeated5151/428449-byte progress.
A later local passive-parser read found13515/428449 at2026-11-14T20:22:07 UTC.
These are observed snapshots, not a promise of current state. No agent printer
connection or control command was used. Firmware/client-version context remains
that in the source capture (FinderV1.5; FlashPrint version unknown).

```sh
python3 -m unittest discover -s tests -v
node tests/test_web_ui.js
node tests/test_passive_status_ui.js
node tests/test_active_status_ui.js
```

Active tests additionally use fresh loopback dummies to check startup opt-in,
manual Stop/Start/gates, persistent sessions, shared-lock Save/resume without
start/cancel, stop-on-failure/quota, no reconnect after uncertain Save, early
shutdown and storage failure before connection. Launcher checks verify proxy /
owned-dummy defaults and offline no-connect. These automated checks claim no
physical monitoring or rendered browser acceptance; the separate user-host
observation above has its own bounded evidence.

Passive tests use synthetic recordings, fresh local HTTP contexts and mocked browser
requests. They cover fragmented/coalesced frames, stale/partial/error samples,
clock skew, zero/over-total progress, source matching, no cross-session blending,
read-only file hashes, no FinderClient invocation, duplicate poll prevention
and clearing values on read failure. They do not validate a rendered browser,
all firmware status variants or physical printer behavior. Passive reading of
an actual user capture was checked separately. The agent performed no active
hardware test; the user-host monitor observation is documented above.
