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
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

import korekty as korekty_mod

NIEZIEMIA = -1          # brak właściciela / brak ziemi

# Próg odprysku (test spójności, część B2 briefu 0003): spójna składowa
# komórek państwa mniejsza niż tyle komórek wraca do ziemi niczyjej (uznajemy
# ją za szum na granicy, nie za prawdziwą wyspę). Składowe >= progu zostają
# i lądują w logu jako wyspy (np. Sheppey, Thanet, Wight) — pokrętło do
# regulacji, nie magiczna liczba w środku kodu.
PROG_ODPRYSKU = 4

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


def _filtr_wiekszosciowy(kom_panstwo, lad, indptr, indices, n_panstw, przypiete=None):
    """Każda komórka LĄDOWA przyjmuje przynależność większości spośród: siebie
    i swoich lądowych sąsiadów (NIEZIEMIA jest pełnoprawnym kandydatem).
    Remis -> bez zmiany. Liczone wektorowo przez bincount na parach z CSR,
    bez pętli po komórkach (patrz CLAUDE.md, zasada 2).

    `przypiete` (edytor świata, brief 0004): komórki dotknięte ręcznie w
    korekty.json NIE głosują wynikiem — zostają dokładnie tym, czym są,
    inaczej automat w kółko kasowałby ręczną poprawkę."""
    n = len(lad)
    K = n_panstw + 1   # przesunięcie o +1: bincount nie lubi indeksów ujemnych
    ii = np.repeat(np.arange(n), np.diff(indptr))
    jj = indices
    ll = lad[ii] & lad[jj]
    ii, jj = ii[ll], jj[ll]

    lad_idx = np.flatnonzero(lad)
    # głosy: każdy lądowy sąsiad + jeden głos własny (self-loop)
    cel_i = np.concatenate([ii, lad_idx])
    cel_v = np.concatenate([kom_panstwo[jj] + 1, kom_panstwo[lad_idx] + 1])
    flat = cel_i.astype(np.int64) * K + cel_v
    liczba = np.bincount(flat, minlength=n * K).reshape(n, K)

    maks = liczba.max(axis=1)
    zwyciezca = liczba.argmax(axis=1) - 1
    remis = (liczba == maks[:, None]).sum(axis=1) > 1

    wynik = kom_panstwo.copy()
    wynik[lad_idx] = np.where(remis[lad_idx], kom_panstwo[lad_idx], zwyciezca[lad_idx])
    if przypiete is not None:
        wynik[przypiete] = kom_panstwo[przypiete]
    return wynik


def _graf_ladowy_bez_ciesnin(lad, indptr, indices, zerwane_a, zerwane_b):
    """Krawędzie sąsiedztwa ląd-ląd, z pominięciem zerwanych cieśnin — wyspa
    oddzielona cieśniną nie jest sąsiadem lądu (patrz CLAUDE.md, zasada 5)."""
    n = len(lad)
    ii = np.repeat(np.arange(n), np.diff(indptr))
    jj = indices
    ok = lad[ii] & lad[jj]
    ii, jj = ii[ok], jj[ok]
    zerw = set(zip(zerwane_a.tolist(), zerwane_b.tolist()))
    zerw |= set(zip(zerwane_b.tolist(), zerwane_a.tolist()))
    zywe = np.array([(a, b) not in zerw for a, b in zip(ii.tolist(), jj.tolist())])
    return ii[zywe], jj[zywe]


def _wyczysc_spojnosc(kom_panstwo, ii_graf, jj_graf, n, panstwa_lista, prog_odprysku,
                       przypiete=None):
    """Dla każdego państwa: spójne składowe jego komórek na grafie sąsiedztwa
    (bez zerwanych cieśnin). Największa składowa = korpus, zostaje. Pozostałe
    składowe < prog_odprysku wracają do ziemi niczyjej (szum "sól i pieprz"
    na granicy); >= prog_odprysku to prawdziwe wyspy — zostają, trafiają do
    logu.

    `przypiete` (edytor świata, brief 0004): składowa, w której siedzi choć
    jedna komórka dotknięta ręcznie w korekty.json, NIGDY nie wraca do ziemi
    niczyjej — to dokładnie przypadek Sheppey: 2-3 komórki, które bez tego
    automat kasowałby w kółko, ilekroć ktoś by go uruchomił ponownie."""
    if przypiete is None:
        przypiete = np.zeros(n, dtype=bool)
    kom_panstwo = kom_panstwo.copy()
    usuniete_total = 0
    wyspy = []
    for pid, nazwa in enumerate(panstwa_lista):
        idx = np.flatnonzero(kom_panstwo == pid)
        if len(idx) == 0:
            continue
        maska_e = (kom_panstwo[ii_graf] == pid) & (kom_panstwo[jj_graf] == pid)
        a, b = ii_graf[maska_e], jj_graf[maska_e]
        lokalny = -np.ones(n, dtype=np.int64)
        lokalny[idx] = np.arange(len(idx))
        mat = csr_matrix(
            (np.ones(len(a)), (lokalny[a], lokalny[b])),
            shape=(len(idx), len(idx)),
        )
        n_skladowych, etykiety = connected_components(mat, directed=False)
        rozmiary = np.bincount(etykiety, minlength=n_skladowych)
        najwieksza = int(rozmiary.argmax())
        for sk in range(n_skladowych):
            if sk == najwieksza:
                continue
            rozmiar = int(rozmiary[sk])
            komorki_sk = idx[etykiety == sk]
            if przypiete[komorki_sk].any():
                wyspy.append((nazwa, rozmiar))
            elif rozmiar < prog_odprysku:
                kom_panstwo[komorki_sk] = NIEZIEMIA
                usuniete_total += rozmiar
            else:
                wyspy.append((nazwa, rozmiar))
    return kom_panstwo, usuniete_total, wyspy


def main():
    d = np.load("world.npz")
    meta = json.load(open("world_meta.json"))
    lonlat = d["lonlat"]        # (N,2) — kanoniczna tożsamość geograficzna komórki
    punkty = d["punkty"]        # (N,2) — te same komórki, ale w pikselach "płótna"
    lad = d["lad"]
    indptr, indices = d["indptr"], d["indices"]
    zerwane_a, zerwane_b = d["zerwane_a"], d["zerwane_b"]
    n = len(lad)

    granice = json.load(open("kent_sussex.json"))

    # Komórki dotknięte ręcznie w edytorze (korekty.json, jeśli istnieje) —
    # automatyczne czyszczenie granic niżej ma je omijać (brief 0004:
    # "automat robi masę, ręka robi przypadki jednostkowe").
    korekty = korekty_mod.wczytaj()
    przypiete = np.zeros(n, dtype=bool)
    for idx in korekty_mod.komorki_przypiete(korekty, lonlat):
        przypiete[idx] = True
    if przypiete.any():
        print(f"Korekty ręczne: {int(przypiete.sum())} komórek przypiętych "
              f"(czyszczenie granic je pominie)")

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

    # --- 1b. CZYSZCZENIE NA GRAFIE SĄSIEDZTWA -------------------------------
    # Punkt-w-poligonie testuje wyłącznie ŚRODEK komórki: przy komórkach rzędu
    # 10 km i postrzępionym wybrzeżu środek nadwybrzeżnej komórki potrafi
    # wpaść do poligonu, choć sama komórka jest odcięta od korpusu państwa
    # wodą albo pasem ziemi niczyjej (eksklawa) — i odwrotnie, pojedyncza
    # komórka niczyja potrafi zostać "dziurą" w środku państwa. Oba efekty to
    # szum "sól i pieprz", nie decyzja polityczna, więc sprzątamy go PRZED
    # podziałem na ziemie (żeby ziemie wyrastały z już czystej maski) — patrz
    # brief 0003, część B.
    panstwa_lista = list(PANSTWA.keys())
    n_panstw = len(panstwa_lista)

    print("\nFiltr większościowy (2 przebiegi):")
    kom_panstwo_przed = kom_panstwo.copy()
    for _ in range(2):
        kom_panstwo = _filtr_wiekszosciowy(
            kom_panstwo, lad, indptr, indices, n_panstw, przypiete=przypiete)
    zmienionych = int((kom_panstwo != kom_panstwo_przed).sum())
    print(f"  zmienił przynależność {zmienionych} komórek")

    print("\nTest spójności (ochrona wysp, próg odprysku = "
          f"{PROG_ODPRYSKU} komórek):")
    ii_graf, jj_graf = _graf_ladowy_bez_ciesnin(lad, indptr, indices, zerwane_a, zerwane_b)
    kom_panstwo, usuniete, wyspy = _wyczysc_spojnosc(
        kom_panstwo, ii_graf, jj_graf, n, panstwa_lista, PROG_ODPRYSKU, przypiete=przypiete)
    if usuniete:
        print(f"  usunięto {usuniete} komórek odprysków (wróciły do ziemi niczyjej)")
    else:
        print("  brak odprysków do usunięcia")
    if wyspy:
        for nazwa, rozmiar in wyspy:
            print(f"  wyspa państwa {PANSTWA[nazwa]['nazwa_robocza']}: {rozmiar} komórek")
    else:
        print("  brak wysp >= progu odprysku")

    for klucz in panstwa_lista:
        pid = id_panstwa[klucz]
        print(f"  {PANSTWA[klucz]['nazwa_robocza']:<8} po czyszczeniu -> "
              f"{int((kom_panstwo == pid).sum()):4d} komórek")

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

    # --- 4. KADR STARTOWY: żeby gracz nie musiał szukać Kentu na mapie Europy
    # Bbox (w pikselach "płótna", ten sam układ co punkty/wybrzeże) obu
    # państw, z marginesem — kotwiczony w geografii komórek, nie w stałych
    # z generate_world.py (zasada 5 z CLAUDE.md).
    maska_panstw = kom_panstwo != NIEZIEMIA
    px = punkty[maska_panstw]
    x0, y0 = float(px[:, 0].min()), float(px[:, 1].min())
    x1, y1 = float(px[:, 0].max()), float(px[:, 1].max())
    margines = 0.18 * max(x1 - x0, y1 - y0)
    kadr_startowy = {
        "x0": x0 - margines, "y0": y0 - margines,
        "x1": x1 + margines, "y1": y1 + margines,
    }

    json.dump({
        "rok": 800,
        "panstwa": PANSTWA,
        "ziemie": ziemie,
        "kom_panstwo": kom_panstwo.tolist(),
        "kom_ziemia": kom_ziemia.tolist(),
        "kadr_startowy": kadr_startowy,
    }, open("scenariusz_800.json", "w"), ensure_ascii=False)
    print("Zapisano scenariusz_800.json")


if __name__ == "__main__":
    main()
