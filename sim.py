# -*- coding: utf-8 -*-
"""
sim.py — SERCE GRY: czysta symulacja, zero sieci, zero interfejsu.

Ten plik celowo nie wie nic o WebSocketach ani przeglądarce. Dzięki temu:
  • możesz go testować bez uruchamiania serwera:  python sim.py
  • możesz w notebooku Jupytera odpalić 1000 ticków i narysować wykresy,
    zanim zdecydujesz, czy formuła podatkowa jest dobrze zbalansowana
  • wymiana interfejsu (kiedyś np. na coś ładniejszego) nie rusza mechanik

Wzorzec jest ten sam, o którym mówiliśmy od początku:
  stan  = tablice NumPy (kolumny)
  tick(): stan -> stan          (jeden krok czasu, czysta matematyka)
  wykonaj_akcje(akcja): rozkazy gracza zmieniają PARAMETRY, nie stan wprost
"""

import json
import numpy as np


class Swiat:
    def __init__(self, plik_npz="world.npz", plik_meta="world_meta.json"):
        d = np.load(plik_npz)
        meta = json.load(open(plik_meta))

        # --- niezmienna geografia -------------------------------------------
        self.punkty = d["punkty"]            # (N,2) float32 — pozycje komórek
        self.lad = d["lad"]                  # (N,)  bool
        self.indptr = d["indptr"]            # sąsiedztwo w formacie CSR
        self.indices = d["indices"]
        self.zyznosc = d["zyznosc"]          # (N,) 0..1
        self.komorka_pow = d["komorka_pow"]  # (N,) -> indeks powiatu (-1 = morze)
        self.n_pow = meta["n_pow"]
        self.n_krol = meta["n_krol"]
        self.nazwy_pow = meta["nazwy_pow"]
        self.nazwy_krol = meta["nazwy_krol"]

        # --- zmienny stan polityczny ----------------------------------------
        self.pow_krol = d["pow_krol_start"].copy()   # (n_pow,) właściciel powiatu

        # --- zmienny stan ekonomiczny (KOLUMNY per komórka) -----------------
        # populacja startowa: żyzne ziemie zaczynają ludniejsze, plus szczypta
        # losowości, żeby świat nie był sterylny
        rng = np.random.default_rng(7)
        self.populacja = np.where(
            self.lad, 20 + 180 * self.zyznosc * rng.uniform(0.6, 1.0, len(self.lad)), 0
        ).astype(np.float32)

        # --- parametry sterowane przez graczy (per królestwo) ---------------
        self.podatek = np.full(self.n_krol, 0.10, dtype=np.float32)  # 0..0.5

        # --- księgowość per królestwo ---------------------------------------
        self.skarbiec = np.zeros(self.n_krol, dtype=np.float32)
        self.tick_nr = 0

    # ------------------------------------------------------------------------
    @property
    def wlasciciel_komorki(self):
        """Kto włada każdą komórką? Składamy dwie tablice indeksowaniem:
        komorka -> powiat -> królestwo. To jedna operacja NumPy, nie pętla.
        Komórki morskie dostają 0, ale i tak nic nie produkują (populacja=0)."""
        return self.pow_krol[np.maximum(self.komorka_pow, 0)]

    # ------------------------------------------------------------------------
    def tick(self):
        """JEDEN KROK CZASU dla całego kontynentu. Zwróć uwagę: ani jednej
        pętli po komórkach — każda linijka działa na wszystkich 60-150 tys.
        komórek naraz. To jest cały sekret wydajności."""
        self.tick_nr += 1
        wlasc = self.wlasciciel_komorki           # (N,) królestwo każdej komórki
        stawka = self.podatek[wlasc]              # (N,) podatek obowiązujący komórkę

        # --- DOCHÓD: ludzie × żyzność × stawka podatku ----------------------
        dochod = self.populacja * self.zyznosc * stawka * 0.1

        # --- do skarbców: "posumuj dochody w grupach po właścicielu" --------
        self.skarbiec += np.bincount(
            wlasc, weights=dochod, minlength=self.n_krol
        ).astype(np.float32)

        # --- POPULACJA: wzrost logistyczny hamowany podatkiem ---------------
        # pojemność terenu zależy od żyzności; wysoki podatek dławi wzrost
        # (to jest właśnie suwak z prawdziwym trade-offem: kasa dziś
        #  albo ludność — czyli kasa — jutro)
        pojemnosc = 50 + 450 * self.zyznosc
        tempo = 0.02 * (1 - 1.4 * stawka)
        self.populacja += np.where(
            self.lad,
            tempo * self.populacja * (1 - self.populacja / np.maximum(pojemnosc, 1)),
            0,
        ).astype(np.float32)
        np.clip(self.populacja, 0, None, out=self.populacja)

        # --- agregaty do wyświetlenia (per powiat i per królestwo) ----------
        kp = self.komorka_pow[self.lad]
        pow_pop = np.bincount(kp, weights=self.populacja[self.lad], minlength=self.n_pow)
        pow_doch = np.bincount(kp, weights=dochod[self.lad], minlength=self.n_pow)
        krol_doch = np.bincount(wlasc, weights=dochod, minlength=self.n_krol)

        return {
            "tick": self.tick_nr,
            "pow_pop": pow_pop.astype(np.float32),
            "pow_doch": pow_doch.astype(np.float32),
            "krol_doch": krol_doch.astype(np.float32),
            "skarbiec": self.skarbiec.copy(),
        }

    # ------------------------------------------------------------------------
    def wykonaj_akcje(self, akcja: dict):
        """Rozkazy gracza. Zwraca opis zmiany (do rozgłoszenia) albo None.
        Zauważ wzorzec: akcje NIE grzebią w stanie ekonomicznym bezpośrednio —
        zmieniają parametry lub przypisania, a skutki policzy najbliższy tick."""
        typ = akcja.get("typ")

        if typ == "podatek":
            k = int(akcja["krolestwo"])
            self.podatek[k] = float(np.clip(akcja["stawka"], 0.0, 0.5))
            return {"typ": "podatek", "krolestwo": k, "stawka": round(float(self.podatek[k]), 3)}

        if typ == "podboj":
            # Zmiana właściciela powiatu = zmiana JEDNEJ liczby w tablicy.
            # Granice na mapie przerysują się same, bo klient wylicza je
            # z przypisań — dokładnie jak w naszym demie SVG.
            p = int(akcja["powiat"])
            k = int(akcja["krolestwo"])
            if 0 <= p < self.n_pow and 0 <= k < self.n_krol:
                self.pow_krol[p] = k
                return {"typ": "podboj", "powiat": p, "krolestwo": k}

        return None


# ----------------------------------------------------------------------------
# Mini-test balansu bez żadnego serwera: uruchom  python sim.py
# To jest ta supermoc oddzielenia symulacji od reszty — eksperymentujesz
# z formułami w sekundę, bez klikania po interfejsie.
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    s = Swiat()
    s.podatek[0] = 0.45   # królestwo 0: pazerny fiskus
    s.podatek[1] = 0.05   # królestwo 1: niskie podatki, gra na wzrost
    for _ in range(300):
        wynik = s.tick()
    print(f"Po {wynik['tick']} tickach:")
    for k in range(s.n_krol):
        print(
            f"  {s.nazwy_krol[k]:<12} podatek {s.podatek[k]:.2f}"
            f"  skarbiec {s.skarbiec[k]:>12.0f}"
            f"  dochód/tick {wynik['krol_doch'][k]:>9.1f}"
        )
