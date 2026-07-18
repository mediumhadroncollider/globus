# -*- coding: utf-8 -*-
"""
scenariusz_800.py — pierwszy scenariusz historyczny: Kent i Sussex, rok 800.

Uruchamiasz PO wygenerowaniu świata:  python scenariusz_800.py
Wynik: scenariusz_800.json  (przypisania komórek + opisy bytów politycznych)

IDEA (i cała lekcja tego pliku):
Świat jest proceduralny, ale scenariusz jest AUTORSKI — i buduje się go
z otwartych danych, nie z ręcznego klikania:

  1. GRANICE państewek biorą się z prawdziwych granic administracyjnych
     (Natural Earth admin-1: Kent+Medway, East+West Sussex+Brighton, które
     z grubsza pokrywają się z anglosaskimi królestwami z VIII/IX w.).
     Test punkt-w-poligonie mówi, która komórka należy do którego państwa.

  2. ZIEMIE (nasze „powiaty scenariuszowe") wyrastają z prawdziwych ośrodków
     administracyjnych epoki — Canterbury, Rochester, Dover, Chichester… —
     bo tak właśnie powstawały regiony historyczne: ziemia to okolica ciążąca
     do grodu (poligony Thiessena / teoria ośrodków centralnych).

  3. Reszta mapy to JEDEN wielki obszar niczyj. Brak właściciela to nie błąd,
     tylko uczciwy stan Europy roku 800 z perspektywy tej rozgrywki.

Wszystko kotwiczymy w lon/lat — nigdy w indeksach komórek (zasada 5 z CLAUDE.md).
"""

import json
import numpy as np
from matplotlib.path import Path

NIEZIEMIA = -1          # brak właściciela / brak ziemi

# ----------------------------------------------------------------------------
# OŚRODKI: prawdziwe grody, każdy zostanie stolicą jednej ziemi
# ----------------------------------------------------------------------------
# Nazwy potrójne — dokładnie jak w prototypie Kent/Sussex i zgodnie z naszą
# zasadą „tożsamość oddzielona od prezentacji":
#   nazwa_robocza — dla nas i dla narzędzi, nigdy się nie zmienia
#   nazwa_gry     — to, co widzi gracz W TEJ EPOCE (tu: łacina)
# Dzięki temu ta sama ziemia może w 1500 nazywać się inaczej bez zmiany danych.
OSRODKI = {
    "kent": [
        # (nazwa_robocza, nazwa_gry, lon, lat)
        ("Canterbury", "Dorovernia",        1.078, 51.279),
        ("Rochester",  "Hrofesceaster",     0.503, 51.389),
        ("Dover",      "Portus Dubris",     1.313, 51.128),
        ("Sandwich",   "Sandwicum",         1.339, 51.272),
        ("Maidstone",  "Vallis Medewege",   0.522, 51.272),
        ("Faversham",  "Fefresham",         0.894, 51.313),
        ("Ashford",    "Essetesford",       0.874, 51.146),
        ("Tonbridge",  "Tunbrycg",          0.276, 51.196),
    ],
    "sussex": [
        ("Chichester", "Cicestria",        -0.779, 50.836),
        ("Steyning",   "Stæningum",        -0.325, 50.888),
        ("Lewes",      "Leuisum",           0.010, 50.874),
        ("Pevensey",   "Anderitum",         0.334, 50.819),
        ("Hastings",   "Hæstingas",         0.573, 50.855),
        ("Midhurst",   "Middeherst",       -0.740, 50.986),
        ("Horsham",    "Horsham",          -0.327, 51.062),
    ],
}

PANSTWA = {
    "kent": {
        "nazwa_robocza": "Kent",
        "nazwa_gry": "Cantia",
        "nazwa_paska": "Cantium",
        "wladca": {"imie": "Cuthred", "tytul": "król Kentu"},
        "gracz": True,
        "zwierzchnik": "mercia",
        "stolica": "Canterbury",
        "kolor": "#c9a227",
    },
    "sussex": {
        "nazwa_robocza": "Sussex",
        "nazwa_gry": "Australes Saxones",
        "nazwa_paska": "Australes Saxones",
        "wladca": {"imie": "Ælfwald", "tytul": "władca Sussexu", "uwaga": "postać umowna"},
        "gracz": False,
        "zwierzchnik": "mercia",
        "stolica": "Chichester",
        # cechy aktora SI — te same opcje co gracz, inne wagi (patrz prototyp)
        "aktor": {"troska_o_poddanych": 0.62, "ostroznosc_fiskalna": 0.68,
                  "szacunek_dla_elit": 0.34},
        "kolor": "#7d9a6a",
    },
}


def main():
    d = np.load("world.npz")
    meta = json.load(open("world_meta.json"))
    lonlat = d["lonlat"]        # (N,2) — kanoniczna tożsamość geograficzna komórki
    lad = d["lad"]
    n = len(lad)

    granice = json.load(open("kent_sussex.json"))

    # --- 1. KTÓRE KOMÓRKI NALEŻĄ DO KTÓREGO PAŃSTWA ------------------------
    # Test punkt-w-poligonie dla WSZYSTKICH komórek naraz (matplotlib.path).
    # Granice to MultiPolygon (wyspy, ujścia), więc sumujemy po składowych.
    kom_panstwo = np.full(n, NIEZIEMIA, dtype=np.int32)
    id_panstwa = {klucz: i for i, klucz in enumerate(PANSTWA)}

    for klucz, geom in granice.items():
        if klucz not in id_panstwa:
            continue
        maska = np.zeros(n, dtype=bool)
        czesci = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for wielokat in czesci:
            maska |= Path(wielokat[0]).contains_points(lonlat)   # pierścień zewnętrzny
        maska &= lad                                             # tylko ląd
        kom_panstwo[maska] = id_panstwa[klucz]
        print(f"{PANSTWA[klucz]['nazwa_robocza']:<8} -> {int(maska.sum()):4d} komórek")

    # --- 2. ZIEMIE: każda komórka trafia do najbliższego ośrodka SWOJEGO państwa
    # (poligony Thiessena wewnątrz granicy państwa = strefy ciążenia do grodów)
    kom_ziemia = np.full(n, NIEZIEMIA, dtype=np.int32)
    ziemie = []
    for klucz, lista in OSRODKI.items():
        pid = id_panstwa[klucz]
        moje = np.flatnonzero(kom_panstwo == pid)
        if not len(moje):
            continue
        srodki = np.array([[lo, la] for _, _, lo, la in lista])
        # odległości w stopniach skorygowane o cos(lat) — na tym obszarze
        # to w zupełności wystarczy (kilkadziesiąt km)
        skala = np.cos(np.radians(srodki[:, 1].mean()))
        dx = (lonlat[moje, 0][:, None] - srodki[None, :, 0]) * skala
        dy = (lonlat[moje, 1][:, None] - srodki[None, :, 1])
        najblizszy = np.argmin(dx ** 2 + dy ** 2, axis=1)

        for i, (nazwa_rob, nazwa_gry, lo, la) in enumerate(lista):
            idx = len(ziemie)
            kom_ziemia[moje[najblizszy == i]] = idx
            ziemie.append({
                "id": f"ziemia_{idx:04d}_{nazwa_rob.lower()}",
                "nazwa_robocza": nazwa_rob,
                "nazwa_gry": nazwa_gry,
                "panstwo": klucz,
                "osrodek": [lo, la],
                "komorek": int((kom_ziemia == idx).sum()),
            })

    # --- 3. RAPORT + ZAPIS --------------------------------------------------
    print()
    for z in ziemie:
        znak = "  " if z["komorek"] else "! "   # ! = ziemia bez komórek (za mało siatki)
        print(f"{znak}{z['nazwa_gry']:<16} ({z['nazwa_robocza']:<10}) "
              f"{z['panstwo']:<7} {z['komorek']:3d} komórek")

    puste = [z for z in ziemie if z["komorek"] == 0]
    if puste:
        print(f"\nUWAGA: {len(puste)} ziem bez ani jednej komórki — siatka jest w tym "
              f"miejscu za rzadka. Zwiększ mnożnik w OBSZARY_SZCZEGOLOWE "
              f"(generate_world.py) albo połącz te ośrodki.")

    ma_wlasciciela = int((kom_panstwo != NIEZIEMIA).sum())
    print(f"\nRazem: {ma_wlasciciela} komórek w państwach, "
          f"{int(lad.sum()) - ma_wlasciciela} komórek lądu niczyjego.")

    json.dump({
        "rok": 800,
        "panstwa": PANSTWA,
        "ziemie": ziemie,
        "kom_panstwo": kom_panstwo.tolist(),
        "kom_ziemia": kom_ziemia.tolist(),
    }, open("scenariusz_800.json", "w"), ensure_ascii=False)
    print("Zapisano scenariusz_800.json")


if __name__ == "__main__":
    main()
