# Manual-control panel: virtual rehearsal, physical controls locked

## Browser interaction update

Recurring confirmation popups are removed at the user's request. A permitted
button click (or explicit simulated-warm checkbox change) now initiates the
virtual intent directly. Revision/typed/ownership/busy/job guards and API
`confirm:true` remain; uncertainty still never auto-retries. Historical
references below to confirmation mean the initiating action, not a modal dialog.

## Current scope

The panel has light colour/off, single-click XYZ steps, and extruder feed/retract.
**It works only in a fresh dummy owned by this web process.** Configured targets,
including a loopback dummy/proxy, are locked: neither upload/job-control flags
nor browser parameters enable physical manual control. This milestone is UI /
validation groundwork, not completed physical printer control.

The capture described in [MANUAL_CONTROLS_CAPTURE.md](MANUAL_CONTROLS_CAPTURE.md)
used Continuous jog and large relative targets, decimal commas and LF-only
manual ACKs. Millimetre-step/mode/temperature behavior remains unverified.
There is deliberately **no command encoder, manual socket client, replay,
parser relaxation, homing, motor release, heater or M112 button** here. No
hardware was contacted. The ordinary TCP mock still rejects motion/heating
commands and still returns its fixed M114/M105 observations; uploaded G-code
is never executed. The control rehearsal is a separate in-memory UI model.

## Try it without Orca or profiles

```sh
./tools/start_control_panel_test.sh
```

Open the printed loopback URL (default8000). Optional HTTP port:
`./tools/start_control_panel_test.sh 8002` (0 selects an ephemeral port).
It starts a **new owned dummy**, never reuses a listener/proxy, and enables
normal virtual Save/Start/Cancel plus automatic status polling to that dummy.
Manual controls themselves send **no TCP/G-code**; they change virtual counters
only. No file or slicer is required to try the panel. The existing owned-dummy
upload launcher also gets the panel; offline/proxy pages display it locked.
Ctrl+C closes the web/dummy, never sends automatic print-cancel.

1. Choose a colour and explicitly confirm Apply colour, or Light off. RGB is
   virtual state, not observed LED feedback or a verified on/off wire policy.
2. Choose XY0.1/1/5mm or Z0.1/1mm and click one direction; confirm each intent.
   There is no press-and-hold or keyboard repeat. The default is0.1mm.
3. Extruder rehearsal is locked in both directions until explicitly checking
   **Simulate warm nozzle**. This changes a boolean only: no heating or physical
   temperature claim. Feed/retract choices are1/5mm. Real extrusion must later
   use fresh measured-temperature/firmware/mode guards, not this fake flag.
4. Virtual XYZ relative totals are bounded to±10mm, extrusion to±20mm. These
   are toy counter limits, **not bed coordinates, calibration or physical travel
   limits**. M114/status temperatures do not change to pretend otherwise.
5. Manual rehearsal is blocked during any local file/job operation, an active
   virtual print or unknown local printer result. Rejected controls never
   cancel a job. Cancel is still a separate, confirmed virtual job action.

## Consistency and recording

Each action is a typed allowlisted intent with explicit confirmation and the
current integer `revision`. Repeated/stale revisions conflict rather than
repeat a step. Two tabs/double clicks cannot apply the same revision twice.
The UI sends no POST on load, colour/step selection, automatic refresh, pointer-down,
keyboard repeat or lost-response retry. An unknown response locks the panel
until explicit **Refresh control state**; cached reads never repeat actions.
The revision is a stale/replay guard, not proof of exactly-once hardware motion.

GET `/api/manual-state` reads only cached toy state and local busy/job flags.
POST `/api/manual` uses the existing same-Origin/token protections, bounded JSON
and exact fields; it accepts no target, file/path, G-code, arbitrary feed/speed,
continuous targets or heater settings. Example virtual-only intent:

```json
{"action":"jog","axis":"X","distance":0.1,"revision":0,"confirm":true}
```

`manual_controls.py` prepares a detached candidate without mutating current
state. The workbench checks ownership/busy/job/unknown state, validates the
intent and reserves storage before recording. No await/network call occurs
between validation, recording and commit. A separate private `manual-virtual`
capture records `manual_virtual_intent` with before/candidate/intent; the counter
change commits only after successful recording finalization. An event alone is
not proof that commit occurred if recording failed or the process crashed.
Captures have no raw network sessions, `wire_commands_sent:false`,64KiB/run
limits and count toward the existing workspace byte/entry admission. There is
no automatic deletion or unlimited action history in memory.

File discard does not reset these counters or the virtual print. Counters reset
on server restart only; captions always say **virtual**, never actual position.
A restart uses a new token; old-page requests cannot silently operate new state.
Private captures remain in `web-data/control-panel-test/` (or the active owned
workspace); do not publish them or unrelated upload captures.

## Actual short-launcher check

A local application trial ran `./tools/start_control_panel_test.sh 0`, fetched
configuration/control state and explicitly applied one virtual X+0.1mm intent
over HTTP, then stopped with SIGTERM. Private intent capture
`web-data/control-panel-test/captures/20261114T211520Z-dc5466b8f23b` finalized
with zero sessions. The companion monitor capture
`20261114T211520Z-fcec1dd5f499` finalized with one fresh-dummy session and only
M601/M115/M119/M105/M27/M602. No light/extrusion/motion/start/cancel command was
sent. This tests the real launcher/HTTP wiring, not browser rendering or Finder
hardware. No Orca/profile/slicer was involved.

## Checks and remaining acceptance

```sh
python3 -m unittest discover -s tests -v
node tests/test_manual_ui.js
```

Pure-model, fresh-loopback HTTP and mocked-DOM tests cover typed/nonfinite/
large/bool input rejection, exact step choices, counter bounds, cold lock,
revision races, busy/active-job/unknown guards, no configured-target unlock,
Origin protection, recording/quota failures without state commit, no TCP client
invocation for manual actions, no repeat on uncertainty, and no implicit moves.
These tests do not render a browser or establish any physical command semantics.

Before physical controls, ask for a separately authorized, supervised capture
of FlashPrint's **smallest millimetre-step mode**, with an empty clear printer,
known mode/position/direction and physical controls available—not during an
active print. Establish mode restoration, decimal interpretation, relative E,
actual measured displacement, limit/thermal behavior and the scoped LF-only
reply parser using independent fault tests. Light colour/off needs its own
isolated observation. Reuse the shared network lock/ownership policy only after
that design is reviewed; this counter-only milestone does not validate it for
physical motion. Never transplant the captured±1000 jog targets or label M112
a verified emergency stop. See the capture notes for existing evidence limits.
