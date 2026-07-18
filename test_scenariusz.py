# -*- coding: utf-8 -*-
"""
test_scenariusz.py — niezmienniki scenariusza 800 (Kent i Sussex).

Wzorem test_ciesnin.py: uruchamiaj po każdej zmianie scenariusz_800.py albo
sim.py. Mapa/scenariusz, który tu nie przechodzi, nie wchodzi do gry.

Wymaga wygenerowanego świata i scenariusza:
    python generate_world.py && python scenariusz_800.py && python test_scenariusz.py
"""

import json
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from sim import Swiat

# Musi być zgodne z PROG_ODPRYSKU w scenariusz_800.py — składowa mniejsza
# niż tyle komórek to "sól i pieprz", nie prawdziwa wyspa.
PROG_ODPRYSKU = 4

OK = True


def sprawdz(nazwa, warunek):
    global OK
    print(("OK " if warunek else "ZLE"), nazwa)
    if not warunek:
        OK = False


# ----------------------------------------------------------------------------
# 1-3: niezmienniki STATYCZNE — wprost na danych scenariusza i świata,
# bez żadnego ticka.
# ----------------------------------------------------------------------------
dane = json.load(open("scenariusz_800.json"))
d = np.load("world.npz")

kom_panstwo = np.array(dane["kom_panstwo"])
kom_ziemia = np.array(dane["kom_ziemia"])
lad = d["lad"]
ziemie = dane["ziemie"]

# 1. Każda ziemia ma >= 1 komórkę.
komorek_na_ziemie = np.bincount(kom_ziemia[kom_ziemia >= 0], minlength=len(ziemie))
sprawdz(
    "każda ziemia ma >= 1 komórkę",
    bool((komorek_na_ziemie >= 1).all()),
)
if not (komorek_na_ziemie >= 1).all():
    puste = [z["nazwa_gry"] for z, n in zip(ziemie, komorek_na_ziemie) if n == 0]
    print("     puste ziemie:", puste)

# 2. Suma komórek państw == liczba komórek z kom_panstwo >= 0.
suma_panstw = sum(int((kom_panstwo == i).sum()) for i in range(len(dane["panstwa"])))
sprawdz(
    "suma komórek państw == liczba komórek z kom_panstwo >= 0",
    suma_panstw == int((kom_panstwo >= 0).sum()),
)

# 3. Żadna komórka morska nie ma właściciela.
sprawdz(
    "żadna komórka morska nie ma właściciela",
    bool((kom_panstwo[~lad] < 0).all()),
)

# 4. Komórki każdego państwa tworzą JEDNĄ spójną składową na grafie
# sąsiedztwa (z pominięciem zerwanych cieśnin — wyspa oddzielona cieśniną nie
# jest sąsiadem lądu), poza jawnie dopuszczonymi wyspami >= PROG_ODPRYSKU.
# Odpryski mniejsze od progu oznaczałyby, że scenariusz_800.py nie posprzątał
# eksklaw/dziur po teście punkt-w-poligonie (patrz brief 0003, część B).
n = len(lad)
indptr, indices = d["indptr"], d["indices"]
zerwane_a, zerwane_b = d["zerwane_a"], d["zerwane_b"]
_ii = np.repeat(np.arange(n), np.diff(indptr))
_jj = indices
_ok = lad[_ii] & lad[_jj]
_ii, _jj = _ii[_ok], _jj[_ok]
_zerw = set(zip(zerwane_a.tolist(), zerwane_b.tolist()))
_zerw |= set(zip(zerwane_b.tolist(), zerwane_a.tolist()))
_zywe = np.array([(a, b) not in _zerw for a, b in zip(_ii.tolist(), _jj.tolist())])
_ii, _jj = _ii[_zywe], _jj[_zywe]

spojne = True
wyspy = []
for pid, (klucz, panstwo) in enumerate(dane["panstwa"].items()):
    idx = np.flatnonzero(kom_panstwo == pid)
    if len(idx) == 0:
        continue
    maska_e = (kom_panstwo[_ii] == pid) & (kom_panstwo[_jj] == pid)
    a, b = _ii[maska_e], _jj[maska_e]
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
        if rozmiar >= PROG_ODPRYSKU:
            wyspy.append((panstwo["nazwa_robocza"], rozmiar))
        else:
            spojne = False

sprawdz(
    f"komórki każdego państwa tworzą jedną spójną składową "
    f"(poza wyspami >= {PROG_ODPRYSKU} komórek)",
    spojne,
)
print("     wyspy:", wyspy if wyspy else "brak")

# ----------------------------------------------------------------------------
# 5-6: niezmienniki DYNAMICZNE — trzeba odpalić symulację.
# ----------------------------------------------------------------------------
s = Swiat()
sprawdz("Swiat() wchodzi w tryb scenariusza", s.tryb_scenariusza)

pop_niczyje_start = float(s.populacja[s.lad & (s.wlasciciel_komorki < 0)].sum())

for _ in range(100):
    wynik = s.tick()

# 5. Po 100 tickach: skarbce Cantii i Sussexu > 0, populacja na ziemiach
#    niczyich > 0 i zmieniła się względem startu.
klucze = [p["klucz"] for p in s.panstwa]
sprawdz(
    "skarbiec Cantii > 0 po 100 tickach",
    float(s.skarbiec[klucze.index("kent")]) > 0,
)
sprawdz(
    "skarbiec Sussexu > 0 po 100 tickach",
    float(s.skarbiec[klucze.index("sussex")]) > 0,
)
pop_niczyje_koniec = float(s.populacja[s.lad & (s.wlasciciel_komorki < 0)].sum())
sprawdz("populacja na ziemiach niczyich > 0 po 100 tickach", pop_niczyje_koniec > 0)
sprawdz(
    "populacja na ziemiach niczyich zmieniła się (tło żyje)",
    pop_niczyje_koniec != pop_niczyje_start,
)

# 6. Podbój ziemi niczyjej to jawna odmowa (nie ginie po cichu jak None,
#    patrz zadanie 0002 — gracz musi wiedzieć, że kliknął źle).
wynik_podboju = s.wykonaj_akcje({"typ": "podboj", "ziemia": -1, "panstwo": klucze.index("kent")})
sprawdz(
    "podbój ziemi niczyjej (ziemia=-1) zwraca jawną odmowę",
    isinstance(wynik_podboju, dict) and wynik_podboju.get("typ") == "odmowa",
)

print()
print("WYNIK:", "wszystkie niezmienniki scenariusza OK" if OK else "SĄ BŁĘDY!")
if not OK:
    raise SystemExit(1)
