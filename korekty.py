# -*- coding: utf-8 -*-
"""
korekty.py — wspólna obsługa korekt.json (edytor świata, zadanie 0004).

Korekty to ręczne poprawki geografii/przynależności zakotwiczone w lon/lat
(zasada 5 z CLAUDE.md), NIGDY w indeksach komórek — indeksy zmieniają się
z każdą regeneracją world.npz (nowe ziarno, inna gęstość), lon/lat zostaje.

Ten plik tylko ROZSTRZYGA korekty na indeksy BIEŻĄCEJ siatki (kd-drzewo po
`lonlat`) — nie wie nic o sim.py ani o scenariuszu. Używają go dwie strony,
które muszą się zgadzać co do tego, która komórka/krawędź jest "przypięta":
  • sim.py           — nakłada wartości korekt na żywy stan świata
  • scenariusz_800.py — omija przypięte komórki przy automatycznym czyszczeniu

UWAGA o precyzji: dopasowanie liczone jest na płaskich (lon, lat) w stopniach,
bez korekty cos(szerokość) — dokładnie tak samo "niedokładnie" jak istniejące
już w tym repo dopasowanie ziem do ośrodków w scenariusz_800.py. Przy skali
pojedynczej komórki (rząd 10 km) i regionalnym zasięgu scenariusza to różnica
bez znaczenia; nie ma potrzeby komplikować.
"""

import json
import pathlib

import numpy as np
from scipy.spatial import cKDTree

PLIK_DOMYSLNY = "korekty.json"
PLIK_KOPII = "korekty.json.bak"


def puste():
    return {"wersja": 1, "komorki": [], "krawedzie": []}


def wczytaj(sciezka=PLIK_DOMYSLNY):
    """Zwraca zawartość pliku korekt, albo pustą strukturę, jeśli pliku nie ma
    (świeży checkout repo, nikt jeszcze niczego nie poprawiał ręcznie)."""
    p = pathlib.Path(sciezka)
    if not p.exists():
        return puste()
    with open(p, encoding="utf-8") as f:
        dane = json.load(f)
    dane.setdefault("komorki", [])
    dane.setdefault("krawedzie", [])
    return dane


def zapisz(dane, sciezka=PLIK_DOMYSLNY, plik_kopii=PLIK_KOPII):
    """Zapisuje plik korekt, ale najpierw robi kopię istniejącego pliku —
    praca ręczna jest cenna, nie wolno jej stracić przez nadpisanie z błędem."""
    p = pathlib.Path(sciezka)
    if p.exists():
        p.replace(plik_kopii)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)


def rozstrzygnij_komorki(korekty, lonlat):
    """Każdy wpis "komorki" -> (indeks_najblizszej_komorki, wpis), w kolejności
    z pliku. Gdy kilka wpisów trafia w tę samą komórkę, PÓŹNIEJSZY nadpisuje
    wcześniejszy — dokładnie tak, jak przy zwykłym odtwarzaniu logu zmian."""
    wpisy = korekty.get("komorki", [])
    if not wpisy:
        return []
    drzewo = cKDTree(lonlat)
    punkty = np.array([w["lonlat"] for w in wpisy], dtype=np.float64)
    _, idx = drzewo.query(punkty)
    return list(zip((int(i) for i in idx), wpisy))


def rozstrzygnij_krawedzie(korekty, lonlat):
    """Każdy wpis "krawedzie" -> (idx_a, idx_b, wpis) — para komórek
    najbliższych do końców "a"/"b" odcinka."""
    wpisy = korekty.get("krawedzie", [])
    if not wpisy:
        return []
    drzewo = cKDTree(lonlat)
    pa = np.array([w["a"] for w in wpisy], dtype=np.float64)
    pb = np.array([w["b"] for w in wpisy], dtype=np.float64)
    _, ia = drzewo.query(pa)
    _, ib = drzewo.query(pb)
    return list(zip((int(i) for i in ia), (int(i) for i in ib), wpisy))


def komorki_przypiete(korekty, lonlat):
    """Zbiór indeksów komórek DOTKNIĘTYCH RĘCZNIE — używane przez
    scenariusz_800.py, żeby automatyczne czyszczenie granic (filtr
    większościowy + test spójności, brief 0003) ich nie ruszało."""
    return {idx for idx, _ in rozstrzygnij_komorki(korekty, lonlat)}
