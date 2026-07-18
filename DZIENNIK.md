# DZIENNIK.md — dziennik zmian (skrótowo, po ludzku)

## 2026-07-18 — zadanie 0001: podpięcie scenariusza 800 (Kent i Sussex)

Co zrobione: `sim.py` umie teraz wystartować z warstwą scenariusza
(`scenariusz_800.json`, jeśli plik istnieje obok) — wtedy jednostką
polityczną jest ZIEMIA, a nie proceduralny powiat, i gracz gra Cantią.
Bez pliku scenariusza świat działa dokładnie jak wcześniej (proceduralne
powiaty/królestwa) — sprawdzone ręcznie przez tymczasowe przeniesienie
`scenariusz_800.json` i porównanie działania serwera/klienta w obu trybach.
`server.py` dorzuca `kom_ziemia` do protokołu binarnego (zawsze, w obu
trybach — jeden protokół, zero rozgałęzień po stronie parsowania) i
rozgłasza agregaty per ziemia zamiast per powiat, gdy scenariusz aktywny.
`static/index.html` przepisany na generyczne pojęcia "jednostka"/"właściciel"
(ziemia+państwo w scenariuszu, powiat+królestwo proceduralnie) — jeden kod
renderujący dla obu trybów. `scenariusz_800.py` liczy teraz `kadr_startowy`
(bbox obu państw w px płótna) z geografii komórek, nie ze stałych generatora.
Dopisano `test_scenariusz.py` (5 kryteriów z brief-u) — przechodzi.

Co zaskoczyło: `/api/meta` pierwotnie zwracał właściciela każdej ziemi ze
STATYCZNEGO zapisu scenariusza (`swiat.ziemie[i]["panstwo"]`), a nie z żywej
tablicy `ziemia_panstwo`, którą zmienia podbój. Efekt: gracz łączący się
PO czyimś podboju widział starą własność ziemi, dopóki nie nadszedł kolejny
podbój na jego oczach. Znalezione dopiero przy teście end-to-end w
przeglądarce (Playwright) — konkretnie przy odświeżeniu strony po podboju.
Naprawione: `/api/meta` liczy `panstwo` z `swiat.ziemia_panstwo[i]` na
żywo; klient dostaje już gotowy indeks (nie trzeba mapować klucza państwa
po stronie przeglądarki). Druga rzecz: sandboxowe `bash` w tej sesji potrafiło
zwracać mylący kod wyjścia (144) dla poleceń z `&`/`setsid`/`pkill` mimo że
polecenie faktycznie się wykonało — testowanie przez `ps`/`ls` zamiast ufania
kodowi wyjścia.

## 2026-07-18 — zadanie 0002: sterowanie kamerą (limity zoomu, płynność, próg przeciągania)

Co zrobione: limity zoomu (`kam.min`/`kam.max`, dawne `kam.fit`) liczone
teraz zawsze od skali "cała mapa w oknie", niezależnie od `kadr_startowy` —
dzięki temu jednym gestem da się dojść od Kentu do widoku całej Europy i
z powrotem. Zoom kółkiem/gładzikiem: krok proporcjonalny do `deltaY`
(znormalizowany przez `deltaMode`) zamiast sztywnych 15%, i rysowanie
spięte z `requestAnimationFrame` (`zaplanujRysowanie()`) zamiast
synchronicznego `rysuj()` na każde zdarzenie — przy dużym oddaleniu
dodatkowo pomijana najcieńsza warstwa granic (i tak niewidoczna). Klik i
tak dalej nie przesuwają mapy: próg przeciągania 4px (`nacisk`/`przeciagam`)
zastąpił natychmiastowe panoramowanie od `pointerdown`. Dodano reset widoku
(klawisz `Home` i podwójny prawy klik) do `kadr_startowy`. `sim.py`:
podbój ziemi niczyjej zwraca teraz jawną odmowę
(`{"typ":"odmowa","powod":...}`) zamiast `None`, które ginęło po cichu —
klient pokazuje to w panelu info na 3 sekundy. Zaktualizowano
`test_scenariusz.py` (kryterium 5) pod nowy kontrakt.

Co zaskoczyło: nic architektonicznie — to była wymiana czystego JS-u w
jednym pliku. Jedyna pułapka przy testowaniu: porównywanie całych
zrzutów ekranu, żeby sprawdzić "czy klik przesunął mapę", dawało fałszywe
alarmy, bo podświetlenie komórki pod kursorem SAMO w sobie zmienia obraz
przy pierwszym najechaniu myszą. Trzeba było porównywać wycinek ekranu z
dala od kursora, żeby odizolować sam efekt panoramowania.
