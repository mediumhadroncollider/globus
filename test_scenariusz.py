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

from sim import Swiat

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

# ----------------------------------------------------------------------------
# 4-5: niezmienniki DYNAMICZNE — trzeba odpalić symulację.
# ----------------------------------------------------------------------------
s = Swiat()
sprawdz("Swiat() wchodzi w tryb scenariusza", s.tryb_scenariusza)

pop_niczyje_start = float(s.populacja[s.lad & (s.wlasciciel_komorki < 0)].sum())

for _ in range(100):
    wynik = s.tick()

# 4. Po 100 tickach: skarbce Cantii i Sussexu > 0, populacja na ziemiach
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

# 5. Podbój ziemi niczyjej to jawna odmowa (nie ginie po cichu jak None,
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
