# Hegemon

Przeglądarkowa gra strategiczna (styl Paradox: Europa Universalis / Victoria),
osadzona w okresie 800–1900. Zamiast klikania pojedynczych jednostek wojskowych —
zarządzanie państwem w czasie pokoju (podatki, gospodarka), gdzie wojna jest
kryzysem ekonomicznym, nie osobną minigrą.

Wyróżnik projektu: świat podzielony jest na bardzo dużą liczbę drobnych
jednostek geograficznych (komórek Woronoja, dziesiątki tysięcy naraz), a nie
kilkadziesiąt uproszczonych prowincji — to ta sama siatka służy i mapie, i
symulacji ekonomii pod spodem.

## Co dziś działa

- **Generator świata** — buduje mapę (wybrzeża, podział na komórki, hierarchię
  powiat/księstwo/królestwo) na podstawie prawdziwej geografii.
- **Edytor świata w przeglądarce** — ręczne poprawki mapy (ląd/woda,
  przynależność, cieśniny, rzeki) bez ingerencji w kod czy dane rozgrywki.
- **Prymitywna symulacja ekonomiczna** — serwer liczy co tick (w NumPy, dla
  całej mapy naraz) plony i wpływy podatkowe każdej jednostki; klient
  pokazuje to na żywo na mapie i pozwala ustawić poziom podatku.

Projekt jest we wczesnej, hobbystycznej fazie rozwoju.

## Uruchomienie lokalne

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --reload
```

Otwórz **http://127.0.0.1:8000**. Przy pierwszym starcie serwer sam
wygeneruje świat — zajmuje to chwilę, tylko przy pierwszym uruchomieniu.

Edytor świata: **http://127.0.0.1:8000/?edytor=1**.

## Struktura projektu

```
generate_world.py   → generator mapy (geografia + hierarchia jednostek)
scenariusz_800.py    → scenariusz historyczny (rok 800)
sim.py               → symulacja (NumPy, niezależna od sieci i UI)
server.py            → serwer FastAPI + WebSocket
static/index.html    → klient (mapa na canvasie)
```

Szczegóły architektury i zasady rozwoju projektu — patrz `CLAUDE.md`.
