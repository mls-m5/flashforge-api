# Questions before implementation and hardware testing

These answers help select the first useful test setup. They do not all block offline proxy development.

## Most useful answers now

1. **Which GitHub project did you mean?** Please provide the URL. `vtolvr/flashforge-finder-api-enhanced` looks relevant and reports upload CRC errors, but we have not confirmed it is your reference.
2. **What exact model and firmware does the printer show?** A photo or the text from its information screen helps avoid mixing Finder generations.
3. **Which FlashPrint version and operating system do you use?** Can you enter a printer IP manually, and does the dialog allow a custom port?
4. **Can you make a supervised capture with the real printer?** Ideally: search, connect, wait for status, disconnect; later a separately approved upload. An existing PCAP would also help.
5. **Is there an upload-only action in your FlashPrint version?** We must distinguish file transfer from transfer-and-print before a hardware upload test.
6. **Where should the tools run?** On the FlashPrint computer, another LAN computer, a Raspberry Pi or a container? Which OS and Python version are available there?

## Product decisions

- Is the first web version strictly upload-only, as proposed? Should any future print-start control remain a separate feature requiring confirmation?
- Which files should the web UI accept: Finder-targeted `.gx`, plain `.gcode`, or both if verified? Can you provide a small working file exported by your FlashPrint setup?
- Will one person use the web UI locally, or should other LAN devices access it? This affects authentication and browser-request protections.
- Is there one printer and one active upload at a time? A single configured target is the proposed first version.
- What maximum file size and local retention of uploaded files/captures are appropriate?

## Simulator expectations

- Which workflows matter first: manual connection, automatic discovery, status, file transfer, file listing or simulated printing?
- Is direct-IP simulator access acceptable initially, with automatic discovery added after we capture it?
- Is a separate simulator host available if FlashPrint and the simulator compete for network ports on one machine?
- Do you need compatibility with one fixed FlashPrint/firmware combination, or several versions?

The target is to make FlashPrint behave as though it is talking to the printer for explicitly tested workflows. We cannot honestly promise complete impersonation before observing its required responses. A reference capture greatly improves the first simulator; without one, development starts with a clearly labeled synthetic profile.

## Proposed defaults if you have no preference

- Python 3.11+, `asyncio`, `pytest`; add web dependencies only in the web milestone.
- TCP 8899 as a configurable default, not a universal protocol fact.
- Loopback binding by default; explicit LAN address when FlashPrint runs elsewhere.
- One printer/operation at a time, bounded local storage, upload-only behavior.
- Byte-preserving proxy first; evidence-based stateful simulator next; web UI last.
- No active network discovery, hardware commands or physical tests without approval.

See [ROADMAP.md](ROADMAP.md) for the first offline-testable deliverable and [EXPERIMENTS.md](EXPERIMENTS.md) for the capture procedure.
