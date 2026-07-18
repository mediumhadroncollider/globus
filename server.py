# -*- coding: utf-8 -*-
"""
server.py — most między symulacją a przeglądarką.

Uruchomienie:   uvicorn server:app --reload
Potem otwórz:   http://127.0.0.1:8000

Ten plik robi tylko trzy rzeczy (i celowo nic więcej):
  1. Serwuje pliki klienta (static/index.html).
  2. Wystawia świat do pobrania: małe dane jako JSON, duże jako czyste bajty.
  3. Kręci pętlę ticków i rozgłasza wyniki wszystkim podłączonym po WebSockecie.

WebSocket vs zwykłe zapytania HTTP — obrazowo: HTTP to wysyłanie listów
(pytanie-odpowiedź i koniec), WebSocket to rozmowa telefoniczna — połączenie
wisi otwarte i OBIE strony mogą się odzywać, kiedy chcą. Do gry, gdzie serwer
co sekundę ma coś do powiedzenia, telefon jest naturalny.
"""

import asyncio
import json

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from sim import Swiat

# --- na starcie serwera: załaduj świat; jeśli go nie ma — wygeneruj ---------
import pathlib
if not pathlib.Path("world.npz").exists():
    print("Brak world.npz — generuję świat (to chwilę potrwa, tylko raz)…")
    import generate_world  # sam import uruchamia skrypt

swiat = Swiat()
TICK_CO_ILE_SEKUND = 1.0

app = FastAPI()

# ----------------------------------------------------------------------------
# DANE ŚWIATA DLA KLIENTA
# ----------------------------------------------------------------------------
@app.get("/api/meta")
def meta():
    """Małe dane opisowe — zwykły JSON."""
    m = json.load(open("world_meta.json"))
    m["komorka_pow"] = None  # duże tablice NIE idą JSON-em (patrz niżej)
    m["kom_ziemia"] = None   # to samo — kom_ziemia jedzie w /api/dane, nie tutaj
    m["podatki"] = swiat.podatek.tolist()
    m["tryb_scenariusza"] = swiat.tryb_scenariusza

    if swiat.tryb_scenariusza:
        # Warstwa scenariusza: ZIEMIE i PAŃSTWA zamiast powiatów/królestw.
        m["panstwa"] = swiat.panstwa
        m["ziemie"] = [
            {
                "id": z["id"],
                "nazwa_robocza": z["nazwa_robocza"],
                "nazwa_gry": z["nazwa_gry"],
                # UWAGA: indeks BIEŻĄCEGO właściciela (ziemia_panstwo — żywy,
                # zmieniany podbojem), NIE statyczny klucz z JSON-u scenariusza
                # (ten zawsze pokazywałby stan sprzed pierwszego podboju —
                # klient łączący się później musi widzieć prawdę na TERAZ).
                "panstwo": int(swiat.ziemia_panstwo[i]),
            }
            for i, z in enumerate(swiat.ziemie)
        ]
        m["panstwo_gracz"] = swiat.panstwo_gracz
        m["kadr_startowy"] = swiat.kadr_startowy
        m["pow_krol"] = None
    else:
        m["pow_krol"] = swiat.pow_krol.tolist()

    return m

@app.get("/api/dane")
def dane():
    """DUŻE tablice — jako surowe bajty, sklejone jedna za drugą.
    JSON zamieniłby 60 000 liczb w megabajty tekstu do żmudnego parsowania;
    binarnie przeglądarka dostaje je 'gotowe do użycia': opakuje bufor
    w Float32Array/Int32Array bez żadnego kopiowania. Kolejność i typy
    muszą się zgadzać po obu stronach — to nasz mini-protokół:
        punkty     float32 × N×2   (bajty 0    … 8N)
        kom_pow    int32   × N     (8N   … 12N)
        kom_ziemia int32   × N     (12N  … 16N)
        zyznosc    float32 × N     (16N  … 20N)
        lad        uint8   × N     (20N  … 21N)
    Uwaga-pułapka: tablica uint8 stoi CELOWO na końcu. Typy 4-bajtowe
    (Int32Array, Float32Array) można nałożyć na bufor tylko pod adresem
    podzielnym przez 4 — gdyby bajty lądu stały w środku, wszystko za nimi
    byłoby przesunięte o N bajtów i przeglądarka rzuciłaby błędem wyrównania.
    kom_ziemia jest ZAWSZE w tym bloku (tryb proceduralny wysyła samo -1) —
    protokół binarny jednakowy w obu trybach, żeby klient nie musiał się
    rozgałęziać przy parsowaniu.
    """
    czesci = [
        swiat.punkty.astype("<f4").tobytes(),
        swiat.komorka_pow.astype("<i4").tobytes(),
        swiat.kom_ziemia.astype("<i4").tobytes(),
        swiat.zyznosc.astype("<f4").tobytes(),
        swiat.lad.astype(np.uint8).tobytes(),
    ]
    return Response(content=b"".join(czesci), media_type="application/octet-stream")

# ----------------------------------------------------------------------------
# WEBSOCKET: rozgłaszanie ticków i przyjmowanie rozkazów
# ----------------------------------------------------------------------------
polaczeni: set[WebSocket] = set()

async def rozglos(wiadomosc: dict):
    """Wyślij JSON do wszystkich podłączonych przeglądarek."""
    tekst = json.dumps(wiadomosc)
    martwi = []
    for ws in polaczeni:
        try:
            await ws.send_text(tekst)
        except Exception:
            martwi.append(ws)
    for ws in martwi:
        polaczeni.discard(ws)

@app.websocket("/ws")
async def gniazdo(ws: WebSocket):
    await ws.accept()
    polaczeni.add(ws)
    try:
        while True:
            # czekamy na rozkazy gracza; skutki policzy najbliższy tick,
            # ale o zmianach politycznych/parametrów informujemy od razu
            akcja = json.loads(await ws.receive_text())
            zmiana = swiat.wykonaj_akcje(akcja)
            if zmiana:
                await rozglos({"co": "zmiana", **zmiana})
    except WebSocketDisconnect:
        polaczeni.discard(ws)

# ----------------------------------------------------------------------------
# PĘTLA GRY — serce serwera
# ----------------------------------------------------------------------------
@app.on_event("startup")
async def start_petli():
    async def petla():
        while True:
            await asyncio.sleep(TICK_CO_ILE_SEKUND)
            wynik = swiat.tick()          # cała ekonomia kontynentu: ~1 ms
            # tablice per ziemia/powiat są małe (tysiące liczb) — JSON
            # wystarczy; zaokrąglamy, żeby nie słać 17 cyfr po przecinku
            wiadomosc = {
                "co": "tick",
                "tick": wynik["tick"],
                "skarbiec": np.round(wynik["skarbiec"], 1).tolist(),
                "podatki": np.round(swiat.podatek, 3).tolist(),
            }
            if swiat.tryb_scenariusza:
                wiadomosc["ziemia_pop"] = np.round(wynik["ziemia_pop"], 1).tolist()
                wiadomosc["ziemia_doch"] = np.round(wynik["ziemia_doch"], 2).tolist()
                wiadomosc["niczyje_pop"] = round(wynik["niczyje_pop"], 1)
            else:
                wiadomosc["pow_pop"] = np.round(wynik["pow_pop"], 1).tolist()
                wiadomosc["pow_doch"] = np.round(wynik["pow_doch"], 2).tolist()
                wiadomosc["krol_doch"] = np.round(wynik["krol_doch"], 1).tolist()
            await rozglos(wiadomosc)
    asyncio.create_task(petla())

# ----------------------------------------------------------------------------
# KLIENT
# ----------------------------------------------------------------------------
@app.get("/")
def strona_glowna():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
