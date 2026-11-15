# Web storage admission and explicit rejection feedback

The active web limit defaults to **256MiB persistent workspace storage**, not Python/browser RAM
or the operating system's free memory. It counts old captures plus current and
abandoned file slots under the configured `web-data/...` workspace, and reserves
worst-case space before a new operation. The repository `.tmp/` and external
proxy captures are not part of that web quota; deleting `.tmp/` does not free
this admission budget and can break active native jobs. Filesystem free disk is
a separate constraint. Neither arbitrary temp deletion nor disabling limits is
a default recovery action.

An active monitor reserves its remaining64MiB recording allowance plus1MiB
metadata overhead. Slice admission reserves another73MiB (capture64 + output8 +
metadata1). Thus154MiB used can exceed256MiB admission even though files alone
are below it. A received model can fit while the subsequent Slice is rejected
**before task/capture creation**. Stop status polling (not print cancel) releases
the monitor reservation once its recording closes; it does not delete history.
No automatic stop/cancel/printer action is performed to recover space.

Quota rejection now includes used/reserved/limit MiB, the monitor's reservation,
that the operation was not started and manual observation-stop/archive options.
The page mirrors errors at the top. Explicit preflight replies400/403/404/409/
413/415/422/507 no longer latch the uncertain-operation lock: the operator can
correct the issue and deliberately retry. There is still **no automatic retry**.
Lost/malformed responses,408 and server-I/O5xx remain uncertain and require
explicit Refresh; definite rejection must not be conflated with a lost save/
start response. Tests cover this distinction and reservation release.

## Automatic intact archival (now explicitly user-requested)

After a repeat507 during multi-model Slice, the user explicitly requested
automatic archival. It is now enabled by default, **only when admission would
otherwise fail**. Oldest finalized, complete captures with all sessions closed
move intact from `captures/ID/` into **`archive/captures/ID/` inside the same web
data directory**. This keeps records on the same persistent/container volume.
The archive subtree is excluded from the active256MiB admission budget but
separately capped at **2GiB/16384 entries**. An append-only `archive/index.jsonl`
records relative old/new paths, size and time. Raw files/manifests are not edited,
merged, overwritten or deleted. This is quota relief, not OS disk-space cleanup.

Active/incomplete/crash-partial captures, current selected/save/start references,
the current monitor capture and all model/plate/output slots are protected.
If no eligible history exists, a collision/permission/scan error occurs, or the
archive budget is full, admission still fails visibly; there is no silent data
loss, unlimited retention or automatic printer action. Existing operation locks,
job reservations and unknown-result/no-retry safeguards remain. No archival is
triggered by cached GETs. The page reports a successful archive near Slice, and
rejection text now appears **beside Slice**, not only at the top/bottom.

Options for raw web and all standard wrappers:

```sh
./tools/start_proxy_web.sh --storage-limit-mib 512 # add your usual job/generated-file flags if required
./tools/start_lan_web.sh --storage-limit-mib 512
# Optional research opt-out:
./tools/start_web_interface.sh --no-auto-archive
```

The quota override is explicit, integer128–2048MiB; default stays256. It never
changes RAM, physical disk capacity, archive cap or printer permissions. Restart
the backend/reload browsers for these policies; the existing proxy can stay up.
Do not increase limits without disk-space planning. Moving old archive records
to external storage remains a deliberate user operation when its own cap fills.
Tests use synthetic completed/incomplete/protected/colliding/symlink records,
check exact byte preservation and oldest-first ordering, no unneeded/disabled
move, archive caps, current-slot preservation and visible persistent UI errors.

## User-authorized archive, 2026-11-15

During urgent diagnosis, the newest model receipt existed but no new Slice
capture followed. The host's active monitor was finalized at14:01:45UTC after
the user stopped observation; this was visible in the file logs, not an agent
network action. Workspace was approximately154MiB. Its earlier active-monitor
reservation plus Slice budget would have exceeded the limit (~291MiB). After
observation stopped, quota alone no longer explained a locked Slice button;
the previous UI also treated definite rejection as unknown and put the error
far down the page. Actual HTTP rejection itself was not recorded, so attribution
of each browser click remains limited; do not invent a confirmed HTTP trace.

The user authorized fixing the issue after an archive-not-delete proposal. The
older finalized monitor directory was moved intact (same-filesystem rename):

```text
web-data/proxy-test/captures/20261115T095418Z-2ea7f5062d99/
  -> captures/web-archive/20261115T095418Z-2ea7f5062d99/
```

55.35MiB moved; web usage fell to98.59MiB. Conservative Slice73MiB + full monitor
65MiB then totalled236.59MiB, below256MiB. No raw bytes/manifests were edited or
deleted; all eight archived sessions' raw stream lengths/SHA256 matched the
original finalized manifest after moving. Historical references to the original
capture ID still identify the same recording at the archive location. Root
`captures/` is ignored/private; do not stage its contents. Current source/file
slots, latest monitor and running proxy were untouched. Archiving on the same
filesystem frees the **web quota**, not physical disk space.

A separate offline native2.3/private03 Slice of the current user STL with the
previous submitted compensation values succeeded (399504 bytes, no priming
issues), capture `.tmp/urgent-slice-captures/20261115T140630Z-c96ec923062f`.
Original source unchanged, no web-state mutation/client/proxy/hardware calls.
This does not establish host2.5/browser/physical execution. No generated file was
uploaded/started. Subsequent browser acceptance remains user-run.

## Repeat507 and user-confirmed multi-model recovery

The user supplied browser evidence `POST /api/slice 507` after the multi-model
change, confirming actual HTTP rejection rather than only inferred budget math.
Active workspace was~163MiB. Manual intact archival under the earlier approved
archive-not-delete policy moved these complete monitors to `captures/web-archive/`:

- `20261115T140753Z-6b9307e441ef` (52.29MiB)
- `20261114T215830Z-2c698c141f55` (11.98MiB)
- `20261115T083435Z-dca7e3e8a572` (11.04MiB)

Raw stream lengths/hashes were checked against finalized manifests before the
same-filesystem moves; no raw bytes/current recording/plate/proxy were changed.
Web usage fell88.63MiB; full plate Slice89MiB plus monitor65MiB total242.63MiB,
within256MiB. This second manual recovery preceded the automatic policy above.
The user then confirmed Slice works. User-host finalized Slice
`web-data/proxy-test/captures/20261115T180930Z-91f12d5e57e8` independently records
two models/111004 triangles with native host2.5.0 AppRun, no priming issues and
zero printer sessions. This adds scoped host multi-model slicing acceptance,
not physical print/clearance validation; agent only read files.

Hard-reload the page to load the updated rejection feedback; the proxy need not
restart. Archive only known finalized/inactive records with user approval; never
move/delete an active recording or prune history implicitly. Automatic on-demand archival and bounded explicit limit configuration were
subsequently requested/implemented above; neither deletes evidence or makes
storage unbounded.
