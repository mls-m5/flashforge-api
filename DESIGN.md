# Design

## 1. Goals and scope

Build a local protocol lab for **FlashForge Finder 2**, then a small web application for uploading print files. The workflow shows progress and honest save/start outcomes. File receipt and slicing never start prints. The user-requested web start-after-upload checkbox defaults checked when job controls are enabled; the clearly labelled initiating Save + start click supplies combined intent. Unchecked and CLI defaults remain save-only.

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

`finderlab/slicer.py` exposes a separate async STL → plain G-code adapter. `slice` invokes it offline; upload's `--slice` invokes it before opening a printer session. Trusted self-contained JSON profiles, isolated datadir/workspace, capability probing, bounded output/logs/time/address space, process-group cleanup and a per-workspace single-job lock prevent accidental fallback to arbitrary shell options or unbounded concurrent jobs. These are resource/orchestration boundaries, not a native-code security sandbox or motion-safety check. Logs/hash provenance share the capture lifecycle; generated output is separately size-bounded. No fallback guessed Finder profile, G-code rewriting or automatic start is introduced by slicing. GX wrapping/thumbnail generation now exists as a separate explicit offline export stage described below. See [docs/SLICING.md](docs/SLICING.md). Native Orca 2.3.0 now generates geometry for the separately authorized offline draft 02. It is not a validated motion profile; the original Sailfish draft still fails. See [docs/ORCA_FINDER_DRAFT_02.md](docs/ORCA_FINDER_DRAFT_02.md) for actual trials, E/reset ownership and the layer-change Z split. Tests use a fake CLI and dummy printers; no reviewed Finder profile is available.

### Standalone web workbench

`finderlab/web.py` and `finderlab/webstatic/` implement a dependency-free loopback page. One bounded raw file receive stores an STL/print file; a separate confirmed Slice uses server-owned Orca/profiles; a third confirmed Save uses the existing client. With job controls enabled the user-requested start-after-upload checkbox defaults checked; that explicit combined click composes confirmed save, healthy release/finalized recording and fresh-session READY/exact-identity start. Unchecked/legacy API stays save-only. See START_AFTER_UPLOAD.md for immutable outcome facts, continuous busy ownership, failure gates and separate captures; no automatic stop/retry. Generated G-code is downloadable for review and cannot be sent unless the operator explicitly enables generated-output saving. Separately opt-in job controls (`--enable-job-controls`) expose confirmed Start of the exact saved filename (per-save identity, one attempt, fresh READY check) and confirmed Cancel (not emergency stop). They share the operation lock, never run automatically and preserve save confirmation separately from uncertain job results. No HTTP request can select targets, profiles, host paths or arbitrary native flags. GET cached status never connects to a printer. Low-level startup stays disconnected unless configured with `--auto-monitor`; the proxy/owned-dummy launcher now selects that status-only startup mode by user request. Offline slicing and the passive watcher stay disconnected. Host/Origin/token checks, bounded HTTP parsing/timeouts, single-slot/process locks, capture quotas and conservative persistent storage admission bound this experimental local service. Native process limits are not a sandbox. No validated Finder Orca profile ships: the original Sailfish rejection remains; a separate Marlin-emission draft 02 now generates offline review artifacts with unresolved physical blockers. See [docs/WEB.md](docs/WEB.md). The default Compose now starts this page; Podman CLI is also documented.

### Read-only modular toolpath view

A pinned local MIT Three.js renderer, bounded Web Worker parser and independent
controller now preview only the current server artifact. Batch LineSegments
and per-segment height shader filtering avoid per-move objects/reuploads.
Unknown origins and unsupported paths are omitted/reported; extrusion modes /
E resets/retract debt are nominal interpretation, not firmware/material physics.
GET artifact ETag/If-Match and controller generations/termination prevent stale
async results replacing a changed slot. No server parse/cache/printer endpoint
or mutation is introduced. Static assets/worker retain LAN auth/Host policy and
CSP self-only. See PREVIEW.md; renderer/GPU/browser acceptance remains pending.
Future volume/image export/arrangement are separate, not implemented.

Browser popups are removed by explicit user request. The initiating button click
is consent; API confirm fields, backend locks/policies/identity/READY gates and
no-auto-start/no-retry remain. Persistent labels replace modal reminders.

### Independent source-model mesh preview

The source hash/model identity is retained separately from the generated print
artifact. `model-preview.js` uses fixed config/state/model GETs; the model read
requires a token because 3MF may prepare a local derived STL cache. Conversion
runs in a bounded/reaped Python worker, never Orca/client, reserves workspace
capacity, blocks overlapping local operations and restores state on failure.
STL streams unchanged. Discard removes its cache. Browser geometry parsing is
bounded/off-thread; the shared Three scene accepts a shaded mesh/wireframe with
visual-only centered/on-bed translation, without mutating source/slicer input.
The user accepted that initial preview. A typed single-model editor now adds
uniform scale, extrinsic XYZ rotations and XY centre movement, with on-bed Z.
Source-bound browser drafts commit only on explicit Slice; server bakes private
STL with bounded stdlib worker, captures original/derived identities and asks
Orca for arrange0/orient0. Automatic mode/CLI retain arrange1. Original source
and completed artifacts remain immutable; server snapshot freezes editor fields
at Slice. Native2.3 coordinate-preservation trials passed; new browser/host2.5
acceptance remains pending. Gizmos/face picking/multiple models remain future.
See MODEL_PREVIEW.md and MODEL_TRANSFORMS.md for limits, mathematical contract,
source/artifact generation guards, tests and fixed-purge/clearance limitations.

### Explicitly requested automatic finalized-record archival

Admission still reserves monitor/foreground budgets, but can now archive oldest
complete inactive captures intact into DATA_DIR/archive/captures on the same
persistent volume. Active quota excludes this subtree; archive is separately
bounded2GiB/16384 entries with an append-only index. Current selected/save/start /
monitor paths, incomplete/active logs and all model/plate files are protected.
No deletion/overwrite/raw edit, automatic retry, GET-triggered work or printer
operation. Lack of eligible space or full/error archive remains a visible
rejection, now shown beside Slice. Explicit bounded active-quota override and
archive opt-out are startup configuration, never HTTP-selected host paths.
See STORAGE.md for exact policy, tests and confirmed host507 recovery.

### Multiple STL plate sources and immutable compound layout

The web slot can now hold up to8 unsliced STL sources (64MiB aggregate), with
serial receipt, individual opaque identities, revision-bound removal and source
GETs. Single3MF/print-file slots remain standalone. A dedicated plate controller
shares the bounded parser/Three renderer but retains independent numeric drafts,
mesh selection and cached generation tickets. Every source must appear exactly
once in explicit Slice's typed plate snapshot; stale/missing/injected models
cannot fall back to slicing only the first file. Assembly bakes disjoint nominal
XY layouts in a bounded worker into one private STL, arrange0/orient0 and private
process by-layer sequencing. Full-height XY AABBs need1mm separation; this is
conservative geometry admission, not head/clip/firmware clearance simulation.
Originals stay unchanged; successful Slice retains the exact compound mesh for
whole-plate GX, with separate input/compound hashes/capture provenance. Same
operation/job/access/priming guards; no automatic Slice/Save/Start or hardware
connection. See PLATE.md for limits, endpoints, native2.3/HTTP trials and browser /
host2.5 acceptance gaps. Gizmos/face picking remain future.

### Explicit experimental GX packaging and CPU miniature

After a successful supported model Slice, the page offers a separate GX action.
The slicer retains optional header metadata from exact effective snapshots/output
estimates (failure disables export, not Slice). A bounded stdlib helper renders
80×60 grayscale mesh/BMP and the observed two-sample Finder envelope, retaining
G-code bytes exactly. Source/artifact/receipt hashes, snapshot transforms and
complete export capture gate new artifact selection. No printer call or auto
Slice/Save/Start; generated GX keeps sliced provenance and upload capability
restrictions. Existing print files are not repackaged by the web API. Local
CPU rendering avoids browser/GPU/external dependency; source mesh fits the
camera but auto-arrangement/support/compensation are not reproduced. Separate
GET serves only the current hash-bound bitmap under LAN auth and self-only img
CSP. See GX_GENERATION.md for unknown constants, external-vs-local evidence,
resource/process limits, native offline trial and pending physical acceptance.

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

### Geometry-only 3MF import

The initial 3MF path deliberately does not load a project into Orca. A bounded
stdlib ZIP/XML importer (`model_3mf.py`) flattens supported core mesh build items
with units/transforms into private STL. Project presets, scripts, modifiers and
start code never reach the native slicer; server JSON and typed overrides stay
authoritative. Components/external/required-extension geometry is rejected.
Original input hash and derived geometry hash/bounds/count/skipped zero-area
facets are captured separately. See 3MF.md for limits and native user-tool trial.
No printer/network operations occur during import or slicing.

### Opt-in nominal priming review before publication

The independent03 experiment now has a bounded stdlib first-layer diagnostic /
pre-publication guard (`priming_review.py`, trusted `--check-priming` option).
It checks declared tagged linear deposition, first native skirt, no fixed XY
startup extrusion, centreline intersections/gaps and conservative nominal±69mm
bounds. A native exit0 edge counterexample motivated the guard; failure leaves
no artifact for Save + start. No rewriting, physical/swept-volume simulation or
new protocol behavior. Source/report SHA, helper resource limits, private
capture metadata and full raw outputs remain separate. The user subsequently
explicitly selected03 for all standard web launchers: offline, owned dummy,
proxy and LAN now always enable the guard and never fall back to02. The isolated
03 test workspace still restricts target mode. This software-default decision
is not physical startup/host2.5 validation; existing files need re-slicing.
See PRIMING_REVIEW.md.

### Per-slice quality settings

`slice_settings.py` validates only layer height, brim mode/width and bounded
independent per-edge XY hole/outer-contour compensation (−0.5..+0.5mm or profile). The web
API accepts that typed object only on confirmed Slice, not Save/Start or a
running operation. The adapter applies an allowlist to its private process
snapshot, records original/effective hashes and settings, and leaves machine,
filament, first-layer and retraction/templates unchanged. Omitted/profile values preserve profile bytes; the UI's initial
hole0 explicitly disables any nonzero profile compensation. Positive hole
values expand internal XY contours, not global model scale or guaranteed fits. Cached applied values belong to the generated artifact; controls
cannot mutate an existing print file. This is not generic JSON editing, a
native-code sandbox or physical bed/clearance validation. See WEB.md for limits.

### Separate OctoPrint plugin experiment (paused)

The research repo includes a separately packaged GPLv3 plugin in `plugins/octoprint-flashforge-finder2` (registered as a Git submodule). It uses OctoPrint admin-only Settings/Simple API/Template mixins to upload an OctoPrint local file through a bounded background worker. It does not replace OctoPrint's PrinterInterface or serial transport, and exposes no start/stop, arbitrary G-code, automatic connection or slicer. The plugin is disabled by default and is independently installable. Its Linux Compose test shares host networking only to reach a deliberately configured host-loopback dummy/proxy; OctoPrint binds its UI to loopback. Docker runtime/browser acceptance is still pending. See [docs/OCTOPRINT.md](docs/OCTOPRINT.md) and the plugin's own README/SOURCE for exact limits and evidence.

The standalone page delivers the file selection, configured target, confirmation, bounded transfer and honest progress subset below. Browser/container acceptance, richer volume/arrangement preview, native Finder profile validation and richer job cancellation remain outstanding:

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
