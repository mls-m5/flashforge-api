# Web storage admission and explicit rejection feedback

The web limit is **256MiB persistent workspace storage**, not Python/browser RAM
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

Hard-reload the page to load the updated rejection feedback; the proxy need not
restart. Archive only known finalized/inactive records with user approval; never
move/delete an active recording or prune history implicitly. If disk space or
quota fills again, deliberate retention/limit configuration is future work, not
an excuse to remove evidence or make storage unbounded.
