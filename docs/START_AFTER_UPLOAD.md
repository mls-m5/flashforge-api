# Web checkbox: start after confirmed upload

## Changed default, explicitly requested by the user

With server upload/job controls enabled, the page now has **Start print when
upload completes**, **checked by default**. Save's label becomes **Save + start
<exact name> · may heat/move**. Uncheck for **Save · no start**. A chosen
save-only preference is not rechecked by state refresh; reloading the page
restores its initial default. No confirmation popups. Without server job controls
the checkbox is disabled/unchecked and Save remains save-only. Server capabilities
are not enabled by this UI change.

Selecting/dropping/slicing a file, editing geometry, GETs, opening a page or
starting status observation never request print start. The initiating combined
button click is explicit save/start intent. The separate Start button remains
for a confirmed saved file, and Cancel remains separate/not emergency stop.
CLI upload defaults and `--start` behavior are unchanged.

**This changes the previous web Save default when job controls are enabled.**
Restart backend and reload browsers; inspect the button/checkbox before clicking.
Losing a browser response or closing its page does not cancel an already accepted
backend workflow: it may still finish save/start. Refresh, never blindly repeat.

## Backend composition and outcomes

POST `/api/save` accepts typed `start_after_upload` (boolean, omitted=false for
legacy API callers). True additionally requires the exact current
`artifact_sha256` and per-receipt `source_id`; browser Save sends these identities
also for save-only. Stale/missing identities, wrong types, disabled job controls
or generated-output permissions fail before connecting. Local identity checks
are not remote file read-back or defense against competing printer clients.

1. Hold one busy local operation slot for the whole request. Use the existing
   byte-preserving uploader/firmware gate and require all block ACKs/final M29.
2. Record confirmed save immediately, even if later release/logging/start fails.
   Verify actual uploaded hash matches the requested artifact hash; otherwise
   keep the confirmed save fact but block start and report unknown/error.
3. Release/close that session healthily, finalize the **save capture**, require
   complete recording and unchanged exact saved name/hash/save identity.
4. Only then mark the one start attempt and open a **fresh** firmware-gated
   session. `FinderClient.start` rechecks READY before M23 for that saved name.
   The busy slot never opens between stages; monitor cannot reclaim it there.
5. Record start ACK separately. Failed save, unknown M29, unhealthy release,
   changed identity/hash, recording failure, cancellation or not-READY never
   produce a blind follow-up/retry/stop. A start failure never reuploads the file.
   `start_attempted` prevents repeating the attempt, including failed READY or
   uncertain start; no automatic M26/deletion is sent.

State retains `start_after_upload`, `save_capture`, `start_capture`, confirmed
save identity and `job_result` independently. `start_not_sent` means the request
was blocked before its follow-up; `start_pending`, `start_acknowledged` and
`start_unknown` distinguish subsequent stages. Not-sent is scoped to this
operation, not a claim that the printer is globally idle. Save-only retains
`not_requested`. Explicit manual recovery remains separate.

Two private captures keep stages independent: save mode/client operation`save`
contains requested combined intent and save result; start operation`start`
references the save capture/name/save_id, with `start_after_upload:true` only
for the backend continuation. Save capture is not edited after finalization.
Save recording limit64MiB remains; job-only Start/Cancel captures are now1MiB.
Admission reserves both save and follow-up job budgets up front, alongside
remaining monitor capacity. Captures include uploaded bytes and remain ignored.

## Validation and limits

Fresh loopback dummies/scripted clients test exact destination, finalized
separate records and healthy release before fresh READY/M23, continuous busy
slot, capability/type/stale identities, changed source bytes, save failure,
release/finalization failure, not-READY and uncertain start, no repeat and no
M26. Existing omitted/false save-only cases still assert no start. UI tests
cover checked default, exact button name, unchecking persistence, capability
fallback, double click and one POST (the browser does not independently submit
Start). No popup, physical printer/proxy or hardware motion test.

Run the normal Python/Node suite and `node tests/test_start_after_upload_ui.js`.
Browser/host acceptance remains user-run. Existing profile/priming/clearance and
remote overwrite/concurrency limitations are not fixed by this checkbox. It
is not permission to print unreviewed generated G-code or an agent hardware
trial. In particular the existing fixed prime can still cross some models;
placement-aware skirt/edge review now exists separately in PRIMING_REVIEW.md,
but changed startup has not been promoted to the normal printer profile.
