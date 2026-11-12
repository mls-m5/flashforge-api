# Protocol evidence and open questions

This is a working journal, **not a complete Finder 2 specification**. A user-collected real-printer proxy capture now establishes a connection/idle baseline; see FINDER-IDLE-003 below. Behaviors outside the observed exchanges remain unverified.

## Implemented profiles

The default `finder-v1.5` combines captured connection/idle replies with observed block upload and job-command reply formats. Name/serial are anonymized. `finder-v1.5-idle` retains the earlier connection-only profile with experimental raw upload; `synthetic-v1` retains the original mock. See [MOCK.md](MOCK.md) for scope. Errors, release/control policy, listing and virtual job dynamics are still mock conventions. The original `upload.py` is incompatible with the framed upload now observed on this printer.

## FINDER-IDLE-003 — Real-printer connection and status baseline

Source: `captures/20261112T190818Z-31ded6e5f0a5`, session `s0001`, starting 2026-11-12 19:08 UTC. User-reported model: Finder 2. Observed identity: `Flashforge Finder`, firmware `V1.5 20170419`. FlashPrint version and selected machine profile are unknown. The manifest has subsequently been finalized successfully.

Observed sequence: `M601 S1 → M115 → M650 → M115 → M114 → M27 → M119 → M105`, then sustained status polling. The client's repeated `M115` is therefore also present in a successful real-printer session and is not itself a failure indicator.

Important differences from `synthetic-v1`:

- `M601`: `Control Success.` (no `V2.1` suffix).
- `M115`: machine type has no `2`; real firmware text; two spaces between axis dimensions; no MAC field.
- `M650`: `X: 34 Y: 0`.
- `M114`: integer coordinate formatting.
- `M119`: `Z-max`, different endstop/status values and field order; no LED/current-file lines.
- `M105`: `T0:21 /0 B:0 /0` in the selected idle baseline.

The reviewed fixture `tests/fixtures/finder-v1.5-idle.json` contains the first 14 complete exchanges: client bytes `[0,98)`, server bytes `[0,1076)`. Only name and serial were replaced, preserving lengths. It was compared offline to the actual raw ranges with those two substitutions. Raw captures/private identifiers are not committed. See `tests/fixtures/README.md` for provenance and sanitized hash.

This is evidence for the observed responses, not for arbitrary error handling, control conflicts, release, upload, discovery or timing requirements. Snapshot temperatures/endstops are not a dynamic physical model.

## FINDER-MOCK-004 — FlashPrint accepts the updated idle profile

User-reported successful connection, supported by `captures/20261112T191332Z-4bda35d1b451`, session `s0001`, 2026-11-12 19:13 UTC. The finalized capture uses `finder-v1.5-idle` with the anonymized name/serial.

The client sent 57 commands: one control claim, two identity queries, one offset query, one position query, and 52 status queries (`M27`: 17, `M119`: 18, `M105`: 17). Every command has a corresponding successful reply; no error events or error replies were recorded. Polling lasted about 17 seconds until recording shutdown (`capture_shutdown`), rather than the previous immediate release/disconnect. Raw stream sizes and hashes match the manifest.

This validates manual connection and idle polling in the user's setup (FlashPrint version still unknown), not uploads or printing. No single field has been isolated as the cause of the earlier failure.

## FINDER-UPLOAD-005 — Framed upload, explicit start and cancel

Source: `captures/20261112T191450Z-2b04f784b894`, session `s0001`, 2026-11-12 19:15 UTC. Same observed machine type and firmware as FINDER-IDLE-003. The user reports saving a file, starting the job and aborting it. FlashPrint version remains unknown. The following complete transfer interval was inspected offline; the full recording was still unfinalized at inspection.

The client sent `M28 102989 0:/user/<name>.gx`, then **26 frames of 4112 bytes**, then `M29`, then **separate** `M23` start and later **separate** `M26` cancel. No `M24` was sent in this workflow. Filename in checked-in examples is anonymized to `test_box.gx`.

Wire data interval: client bytes `[745,107657)`, totaling 106912 bytes. Each frame:

| Offset | Length | Meaning |
| --- | --- | --- |
| 0 | 4 | Magic bytes `5a 5a a5 a5` |
| 4 | 4 | Zero-based block index, unsigned big-endian |
| 8 | 4 | Logical file-byte count in this block, unsigned big-endian |
| 12 | 4 | CRC32 of **logical payload bytes only**, unsigned big-endian |
| 16 | 4096 | Payload plus zero padding to fixed wire size |

All 26 headers, indexes, CRCs and padding were checked against the actual raw bytes. Logical lengths were 4096 for blocks 0–24 and 589 for block 25; last-block padding was 3507 zero bytes. CRC matches Python `zlib.crc32` over unpadded data, not the header or padding. Reconstructed logical byte count equals the advertised 102989. All block acknowledgements were `N<index> ok\r\n`, indexes 0–25.

Captured reply bodies (standard `CMD ... Received.` / `ok` envelope):

- `M28`: `Writing to file: 0:/user/test_box.gx  Length: 102989` (two spaces before `Length`).
- `M29`: `Done saving file.`
- `M23`: `File opened: 0:/user/test_box.gx Size: 102989`, then `File selected`.
- `M26`: no additional body.

After `M23`, status became `BUILDING_FROM_SD`, first `HOMING`, later `WAIT_ON_TOOL`; the temperature target was 220. After `M26`, intermediate `PAUSED`/building status appeared before `READY` and a zero target. These transitions are observations, not proof of safe emergency-stop behavior. Actual execution progress used a denominator of 88477 rather than the GX file size 102989; interpreting GX headers/execution offsets remains open.

Implementation: `finder-v1.5` validates the captured framing and returns ACKs, saves only on `M29`, starts a **virtual** job only on `M23`, and cancels only on `M26`. There is no automatic print-start, abort, timed completion, motion or heating. Virtual active status uses representative captured shapes; progress stays zero over logical file size. Thermal/homing/cancel transients are not replayed. Release/disconnect does not cancel a virtual job.

Limits of evidence: one successful file-transfer capture, not all sizes/firmware variants. Bad-CRC handling/retries were not observed; the mock deliberately errors and closes rather than inventing retransmission behavior. It requires the observed full-block/final-block lengths and zero padding. The existing raw uploader does **not** implement this framing or ACK format and remains unchanged.

`tests/fixtures/finder-v1.5-upload.json` stores reviewed framing facts and command/reply frames, not model content. Tests generate deterministic payloads, include an independent CRC32 test vector and separately test upload-only, start-without-cancel, and explicit cancel. A broader sanitized trace corpus and reusable replay tooling are planned, not implemented by these tests.

## FP-M650-001 — User-reported FlashPrint connection attempt

- **Evidence:** user-provided mock log, dated `2026-11-12 14:29:22` (timezone unknown). No raw capture, FlashPrint version, OS or real-printer firmware was supplied.
- **Observed incoming sequence:** `~M601 S1` → `~M115` → `~M650` → about one second later `~M602`, followed by disconnect. The old mock logged `M650` as unsupported and its implementation sends an error for that command.
- **Interpretation:** the rejection is a plausible reason FlashPrint abandoned the connection, but the log alone does not prove it is the only issue or that the identity response was fully accepted.
- **External evidence:** [S6] describes `M650` as reading machine extruder distance and shows `X: 25 Y: 15` followed by `ok`. [S3] describes XY offsets on 5M-series machines. Neither establishes Finder 2's exact response.
- **Synthetic hypothesis:** return `CMD M650 Received.\r\nX: 0 Y: 0\r\nok\r\n`, using the mock's existing reply envelope. Zero values, the envelope and allowing reads without control are mock conventions, not observed Finder behavior. No offset setter or movement is implemented.
- **Regression:** `test_reported_connection_sequence_with_m650` checks the reported command order against the mock; `test_m650_is_read_only_and_rejects_arguments` checks repeatable replies and unchanged control ownership/storage.
- **Next validation:** restart the updated mock and retry FlashPrint. Record the next commands/UI outcome and FlashPrint version. A real-printer reply capture is still needed to validate formatting and values.

## FP-IDENTITY-002 — Second identity query followed by disconnect

- **Evidence:** subsequent user-provided mock log dated `2026-11-12 14:34:08` (timezone unknown). Client version, OS, selected machine profile and UI error remain unknown.
- **Observed sequence:** `~M601 S1` → `~M115` → `~M650` → `~M115` → `~M602` → disconnect, all within milliseconds. No unsupported-command warning appears.
- **Conclusion:** adding `M650` changed the client's observed progression, but did not produce a sustained connection. The log alone cannot establish why FlashPrint released control or whether any particular reply was accepted.
- **Hypotheses:** model/identity recognition, firmware string parsing, required identity fields or offset reply formatting. Do not silently change identity fields based on this log alone.
- **Next experiment:** record both this mock attempt and a successful real-printer connection with the same client/profile through the new [recording proxy](PROXY.md), then compare exact request/reply bytes. Persistent [captures](CAPTURES.md) now make replies and historical sessions available without copying terminal logs. Hardware experiments remain manual and explicitly approved.
- **Local validation:** `test_reported_second_m115_sequence_has_full_reply_history` checks recording of two sessions using the reported command order; it is not a FlashPrint acceptance test.

## Evidensnivåer

- **Kodobservation:** vad projektets befintliga program gör; bevisar inte skrivarens beteende.
- **Extern uppgift:** vad en länkad källa uppger för angiven modell/familj.
- **Hypotes:** något vi avser att testa.
- **Locally observed/reference-backed:** a recorded attempt with environment and capture references. FINDER-IDLE-003 and FINDER-MOCK-004 now provide bounded evidence; missing environment details remain explicit.

## Initial hypothesis inventory (predates the captured baseline)

The following inventory records the starting assumptions. See the observations above for newer evidence; do not treat these initial unknowns as a summary of current implementation.

| Ämne | Vad vi har | Status och nästa kontroll |
| --- | --- | --- |
| Transport | `upload.py` och Finder-repo [S1] använder TCP 8899. | Rimlig standard; verifiera på användarens Finder 2. Gör porten konfigurerbar i nya verktyg. |
| Kommandon | Skriptet skickar ASCII med `~` och `\r\n`. [S1, S3] beskriver samma form. | Mät exakta byte, inklusive radslut och eventuella varianter. |
| Kontrollsession | Skriptet använder `~M601 S1` och `~M602`. [S1] beskriver kontrollbegäran. | Mät krav, svar, ägarskap och beteende efter avbrott. |
| Svarsavslut | Skriptet kräver en separat rad `ok`. [S3] visar också andra former av bekräftelse. | En generell `ok`-detektor är inte verifierad. Ta reda på avslut per kommando. |
| Upload | Skriptet skickar `~M28 <storlek> 0:/user/<namn>`, råa byte, paus, `~M29`. | Oprövad Finder 2-hypotes. Råström beskrivs för A3/A4 Pro [S3], inte därmed Finder 2. |
| CRC/block | [S1] rapporterar CRC-problem vid upload. | Ledtråd, inte bevis för viss CRC-algoritm eller paketlayout. Jämför fungerande FlashPrint-flöde. |
| Tidsberoende | Skriptet har tre sekunders paus före M29. | Ingen lokal evidens för att pausen behövs eller räcker. |
| Filformat | Skriptet visar `.gx` som exempel men granskar inte innehållet. | Bekräfta format från FlashPrint och vad Finder 2 accepterar. |
| UDP discovery | Externa källor beskriver flera olika varianter. | Ingen variant verifierad för denna Finder 2; se nedan. |

## Portar: TCP är inte UDP

`8899/TCP` är den starkaste utgångspunkten för kommandokanalen. Även om firmware använder en fast port bör våra verktyg tillåta annan lyssningsport, målport och lokal bindningsadress för tester och portkonflikter. FlashPrint kan däremot kräva en bestämd port eller följa en port annonserad i discovery; det måste mätas.

Discovery-källorna ska hållas isär:

- I Cura-ärendet [S5] finns en **Adventurer 3**-observation med multicast `225.0.0.9:19000/UDP`, lokal port `18001` och en probe vars payload rapporteras innehålla avsändar-IP och svarsport. Ärendets titel gäller Finder men detta enskilda exempel gäller inte Finder 2.
- Wikins legacy-beskrivning [S4] gäller **Adventurer 3/4 Pro** och anger multicast `225.0.0.9:8899/UDP`, med ett 140-byte-svar.
- Samma wiki anger `19000/UDP` och broadcast `48899/UDP` för nyare modeller. Det är inte evidens för att Finder 2 använder dessa.

Skillnaderna kan bero på firmware, klientversion eller olika discovery-vägar. Vi ska fånga FlashPrints sökning och riktiga skrivarens svar innan vi väljer paketmall. Börja med bred UDP-fångst så att en felaktig portgissning inte döljer trafiken. Simulator/proxy måste annonsera sin nåbara adress/port, inte råka skicka tillbaka den riktiga skrivarens identitet och dirigera FlashPrint förbi inspelningen.

## Befintligt skript: kända begränsningar

`upload.py` är användbart som läsbar hypotes men ännu inte en robust protokollklient:

- Port 8899 är hårdkodad; ingen capture, simulator eller upptäckt av skrivare.
- Varje `read_reply` har en egen buffert och lämnar inte tillbaka eventuella efterföljande meddelanden till nästa läsning.
- Sökning efter en `ok`-rad sker på delvis mottagen text. Den kan både missa andra giltiga svar och tolka en ofullständig rad som klar.
- Ett svar som innehåller både fel och `ok` hanteras inte med verifierad felprioritet.
- Timeout kan ge partiellt svar; `command()` kontrollerar sedan bara förekomsten av `ok`.
- Blockstorlek 4096 är en lokal `read`/`sendall`-detalj, inte bevis på skrivarens protokollblock.
- Fast paus före M29 och upload med råa byte saknar lokal verifiering.
- Skriptet skickar inget explicit utskriftsstartkommando, men upload-only-beteendet måste ändå verifieras på aktuell firmware.

## Frågor som fångster ska besvara

1. Öppnar FlashPrint en eller flera TCP-anslutningar? Krävs kontroll innan identifiering/status?
2. Vilka kommandon krävs för att klienten ska godkänna Finder 2:s identitet och visa redo?
3. Exakta svar, radslut, bekräftelser och ordning? Kommer data efter en initial `ok`?
4. Är upload råa filbyte eller block med header, sekvensnummer, längd och checksumma?
5. Avser deklarerad längd hela `.gx`-filen, payload eller något annat? Vad händer med sista blocket?
6. Finns ACK per block, återförsök eller separat dataanslutning?
7. Hur avslutas och verifieras överföringen? Vad betyder kvittot egentligen: mottaget, sparat eller bara syntaktiskt accepterat?
8. Vilka filnamn, sökvägar, ändelser och storleksgränser fungerar?
9. Skickar FlashPrint alltid utskriftsstart efter upload, eller finns ett separat upload-only-flöde?
10. Vad händer vid avbrott och nästa anslutning? Finns temporära filer eller kvarhållen kontroll?

## Mall för en ny observation

```text
ID:
Påstående / hypotes:
Evidensnivå:
Modell och firmware:
FlashPrint-version och operativsystem:
Capture-ID, session, riktning och byteoffset:
Försök / enda ändrade variabel:
Förväntat resultat:
Observerat resultat:
Alternativa förklaringar:
Hur försöket upprepas:
Säkerhetsbedömning och godkännande vid hårdvara:
```

## Källor och läsanvisning

Källorna granskades när grunddokumenten skrevs. De är sekundärmaterial tills uppgifterna reproducerats på användarens enhet. För framtida kodanvändning: kontrollera licens och spara commit/version; länkar till föränderliga README/wiki-sidor är inte frysta referenser.

- **[S1]** [vtolvr/flashforge-finder-api-enhanced](https://github.com/vtolvr/flashforge-finder-api-enhanced). README anger TCP 8899, kontrollsekvens och kända CRC-fel vid upload. Inte verifierat att detta är projektet användaren avser eller exakt samma Finder-variant.
- **[S2]** [01F0/flashforge-finder-api](https://github.com/01F0/flashforge-finder-api). Ursprung som [S1] hänvisar till; en kandidat för fortsatt kodgranskning, inte separat granskad här.
- **[S3]** [Parallel-7 TCP Protocol](https://github.com/Parallel-7/flashforge-api-docs/wiki/TCP-Protocol), läst via [spegel](https://github-wiki-see.page/m/Parallel-7/flashforge-api-docs/wiki/TCP-Protocol). Blandar skrivarfamiljer; upload-avsnittet gäller A3/A4 Pro.
- **[S4]** [Parallel-7 Discovery Protocol](https://github.com/Parallel-7/flashforge-api-docs/wiki/Discovery-Protocol), läst via [spegel](https://github-wiki-see.page/m/Parallel-7/flashforge-api-docs/wiki/Discovery-Protocol). Använd som hypoteskälla, inte Finder 2-specifikation.
- **[S5]** [Ultimaker/Cura #7829: FlashForge Finder support](https://github.com/Ultimaker/Cura/issues/7829). Lång diskussion med flera modeller; discovery-exemplet ovan uppger Adventurer 3.
- **[S6]** [Mrnt/OctoPrint-FlashForge G-Code Reference](https://github.com/Mrnt/OctoPrint-FlashForge/wiki/G-Code-Reference), read via [mirror](https://github-wiki-see.page/m/Mrnt/OctoPrint-FlashForge/wiki/G-Code-Reference). Its `M650` section reports machine extruder distance and an XY-shaped reply; it does not verify this project's Finder 2 response. Treat as a response-shape hypothesis, not a firmware specification.
