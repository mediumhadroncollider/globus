# Hegemon — szkielet gry grand strategy (Python + NumPy + przeglądarka)

Oddychający kontynent: serwer w Pythonie liczy co sekundę ekonomię
kilkudziesięciu tysięcy komórek naraz (NumPy), a przeglądarka pokazuje żywą
mapę i wysyła rozkazy (suwak podatkowy, podboje) po WebSockecie.

## Uruchomienie

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --reload
```

Otwórz **http://127.0.0.1:8000**. Przy pierwszym starcie serwer sam wygeneruje
świat (`world.npz` + `world_meta.json`) — chwilę to trwa, tylko raz.

Co umie klient: trzy widoki mapy (władcy / populacja / dochód — dwa ostatnie
żyją co tick), hover z danymi powiatu, suwak podatku wybranego królestwa,
**Shift+klik** = podbój powiatu, ranking skarbców na żywo.

## Architektura (i dlaczego taka)

```
generate_world.py   → world.npz          (jednorazowo: geografia + hierarchia)
sim.py              → klasa Swiat        (CZYSTA symulacja: stan = kolumny NumPy,
                                          tick() = matematyka, zero sieci)
server.py           → FastAPI            (pętla ticków + WebSocket + wydawanie danych)
static/index.html   → klient             (canvas + Woronoj odtworzony z punktów)
```

Trzy zasady, na których wszystko stoi:

1. **Stan to kolumny, nie obiekty** (Structure-of-Arrays). "Policz dochód
   wszystkich komórek" to jedna linijka NumPy wykonywana w C, nie pętla.
2. **Symulacja nie zna interfejsu.** `sim.py` można testować bez serwera
   (`python sim.py` — gotowy mini-test balansu) albo z notebooka: odpal
   1000 ticków, wczytaj wyniki do pandas, narysuj wykresy.
3. **Jedno źródło prawdy.** Klient niczego nie zmienia sam — wysyła rozkaz,
   serwer go wykonuje i rozgłasza zmianę wszystkim. Zero rozjazdów stanu.

Transfer danych: wielkie i niezmienne (punkty, przypisania) — binarnie, raz,
przez `/api/dane` (przeglądarka nakłada `Float32Array` wprost na bajty);
małe i częste (agregaty per powiat co tick) — JSON-em po WebSockecie.

## Ręczne korekty świata (sekcja KOREKTY w generate_world.py)

Świat jest proceduralny, ale masz nad nim autorską kontrolę — dwie listy,
obie zapisane WSPÓŁRZĘDNYMI geograficznymi (nie indeksami komórek, bo te
zmieniają się z każdym ziarnem):

- `WYSPY_OBOWIAZKOWE` — punkty lon/lat, które muszą być lądem (Malta, Muhu…);
  najbliższa komórka zostaje przymusowo zlądowana.
- `CIESNINY` — odcinki lon/lat poprowadzone wodą (Mesyna, Bosfor, Öresund…);
  każde sąsiedztwo komórek przecinające taki odcinek jest ZRYWANE w grafie.
  Geometria i wybrzeże zostają nietknięte — naprawiamy topologię, nie rysunek.
  Rozrost powiatów/księstw tamtędy nie przejdzie, a klient rysuje zerwane
  krawędzie kreską wybrzeża. Kiedy dodasz armie: cieśnina to naturalne
  miejsce na mechanikę "przeprawy".

Wpisy nadmiarowe nie szkodzą: jeśli przy danym ziarnie cieśninę i tak
wypełnia komórka morska, odcinek po prostu nic nie zetnie — to darmowe
ubezpieczenie na inne gęstości. Weryfikację najlepiej robić testem BFS
("z Palermo nie da się dojść lądem do Reggio") — wzór masz w historii
naszej rozmowy; warto go wkleić do stałego zestawu testów projektu.

## Edytor świata w przeglądarce (`?edytor=1`)

Adres: **http://127.0.0.1:8000/?edytor=1** (w grze prowadzi do niego
dyskretny link „Edytor" w prawym rogu paska; z edytora „Do gry" wraca na `/`).

Edytor dotyczy **świata** (geografia, przynależność ziem, cieśniny, rzeki),
nigdy **stanu** (populacja, skarbce, podatki, podboje, ticki) — te dwie
kategorie są celowo rozdzielone:

- w edytorze nie ma suwaka podatku, wyboru „Grasz jako", przełącznika widoków
  ani panelu rankingu — edytor zawsze pokazuje widok polityczny;
- karta w trybie edytora **w ogóle nie łączy się z WebSocketem** — bez
  ticków, bez rankingu, bez map ciepła nie ma po co; Shift+klik (podbój w
  grze) w edytorze nic nie robi.

Narzędzia (pasek u góry): **Nawigacja** (domyślne po wejściu — kliknięcia
niczego nie zmieniają, mapa jest do oglądania), **Ląd/woda**,
**Przynależność** (+ wybór państwa/ziemi docelowej; Alt+klik = do niczyich),
**Cieśnina**, **Rzeka**, **Gumka** (usuwa korektę wskazanej komórki/krawędzi).

Sterowanie: **lewy przycisk myszy** obsługuje jedno i drugie — kliknięcie
(bez ruchu) stosuje aktywne narzędzie do komórki/krawędzi pod kursorem,
przeciągnięcie panoramuje mapę (żadne narzędzie się nie odpala). Jedno
kliknięcie = jedna komórka — nie ma malowania przeciągnięciem, bo korekt są
i będą dosłownie dziesiątki, nie tysiące. **Esc** wraca do Nawigacji.
**Ctrl+Z** cofa ostatnią operację. Panel informacyjny pod kursorem pokazuje
lon/lat, ląd/wodę, jednostkę i właściciela oraz czy komórka ma już korektę
(i jaką) — nigdy populację ani dochód, bo to nie należy do świata.

Przycisk **Zapisz** wysyła zebrane korekty do `POST /api/korekty` (serwer
robi kopię `korekty.json.bak` przed nadpisaniem). Zmiana widoczna w grze
dopiero po restarcie serwera — edytor nie przeładowuje stanu symulacji na
żywo.

## Pomysły na następne kroki (rosnąca trudność)

- **Suwaki**: drugi parametr per królestwo (np. nakłady na infrastrukturę
  podnoszące żyzność efektywną) — przećwiczysz pełną pętlę: sim → server → UI.
- **Zapis gry**: `np.savez("save.npz", populacja=..., pow_krol=...)` +
  przycisk w kliencie. Zauważ, że zapis to dosłownie zrzut kolumn.
- **Aktywny podział powiatu**: akcja, która wybiera połowę komórek powiatu
  (np. po stronie prostej przez centroid) i nadaje im nowy indeks — geometria
  nie drgnie, granice przerysują się same.
- **Wyniszczenie wojenne**: pole `dewastacja` per komórka, rosnące w podbitych
  powiatach i wygasające w pokoju — wojna tą samą maszynerią co pokój.
- **AI**: co N ticków każde królestwo bez gracza wybiera akcję prostą
  heurystyką (np. podbija najbogatszy sąsiedni powiat słabszego).

## Drobne pułapki, które już obeszliśmy (warto wiedzieć)

- Tablice `uint8` w binarnym pakiecie idą **na końcu** — typy 4-bajtowe
  wymagają w przeglądarce adresu podzielnego przez 4.
- Dane wybrzeży (`europa_wybrzeza.json`) powstały z Natural Earth 50m po
  naprawie defektu topologicznego przy antypołudniku — nie regeneruj ich
  naiwnie z surowych danych.
- Biblioteka d3-delaunay leży lokalnie w `static/` (vendoring) — pierwsza
  wersja ładowała ją z błędnego adresu CDN i klient padał po cichu na 404.
  Lokalny plik = zero zależności od sieci i wersja przypięta na zawsze.
- Klient odtwarza Woronoja z samych punktów (diagram jest jednoznaczny),
  więc serwer nie musi przesyłać żadnych wielokątów.
