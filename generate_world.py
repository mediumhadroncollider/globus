# -*- coding: utf-8 -*-
"""
generate_world.py — JEDNORAZOWA budowa świata gry.

Uruchamiasz raz (albo gdy chcesz nową mapę):  python generate_world.py
Wynik:
  world.npz        — wszystkie tablice świata (format binarny NumPy, kilka MB)
  world_meta.json  — małe dane opisowe: nazwy, liczby, wybrzeże do narysowania

FILOZOFIA (ważniejsza niż kod):
Świat NIE jest listą obiektów "Komorka" z polami. Świat to zestaw KOLUMN:
jedna tablica ze współrzędnymi wszystkich komórek, jedna z żyznością wszystkich
komórek itd. Dzięki temu każdą operację na "wszystkich komórkach naraz" NumPy
wykona w C, tysiące razy szybciej niż pętla w Pythonie. To się nazywa
Structure-of-Arrays i to jest sposób myślenia silników gier oraz baz danych.
"""

import json
import numpy as np
from scipy.spatial import cKDTree, Delaunay
from scipy.ndimage import gaussian_filter
from matplotlib.path import Path

# ----------------------------------------------------------------------------
# KONFIGURACJA — śmiało zmieniaj
# ----------------------------------------------------------------------------
N_KOMOREK = 60_000       # gęstość mapy; 150_000 też działa, generacja potrwa dłużej
ZIARNO = 966             # seed: ta sama liczba => identyczny świat (odtwarzalność!)
KOMOREK_NA_POWIAT = 30   # średni rozmiar powiatu w komórkach
GESTOSC_WYBRZEZA = 4.0   # ile razy gęstsze komórki przy samym brzegu (1.0 = wyłącz)
PAS_WYBRZEZA = 25        # zasięg zagęszczenia w px płótna (~75 km); dalej wygasa
POWIATOW_NA_KROLESTWO = 140
W, H = 1500, 1150        # "płótno" świata w umownych jednostkach

rng = np.random.default_rng(ZIARNO)   # generator losowości z ziarnem

# ----------------------------------------------------------------------------
# 1. ODWZOROWANIE KARTOGRAFICZNE (Albers — stożkowe równopowierzchniowe)
# ----------------------------------------------------------------------------
# Mapa żyje w płaskich współrzędnych x,y, ale wybrzeża mamy w lon/lat (stopnie).
# Potrzebujemy funkcji w OBIE strony. "Równopowierzchniowe" znaczy: pola się
# nie przekłamują, więc komórka w Laponii i na Krecie ma uczciwie podobny obszar.
# Wzory to standardowy Albers z podręcznika kartografii — potraktuj jak czarną
# skrzynkę; ważne, że wszystkie działania są na CAŁYCH TABLICACH naraz.

FI1, FI2 = np.radians(40), np.radians(68)   # równoleżniki styczne
LAM0, FI0 = np.radians(15), np.radians(52)  # środek odwzorowania

_n = (np.sin(FI1) + np.sin(FI2)) / 2
_C = np.cos(FI1) ** 2 + 2 * _n * np.sin(FI1)
_rho0 = np.sqrt(_C - 2 * _n * np.sin(FI0)) / _n

def projektuj(lon_deg, lat_deg):
    """lon/lat (stopnie) -> x,y na płaszczyźnie (jeszcze bez skalowania do W×H)."""
    lam, fi = np.radians(lon_deg), np.radians(lat_deg)
    rho = np.sqrt(_C - 2 * _n * np.sin(fi)) / _n
    th = _n * (lam - LAM0)
    return rho * np.sin(th), _rho0 - rho * np.cos(th)

def odprojektuj(x, y):
    """x,y (w jednostkach odwzorowania) -> lon/lat w stopniach."""
    rho = np.sqrt(x ** 2 + (_rho0 - y) ** 2)
    th = np.arctan2(x, _rho0 - y)
    lon = np.degrees(LAM0 + th / _n)
    lat = np.degrees(np.arcsin((_C - (rho * _n) ** 2) / (2 * _n)))
    return lon, lat

# Wybrzeża Europy (przygotowane wcześniej z danych Natural Earth 50m).
wybrzeza = json.load(open("europa_wybrzeza.json"))

# Dopasowanie: rzutujemy wybrzeża, mierzymy ich prostokąt i wyliczamy skalę,
# żeby kontynent ładnie wypełnił płótno W×H.
wsz_x, wsz_y = [], []
for ring in wybrzeza:
    r = np.array(ring)
    x, y = projektuj(r[:, 0], r[:, 1])
    wsz_x.append(x); wsz_y.append(y)
minx = min(a.min() for a in wsz_x); maxx = max(a.max() for a in wsz_x)
miny = min(a.min() for a in wsz_y); maxy = max(a.max() for a in wsz_y)
SKALA = min((W - 20) / (maxx - minx), (H - 20) / (maxy - miny))

def na_plotno(x, y):
    """jednostki odwzorowania -> piksele płótna (y rośnie w dół, jak na ekranie)"""
    return (x - minx) * SKALA + 10, (maxy - y) * SKALA + 10

def z_plotna(px, py):
    return (px - 10) / SKALA + minx, maxy - (py - 10) / SKALA

# wybrzeże w pikselach — klient je tylko narysuje, nie musi nic liczyć
wybrzeze_px = []
for x, y in zip(wsz_x, wsz_y):
    px, py = na_plotno(x, y)
    wybrzeze_px.append(np.round(np.stack([px, py], axis=1), 1).tolist())

# ----------------------------------------------------------------------------
# 2. KOMÓRKI: losowe punkty + relaksacja Lloyda (metodą Monte Carlo)
# ----------------------------------------------------------------------------
# Relaksacja Lloyda "rozpycha" punkty, żeby komórki miały podobne rozmiary.
# Klasycznie liczy się środki ciężkości wielokątów Woronoja; my robimy sprytniej
# i bardziej "numpy'owo": sypiemy 2 mln losowych ziarenek piasku, każde ziarenko
# pytamy "który punkt jest ci najbliżej?" (drzewo kd — bardzo szybkie szukanie
# najbliższego sąsiada), a potem każdy punkt przesuwamy do średniej pozycji
# swoich ziarenek. To jest środek ciężkości komórki z dokładnością Monte Carlo.

# ----------------------------------------------------------------------------
# 2a. GĘSTOŚĆ WAŻONA WYBRZEŻEM
# ----------------------------------------------------------------------------
# Chcemy drobne komórki przy linii brzegowej (precyzyjne wybrzeże "od zawsze"),
# a większe w głębi lądu I na otwartym morzu (tam szkoda budżetu komórek).
# Realizacja: próbkowanie z odrzucaniem — kandydat w odległości d od wybrzeża
# jest przyjmowany z prawdopodobieństwem waga(d), która przy brzegu wynosi 1,
# a daleko spada do 1/GESTOSC_WYBRZEZA.
#
# PUŁAPKA, którą trzeba znać: sama zmiana rozsiewu punktów by NIE wystarczyła,
# bo relaksacja Lloyda z natury wyrównuje gęstość. Dlatego ważymy TAKŻE piasek
# Monte Carlo w relaksacji — wtedy Lloyd stabilizuje dokładnie ten rozkład,
# który chcemy (tzw. ważona teselacja centroidalna).

# drzewo odległości od wybrzeża: wierzchołki pierścieni dogęszczone co ~6 px,
# żeby odległość do brzegu była mierzona uczciwie, a nie "do co 20. wierzchołka"
_brzeg = []
for _ring in wybrzeze_px:
    _r = np.array(_ring)
    for _i in range(len(_r) - 1):
        _dl = np.hypot(*(_r[_i + 1] - _r[_i]))
        _n_wst = max(1, int(_dl // 6))
        for _t in range(_n_wst):
            _brzeg.append(_r[_i] + (_r[_i + 1] - _r[_i]) * (_t / _n_wst))
drzewo_brzegu = cKDTree(np.array(_brzeg))

def waga_gestosci(pkt):
    d, _ = drzewo_brzegu.query(pkt, workers=-1)
    return (1 + (GESTOSC_WYBRZEZA - 1) * np.exp(-d / PAS_WYBRZEZA)) / GESTOSC_WYBRZEZA

def losuj_wazone(ile):
    """Losuje `ile` punktów z gęstością ~waga_gestosci (odrzucanie)."""
    zebrane = []
    brakuje = ile
    while brakuje > 0:
        kandydaci = rng.random((brakuje * 3 + 1000, 2)) * [W, H]
        przyjete = kandydaci[rng.random(len(kandydaci)) < waga_gestosci(kandydaci)]
        zebrane.append(przyjete[:brakuje])
        brakuje -= len(przyjete[:brakuje])
    return np.concatenate(zebrane)

print(f"Punkty: {N_KOMOREK} (gęstość wybrzeża ×{GESTOSC_WYBRZEZA}) …")
punkty = losuj_wazone(N_KOMOREK).astype(np.float64)

for iteracja in range(2):
    piasek = losuj_wazone(2_000_000)   # piasek ważony — patrz komentarz wyżej
    drzewo = cKDTree(punkty)
    _, najblizszy = drzewo.query(piasek, workers=-1)   # dla każdego ziarenka: indeks komórki
    # bincount z wagami = "posumuj wartości w grupach" jedną instrukcją
    sx = np.bincount(najblizszy, weights=piasek[:, 0], minlength=N_KOMOREK)
    sy = np.bincount(najblizszy, weights=piasek[:, 1], minlength=N_KOMOREK)
    ile = np.bincount(najblizszy, minlength=N_KOMOREK)
    ma = ile > 0
    punkty[ma, 0] = sx[ma] / ile[ma]
    punkty[ma, 1] = sy[ma] / ile[ma]
    print(f"  Lloyd {iteracja + 1}/2 gotowy")

# ----------------------------------------------------------------------------
# 3. LĄD CZY MORZE? Test punkt-w-poligonie dla wszystkich komórek NARAZ
# ----------------------------------------------------------------------------
# Zasada parzystości (even-odd): punkt jest na lądzie, jeśli leży wewnątrz
# NIEPARZYSTEJ liczby pierścieni (zewnętrzny kontur = 1, jezioro w środku = 2…).
# XOR (^=) po wszystkich pierścieniach realizuje dokładnie tę zasadę.

print("Klasyfikacja ląd/morze …")
lon, lat = odprojektuj(*z_plotna(punkty[:, 0], punkty[:, 1]))
pkt_ll = np.stack([lon, lat], axis=1)
lad = np.zeros(N_KOMOREK, dtype=bool)
for ring in wybrzeza:
    lad ^= Path(ring).contains_points(pkt_ll)
print(f"  lądu (przed korektami): {lad.sum()} komórek ({100 * lad.mean():.0f}%)")

# ----------------------------------------------------------------------------
# 3a. KOREKTY RĘCZNE — autorska kontrola nad światem
# ----------------------------------------------------------------------------
# Zasada nadrzędna: korekt NIE zapisujemy indeksami komórek (indeksy zmieniają
# się z każdym ziarnem i gęstością!), tylko WSPÓŁRZĘDNYMI GEOGRAFICZNYMI.
# Dzięki temu ta sama lista poprawek działa dla każdej wygenerowanej mapy.
#
# Dwa różne problemy — dwa różne narzędzia:
#  • wyspa "znika" (za mała, przegrała z progiem rozdzielczości)
#      -> WYSPY_OBOWIAZKOWE: punkt lon/lat; najbliższa komórka staje się lądem
#  • dwa lądy "zrastają się" przez cieśninę węższą niż komórka (Mesyna!)
#      -> CIESNINY: odcinek lon/lat poprowadzony wodą; każde sąsiedztwo
#         komórek, którego linia środków przecina ten odcinek, zostaje
#         ZERWANE w grafie. Geometria i wybrzeże zostają nietknięte —
#         naprawiamy topologię, nie rysunek. (Tak samo robią gry Paradoxu:
#         cieśnina to dane, nie geometria.)

WYSPY_OBOWIAZKOWE = {          # nazwa -> (lon, lat)
    "Malta":    (14.40, 35.88),
    "Bornholm": (14.92, 55.13),
    "Muhu":     (23.25, 58.60),
    "Hiiumaa":  (22.63, 58.90),
}
CIESNINY = {                   # nazwa -> ((lon1, lat1), (lon2, lat2))
    "Mesyńska":        ((15.70, 38.33), (15.40, 37.85)),
    "Suur väin":       ((23.30, 58.80), (23.50, 58.35)),
    "Soela":           ((22.30, 58.72), (22.95, 58.69)),
    "Hiiumaa–ląd":     ((23.05, 59.15), (23.55, 58.72)),
    "Öresund":         ((12.55, 56.20), (12.95, 55.30)),
    "Bosfor":          ((28.85, 41.35), (29.25, 40.85)),
    "Dardanele":       ((26.05, 40.55), (26.80, 39.90)),
}

# wyspy obowiązkowe: najbliższa komórka -> ląd
drzewo_wsz = cKDTree(punkty)
for nazwa_w, (lo, la) in WYSPY_OBOWIAZKOWE.items():
    px, py = na_plotno(*projektuj(np.array([lo]), np.array([la])))
    _, c = drzewo_wsz.query([px[0], py[0]])
    if not lad[c]:
        lad[c] = True
        print(f"  wyspa obowiązkowa: {nazwa_w} -> komórka {c} wymuszona na ląd")

idx_ladu = np.flatnonzero(lad)              # indeksy komórek lądowych
print(f"  lądu: {lad.sum()} komórek ({100 * lad.mean():.0f}%)")

# ----------------------------------------------------------------------------
# 4. SĄSIEDZTWO KOMÓREK (z triangulacji Delaunaya)
# ----------------------------------------------------------------------------
# Triangulacja Delaunaya łączy krawędzią dokładnie te punkty, których komórki
# Woronoja się stykają — czyli daje nam graf sąsiedztwa za darmo. SciPy zwraca
# go w formacie CSR: indeksy sąsiadów komórki i to indices[indptr[i]:indptr[i+1]].
# Ten sam format zapiszemy do pliku — symulacja będzie z niego korzystać.

print("Triangulacja i sąsiedztwo …")
tri = Delaunay(punkty)
indptr, indices = tri.vertex_neighbor_vertices
indptr = indptr.astype(np.int32)
indices = indices.astype(np.int32)

def sasiedzi(i):
    return indices[indptr[i]:indptr[i + 1]]

# ----------------------------------------------------------------------------
# 4a. CIESNINY: zrywanie krawędzi lądowych przecinających odcinki cieśnin
# ----------------------------------------------------------------------------
# Wszystkie lądowe pary sąsiadów jako dwie kolumny (a, b) — z formatu CSR:
_ii = np.repeat(np.arange(N_KOMOREK), np.diff(indptr))
_jj = indices
_m = (_ii < _jj) & lad[_ii] & lad[_jj]      # każda para raz; tylko ląd-ląd
kraw_a, kraw_b = _ii[_m], _jj[_m]

def _orient(px, py, ax, ay, bx, by):
    """>0 gdy punkt p leży po lewej stronie odcinka a->b (iloczyn wektorowy).
    Dwa odcinki się przecinają, gdy końce każdego leżą po przeciwnych
    stronach drugiego — klasyczny test geometrii obliczeniowej,
    tu policzony dla WSZYSTKICH krawędzi naraz."""
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)

zerwij = np.zeros(len(kraw_a), dtype=bool)
Ax, Ay = punkty[kraw_a, 0], punkty[kraw_a, 1]
Bx, By = punkty[kraw_b, 0], punkty[kraw_b, 1]
for nazwa_c, (p1, p2) in CIESNINY.items():
    sx, sy = na_plotno(*projektuj(np.array([p1[0], p2[0]]), np.array([p1[1], p2[1]])))
    s1x, s1y, s2x, s2y = sx[0], sy[0], sx[1], sy[1]
    po_str_a = _orient(Ax, Ay, s1x, s1y, s2x, s2y)
    po_str_b = _orient(Bx, By, s1x, s1y, s2x, s2y)
    po_str_1 = _orient(s1x, s1y, Ax, Ay, Bx, By)
    po_str_2 = _orient(s2x, s2y, Ax, Ay, Bx, By)
    trafione = (po_str_a * po_str_b < 0) & (po_str_1 * po_str_2 < 0)
    if trafione.any():
        print(f"  cieśnina {nazwa_c}: zerwano {int(trafione.sum())} sąsiedztw")
    zerwij |= trafione

zerwane_a = kraw_a[zerwij].astype(np.int32)
zerwane_b = kraw_b[zerwij].astype(np.int32)
# szybki test przynależności dla pętli rozrostu (pary zawsze (mniejszy, większy))
zerwane_set = set(zip(zerwane_a.tolist(), zerwane_b.tolist()))

def zerwana(a, b):
    return ((a, b) if a < b else (b, a)) in zerwane_set

# ----------------------------------------------------------------------------
# 5. POWIATY: rozsiane ziarna + losowy rozrost po lądzie
# ----------------------------------------------------------------------------
# a) Ziarna metodą "najdalszego punktu": każde kolejne ziarno stawiamy tam,
#    gdzie jest NAJDALEJ od wszystkich dotychczasowych — rozsiewa idealnie
#    równomiernie. Trzymamy tablicę d2 = odległość każdej komórki lądowej do
#    najbliższego ziarna i aktualizujemy ją po każdym nowym ziarnie (wektorowo).

n_pow = max(12, len(idx_ladu) // KOMOREK_NA_POWIAT)
print(f"Powiaty: {n_pow} …")
pkt_ladu = punkty[idx_ladu]
d2 = np.full(len(idx_ladu), np.inf)
ziarno_i = rng.integers(len(idx_ladu))
ziarna_pow = [idx_ladu[ziarno_i]]
for _ in range(n_pow - 1):
    roznica = pkt_ladu - punkty[ziarna_pow[-1]]
    d2 = np.minimum(d2, (roznica ** 2).sum(axis=1))
    ziarna_pow.append(idx_ladu[int(np.argmax(d2))])
ziarna_pow = np.array(ziarna_pow)

# b) Rozrost: klasyczny "zalew" z wielu źródeł naraz, ale kolejkę opróżniamy
#    w LOSOWEJ kolejności — dzięki temu powiaty mają organiczne, poszarpane
#    kształty, a nie idealne plastry. (Czysty Python, ale to koszt jednorazowy.)
komorka_pow = np.full(N_KOMOREK, -1, dtype=np.int32)
komorka_pow[ziarna_pow] = np.arange(n_pow)
kolejka = list(ziarna_pow)
los = np.random.default_rng(ZIARNO + 1)
while kolejka:
    j = los.integers(len(kolejka))
    kolejka[j], kolejka[-1] = kolejka[-1], kolejka[j]
    c = kolejka.pop()
    for nb in sasiedzi(c):
        # zalew NIE przechodzi przez zerwane cieśniny — Sycylia zostaje Sycylią
        if lad[nb] and komorka_pow[nb] == -1 and not zerwana(c, nb):
            komorka_pow[nb] = komorka_pow[c]
            kolejka.append(nb)

# c) Sieroty (odcięte wysepki, do których zalew nie dopłynął) -> najbliższe ziarno.
sieroty = idx_ladu[komorka_pow[idx_ladu] == -1]
if len(sieroty):
    drzewo_ziaren = cKDTree(punkty[ziarna_pow])
    _, kto = drzewo_ziaren.query(punkty[sieroty])
    komorka_pow[sieroty] = kto
    print(f"  przygarnięto {len(sieroty)} komórek-sierot (wyspy)")

# ----------------------------------------------------------------------------
# 6. KRÓLESTWA: ten sam trik piętro wyżej (graf sąsiedztwa POWIATÓW)
# ----------------------------------------------------------------------------
print("Królestwa …")
# centroid każdego powiatu — znowu bincount zamiast pętli
cx = np.bincount(komorka_pow[idx_ladu], weights=punkty[idx_ladu, 0], minlength=n_pow)
cy = np.bincount(komorka_pow[idx_ladu], weights=punkty[idx_ladu, 1], minlength=n_pow)
ile_kom = np.bincount(komorka_pow[idx_ladu], minlength=n_pow)
pow_xy = np.stack([cx / ile_kom, cy / ile_kom], axis=1)

# sąsiedztwo powiatów: przeglądamy wszystkie krawędzie komórek i zbieramy pary
sasiedztwo_pow = [set() for _ in range(n_pow)]
for c in idx_ladu:
    pc = komorka_pow[c]
    for nb in sasiedzi(c):
        # cieśniny zrywają też sąsiedztwo POWIATÓW (księstwa nie zrosną się
        # przez Mesynę); przeprawy morskie dodasz kiedyś jako osobną mechanikę
        if lad[nb] and komorka_pow[nb] != pc and not zerwana(c, nb):
            sasiedztwo_pow[pc].add(int(komorka_pow[nb]))

n_krol = max(4, n_pow // POWIATOW_NA_KROLESTWO)
d2 = np.full(n_pow, np.inf)
ziarna_krol = [int(rng.integers(n_pow))]
for _ in range(n_krol - 1):
    d2 = np.minimum(d2, ((pow_xy - pow_xy[ziarna_krol[-1]]) ** 2).sum(axis=1))
    ziarna_krol.append(int(np.argmax(d2)))

pow_krol = np.full(n_pow, -1, dtype=np.int32)
pow_krol[ziarna_krol] = np.arange(n_krol)
kolejka = list(ziarna_krol)
while kolejka:
    j = los.integers(len(kolejka))
    kolejka[j], kolejka[-1] = kolejka[-1], kolejka[j]
    p = kolejka.pop()
    for q in sasiedztwo_pow[p]:
        if pow_krol[q] == -1:
            pow_krol[q] = pow_krol[p]
            kolejka.append(q)
pow_krol[pow_krol == -1] = los.integers(0, n_krol, (pow_krol == -1).sum())

# ----------------------------------------------------------------------------
# 7. ŻYZNOŚĆ TERENU — łagodne pole losowe + gradient południa
# ----------------------------------------------------------------------------
# Losowa kratka 90×90 rozmyta filtrem Gaussa daje naturalne "plamy" dobrych
# i słabych ziem; do tego cieplejsze południe dostaje bonus. Wartości 0..1.
print("Żyzność …")
kratka = gaussian_filter(rng.random((90, 90)), sigma=5)
kratka = (kratka - kratka.min()) / (kratka.max() - kratka.min())
gx = np.clip((punkty[:, 0] / W * 89).astype(int), 0, 89)
gy = np.clip((punkty[:, 1] / H * 89).astype(int), 0, 89)
zyznosc = 0.65 * kratka[gy, gx] + 0.35 * (punkty[:, 1] / H)   # niżej = cieplej
zyznosc = np.where(lad, zyznosc, 0).astype(np.float32)

# ----------------------------------------------------------------------------
# 8. NAZWY (czysta zabawa) i ZAPIS
# ----------------------------------------------------------------------------
SYL = ["bo","go","mi","ra","sła","wo","dro","ze","ka","le","po","ni","sto",
       "gnie","wi","cha","rze","łu","ma","tu","brze","ost","wielo","krze"]
KON = ["ów","ice","no","sk","in","owo","iec","any"]
def nazwa(r):
    s = "".join(r.choice(SYL) for _ in range(int(r.integers(1, 3)))) + r.choice(KON)
    return s.capitalize()
los_n = np.random.default_rng(ZIARNO + 2)
nazwy_pow = [nazwa(los_n) for _ in range(n_pow)]
nazwy_krol = [nazwa(los_n) for _ in range(n_krol)]

np.savez_compressed(
    "world.npz",
    punkty=punkty.astype(np.float32),
    lad=lad,
    indptr=indptr, indices=indices,
    komorka_pow=komorka_pow,
    pow_krol_start=pow_krol,
    zyznosc=zyznosc,
    zerwane_a=zerwane_a, zerwane_b=zerwane_b,   # zerwane sąsiedztwa (cieśniny)
)
json.dump(
    {
        "n_komorek": int(N_KOMOREK), "n_pow": int(n_pow), "n_krol": int(n_krol),
        "W": W, "H": H,
        "nazwy_pow": nazwy_pow, "nazwy_krol": nazwy_krol,
        "wybrzeze": wybrzeze_px,
        "zerwane": np.stack([zerwane_a, zerwane_b], axis=1).tolist(),
    },
    open("world_meta.json", "w"), ensure_ascii=False,
)
print(f"Zapisano world.npz i world_meta.json — {n_pow} powiatów, {n_krol} królestw. Gotowe.")
