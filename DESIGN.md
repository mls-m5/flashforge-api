# Design

## 1. Goals and scope

Build a local protocol lab for **FlashForge Finder 2**, then a small web application for uploading print files. The default workflow should show progress and an honest save confirmation without starting a print.

The simulator should replace hardware for as much of FlashPrint's normal workflow as supported by evidence. Compatibility is scoped to a Finder model/firmware/FlashPrint combination, not every FlashForge device. Full physical/firmware simulation is out of scope.

We do not build a slicing engine, cloud service or generic motion/heating control. An optional local Orca subprocess adapter now supports STL slicing before upload, with explicit trusted profiles; a separate draft 02 now produces native geometry but physical profile validation remains outstanding. The standalone loopback web workbench is implemented as described in section 6; live browser/container acceptance remains pending. `.gcode`, `.g` and `.gx` are transfer candidates, not proven equivalent firmware formats. Renaming G-code cannot make it Finder-compatible or create a GX container.

## 2. Utgångsläge och principer

Current implementation: the unchanged incompatible experimental `upload.py`, an offline mock in `finderlab/simulator/`, per-run recording in `finderlab/capture.py`, a byte-preserving TCP proxy in `finderlab/proxy.py`, and the new framed-upload client in `finderlab/client.py` with CLI in `cli_client.py`. See [docs/MOCK.md](docs/MOCK.md), [docs/PROXY.md](docs/PROXY.md) and [docs/CAPTURES.md](docs/CAPTURES.md). Default `finder-v1.5` combines captured connection/idle replies with framed upload and explicit virtual job commands. The earlier idle baseline has a user-recorded FlashPrint success. Upload framing (big-endian 16-byte header, CRC32, fixed padded blocks and ACKs) was checked against all 922 frames from two differently sized real transfers, and a subsequent user mock capture now includes successful FlashPrint file transfer and explicit virtual start/cancel. The new uploader also passed an actual CLI-to-dummy transfer of the user's GX with identical bytes and no start/stop. A subsequent user-run host/proxy upload-only trial confirmed all 896 block ACKs, final save and release against the real printer; client/proxy streams matched and no start/stop was sent. Other hardware actions/variants still need separate explicit approval/evidence. The larger capture also establishes unquoted internal spaces in filenames: the framed profile preserves the complete path remainder in M28/M23 rather than splitting it into tokens. Earlier `finder-v1.5-idle` and `synthetic-v1` remain selectable. The original uploader is not compatible with the observed framing. Virtual jobs are not physical/thermal simulation and never cancel automatically; M29 saves, M23 starts, M26 cancels. Other behavior remains bounded mock policy, not a verified full specification. Automated proxy/recording tests use only localhost fake servers. Discovery and replay/standalone analysis remain planned. The standalone web workbench now exists; its explicitly user-authorized native draft 02 slicing path produces geometry, but physical Finder profile compatibility remains unverified.

- Råa byte är primär evidens; textavkodning är en härledd vy.
- Skilj lokal observation, extern uppgift och oprövad hypotes åt.
- Använd samma strömparser och protokollmodeller i analys, simulator och klient när beteendet är verifierat.
- Håll transportproxy oberoende av parsern. En parserbugg får inte korrumpera en mätning.
- Bygg först reproducerbara tester utan hårdvara.
- Ett godkänt simulatortest bevisar inte hårdvarukompatibilitet om klient och simulator delar samma oprövade antagande.

## 3. Arkitektur

```text
FlashPrint ── TCP ── inspelningsproxy ── TCP ── Finder 2
                           │
                           └── captures → analys → fixtures / profil

FlashPrint ── TCP (+ senare UDP discovery) ── simulator
                                              │
                                              └── virtuell lagring / tillstånd / captures

Webbläsare ── HTTP ── lokal backend ── protokollklient ── Finder 2
                                                └───── simulator i tester
```

TCP-kommunikation och UDP-discovery är olika delsystem. Att TCP-porten fungerar betyder inte att FlashPrint hittar enheten automatiskt.

### Föreslagen teknik och struktur

The implemented baseline uses Python 3.11+, `asyncio` for networking and standard-library `unittest` for tests. The mock runs without installation or third-party dependencies; `pytest` was an initial suggestion, not a requirement. Proxy and simulator must remain usable without web dependencies. FastAPI/Uvicorn with static HTML/JavaScript remains a possible later web stack, not a current dependency.

Current tools use a flat `finderlab/` package (`__main__.py`, `client.py`, `cli_client.py`, `simulator/`, `protocol/upload.py`, `capture.py`, `proxy.py`) and `tests/` so they can run without installation. Runtime test files use ignored project-local `.tmp/`; recordings use ignored `captures/`. The following remains a proposed longer-term structure rather than a current tree:

```text
src/finderlab/
  cli.py
  transport/       # proxy, anslutningar, tidsgränser
  capture/         # rådata, händelser, validering
  protocol/        # inkrementell parser och verifierade kommandon
  simulator/      # tillstånd, profiler, virtuell fillagring, discovery
  client/         # sessionsägarskap och uppladdning
  analysis/       # inspektion, jämförelse, återspelning
  web/            # HTTP-API och statiska resurser
profiles/         # versionsbundna simulatorprofiler med evidensreferenser
tests/fixtures/  # små granskade, avidentifierade referenser
captures/        # lokala mätdata; ska ignoreras av Git
```

## 4. Bytebevarande inspelningsproxy

Konfigurera lyssningsadress/-port och explicit mål-IP/-port. TCP `8899` är föreslagen standard, inte hårdkodat krav. Standardbindning är loopback; åtkomst från annan dator kräver explicit LAN-bindning.

Varje inkommande anslutning ger en separat målanslutning. Vidarebefordra data kontinuerligt i båda riktningar med backpressure och begränsade buffertar. Proxy ska inte lägga till radslut, normalisera teckenkodning, vänta på `ok`, införa pauser eller injicera kommandon. Den bevarar byteströmmar, inte TCP-paketindelning eller exakt timing.

Logga anslutning, riktning, tidsstämpel, byteoffset, fel, EOF och avslut enligt [CAPTURES.md](docs/CAPTURES.md). Hantera half-close: EOF i ena riktningen behöver inte betyda att den andra är klar. Tidsgränser ska vara konfigurerbara; långsam men aktiv filöverföring får inte likställas med inaktivitet.

Om loggning misslyckas ska fångsten markeras ofullständig och sessionen avbrytas med tydligt fel; verktyget får inte påstå att inspelningen är komplett. Ett sådant avbrott kan lämna en partiell fil på skrivaren och kräver dokumenterad återställning.

Transparent läge ändrar inte farliga kommandon. Eventuellt framtida filtrerande läge måste vara ett separat, tydligt märkt läge och får inte beskrivas som transparent. Enkel textsökning efter farliga G-koder är inte ett säkert filter eftersom samma bytes kan finnas i filpayload.

MVP-proxyn hanterar bara TCP. Automatisk discovery får inte utlovas: prova manuell IP-anslutning i FlashPrint. Om det inte går blir discovery ett tidigt separat delmål. Avvisa uppenbar anslutning till den egna lyssnaren för att undvika proxyloopar.

## 5. Realistisk Finder-simulator

### Realismnivåer

1. **Syntetisk startprofil:** explicit omärkt/overifierad som hårdvarufacit; kan testa transport och parser, men kan inte utlovas accepteras av FlashPrint.
2. **Inspelningsbaserad profil:** exakta svar och identitetsfält från en verklig Finder 2 för ett avgränsat referensflöde.
3. **Tillståndsbaserad profil:** stöder variationer i filnamn, filstorlek, polling, återanslutning och fel, inte bara en enda inspelad följd.
4. **Utökad kompatibilitet:** verifierad discovery, fler FlashPrint-versioner, virtuella utskriftsförlopp och särskilda firmwarebeteenden.

Profiler ska ange modell, firmware, FlashPrint-version, källinspelningar, kända avvikelser och verifierade flöden. Uppge inte en annan skrivarmodells egenskaper som Finder 2:s. Använd syntetiskt serienummer/MAC i delade profiler och håll dem konsekventa mellan discovery och TCP-svar.

### Tillstånd och beteende

Separera minst:

- anslutning och eventuell kontrollägare;
- protokollfas: kommandoläge, mottagning av fil och slutförande;
- virtuell enhet: redo, upptagen, fel samt senare simulerad utskrift/paus;
- filer: temporära och bekräftade, namn, exakt byteinnehåll och lagringskvot.

De exakta övergångarna bestäms av mätningar. `M601`, `M602`, identifiering/status och upload är första kandidaterna. En uppkoppling får inte alltid svaras med `ok`: kontrollkonflikt, ogiltig storlek, lagringsbrist, okända kommandon och bruten överföring måste kunna ge relevanta fel. Okänt kommando ska loggas tydligt och ge ett explicit profilbeteende (fel eller timeout), aldrig automatiskt godkännas för att dölja en lucka.

Parsern är inkrementell: en `recv()` kan innehålla en halv rad, flera kommandon eller övergången mellan filbyte och nästa kommando. Om längdstyrd rå överföring bekräftas ska parsern konsumera exakt annonserat antal byte och bevara överskottet till nästa fas. Om fångster visar binära block med header/CRC behövs motsvarande tillstånd i stället. Sök inte efter `~M29` inne i filinnehåll som slutmarkör utan evidens för sådan inramning.

Virtuell lagring får inte mappa skrivarens sökväg direkt till värddatorns filsystem. Begränsa storlek, antal filer, radlängd och sessioner. Avbrutna filer ska hanteras enligt uppmätt beteende och aldrig bli bekräftade av misstag. Simulatorn får inte innehålla någon anslutning till fysisk skrivare eller exekvera G-code.

Identifiering och status ska vara sammanhängande. Efter accepterad överföring ska filnamn, filstorlek och listning (om stödd) återspegla den virtuella filen. Framtida simulerad utskrift ändrar enbart virtuellt tillstånd; detta är inte en fysikmodell.

### Discovery och återspelning

Fånga först både fråga och svar på riktigt LAN. Bind multicast till explicit valt gränssnitt och kontrollera vilka IP-/portfält svaret behöver annonsera. På samma dator kan FlashPrint och simulator konkurrera om UDP-portar; en separat LAN-dator kan förenkla testet. Discovery hålls avstängd tills en profil stöder det för att undvika vilseledande annonsering.

Ren återspelning används som strikt regressionstest för en känd följd. Den ersätter inte den tillståndsbaserade simulatorn. Matcha meddelanden i en rekonstruerad ström, inte storleken på inspelade socket-läsningar. Timing kan återges relativt eller accelereras, men OS kan inte garantera identisk paketindelning.

## 6. Upload client and future web interface

Implemented client contract: `.gx`/`.gcode`/`.g` byte-preserving transfer (no container conversion or safety inference); upload-only by default; explicit endpoint/firmware guard; bounded incremental CRLF reply parsing with preserved surplus bytes; exact indexed ACK validation; no automatic retries; distinct final-save confirmation and UNKNOWN outcomes. Save/start/stop remain separate library actions. Upload CLI `--start` explicitly composes confirmed save and a fresh READY check with start of the exact returned destination; an unsuccessful/uncertain save never triggers it. No stop is automatically appended. File/name preflight failures are logged before any connection; capture metadata distinguishes start intent, saved-file confirmation and acknowledged start. On a failed binary transfer, close without injecting release/stop into payload. Release is attempted only at a healthy command boundary. Source files are streamed unchanged (including existing previews), checked for mutation, and hashed; a source hash is not remote read-back validation. Non-loopback CLI targets require opt-in, but loopback may itself proxy hardware. See [docs/CLIENT.md](docs/CLIENT.md).

### Optional slicing stage

`finderlab/slicer.py` exposes a separate async STL → plain G-code adapter. `slice` invokes it offline; upload's `--slice` invokes it before opening a printer session. Trusted self-contained JSON profiles, isolated datadir/workspace, capability probing, bounded output/logs/time/address space, process-group cleanup and a per-workspace single-job lock prevent accidental fallback to arbitrary shell options or unbounded concurrent jobs. These are resource/orchestration boundaries, not a native-code security sandbox or motion-safety check. Logs/hash provenance share the capture lifecycle; generated output is separately size-bounded. No fallback guessed Finder profile, G-code rewriting, GX wrapping, thumbnail generation or automatic start is introduced. See [docs/SLICING.md](docs/SLICING.md). Native Orca 2.3.0 now generates geometry for the separately authorized offline draft 02. It is not a validated motion profile; the original Sailfish draft still fails. See [docs/ORCA_FINDER_DRAFT_02.md](docs/ORCA_FINDER_DRAFT_02.md) for actual trials, E/reset ownership and the layer-change Z split. Tests use a fake CLI and dummy printers; no reviewed Finder profile is available.

### Standalone web workbench

`finderlab/web.py` and `finderlab/webstatic/` implement a dependency-free loopback page. One bounded raw file receive stores an STL/print file; a separate confirmed Slice uses server-owned Orca/profiles; a third confirmed Save uses the existing client without start/stop. Generated G-code is downloadable for review and cannot be sent unless the operator explicitly enables generated-output saving. Separately opt-in job controls (`--enable-job-controls`) expose confirmed Start of the exact saved filename (per-save identity, one attempt, fresh READY check) and confirmed Cancel (not emergency stop). They share the operation lock, never run automatically and preserve save confirmation separately from uncertain job results. No HTTP request can select targets, profiles, host paths or arbitrary native flags. GET cached status never connects to a printer. Low-level startup stays disconnected unless configured with `--auto-monitor`; the proxy/owned-dummy launcher now selects that status-only startup mode by user request. Offline slicing and the passive watcher stay disconnected. Host/Origin/token checks, bounded HTTP parsing/timeouts, single-slot/process locks, capture quotas and conservative persistent storage admission bound this experimental local service. Native process limits are not a sandbox. No validated Finder Orca profile ships: the original Sailfish rejection remains; a separate Marlin-emission draft 02 now generates offline review artifacts with unresolved physical blockers. See [docs/WEB.md](docs/WEB.md). The default Compose now starts this page; Podman CLI is also documented.

### Optional private-LAN access

`web_access.py` validates explicit specific-interface LAN opt-in, restricts
socket peers to192.168/16 or a narrower configured subnet plus local IPv4, and
requires a random per-run Basic password for all routes/assets. Forwarded
headers are never identity. Default startup remains loopback; wildcard/public
binds are rejected. Host/Origin/token/capability/file/job guards remain unchanged.
The full-workflow LAN wrapper needs no IP argument: bounded Linux local
interface ioctls select the sole eligible primary192.168 address without DNS,
probes or a target connection. Missing/multiple candidates fail rather than
falling back to a wildcard. Explicit overrides remain. The wrapper selects
existing Save/Start/generated-output flags; sharing alone does not grant capabilities. Users share one
workspace/login, not per-user jobs/roles. Basic HTTP is unencrypted and suitable
only for a deliberately trusted home network, never a public tunnel/router
forward/reverse proxy. No TLS or production-security claim. See LAN.md.

### Passive status panel

`passive_status.py` reads bounded tails of existing proxy event/raw-server
streams, matches complete M105/M119/M27 replies and derives per-sample
observation ages. It never opens a printer socket. The startup-configured
capture source is matched to the web target's proxy listener host/port; source,
session and captured upstream are shown, not assumed immutable identity. A
separate `watch_printer.sh` serves read-only observation on localhost8001 so the
operator need not restart a running control connection. Status changes do not
unlock or trigger actions. Missing/stale/malformed metrics stay unknown/stale;
byte counters are not job-completion or motion proof. No source path or command
is accepted over HTTP. See STATUS.md for tail/source/session limitations.

### Active status ownership

`active_status.py` maintains a firmware-gated status-only session, requesting
serial M119/M105/M27 batches one second after each previous batch. The backend
owns its lifecycle independently of browser GETs/tabs. Proxy and owned-dummy
launchers default to automatic monitoring with `--no-monitor` opt-out; this does
not enable automatic Save/Start/Cancel. A shared network lock yields/releases
monitor ownership before local printer operations, pauses during busy work,
and resumes only after normal outcomes. Query/identity/recording/release errors
or uncertain printer operations stop monitoring without automatic reconnect.
External FlashPrint processes are not covered by this lock. Stop monitoring
closes its session, never sends M26. Per-run bounded private captures reserve
workspace capacity; cache timestamps reflect batch completion, not physical
execution. See STATUS.md for limits and pending hardware/browser acceptance.

### Manual-control rehearsal, not hardware motion

`manual_controls.py` implements a typed, bounded counter/light model with no
wire-command encoder. Only an owned fresh dummy web server installs it;
configured targets (including loopback proxies) cannot unlock it via flags or
JSON. Independent `manual.js` provides explicit confirmed, revision-bound
single-click actions and cached local-state reads; it never automatically
repeats an action. Busy/active-job/unknown state and toy cold-extrusion guards
are server enforced. Capture finalization precedes in-memory commit; counter
state cannot silently mutate on recording failure. This model does not change
TCP mock replies or execute G-code. Small-step semantics, mode restoration,
scoped LF-only manual reply parsing and real temperature/position/limit guards
still need separate reviewed evidence before implementing physical controls.
See MANUAL_CONTROLS.md; the existing shared network lock is not claimed tested
for physical manual motion by a counter-only rehearsal.

### Per-slice quality settings

`slice_settings.py` validates only layer height and brim mode/width. The web
API accepts that typed object only on confirmed Slice, not Save/Start or a
running operation. The adapter applies an allowlist to its private process
snapshot, records original/effective hashes and settings, and leaves machine,
filament, first-layer and retraction/templates unchanged. Defaults preserve
profile bytes. Cached applied values belong to the generated artifact; controls
cannot mutate an existing print file. This is not generic JSON editing, a
native-code sandbox or physical bed/clearance validation. See WEB.md for limits.

### Separate OctoPrint plugin experiment (paused)

The research repo includes a separately packaged GPLv3 plugin in `plugins/octoprint-flashforge-finder2` (registered as a Git submodule). It uses OctoPrint admin-only Settings/Simple API/Template mixins to upload an OctoPrint local file through a bounded background worker. It does not replace OctoPrint's PrinterInterface or serial transport, and exposes no start/stop, arbitrary G-code, automatic connection or slicer. The plugin is disabled by default and is independently installable. Its Linux Compose test shares host networking only to reach a deliberately configured host-loopback dummy/proxy; OctoPrint binds its UI to loopback. Docker runtime/browser acceptance is still pending. See [docs/OCTOPRINT.md](docs/OCTOPRINT.md) and the plugin's own README/SOURCE for exact limits and evidence.

The standalone page delivers the file selection, configured target, confirmation, bounded transfer and honest progress subset below. Browser/container acceptance, a 3D/toolpath preview, native Finder profile validation and richer job cancellation remain outstanding:

Klienten ska ha konfigurerbar målport, begränsade väntetider, inkrementell svarsläsning och ett verifierat sätt att avgöra framgång. Ingen godtycklig tresekunderspaus utan evidens. Lås en aktiv operation per fysisk skrivare som konservativt grundval. Återförsök aldrig en delvis genomförd uppladdning blint; resultatet kan vara okänt och kräva återanslutning/manuell kontroll.

Webb-MVP:

- släppzon och vanlig filväljare;
- visa vald, serverkonfigurerad skrivare och filnamn/storlek;
- explicit knapp för **Ladda upp**, ingen automatisk utskriftsstart;
- skilj webbläsare → backend från backend → skrivare i förloppsvisningen;
- visa skickade byte separat från skrivarens slutbekräftelse;
- vid osäker slutstatus: visa **okänt resultat**, inte lyckad överföring;
- avbryt väntande arbete; vid aktiv överföring förklara att partiell fil kan finnas kvar;
- inget generellt G-code-kommando-API, ingen godtycklig mål-IP från webbläsaren.

Validera filstorlek och filnamn, använd servergenererade temporärnamn och skydda mot path traversal. Tillåtna ändelser fastställs efter hårdvaruverifiering; ändelsekontroll bevisar inte säkert innehåll. Begränsa uppladdningsstorlek, lagring, kö och samtidighet. Städa temporärfiler även vid fel.

The web server binds loopback by default. Explicit LAN sharing now uses the
private-IPv4/password policy above, preserving CSRF/Origin/Host guards. Firewall,
network trust and shared access to files remain operator decisions. The target
is server-configured, never a browser-selected general network proxy (SSRF).
Internet exposure is not supported.

### Offline G-code numerical diagnostics

`finderlab/gcode_review.py` (`python3 -m finderlab review FILE`) is read-only and never connects to a printer. It models a bounded basic linear-command subset for nominal endpoints, E deltas/resets and resolved XYZ-feed components. Unknown origins/modes, unmodeled homing/offsets and parse warnings remain explicit. Absolute-E intent for references without M82/M83 requires a labeled caller assumption. Alerts can expose the copied +363 mm end step and excessive nominal mixed-Z components, but missing alerts are not a safety verdict. No code rewriting, physical clearance model, firmware certification or automatic upload gate is introduced by this diagnostic tool.

## 7. Kvalitetskrav och validering

Transporttester ska omfatta binärdata, samtidig trafik, fragmentering, sammanslagna läsningar, långsamma mottagare, half-close och avbrutna anslutningar. Jämför byte/hash i båda ändar, inte bara utskrivna loggar.

Simulatorn testas både med egen klient och med referensinspelningar från FlashPrint/riktig skrivare. Ett manuellt acceptanstest är att en specificerad FlashPrint-version kan ansluta, identifiera Finder-profilen, polla status och överföra två olika filer med korrekta virtuella byte utan fysisk skrivare.

Hårdvarutester är opt-in, kräver explicit mål och utförs aldrig i vanliga tester eller av en agent utan användarens godkännande. Upload-only måste också verifieras på hårdvara; anta inte att alla firmwarevarianter beter sig lika.

Se [ROADMAP.md](docs/ROADMAP.md) för etapper och [QUESTIONS.md](docs/QUESTIONS.md) för beslut som återstår.
