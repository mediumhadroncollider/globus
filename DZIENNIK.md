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

## 2026-07-18 — zadanie 0003: koszt klatki + osierocone komórki na granicach

**Część A — koszt klatki.** Zadanie 0002 naprawiło częstotliwość rysowania
(rAF), ale nie koszt jednej klatki. Cztery poprawki w `static/index.html`:
1. Podświetlenie pod kursorem **nigdy nie rysuje ziemi niczyjej** — dawniej
   `g.fill(sciezkaNiczyje)` (~23 600 wielokątów) leciało w KAŻDEJ klatce,
   bo kursor stoi nad ziemią niczyją niemal zawsze. Teraz podświetlana jest
   wyłącznie jednostka z właścicielem; ziemia niczyja — zero kosztu.
2. `sciezkaNiczyje` (warstwa całkowicie niezmienna) wypalona RAZ na osobny
   canvas (`niczyjeCv`), tak jak wcześniej zrobiono z warstwą władców —
   mapy ciepła (Populacja/Dochód) teraz kopiują gotowy obrazek zamiast
   fill+stroke tych samych 23 600 wielokątów co klatkę/tick.
3. Próg pomijania granic jednostek przy oddaleniu zaostrzony z `kam.min*3`
   do `kam.min*1.5` — dawny próg chronił przed kosztem, który w trybie
   scenariusza (ziemia niczyja to JEDNA jednostka bez wewnętrznych krawędzi)
   w ogóle nie istnieje, a chował granice ziem Kentu/Sussexu przy oddaleniu.
4. Licznik czasu klatki pod klawiszem `F` (domyślnie wyłączony): `performance.now()`
   wokół treści `rysuj()`, średnia z 30 ostatnich klatek, panel obok rankingu.

**Pomiar (headless Chromium + Playwright, bo to środowisko nie ma prawdziwego
wyświetlacza/kompozytora GPU — bezwzględne liczby są dużo niższe niż w
realnej przeglądarce autora, ale KIERUNEK zmiany jest wiarygodny, bo mierzy
dokładnie te same wywołania Canvas2D przed i po):
seria 50 zdarzeń kółka myszy z kursorem nad ziemią niczyją, po oddaleniu na
całą Europę, mierzone jako suma czasu w `fill()`/`stroke()` na klatkę:

| widok | PRZED | PO | wywołań fill+stroke/klatkę PRZED → PO |
|---|---|---|---|
| Władcy (hover niczyja) | 0.010 ms/klatkę | 0.008 ms/klatkę | 3.0 → 2.0 |
| Populacja (mapa ciepła) | 0.098 ms/klatkę | 0.014 ms/klatkę | 72.8 → 33.3 |

Mapa ciepła: ~7× mniej czasu w Canvas2D na klatkę i mniej niż połowa wywołań
fill/stroke — dokładnie efekt wypalenia `niczyjeCv` raz zamiast malowania go
co klatkę. W widoku Władców różnica to dokładnie 1 wywołanie fill/klatkę
(hover niczyja usunięty) — mała w liczbie wywołań, ale w realnej przeglądarce
ten JEDEN fill obejmował Path2D z 23 600 podścieżek, więc jego koszt per
wywołanie jest tam nieporównanie wyższy niż w tym środowisku (potwierdza to
architektura zmiany, nie tylko liczba). Obie wartości mieszczą się wygodnie
pod progiem 16 ms z zapasem — w headless nie da się odtworzyć "szarpania",
które autor widział gołym okiem, ale metoda pomiaru (licznik `F`) jest teraz
w kodzie na stałe, więc kolejny pomiar na prawdziwym sprzęcie jest jednym
klawiszem.

**Część B — osierocone komórki na granicach.** `scenariusz_800.py`
przypisywał komórkę do państwa na podstawie testu punkt-w-poligonie na jej
ŚRODKU — przy komórkach ~10 km i postrzępionym wybrzeżu to potrafi dać
eksklawę (komórka odcięta wodą, ale jej środek wpadł do poligonu) albo dziurę
(pojedyncza komórka niczyja w środku państwa). Poprawka: dwa przebiegi na
grafie sąsiedztwa z `world.npz` (`indptr`/`indices`), uruchamiane PO
przypisaniu państw, PRZED podziałem na ziemie:
1. **Filtr większościowy** (2 przebiegi, wektorowo przez `np.bincount` na
   parach CSR) — każda komórka lądowa przyjmuje przynależność większości
   spośród siebie i lądowych sąsiadów (remis = bez zmiany).
2. **Test spójności z ochroną wysp** — spójne składowe każdego państwa na
   grafie sąsiedztwa (z pominięciem zerwanych cieśnin z `world.npz`).
   Największa składowa zostaje; mniejsze od `PROG_ODPRYSKU = 4` komórek
   wracają do ziemi niczyjej; większe/równe zostają jako prawdziwe wyspy
   i trafiają do logu.

Wynik na scenariuszu Kent/Sussex: filtr większościowy zmienił przynależność
**8 komórek** (szum sól-i-pieprz wzdłuż wybrzeża/granicy). Test spójności nie
znalazł żadnych odprysków do usunięcia ani wysp >= progu — przy tej
rozdzielczości siatki i tym wybrzeżu (Kent/Sussex, Anglia) korpusy obu
państw okazały się już spójne bez pomocy (sprawdzone też NA SUROWYCH danych
sprzed filtra większościowego — zero fragmentów nawet bez niego). To nie
znaczy, że mechanizm jest zbędny: filtr większościowy realnie posprzątał
8 komórek, a test spójności jest teraz na stałe w `scenariusz_800.py` i
`test_scenariusz.py` — złapie regresję przy każdej zmianie granic czy
gęstości siatki, nawet jeśli akurat tutaj nie miał nic do odcięcia.
`test_scenariusz.py` ma teraz kryterium 4 (spójność + lista wysp) obok
istniejących 1-3 (puste ziemie / suma komórek / brak właściciela na morzu)
i 5-6 (dawne 4-5, dynamiczne). Wszystkie 9 kryteriów przechodzi, `test_ciesnin.py`
bez zmian też.

Co zaskoczyło: headless Chromium (SwiftShader, bez prawdziwego kompozytora)
renderuje te same wywołania Canvas2D dużo szybciej niż realna przeglądarka na
ekranie — więc automatyczny pomiar w tym środowisku nie odtwarza wielkości
regresji, jaką autor czuł "na oko". Rozwiązanie: mierzyć KIERUNEK i STRUKTURĘ
zmiany (te same wywołania przed/po, licznik `F` wbudowany na stałe), nie tylko
bezwzględne milisekundy z jednego środowiska.

## 2026-07-18 — zadanie 0004: edytor świata (graficzne korekty zamiast heurystyk)

Co powstało: nowy plik `korekty.py` (dzielony przez `sim.py` i
`scenariusz_800.py`) rozstrzyga wpisy `korekty.json` — zakotwiczone w lon/lat,
nigdy w indeksach komórek — na indeksy BIEŻĄCEJ siatki przez `cKDTree`.
`sim.py` (`Swiat.__init__`) nakłada korekty w kolejności z briefu: `lad` →
krawędzie (cieśniny) → scenariusz → `panstwo`/`ziemia` → oznaczenie komórek
jako `przypięte`. `scenariusz_800.py` czyta te same korekty i wyklucza
przypięte komórki z filtra większościowego i testu spójności — bez tego
automat w kółko kasowałby ręczną poprawkę (dokładnie przypadek Sheppey z
briefu: 2–3 komórki poniżej `PROG_ODPRYSKU`, usuwane jako "odprysk", teraz
chronione niezależnie od rozmiaru składowej, jeśli ktoś je przypiął).
`server.py` dostał `GET`/`POST /api/korekty` (zapis robi `korekty.json.bak`
przed nadpisaniem) — GET dorzuca rozstrzygnięte indeksy i stan SPRZED korekt
(`_bazowe`/`_krawedzie_idx`), żeby klient-edytor nie musiał sam liczyć
najbliższej komórki ani zgadywać, do czego wraca "gumka". Protokół binarny
`/api/dane` dostał nowy blok `lonlat` (tożsamość geograficzna każdej komórki —
jedyny sposób, żeby edytor w przeglądarce wiedział, JAKI punkt zapisać w
korekcie, bez duplikowania matematyki odwzorowania Albersa w JS).

Klient (`static/index.html`, `?edytor=1`): pięć narzędzi (Ląd/woda z
malowaniem przeciąganiem, Przynależność z wyborem państwa/ziemi, Cieśnina,
Rzeka, Gumka), pędzel 1/2 (`[`/`]`), Ctrl+Z cofający całe pociągnięcie (nie
pojedynczą komórkę), licznik niezapisanych zmian + ostrzeżenie
`beforeunload`, złota kreska przerywana prawdziwego wybrzeża Natural Earth
(`meta.wybrzeze`, dane już były w projekcie, tylko nieużywane przez klienta),
znaczniki na komórkach z korektą. Największa decyzja projektowa: diagram
Woronoja (ścieżki jednostek/granic/wybrzeża) jest teraz PRZEBUDOWYWANY
(`przebudujGeometrie()`/`przebudujGranice()`), nie tylko budowany raz przy
starcie — batchowane przez `requestAnimationFrame` tym samym trikiem co
`zaplanujRysowanie()`, żeby seria kliknięć podczas malowania nie przeliczała
diagramu 60 razy na sekundę. W edytorze lewy przycisk myszy należy do
narzędzia, prawy (już wcześniej działał jako pan, bo kod nie sprawdzał
przycisku) przejął panoramowanie — zero zmiany zachowania poza edytorem.

Druga decyzja: rozróżnienie "cofnij" (Ctrl+Z — wraca do stanu SPRZED TEGO
pociągnięcia, może to być inna wcześniejsza korekta) od "gumka" (wraca do
PRAWDZIWEGO stanu sprzed jakiejkolwiek korekty). Obie operacje dzielą jedną
funkcję (`zastosujDoZywegoStanu`), różni je tylko to, jaki obiekt jej
podajemy — ale wymagało to trzymania dwóch osobnych "baseline'ów": stanu
sesyjnego (leniwie łapanego przy pierwszym dotknięciu komórki) i stanu
sprzed korekt w ogóle (od serwera, dla komórek poprawionych w poprzednich
sesjach). Sprawdzone w przeglądarce (Playwright, headless Chromium):
kliknięcie zmienia mapę natychmiast, Ctrl+Z cofa całe pociągnięcie z wielu
komórek naraz jedną operacją, zapis tworzy poprawny `korekty.json`
(lon/lat, nie indeksy), a po przeładowaniu strony korekta wraca z serwera z
licznikiem niezapisanych = 0 (bo już zapisana), i "gumka" na niej poprawnie
przywraca PRAWDZIWY stan sprzed korekty (nie stan sprzed bieżącej sesji).
Zweryfikowano też ręcznie przez `curl`: korekta `lad` zapisana przez
`POST /api/korekty`, restart serwera (`uvicorn`), `GET /api/dane` pokazuje
zmienioną komórkę — przeżywa restart, zgodnie z kryterium akceptacji.

`test_scenariusz.py` dostał kryterium 7 w dwóch częściach: syntetyczny plik
korekt (zawsze uruchamiany, nie zależy od tego, czy w repo jest jakiś
prawdziwy `korekty.json`) sprawdza sam mechanizm (`lad`, `panstwo`+`ziemia`,
`przypięte`); jeśli w repo istnieje prawdziwy `korekty.json`, jego wpisy też
są sprawdzane względem świeżego `Swiat()`. Wszystkie istniejące niezmienniki
(`test_ciesnin.py`, kryteria 1–6 `test_scenariusz.py`) przechodzą bez zmian.

Co zaskoczyło: pilnowanie SPÓJNOŚCI między "ziemia" a "państwo" komórki.
`kom_ziemia` i `kom_panstwo` to w `sim.py` NIEZALEŻNE tablice (ziemia to
podział wewnątrz własności, nie sama własność) — edytor mógłby więc
teoretycznie ustawić komórce państwo bez zmiany ziemi, co zepsułoby
renderowanie po stronie klienta (kolor komórki liczony jest per ZIEMIA, żeby
uniknąć osobnej tablicy właściciela na komórkę — koszt klatki się nie
zmienia). Rozwiązanie: narzędzie "Przynależność" zawsze ustawia oba pola
naraz (i czyści oba naraz przy Alt+klik) — format `korekty.json` i tak
dopuszcza samo `panstwo` bez `ziemia` (dla ręcznej edycji pliku), ale edytor
graficzny tej niespójności po prostu nie produkuje.

### Poprawki po review (chatgpt-codex-connector, PR #4)

Dwa zgłoszenia, oba potwierdzone odtworzeniem błędu, oba naprawione:

1. **Crash w trybie proceduralnym.** Korekta `lad` zamieniająca morze na ląd
   zostawiała nowej komórce `komorka_pow == -1` (world.npz przydziela powiat
   tylko lądowi ze swojej generacji). W trybie proceduralnym `tick()` liczy
   `np.bincount(self.komorka_pow[self.lad], ...)` — `-1` w indeksach wywala
   `ValueError` na pierwszym ticku po takiej korekcie. Odtworzone bezpośrednio
   przed poprawką. Naprawa w `sim.py` (`_zastosuj_korekty_lad`): dokładnie ten
   sam trik co sieroty w `generate_world.py` — najbliższy lądowy sąsiad z
   już przydzielonym powiatem (`cKDTree` po `punkty`) użycza swojego.
   Nieszkodliwe w trybie scenariusza (komorka_pow tam się w ogóle nie liczy).
2. **Niespójność testu z briefem.** `scenariusz_800.py` celowo chroni
   przypiętą małą wyspę (< `PROG_ODPRYSKU`) przed usunięciem — ale
   `test_scenariusz.py` kryterium 4 liczyło spójność OD NOWA z samego
   `scenariusz_800.json`, nic nie wiedząc o przypięciu, więc poprawnie
   zachowana wysepka (dokładnie przypadek Sheppey, po który sięga cały
   brief) wyglądałaby jak regresja. Naprawa: kryterium 4 wczytuje teraz
   `korekty.json` i wyklucza przypięte komórki z testu spójności — DOKŁADNIE
   tą samą regułą co `scenariusz_800.py` (`_wyczysc_spojnosc`), wydzieloną do
   wspólnej funkcji `spojnosc_panstw`, żeby te dwa miejsca nie mogły się już
   rozjechać po cichu.

Do obu poprawek dopisano syntetyczne testy regresyjne w `test_scenariusz.py`
(kryteria 7b/7c) — nie zależą od tego, czy przy AKTUALNYM ziarnie świata
akurat istnieje naturalny mały odprysk do przypięcia (sprawdziłem: przy
bieżącym ziarnie żaden się nie trafia), więc łapią regresję niezależnie od
przyszłych zmian generatora. Wszystkie niezmienniki (`test_ciesnin.py`,
1–7 `test_scenariusz.py`) przechodzą.
