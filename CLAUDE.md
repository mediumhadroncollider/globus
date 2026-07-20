# CLAUDE.md — Hegemon

Hobbystyczna gra grand strategy (styl Paradox, epoki 800–1900), vibe-codowana
przez laika uczącego się technologii. Priorytety: immersja, mechaniki czasu
pokoju (suwaki, zarządzanie), wojna jako kryzys ekonomiczny — nie klikanie
jednostek. Autor jest biegły w web UI/typografii; Python i NumPy to dla niego
materiał do nauki — **kod ma być obficie komentowany po polsku, poziom
"dla laika, który chce zrozumieć", nie tylko "co robi linijka"**.

## Architektura (nie łamać bez dyskusji)

```
generate_world.py  → world.npz + world_meta.json   (jednorazowa budowa świata)
scenariusz_800.py  → scenariusz_800.json            (warstwa historyczna: Kent i Sussex, rok 800)
korekty.py         → (bez własnego pliku wynikowego) (rozstrzyganie korekt.json na bieżącą siatkę)
korekty.json       → (ręcznie tworzony, COMMITOWANY) (poprawki edytora świata, zakotwiczone w lon/lat)
sim.py             → klasa Swiat                    (czysta symulacja NumPy)
server.py          → FastAPI + WebSocket            (pętla ticków, rozgłaszanie, /api/korekty)
static/index.html  → klient canvas                  (Woronoj odtwarzany z punktów; ?edytor=1 = edytor świata)
test_ciesnin.py    → niezmienniki świata            (uruchamiać po każdej regeneracji)
test_scenariusz.py → niezmienniki scenariusza       (uruchamiać po zmianie scenariusz_800.py/sim.py/korekty.json)
```

## Zasady fundamentalne

1. **Geometria jest wieczna, zmienny jest tylko stan.** Jedna trwała siatka
   komórek Woronoja na wszystkie epoki. Miasto/państwo/epoka to zapis w stanie
   komórki, nie element geometrii. Żadnego remeshingu między epokami —
   "precyzja epokowa" mapy to sprawa RENDEROWANIA (styl kreski), nie danych.
2. **Structure-of-Arrays.** Stan świata to kolumny NumPy (`populacja[N]`,
   `zyznosc[N]`…), nigdy lista obiektów. Tick = operacje wektorowe na całych
   tablicach; pętla po komórkach w Pythonie to niemal zawsze błąd.
   Agregacje przez `np.bincount`.
3. **Symulacja nie zna sieci ani UI.** `sim.py` musi być uruchamialny
   samodzielnie (`python sim.py` = test balansu). Wzorzec:
   `tick()` czysta matematyka; `wykonaj_akcje()` zmienia parametry/przypisania,
   skutki liczy najbliższy tick.
4. **Jedno źródło prawdy.** Klient nie zmienia stanu sam — wysyła rozkaz,
   serwer wykonuje i rozgłasza (`{"co":"zmiana",...}`) do wszystkich.
5. **Korekty świata kotwiczymy w geografii (lon/lat), NIGDY w indeksach
   komórek** — indeksy zmieniają się z ziarnem i gęstością. Mechanizmy:
   `WYSPY_OBOWIAZKOWE` (punkty wymuszane na ląd), `CIESNINY` (odcinki zrywające
   sąsiedztwo w grafie — topologię naprawiamy w danych, nie w geometrii;
   wybrzeże zostaje nietknięte). Docelowo do wyniesienia do `swiat.toml`.
6. **Hierarchia:** komórka (substrat pomiarowy: ekonomia, geografia) → powiat →
   księstwo → królestwo. Mechaniki obciążające gracza żyją od powiatu w górę.
7. **Transfer:** duże i niezmienne — binarnie raz (`/api/dane`; uint8 na końcu
   bloku, wyrównanie do 4 bajtów!); małe i częste — JSON po WebSockecie.
8. **Determinizm:** wszystko z seedowanych RNG; ta sama konfiguracja = ten sam
   świat.
9. **Ziemie niczyje ŻYJĄ.** Komórki bez właściciela mają normalną populację,
   normalnie rosną (docelowo migrują) — tylko nie płacą danin i nie generują
   decyzji dla gracza. Martwe tło zamieniłoby scenariusz w wyspę otoczoną
   próżnią, a migracja przez granicę to kluczowa przyszła mechanika. Koszt
   zerowy: tick i tak liczy wszystkie komórki jedną operacją wektorową —
   "brak właściciela" to tylko `-1` w kolumnie własności, nie osobna ścieżka
   kodu w pętli wzrostu. Ziemia niczyja nie ma podziału wewnętrznego (jedna
   szara masa na mapie) — podział pojawi się dopiero, gdy ktoś ją zagarnie.

## Warstwa mapy — decyzje podjęte

- Wybrzeża: Natural Earth 50m (domena publiczna) → `europa_wybrzeza.json`.
  UWAGA: surowe dane `land` mają defekt topologiczny przy antypołudniku
  (parzystość pęka w paśmie szerokości Beringa) — nasz plik powstał przez
  rasteryzację scanline zakotwiczoną w Atlantyku + wektoryzację; nie
  regenerować naiwnie.
- Odwzorowanie: Albers równopowierzchniowy (uczciwe pola komórek).
- Gęstość ważona wybrzeżem (`GESTOSC_WYBRZEZA`, `PAS_WYBRZEZA`): piasek
  Lloyda TEŻ musi być ważony, inaczej relaksacja cofa zagęszczenie.
- Granice rysowane z krawędzi Woronoja (klasyfikacja: wybrzeże / królestwo /
  powiat wynika z etykiet), szerokość kreski dzielona przez zoom (stała
  szerokość ekranowa). Zerwane cieśniny klient rysuje kreską wybrzeża.
- Rendering: canvas + batching (Path2D per kolor/powiat); DOM/SVG tylko na
  warstwę UI (etykiety, ikony). Wybór canvas/SVG jest ortogonalny wobec
  modelu danych.
- Biblioteki JS vendorowane lokalnie w `static/` (żadnych CDN-ów). Błędy
  klienta mają krzyczeć z ekranu (panel diagnostyczny), nie ginąć w konsoli.
- **Koszt klatki liczy się w wielokątach, nie w wywołaniach.** `Path2D`
  obejmujący tysiące komórek (np. cała ziemia niczyja) nadaje się do
  wypalenia RAZ na osobny canvas, nigdy do rysowania (`fill`/`stroke`) co
  klatkę — nawet jeden taki `fill()` w pętli renderu (np. pod hoverem, który
  stoi nad tą warstwą niemal zawsze) potrafi zdominować koszt klatki (patrz
  brief 0003, część A).

## Scenariusze

- Jednostką polityczną SCENARIUSZA jest **ZIEMIA** (`kom_ziemia`), nie
  proceduralny powiat. Proceduralne powiaty/księstwa/królestwa zostają w
  `world.npz` nietknięte (przydadzą się do scenariuszy generycznych) —
  scenariusz historyczny ich po prostu nie używa. Analogicznie: właścicielem
  ziemi jest **PAŃSTWO**, nie proceduralne królestwo.
- `Swiat.__init__` przyjmuje opcjonalny `plik_scenariusza` (domyślnie
  `scenariusz_800.json`). Gdy plik istnieje obok — świat startuje w trybie
  scenariusza; gdy nie — zachowuje się dokładnie jak dawniej (proceduralnie).
  Oba tryby dzielą jeden `tick()` i jeden protokół binarny (`kom_ziemia`
  jedzie zawsze, w trybie proceduralnym wypełniony `-1`) — klient i server.py
  nie muszą się rozgałęziać przy parsowaniu, tylko przy interpretacji.
- Granice państw biorą się z prawdziwych granic administracyjnych (test
  punkt-w-poligonie), ziemie z prawdziwych ośrodków epoki (Thiessen wewnątrz
  granicy państwa) — wszystko kotwiczone w lon/lat, nigdy w indeksach komórek
  (zasada 5). Reszta mapy to jedna ziemia niczyja (zasada 9).
- **Przypisanie komórek do bytu politycznego z poligonu ZAWSZE kończy się
  czyszczeniem na grafie sąsiedztwa** (filtr większościowy + spójność z
  ochroną wysp) — test punkt-w-poligonie na środkach komórek sam z siebie
  produkuje eksklawy na postrzępionych wybrzeżach (patrz brief 0003,
  część B; implementacja w `scenariusz_800.py`, próg odprysku
  `PROG_ODPRYSKU`).
- Kamera startowa (`kadr_startowy`, bbox państw scenariusza w px "płótna")
  liczona jest w skrypcie scenariusza z geografii komórek (`punkty`), nie
  z osobnego przeliczenia odwzorowania — unika rozjazdu, gdyby ktoś kiedyś
  zmienił stałe Albersa w `generate_world.py`.
- `scenariusz_800.json` (jak `world.npz`/`world_meta.json`) to artefakt
  generatora — nie commitujemy, trzymać w `.gitignore`.

## Korekty ręczne i edytor

**Automat robi masę, ręka robi przypadki jednostkowe; edytor nie zmienia
świata, tylko listę korekt zakotwiczonych w lon/lat; komórka tknięta ręcznie
jest przypięta i automatyczne czyszczenie jej nie rusza.**

- Czyszczenie granic na grafie sąsiedztwa (poprzedni punkt, brief 0003)
  działa dobrze dla masy, ale przegrywa z pojedynczymi, nazwanymi przypadkami
  (mała wyspa tuż pod progiem odprysku, sierota na granicy) — to nie klasa
  problemów do złapania regułą, tylko lista miejsc do ręcznego rozstrzygnięcia.
  Stąd `korekty.json` (format i przykłady w `korekty.py`/briefie 0004) +
  tryb edytora w `static/index.html` (`?edytor=1`).
- `korekty.json` **jest commitowany** (w przeciwieństwie do `world.npz`,
  `world_meta.json`, `scenariusz_800.json`) — to ręczna praca autora, nie
  odtwarzalny artefakt generatora. Kopia zapasowa `korekty.json.bak`
  (tworzona przy każdym zapisie z edytora) już nie — ta zostaje w `.gitignore`.
- Korekty nakładają się **przy wczytywaniu świata w `sim.py`** (`Swiat.__init__`),
  nie w generatorach — restart serwera (sekundy) wystarcza, regeneracja
  świata (minuty) nie jest potrzebna. Kolejność: `world.npz` → korekty
  `lad` → korekty krawędzi (cieśniny) → scenariusz → korekty
  `panstwo`/`ziemia` → oznaczenie komórek dotkniętych jako `przypięte`.
- `scenariusz_800.py` (który buduje `scenariusz_800.json` z point-in-polygon
  + automatyczne czyszczenie granic) omija komórki przypięte — inaczej
  automat w kółko kasowałby to, co edytor w kółko by przywracał.
- Edytor to narzędzie AUTORSKIE, nie mechanika gry: podgląd w przeglądarce
  jest natychmiastowy (klient sam przelicza ląd/przynależność i przebudowuje
  diagram Woronoja), ale symulacja poznaje zmianę dopiero po restarcie
  serwera — nie ma potrzeby przeładowywać stanu na żywo w trakcie edycji.
- **Edytor dotyczy świata (geografia, przypisania), gra dotyczy stanu
  (populacja, skarbce, podatki, podboje); w trybie edytora nie ma połączenia
  z symulacją ani żadnej akcji zmieniającej stan gry** (brief 0006) — zero
  WebSocketu, zero suwaka podatku/wyboru gracza/przełącznika widoków/rankingu,
  Shift+klik nic nie robi. Widoczne od razu w karcie Sieć przeglądarki
  (brak `WebSocket /ws [accepted]` w logu serwera) — to twardy test, nie tylko
  wygląd interfejsu.
- **Lewy przycisk zawsze przesuwa mapę; narzędzie działa na kliknięcie, nie
  na przeciągnięcie** — edytor jest narzędziem do kilkunastu poprawek, nie do
  malowania (brief 0005). Próg przeciągania (ten sam mechanizm co panoramowanie
  w grze) rozstrzyga na `pointerup`: bez ruchu = klik = jedna operacja na
  jednej komórce/krawędzi; powyżej progu = przeciągnięcie = pan, żadne
  narzędzie się nie odpala. Narzędzie domyślne po wejściu do edytora to
  Nawigacja (klik nic nie robi) — rozglądanie się po mapie ma być bezpieczne
  od razu, bez wybierania niczego. `Esc` wraca do Nawigacji.

## Motywy

**Motyw to dane, renderer to implementacja — w kodzie rysującym nie ma ani
jednej stałej wizualnej; scenariusz mówi KTO jest złoty, motyw mówi JAK
wygląda złoty; mapa i interfejs dzielą paletę przez zmienne CSS.**

- Pliki: `static/motywy/motywy.css` (zmienne CSS interfejsu per klasa
  `.motyw-<nazwa>` na `<body>`) + `static/motywy/<nazwa>.json` (wygląd mapy:
  kolory, kreski, tekstura, winieta). Domyślny motyw to `wspolczesny`
  (1:1 wygląd sprzed zadania 0007); wybór przez `?motyw=`, w edytorze
  (`?edytor=1`) dodatkowo rozwijana lista przełączająca na żywo.
- Podział odpowiedzialności rozstrzygnięty raz: **scenariusz** deklaruje
  kolor bazowy bytu politycznego (tożsamość, wspólna dla wszystkich
  motywów) — **motyw** ten kolor PRZETWARZA (mnożniki nasycenia/jasności,
  RGB→HSL→RGB), nigdy nie zastępuje. Analogicznie Cantia na pergaminie i na
  sztabówce to wciąż ta sama Cantia.
- Kolor współdzielony między mapą a interfejsem (np. podświetlenie jednostki
  pod kursorem) żyje jako zmienna CSS w `motywy.css`, czytana przez canvas
  przez `getComputedStyle(document.body)` — jedno źródło prawdy, nie
  duplikat w JSON-ie i w CSS jednocześnie.
- `tekstura.rodzaj` w JSON-ie wskazuje generator PO NAZWIE (`"brak"`,
  `"papier"`, `"len"`) — same generatory (szum/kreskowanie) zostają w
  kodzie; JSON opisuje, nie wykonuje (ta sama umowa co CSS
  `background-image`). Technika kreski poza `"prosta"` (np. `"wielokrotna"`,
  `"stempel"`) jest zarezerwowana w formacie, ale nieimplementowana.
- Zmiana motywu przebudowuje wypalone warstwy (`wladcyCv`, `niczyjeCv`) —
  inaczej zostają w starych kolorach po przełączeniu.
- Wyjątki od "zero literałów" są jawnie udokumentowane w kodzie: kolor
  panelu błędu startu (musi przeżyć NIEUDANE wczytanie motywu — ale nadal
  przez zmienną CSS, nie literał), szarości wewnątrz generatorów tekstur
  (z definicji zostają w kodzie) i przezroczysty środek gradientu winiety
  (`"transparent"` to definicja winiety, nie wybór koloru).

## Pomysły zaakceptowane kierunkowo (do dyskusji przed implementacją)

- Ziarna powiatów z prawdziwych miast (Natural Earth `populated_places` +
  ręczna lista grodów średniowiecznych) → prawdziwe nazwy ziem; poligony
  Thiessena jako strefy ciążenia.
- Rzeki (`rivers_lake_centerlines`) przyciągane do krawędzi komórek: wizual,
  granice naturalne, korytarze żyzności/handlu, przeprawy.
- Populacja startowa z HYDE (historyczna gęstość zaludnienia).
- Scenariusze granic historycznych: poligon → test punkt-w-poligonie →
  tablica przypisań; komórki mogą mieć właściciela "nikt/plemiona".
- Ewolucja UI i stylu mapy z epokami (pergamin → sztabówka) na TEJ SAMEJ
  geometrii.
- Edytor świata = ten sam klient z innym zestawem narzędzi, zapis do configu.

## Plan skalowania na cały glob (ZAPISANE, NIE implementować teraz)

Mrzonka docelowa: rozgrywka 800–1900 dla całego świata (kolonie; „Aztekowie
kolonizują Europę"). Decyzja architektoniczna podjęta świadomie — spisana, by
jej nie odkrywać na nowo — ale wdrażana dopiero PO zbudowaniu kolejnych
mechanik rozgrywki. Grywalność ma pierwszeństwo nad zasięgiem mapy.

Rozdzielenie danych i rysunku (nasza główna zasada) rozwiązuje „problem
odwzorowania" u źródła:

- **Model danych = KULA, nie odwzorowanie.** Przy globie komórki generujemy
  na sferze (`scipy.spatial.SphericalVoronoi`; punkty rozsiane spiralą
  Fibonacciego = równomierne pokrycie). Pola i sąsiedztwo liczone w geometrii
  sferycznej. Wtedy zniekształcenie odwzorowania ZNIKA z symulacji (nie żyje
  ona na żadnej mapie), pola komórek są uczciwe na całym globie, a antypołudnik
  przestaje być klasą problemu (sąsiedztwo owija się dookoła). `sim.py` się
  nie zmienia — operuje na abstrakcyjnych kolumnach i grafie sąsiedztwa.
- **Render świata = Equal Earth** (Šavrič–Patterson–Jenny 2018): globalne,
  równopowierzchniowe (wizualnie zgodne z tym, co liczy symulacja),
  pseudocylindryczne, jawny wielomian. Render kontynentu = Albers, jak teraz.
  Odwzorowanie to PARAMETR WIDOKU, nie prawda świata — można przełączać.
- **Szew przez Pacyfik (przez wodę).** Trasy/jednostki przecinające szew
  rysujemy DWA RAZY (wybiega za prawą krawędź, wbiega zza lewej — „Pac-Man”).
  To wyłącznie zabieg renderujący: w danych komórki po obu stronach szwu są
  zwykłymi sąsiadami, więc przekroczenie szwu jest dla symulacji
  nieodróżnialne od każdego innego ruchu. Znikanie/pojawianie się „za szwem”
  jest więc darmową konsekwencją trzymania danych na kuli, nie osobną funkcją.
- Wersja premium kiedyś: glob 3D w WebGL (Three.js) — wtedy odwzorowania nie
  ma nawet na ekranie. Osobny, tygodniowy etap; nie na teraz.
- **Odwzorowanie jako USTAWIENIE WIDOKU per gracz** (argentyński nerd wybiera
  projekcję pieszczącą jego kraj, fiński swoją — grają w TEN SAM świat).
  Warunek konieczny: kanoniczna tożsamość komórek trzymana w lon/lat (docelowo
  na kuli), sąsiedztwo policzone RAZ i zamrożone, projekcja nałożona dopiero
  na ostatnim kroku rysowania. Wtedy niezmiennikami są: indeks komórki
  (tożsamość), jej kolumny stanu (historia, populacja, przynależność) ORAZ graf
  sąsiedztwa — zmienia się wyłącznie wielokąt komórki w widoku 2D.
  UWAGA: w obecnym płaskim potoku to NIE działa samo — tożsamość jest zapisana
  we współrzędnych Albersa, więc zmiana projekcji przeliczyłaby geometrię
  (a przy re-generacji i sąsiedztwo). Włączenie tej własności = jedna
  refaktoryzacja (tożsamość → lon/lat, sąsiedztwo policzone raz), która i tak
  wchodzi naturalnie przy przejściu na model sferyczny. Zaplanowane, nie na teraz.

Pierwszy bezpieczny krok (przy przenosinach do repo): plik-zabawka ze
`SphericalVoronoi` — wyłącznie po to, by zobaczyć, że poziom „symulacja na
kuli" jest w zasięgu ręki, i sprawdzić, że dwie komórki po obu stronach szwu
są w grafie sąsiedztwa sąsiadami. Potem wrócić do mechanik.

## Rytuały

- Po każdej zmianie generatora: `python generate_world.py && python test_ciesnin.py`.
- Po każdej zmianie scenariusza: `python scenariusz_800.py && python test_scenariusz.py`
  (wymaga świeżo wygenerowanego `world.npz`).
- Po każdej zmianie `korekty.json` (ręcznie albo przez edytor + Zapisz):
  restart serwera pokazuje efekt od razu w grze; jeśli korekta dotyczy
  przynależności/granic scenariusza, odpal też `python scenariusz_800.py &&
  python test_scenariusz.py`, żeby przeliczyć czyszczenie granic z nowym
  zestawem przypiętych komórek.
- Nowe niezmienniki świata dopisywać do `test_ciesnin.py`, niezmienniki
  scenariusza do `test_scenariusz.py` (lub siostrzanych plików testowych) —
  mapa/scenariusz, który nie przechodzi testów, nie wchodzi do gry.
- Nowe mechaniki najpierw jako czysta funkcja w `sim.py` + mini-test balansu,
  dopiero potem podpięcie do serwera i UI.
- `world.npz` / `world_meta.json` / `scenariusz_800.json` nie commitujemy
  (artefakty generatora) — trzymać w `.gitignore`.
