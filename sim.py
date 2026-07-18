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

SCENARIUSZE — jeśli obok leży plik scenariusza (domyślnie scenariusz_800.json,
patrz scenariusz_800.py), świat rusza z warstwą historyczną: ZIEMIE i PAŃSTWA
zamiast proceduralnych powiatów/królestw. Gdy pliku nie ma, świat działa
dokładnie jak dawniej (tryb proceduralny) — patrz CLAUDE.md, sekcja
"scenariusze" i zasada "ziemie niczyje żyją".
"""

import json
import pathlib
import numpy as np


class Swiat:
    def __init__(
        self,
        plik_npz="world.npz",
        plik_meta="world_meta.json",
        plik_scenariusza="scenariusz_800.json",
    ):
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
        n = len(self.lad)

        # --- zmienny stan polityczny (tryb proceduralny) ---------------------
        self.pow_krol = d["pow_krol_start"].copy()   # (n_pow,) właściciel powiatu

        # --- warstwa scenariusza (ZIEMIE i PAŃSTWA) --------------------------
        # Domyślnie "pusta" (tryb proceduralny). -1 wszędzie = "brak".
        # Kolumny/tablice istnieją ZAWSZE (nawet bez scenariusza), żeby
        # protokół binarny (server.py) nie musiał się rozgałęziać.
        self.tryb_scenariusza = False
        self.kom_ziemia = np.full(n, -1, dtype=np.int32)      # (N,) -> indeks ziemi
        self.ziemia_panstwo = np.zeros(0, dtype=np.int32)     # (n_ziem,) -> indeks państwa
        self.n_ziem = 0
        self.ziemie = []            # opisy ziem (id, nazwy, państwo) — dla server.py
        self.panstwa = []           # opisy państw (nazwy, kolor, władca, gracz)
        self.panstwo_gracz = 0
        self.kadr_startowy = None   # bbox startowej kamery (w px "płótna"), patrz scenariusz_800.py
        self.n_panstw = self.n_krol  # tryb proceduralny: państwo == królestwo

        sciezka_scen = pathlib.Path(plik_scenariusza)
        if sciezka_scen.exists():
            self._wczytaj_scenariusz(sciezka_scen)

        # --- zmienny stan ekonomiczny (KOLUMNY per komórka) -----------------
        # populacja startowa: żyzne ziemie zaczynają ludniejsze, plus szczypta
        # losowości, żeby świat nie był sterylny. Wspólne dla obu trybów —
        # "ziemie niczyje żyją" tak samo jak reszta lądu.
        rng = np.random.default_rng(7)
        self.populacja = np.where(
            self.lad, 20 + 180 * self.zyznosc * rng.uniform(0.6, 1.0, n), 0
        ).astype(np.float32)

        # --- parametry sterowane przez graczy (per państwo/królestwo) -------
        self.podatek = np.full(self.n_panstw, 0.10, dtype=np.float32)  # 0..0.5

        # --- księgowość per państwo/królestwo --------------------------------
        self.skarbiec = np.zeros(self.n_panstw, dtype=np.float32)
        self.tick_nr = 0

    # ------------------------------------------------------------------------
    def _wczytaj_scenariusz(self, sciezka):
        """Wczytuje warstwę scenariusza historycznego (patrz scenariusz_800.py).
        Jednostką polityczną scenariusza jest ZIEMIA, nie proceduralny powiat —
        proceduralne powiaty/królestwa zostają w world.npz nietknięte, po
        prostu w tym trybie ich nie używamy."""
        dane = json.load(open(sciezka, encoding="utf-8"))
        self.tryb_scenariusza = True

        # kom_panstwo: startowy właściciel każdej komórki (-1 = ziemia niczyja
        # lub morze). To jedyna tablica per-komórka dot. własności — reszta
        # (kom_ziemia) to podział WEWNĄTRZ własności, nie sama własność.
        self.kom_panstwo = np.array(dane["kom_panstwo"], dtype=np.int32)
        self.kom_ziemia = np.array(dane["kom_ziemia"], dtype=np.int32)

        klucze_panstw = list(dane["panstwa"].keys())
        id_panstwa = {klucz: i for i, klucz in enumerate(klucze_panstw)}
        self.n_panstw = len(klucze_panstw)
        self.panstwo_gracz = 0
        self.panstwa = []
        for i, klucz in enumerate(klucze_panstw):
            p = dane["panstwa"][klucz]
            self.panstwa.append({
                "klucz": klucz,
                "nazwa_robocza": p["nazwa_robocza"],
                "nazwa_gry": p["nazwa_gry"],
                "kolor": p["kolor"],
                "wladca": p.get("wladca", {}),
                "gracz": bool(p.get("gracz", False)),
            })
            if p.get("gracz"):
                self.panstwo_gracz = i

        self.ziemie = dane["ziemie"]
        self.n_ziem = len(self.ziemie)
        self.ziemia_panstwo = np.array(
            [id_panstwa[z["panstwo"]] for z in self.ziemie], dtype=np.int32
        )

        self.kadr_startowy = dane.get("kadr_startowy")

    # ------------------------------------------------------------------------
    @property
    def wlasciciel_komorki(self):
        """Kto włada każdą komórką? -1 = nikt (ziemia niczyja albo morze).
        Tryb scenariusza: kolumna kom_panstwo wczytana ze scenariusza (i
        aktualizowana przy podboju ziemi). Tryb proceduralny: to samo, co
        zawsze — złożenie komorka -> powiat -> królestwo, jedna operacja
        NumPy, bez pętli."""
        if self.tryb_scenariusza:
            return self.kom_panstwo
        return np.where(
            self.komorka_pow >= 0,
            self.pow_krol[np.maximum(self.komorka_pow, 0)],
            -1,
        )

    # ------------------------------------------------------------------------
    def tick(self):
        """JEDEN KROK CZASU dla całego kontynentu. Zwróć uwagę: ani jednej
        pętli po komórkach — każda linijka działa na wszystkich 60-150 tys.
        komórek naraz. To jest cały sekret wydajności."""
        self.tick_nr += 1
        wlasc = self.wlasciciel_komorki           # (N,) państwo/królestwo każdej komórki (-1 = brak)
        maska_wl = wlasc >= 0
        idx_bezp = np.where(maska_wl, wlasc, 0)    # żeby indeksowanie nie wywaliło się na -1
        stawka = np.where(maska_wl, self.podatek[idx_bezp], 0.0).astype(np.float32)

        # --- DOCHÓD: ludzie × żyzność × stawka podatku ----------------------
        # Ziemie niczyje (i morze) mają stawkę 0 — nikt tam nie zbiera danin.
        dochod = self.populacja * self.zyznosc * stawka * 0.1

        # --- do skarbców: "posumuj dochody w grupach po właścicielu" --------
        # Tylko komórki Z właścicielem (maska_wl) — bincount nie lubi -1.
        dochod_panstwo = np.bincount(
            wlasc[maska_wl], weights=dochod[maska_wl], minlength=self.n_panstw
        ).astype(np.float32)
        self.skarbiec += dochod_panstwo

        # --- POPULACJA: wzrost logistyczny hamowany podatkiem ---------------
        # pojemność terenu zależy od żyzności; wysoki podatek dławi wzrost.
        # Rośnie WSZĘDZIE na lądzie (także bez właściciela — stawka tam = 0,
        # więc rośnie bez hamulca podatkowego). To jest właśnie zasada
        # "ziemie niczyje żyją": tło mapy nie jest martwe.
        pojemnosc = 50 + 450 * self.zyznosc
        tempo = 0.02 * (1 - 1.4 * stawka)
        self.populacja += np.where(
            self.lad,
            tempo * self.populacja * (1 - self.populacja / np.maximum(pojemnosc, 1)),
            0,
        ).astype(np.float32)
        np.clip(self.populacja, 0, None, out=self.populacja)

        if self.tryb_scenariusza:
            # --- agregaty per ZIEMIA (zamiast per powiat) --------------------
            maska_z = self.kom_ziemia >= 0
            ziemia_pop = np.bincount(
                self.kom_ziemia[maska_z], weights=self.populacja[maska_z], minlength=self.n_ziem
            ).astype(np.float32)
            ziemia_doch = np.bincount(
                self.kom_ziemia[maska_z], weights=dochod[maska_z], minlength=self.n_ziem
            ).astype(np.float32)
            # populacja lądu bez właściciela — dowód, że tło żyje (do panelu hover)
            niczyje_pop = float(self.populacja[self.lad & ~maska_wl].sum())
            return {
                "tick": self.tick_nr,
                "ziemia_pop": ziemia_pop,
                "ziemia_doch": ziemia_doch,
                "niczyje_pop": niczyje_pop,
                "skarbiec": self.skarbiec.copy(),
            }

        # --- agregaty do wyświetlenia (per powiat i per królestwo) ----------
        kp = self.komorka_pow[self.lad]
        pow_pop = np.bincount(kp, weights=self.populacja[self.lad], minlength=self.n_pow).astype(np.float32)
        pow_doch = np.bincount(kp, weights=dochod[self.lad], minlength=self.n_pow).astype(np.float32)

        return {
            "tick": self.tick_nr,
            "pow_pop": pow_pop,
            "pow_doch": pow_doch,
            "krol_doch": dochod_panstwo,
            "skarbiec": self.skarbiec.copy(),
        }

    # ------------------------------------------------------------------------
    def wykonaj_akcje(self, akcja: dict):
        """Rozkazy gracza. Zwraca opis zmiany (do rozgłoszenia) albo None.
        Zauważ wzorzec: akcje NIE grzebią w stanie ekonomicznym bezpośrednio —
        zmieniają parametry lub przypisania, a skutki policzy najbliższy tick."""
        typ = akcja.get("typ")

        if typ == "podatek":
            p = akcja.get("panstwo", akcja.get("krolestwo"))
            if p is None or not (0 <= int(p) < self.n_panstw):
                return None
            p = int(p)
            self.podatek[p] = float(np.clip(akcja["stawka"], 0.0, 0.5))
            return {
                "typ": "podatek", "panstwo": p, "krolestwo": p,
                "stawka": round(float(self.podatek[p]), 3),
            }

        if typ == "podboj":
            if self.tryb_scenariusza:
                # Podbój ZIEMI (nie powiatu) — zmiana właściciela to zmiana
                # jednej liczby w ziemia_panstwo, plus przemalowanie jej
                # komórek maską (nadal zero pętli po komórkach).
                z = akcja.get("ziemia")
                p = akcja.get("panstwo")
                if z is None or p is None:
                    return None
                z, p = int(z), int(p)
                # Ziemia niczyja (klient wysyła -1 — tyle warta jest tam
                # "jednostka") nie jest jeszcze zdobywalna: zajmowanie pustki
                # to osobna, późniejsza mechanika. Rozkaz NIE ma ginąć po
                # cichu — gracz ma dostać wprost informację, że to odmowa,
                # nie usterka.
                if z < 0:
                    return {
                        "typ": "odmowa",
                        "powod": "ziemi niczyjej nie można podbić — to osobna mechanika",
                    }
                if not (0 <= z < self.n_ziem and 0 <= p < self.n_panstw):
                    return None
                self.ziemia_panstwo[z] = p
                self.kom_panstwo[self.kom_ziemia == z] = p
                return {"typ": "podboj", "ziemia": z, "panstwo": p}

            # Zmiana właściciela powiatu = zmiana JEDNEJ liczby w tablicy.
            # Granice na mapie przerysują się same, bo klient wylicza je
            # z przypisań — dokładnie jak w naszym demie SVG.
            pw = akcja.get("powiat")
            k = akcja.get("krolestwo")
            if pw is None or k is None:
                return None
            pw, k = int(pw), int(k)
            if 0 <= pw < self.n_pow and 0 <= k < self.n_krol:
                self.pow_krol[pw] = k
                return {"typ": "podboj", "powiat": pw, "krolestwo": k}
            return None

        return None


# ----------------------------------------------------------------------------
# Mini-test balansu bez żadnego serwera: uruchom  python sim.py
# To jest ta supermoc oddzielenia symulacji od reszty — eksperymentujesz
# z formułami w sekundę, bez klikania po interfejsie.
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    s = Swiat()

    if s.tryb_scenariusza:
        s.podatek[s.panstwo_gracz] = 0.20
        for _ in range(300):
            wynik = s.tick()
        print(f"Scenariusz — po {wynik['tick']} tickach:")
        for i, p in enumerate(s.panstwa):
            print(
                f"  {p['nazwa_gry']:<20} podatek {s.podatek[i]:.2f}"
                f"  skarbiec {s.skarbiec[i]:>12.0f}"
            )
        print(f"  {'ziemie niczyje':<20} populacja razem {wynik['niczyje_pop']:>12.0f}")
    else:
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
