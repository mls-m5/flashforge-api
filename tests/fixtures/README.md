# Reviewed protocol fixtures

## `finder-v1.5-idle.json`

Derived offline from the user's proxy recording `20261112T190818Z-31ded6e5f0a5`, session `s0001`, captured on 2026-11-12. The user requested that the dummy reproduce this printer's replies. The user identifies the hardware as Finder 2; its `M115` reports `Flashforge Finder`, firmware `V1.5 20170419`. FlashPrint version and selected machine profile are unknown.

This fixture contains the first **14 complete request/reply exchanges**, covering control acquisition, two identity queries, offsets, position and repeated idle polling. It contains no model payload, network addresses, MAC or printer serial number.

Redactions, reviewed before adding to Git:

- `Machine Name` replaced by `Mock Find` (9 bytes).
- `SN` replaced by synthetic, hexadecimal-shaped `F1AB0001` (8 bytes).
- No other bytes in these reply frames were changed; request bytes are unchanged.

Source stream intervals are half-open: client `[0, 98)`, server `[0, 1076)`. Replacement lengths are unchanged. The concatenated sanitized reply prefix has SHA-256:

```text
af9cf45f7e64c7b1cba2ac7f53278b248cbc651e17d6ffec18ebce08768ee024
```

The fixture was compared offline against these actual raw stream ranges with only the documented redactions applied. Tests load this checked-in fixture, not the private capture and not response constants from the implementation.

The source was still running when the prefix was first extracted; its subsequently finalized manifest has `complete: true`. This fixture covers only the specified **prefix**, not every later exchange. The original capture is preserved unchanged under ignored `captures/`.

Not evidenced by this idle fixture: `M602` release, control conflicts, error responses, file listing, upload framing/CRC, printing, discovery, dynamic temperatures or timing requirements. Observed response latency is not reproduced; tests compare application bytes, not packet segmentation or scheduling.

## `finder-v1.5-upload.json`

Reviewed facts and command/reply frames from user capture `20261112T191450Z-2b04f784b894`, session `s0001`, 2026-11-12 19:15 UTC, firmware `V1.5 20170419`. Client version remains unknown. The inspected upload/start/cancel exchanges were complete while the overall recording was still running.

The client wire interval `[745,107657)` contains 26 frames. Offline checks verified every header/index/CRC, logical length, zero padding and matching `N0` through `N25` ACK. Logical file size: 102989; final block length: 589. No original model payload, addresses or device identity are included. Filename is replaced with `test_box.gx` (11 bytes, unchanged length).

Tests generate byte-ramp or repeated-byte payloads at runtime. They do not claim those generated CRCs/data were captured. A separate standard CRC32 vector (`123456789` → `cbf43926`) checks the algorithm/header layout independently. The command/reply samples preserve captured wording and spacing with the filename substitution.

The recorded `M26` is only an explicit cancel example, never an automatic scenario suffix. Tests separately exercise upload-only and an active job that survives polling/release/reconnect without cancellation. Error handling and simplified virtual job dynamics are labeled mock policies, not captured firmware guarantees.

## Scope and future organization

These are deliberately small reviewed regression artifacts, not a raw-log archive or general replay framework. The future systematic scenario catalog/trace selection/replay plan is in `docs/ROADMAP.md`. Runtime data belongs in ignored `.tmp/`; private raw captures stay in ignored `captures/`.
