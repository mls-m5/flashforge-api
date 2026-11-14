# Reviewed shareable trace derivatives

These escaped transcripts are generated only from the already reviewed
`tests/fixtures/finder-v1.5-idle.json` and `finder-v1.5-upload.json`. Their exact
reviewed hashes are pinned by `tools/export_reviewed_traces.py`; changed inputs
require another explicit privacy review before export.

```sh
python3 tools/export_reviewed_traces.py --check
# To regenerate the deterministic derivatives, then review the diff:
python3 tools/export_reviewed_traces.py
```

`idle-prefix.log` preserves 14 sanitized exchanges with original CRLF bytes
represented as escaped Python byte strings. Machine name and serial are
synthetic replacements. `upload-facts.log` retains only reviewed framing facts
and sanitized command/reply examples: original model payload is omitted and
its CRC vector is explicitly synthetic. Separate M23/start and M26/cancel
examples are dangerous optional actions, NEVER automatic upload suffixes.

No original network endpoints, MAC, private filename or geometry are included.
See `tests/fixtures/README.md` for capture/session ranges and transformations;
`manifest.json` retains fixture/output hashes. Source captures remain unchanged,
private and Git-ignored. These derivatives are **not complete raw streams or a
replay script**, preserve no original timings, and do not validate other firmware,
error/retry handling or physical job dynamics. Do not run them against hardware.
