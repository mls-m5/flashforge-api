# Arbetsregler för agenter och bidragsgivare

## Projektets mål

Reverse-engineera FlashForge Finder 2:s nätverksprotokoll med en inspelningsproxy, en realistisk simulator och reproducerbara experiment. Bygg därefter ett lokalt webbgränssnitt för filuppladdning **utan automatisk utskriftsstart**.

Läs `README.md`, `DESIGN.md`, `docs/PROTOCOL.md` och aktuell etapp i `docs/ROADMAP.md` före implementation. Läs även `docs/CAPTURES.md` när loggning eller fixtures ändras.

## Current status

Implemented: the original experimental `upload.py`, a synthetic TCP mock (`python3 -m finderlab mock`), persistent per-run recording (`finderlab/capture.py`), and a byte-preserving recording proxy (`python3 -m finderlab proxy --target-host IP`). Both CLI modes record to ignored `captures/` by default. The flat package runs from the repository root without installation. Read `docs/MOCK.md`, `docs/PROXY.md` and `docs/CAPTURES.md` before changing their behavior.

Run the dependency-free test suite with `python3 -m unittest discover -s tests -v`. Tests use only ephemeral loopback endpoints and project-local `.tmp/` files. FlashPrint/Finder compatibility remains unverified; replay/standalone analysis, discovery, evidence-based profiles and the web UI remain planned. Inspect the actual tree before describing functionality as implemented.

## Säkerhet: fysisk skrivare

- Anslut aldrig till fysisk skrivare, sök efter den på nätverket eller kör hårdvarutester utan uttryckligt godkännande för det aktuella försöket.
- Använd loopback, fake-server eller simulator i automatiserade tester.
- Skicka aldrig rörelse-, värme-, utskriftsstart-, raderings-, firmware- eller återställningskommandon som en del av vanlig felsökning.
- En transparent proxy vidarebefordrar även farliga kommandon. Beskriv inte den som ett skydd.
- Simulatorn får aldrig styra hårdvara eller exekvera uppladdad G-code.
- Bind lokalt som standard. Öppna inte tjänster mot LAN/internet utan användarbeslut.

## Evidens och protokolländringar

- Ange om ett påstående är lokalt observerat, externt rapporterat eller en hypotes.
- Dokumentera modell, firmware, FlashPrint-version och capture-/sessionsreferens när tillgängligt. Skriv `okänt` när det saknas.
- Överför inte beteenden från Adventurer, Dreamer eller Finder 3 till Finder 2 utan test.
- Simulator och egen klient som håller med varandra är inte oberoende protokollevidens.
- Ändra inte CRC, inramning, pauser eller avslutsvillkor på chans. Formulera en hypotes, skapa ett reproducerbart test och registrera utfallet.
- Kopiera inte externa implementationer utan licenskontroll och erforderlig attribution.

## Kod och tester

- The current baseline is Python 3.11+, `asyncio`, and standard-library `unittest` (including `IsolatedAsyncioTestCase`). No third-party dependencies or installation are needed to run the mock/tests. Reassess packaging or additional test tools when needed rather than adding dependencies solely to match an earlier proposal.
- Transport hanterar byte; parser hanterar protokoll; webb hanterar användarflöde. Håll dem separerade.
- En socket-läsning är inte ett meddelande. Testa delade radslut, flera svar per läsning och blandad text/binärdata.
- Logga rådata utan förlust. Avkoda endast för presentation. Proxy får inte normalisera radslut eller injicera kommandon.
- Testa exakt filstorlek, payload som innehåller `ok` och `~M29`, nollbyte, fel, timeout, EOF och avbruten överföring.
- Begränsa minne, disk, radlängd, filstorlek och samtidighet; lita inte på klientens deklarerade längd.
- Använd inga fasta sleeps för att maskera parserfel. Verifierade tidsberoenden ska ligga i profiler och ha evidensreferens.
- Bevara `upload.py` som experiment tills ersättningen är testad; ändra inte dess säkerhetsbeteende tyst.

När en testsvit finns ska dess faktiska kommando dokumenteras i README och köras efter relevanta ändringar. Rapportera vad som körts och vad som inte kunnat verifieras. Hävda aldrig FlashPrint-/hårdvarukompatibilitet utifrån enbart syntetiska tester.

## Temporary files

Use the project-local `.tmp/` directory for all temporary files, test fixtures generated at runtime, scratch scripts and command-output files. It is ignored by Git. Do not use `/tmp` or the system default temporary directory for project work. Pass an explicit project-local directory to `tempfile` APIs; set `TMPDIR="$PWD/.tmp"` when invoking tools that otherwise use system temporary storage. Create the directory first and clean up per-test temporary directories when finished.

## Data och dokumentation

- Write all new documentation, notes, and documentation changes in English. Translate existing Swedish sections when touching them where practical; a full immediate translation is not required. The long-term goal is English-only project documentation. Preserve original protocol bytes and quoted device responses verbatim.
- Råa captures, uppladdade modeller och lokala profiler kan innehålla IP, MAC, serienummer och privat modellinnehåll. Lägg dem inte i Git utan uttrycklig granskning.
- När Git-konfiguration tillkommer: ignorera `captures/`, lokal lagring, hemligheter och virtuella miljöer. Committa bara små, granskade fixtures.
- Redigera inte råinspelningar. Skapa en separat avidentifierad derivatfil och dokumentera ändringarna.
- Uppdatera protokollanteckningar och acceptanskriterier när ny evidens ändrar designen.
- Skilj alltid mellan befintliga kommandon och föreslagna CLI/API-exempel.

## Completing a change and committing

After a major change or completed milestone, review the diff, run the relevant available checks, and commit the project with a clear English commit message. Do not leave a completed major change uncommitted unless the user asks otherwise or a blocker prevents the commit; report any blocker. Small intermediate edits may be grouped into a coherent milestone commit.

Stage only reviewed files belonging to the change. Do not include private captures, uploaded models, secrets, generated artifacts, or unrelated user changes. Never discard unrelated work, rewrite existing history, or push without explicit authorization. If Git identity is missing, ask the user rather than inventing an identity.

Summarize the files changed, checks run, known limitations, next steps, and resulting commit. Ask rather than guess when a decision affects hardware safety or protocol interpretation.
