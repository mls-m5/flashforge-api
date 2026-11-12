# Design

## 1. Mål och avgränsning

Bygg ett lokalt protokollabb för **FlashForge Finder 2**, och därefter en liten webbapplikation för uppladdning av färdigslicade filer. Det primära slutflödet är att släppa en fil, se framsteg och få ett tydligt kvitto utan att starta utskrift.

Simulatorn ska kunna ersätta hårdvaran för så stor del av FlashPrints normala arbetsflöde som möjligt. Målet är observerbar kompatibilitet för en angiven kombination av Finder-modell, firmware och FlashPrint-version, inte en allmän emulator för alla FlashForge-skrivare. Full fysisk simulering och firmwareemulering ingår inte i första versionen.

Vi ska inte bygga slicer, molntjänst eller fjärrstyrning av rörelse/värme i första webbversionen. `.gcode`, `.g` och `.gx` är kandidater att undersöka, inte bekräftade likvärdiga format. Godtycklig G-code blir inte Finder-kompatibel genom att filändelsen byts.

## 2. Utgångsläge och principer

Current implementation: the unchanged experimental `upload.py`, a synthetic TCP mock in `finderlab/simulator/`, per-run recording in `finderlab/capture.py` and a byte-preserving TCP proxy in `finderlab/proxy.py`. See [docs/MOCK.md](docs/MOCK.md), [docs/PROXY.md](docs/PROXY.md) and [docs/CAPTURES.md](docs/CAPTURES.md). The default `finder-v1.5-idle` profile now uses capture-derived, anonymized control/identity/idle replies, with independent golden-byte tests and a user-recorded successful FlashPrint idle connection. The original `synthetic-v1` remains selectable. The uploader's transfer framing and the mock's other behaviors remain hypotheses, not a verified full specification. Automated proxy/recording tests use only localhost fake servers. Discovery, replay/standalone analysis and web support remain planned.

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

Current tools use a flat `finderlab/` package (`__main__.py`, `simulator/`, `capture.py`, `proxy.py`) and `tests/` so they can run without installation. Runtime test files use ignored project-local `.tmp/`; recordings use ignored `captures/`. The following remains a proposed longer-term structure rather than a current tree:

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

## 6. Protokollklient och webbgränssnitt

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

Webbservern binder loopback som standard. LAN-exponering kräver separat beslut om autentisering, CSRF/Origin/Host-kontroller, brandvägg och åtkomst till uppladdade filer. Serverns mål är konfigurerat för att undvika att tjänsten blir en generell nätverksproxy (SSRF). Ingen internetexponering i MVP.

## 7. Kvalitetskrav och validering

Transporttester ska omfatta binärdata, samtidig trafik, fragmentering, sammanslagna läsningar, långsamma mottagare, half-close och avbrutna anslutningar. Jämför byte/hash i båda ändar, inte bara utskrivna loggar.

Simulatorn testas både med egen klient och med referensinspelningar från FlashPrint/riktig skrivare. Ett manuellt acceptanstest är att en specificerad FlashPrint-version kan ansluta, identifiera Finder-profilen, polla status och överföra två olika filer med korrekta virtuella byte utan fysisk skrivare.

Hårdvarutester är opt-in, kräver explicit mål och utförs aldrig i vanliga tester eller av en agent utan användarens godkännande. Upload-only måste också verifieras på hårdvara; anta inte att alla firmwarevarianter beter sig lika.

Se [ROADMAP.md](docs/ROADMAP.md) för etapper och [QUESTIONS.md](docs/QUESTIONS.md) för beslut som återstår.
