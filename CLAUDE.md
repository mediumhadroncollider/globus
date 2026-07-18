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
sim.py             → klasa Swiat                    (czysta symulacja NumPy)
server.py          → FastAPI + WebSocket            (pętla ticków, rozgłaszanie)
static/index.html  → klient canvas                  (Woronoj odtwarzany z punktów)
test_ciesnin.py    → niezmienniki świata            (uruchamiać po każdej regeneracji)
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
- Nowe niezmienniki świata dopisywać do `test_ciesnin.py` (lub siostrzanych
  plików testowych) — mapa, która nie przechodzi testów, nie wchodzi do gry.
- Nowe mechaniki najpierw jako czysta funkcja w `sim.py` + mini-test balansu,
  dopiero potem podpięcie do serwera i UI.
- `world.npz` / `world_meta.json` nie commitujemy (artefakty generatora) —
  trzymać w `.gitignore`.
