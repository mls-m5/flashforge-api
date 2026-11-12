# Inspelningar och referensdata

Detta är föreslaget format för den kommande proxyn/simulatorn, inte befintlig funktionalitet. Formatet ska versionssättas före första implementationen.

## Syfte

En inspelning ska kunna besvara **vilka byte som observerades, i vilken riktning och när**, utan att avkodning förstör data. Den ska räcka för strömjämförelse, parserregression och kontrollerad återspelning mot en simulator. PCAP kompletterar med nätverkspaket och TCP-metadata, men ersätter inte applikationens sessionsmetadata.

## Föreslagen layout (formatversion 1)

```text
captures/<capture-id>/
  manifest.json
  events.jsonl
  sessions/<session-id>/
    client-to-server.bin
    server-to-client.bin
  network.pcapng             # valfri separat nätverksfångst
  notes.md                   # manuella handlingar och observationer
```

`client` betyder den inkommande klienten (oftast FlashPrint); `server` är proxyns mål eller simulatorn. Behåll samma betydelse i samtliga filer.

### Manifest

Ange minst formatversion, capture-ID, verktygsversion/commit om tillgänglig, läge (proxy/simulator), UTC-start, modell/firmware, FlashPrint-version, OS, bindningsadress, mål-IP/-port, experiment-ID och om fångsten avslutades korrekt. Okända miljöfakta ska uttryckligen vara `null`/okända, inte gissade.

Efter stängning anges per råfil storlek och SHA-256. Hashen visar om fångstfilen ändrats; den bevisar inte att skrivaren sparat samma fil. Lämna en synlig ofullständig markering om processen kraschar eller lagringen tar slut.

### Händelser

`events.jsonl` innehåller en JSON-händelse per rad. Föreslagna typer: `connection_open`, `data`, `forward_complete`, `eof`, `error`, `connection_close`, `capture_end`.

Exempel på en `data`-händelse (fältnamn är ett formatförslag):

```json
{"v":1,"seq":12,"session_id":"s001","type":"data","direction":"client_to_server","monotonic_ns":48211000,"stream_offset":0,"length":12}
```

`monotonic_ns` är förfluten monotont uppmätt tid sedan capture-start, inte OS-klockans absoluta värde. `seq` ger en total loggordning; den är inte bevis för exakt kausal ordning mellan samtidiga riktningar. UTC används för att koppla till andra verktyg.

Rådata lagras separat i binärfilen. `stream_offset` och `length` pekar på exakt intervallet för den riktningens session. En socket-läsning motsvarar en observation, **inte ett protokollpaket**.

En datahändelse avser byte som proxy har läst och registrerat, inte bevisat mottagande på motparten. `forward_complete` refererar datahändelsens sekvensnummer när skrivningen till utgående transport slutförts utan känt fel; inte heller det bevisar applikationsmottagande. Vid skrivfel kan redan vidarebefordrad mängd vara okänd och får inte fabriceras.

Fel ska ange fas, riktning, feltyp och om fångsten blivit ofullständig. Half-close loggas per riktning, slutlig stängning separat. På så sätt skiljs timeout från EOF och fullbordad session från krasch.

## Validering och visning

En framtida validerare ska kontrollera:

- formatversion, nödvändiga fält och unika sessions-/händelse-ID:n;
- intervall inom rätt råfil, sammanhängande byteoffset och rimlig tidsordning;
- storlekar, hash och slutmarkering;
- att ofullständig sista JSON-rad eller saknade råbyte ger tydlig varning, inte tyst framgång.

Analysverktyget ska kunna visa hex, ASCII med escapade kontrolltecken, kommandohändelser och tidslinje. Text med ersättningstecken är en vy, aldrig underlag för exakt återspelning. Stora payloads ska visas som intervall/längd/hash, inte fylla terminalen med modellinnehåll.

## Integritet och delning

Captures kan innehålla serienummer, MAC/IP-adresser, datornamn, privata filnamn och hela 3D-modeller. Lagra lokalt med begränsad åtkomst. Ingen automatisk uppladdning till externa tjänster.

Råinspelningar ska vara oförändrade. För delning: skapa ett separat derivat, dokumentera ersatta fält och regenerera längder/offset/hash där det behövs. Att byta en IP-sträng i rådata kan förstöra ett binärt paket. Använd helst en egen liten, delbar modell redan under försöket.

Håll fulla captures utanför versionshantering. Lägg bara små granskade fixtures i `tests/fixtures/`, med proveniens och licens/tillstånd för ingående innehåll. Bestäm lokal lagringskvot, ledigt-utrymme-kontroll och manuell gallringsrutin innan långa fångster startas.
