#!/usr/bin/env python3
"""Render already-reviewed fixtures, never raw captures; no network/replay code."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWED = {
    "finder-v1.5-idle.json": "d51d2b8b3060609cdcc28f5c0dd9321c623a33e60d0296a17d207181443ffdce",
    "finder-v1.5-upload.json": "29b546c83193aca85412c03a5e4e03b879d7fcebee9dc22def3a2c79dd77e6e4",
}


def render(fixtures=ROOT / "tests/fixtures"):
    data = {}
    for name, digest in REVIEWED.items():
        raw = (fixtures / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError(f"Fixture changed since privacy review: {name}; review before exporting")
        data[name] = json.loads(raw)
    idle = data["finder-v1.5-idle.json"]
    upload = data["finder-v1.5-upload.json"]
    lines = ["REVIEWED SANITIZED IDLE PREFIX — not a raw capture or replay script",
             "No original name/serial, endpoints, timestamps or model bytes.",
             "Each value is an escaped byte-string representation; CRLF preserved.",
             f"Source: {idle['source_capture']}, {idle['source_session']}; FlashPrint version unknown.", ""]
    for index, pair in enumerate(idle["exchanges"]):
        lines += [f"Exchange {index + 1}", "C>S " + repr(pair["request"].encode("ascii")),
                  "S>C " + repr(pair["reply"].encode("ascii")), ""]
    outputs = {"idle-prefix.log": "\n".join(lines)}
    lines = ["REVIEWED SANITIZED UPLOAD FACTS — INCOMPLETE STREAM, NOT REPLAYABLE",
             "Filename replaced with test_box.gx. ORIGINAL PAYLOAD OMITTED.",
             f"Source: {upload['source_capture']}, {upload['source_session']}; FlashPrint version unknown.",
             "", "Upload/save (does not require print start or cancel):"]
    for prefix in ("begin",):
        lines += ["C>S " + repr(upload[prefix + "_request"].encode()), "S>C " + repr(upload[prefix + "_reply"].encode())]
    lines += [f"[OMITTED: {upload['frame_count']} frames x {upload['frame_size']} bytes; {upload['file_size']} logical model bytes]",
              "[ACK facts only; not a complete stream]", "S>C " + repr(upload["first_ack"].encode()),
              "...", "S>C " + repr(upload["last_ack"].encode()),
              "C>S " + repr(upload["finish_request"].encode()), "S>C " + repr(upload["finish_reply"].encode()),
              "", "SEPARATE EXPLICIT START — may heat/move hardware; NEVER an upload suffix:",
              "C>S " + repr(upload["start_request"].encode()), "S>C " + repr(upload["start_reply"].encode()),
              "", "SEPARATE EXPLICIT CANCEL — NEVER automatically replay:",
              "C>S " + repr(upload["cancel_request"].encode()), "S>C " + repr(upload["cancel_reply"].encode()),
              "", "SYNTHETIC standard CRC32 vector, NOT original model bytes:",
              "Payload ASCII: " + upload["synthetic_crc_vector"]["payload_ascii"],
              "Header hex: " + upload["synthetic_crc_vector"]["header_hex"], ""]
    outputs["upload-facts.log"] = "\n".join(lines)
    manifest = {"format": 1, "not_replayable": True, "source_fixture_sha256": REVIEWED,
                "privacy": "Only previously reviewed anonymized fixtures; no raw captures read",
                "outputs": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in outputs.items()}}
    outputs["manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    return outputs


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--check", action="store_true", help="fail if committed derivatives differ; do not write")
    args = cli.parse_args()
    try:
        outputs = render()
        folder = ROOT / "docs/traces"
        if args.check:
            if any(not (folder / name).exists() or (folder / name).read_bytes() != text.encode()
                   for name, text in outputs.items()):
                raise ValueError("Reviewed derivatives differ; regenerate and review the diff")
        else:
            folder.mkdir(parents=True, exist_ok=True)
            for name, text in outputs.items():
                (folder / name).write_bytes(text.encode())
    except (OSError, ValueError) as exc:
        cli.exit(1, str(exc) + "\n")
    print("Reviewed trace derivatives " + ("match." if args.check else "written; review before committing."))


if __name__ == "__main__":
    main()
