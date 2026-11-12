# FlashForge Finder 2 – protokollabb och webbuppladdning

Målet är att förstå Finder 2:s nätverksprotokoll och bygga ett enkelt lokalt webbgränssnitt där man släpper en färdigslicad fil för överföring till skrivaren. Uppladdning ska **inte automatiskt starta en utskrift**.

Projektet ska också kunna användas utan fysisk skrivare genom en alltmer verklighetstrogen simulator.

## Status

Det finns i dag bara ett experimentellt skript, [`upload.py`](upload.py). Proxy, simulator, analysverktyg och webbgränssnitt är **planerade, inte implementerade**. Dokumentens framtida beteenden och acceptanskriterier är inte löften om befintlig funktionalitet.

Skriptet använder TCP-port `8899`, skickar `~M601 S1`, `~M28`, råa filbyte, `~M29` och `~M602`. Det är inte verifierat mot projektets Finder 2 och bevisar inte att överföringsformatet är rätt. Det accepterar bara en viss form av `ok`-svar och har en fast paus före M29. Läs [protokollanteckningarna](docs/PROTOCOL.md) innan hårdvarutest.

Om man efter riskbedömning vill prova det befintliga skriptet:

```sh
python3 upload.py SKRIVARENS_IP modell.gx
```

Skriptet har ingen konfigurerbar port och kräver inga tredjepartsbibliotek. Ingen ny körbar funktionalitet tillkommer genom denna dokumentationsetapp.

## Planerade delar

| Del | Uppgift |
| --- | --- |
| Inspelningsproxy | FlashPrint → proxy → riktig skrivare; loggar båda riktningar utan att ändra byteströmmarna. |
| Finder-simulator | FlashPrint → simulerad skrivare; efterliknar identitet, sessioner, status, filöverföring och senare discovery. |
| Analys och återspelning | Inspekterar inspelningar, jämför försök och skapar reproducerbara regressionstest. |
| Klient och webbgränssnitt | Återanvänder det verifierade protokollet för lokal drag-and-drop-uppladdning. |

**Rekommenderad ordning:** passiv fångst → proxy → referensinspelning → simulator → verifierad klient → webbgränssnitt.

## Dokument

- [DESIGN.md](DESIGN.md): arkitektur, simulatorns realism och säkerhetsgränser.
- [AGENTS.md](AGENTS.md): arbetsregler för kodassistenter och bidragsgivare.
- [docs/PROTOCOL.md](docs/PROTOCOL.md): evidens, hypoteser, portar och öppna protokollfrågor.
- [docs/CAPTURES.md](docs/CAPTURES.md): planerat inspelningsformat och integritet.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md): praktiskt upplägg för protokollundersökningen.
- [docs/ROADMAP.md](docs/ROADMAP.md): etapper och testbara acceptanskriterier.
- [docs/QUESTIONS.md](docs/QUESTIONS.md): sådant som behöver förtydligas inför implementation och hårdvarutest.

## Säkerhet

Arbeta på ett betrott, isolerat LAN. Exponera inte skrivare, proxy, simulator eller webbserver direkt mot internet. En transparent proxy är **inte ett säkerhetsfilter**: FlashPrint kan skicka rörelse-, värme- och startkommandon genom den. Ha fysisk uppsikt över skrivaren under experiment. Läs säkerhetsavsnitten i designen och experimentplanen.
