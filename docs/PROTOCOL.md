# Protokoll: evidens och öppna frågor

Detta är en arbetsjournal, **inte en verifierad Finder 2-specifikation**. Inga lokala inspelningar från fysisk skrivare har ännu analyserats i projektet.

## Evidensnivåer

- **Kodobservation:** vad projektets befintliga program gör; bevisar inte skrivarens beteende.
- **Extern uppgift:** vad en länkad källa uppger för angiven modell/familj.
- **Hypotes:** något vi avser att testa.
- **Lokalt verifierat:** reproducerbart försök med miljö och capture-referens. Inga sådana poster ännu.

## Inventering

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
