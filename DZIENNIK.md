# DZIENNIK.md — dziennik zmian (skrótowo, po ludzku)

## 2026-07-18 — zadanie 0001: podpięcie scenariusza 800 (Kent i Sussex)

Co zrobione: `sim.py` umie teraz wystartować z warstwą scenariusza
(`scenariusz_800.json`, jeśli plik istnieje obok) — wtedy jednostką
polityczną jest ZIEMIA, a nie proceduralny powiat, i gracz gra Cantią.
Bez pliku scenariusza świat działa dokładnie jak wcześniej (proceduralne
powiaty/królestwa) — sprawdzone ręcznie przez tymczasowe przeniesienie
`scenariusz_800.json` i porównanie działania serwera/klienta w obu trybach.
`server.py` dorzuca `kom_ziemia` do protokołu binarnego (zawsze, w obu
trybach — jeden protokół, zero rozgałęzień po stronie parsowania) i
rozgłasza agregaty per ziemia zamiast per powiat, gdy scenariusz aktywny.
`static/index.html` przepisany na generyczne pojęcia "jednostka"/"właściciel"
(ziemia+państwo w scenariuszu, powiat+królestwo proceduralnie) — jeden kod
renderujący dla obu trybów. `scenariusz_800.py` liczy teraz `kadr_startowy`
(bbox obu państw w px płótna) z geografii komórek, nie ze stałych generatora.
Dopisano `test_scenariusz.py` (5 kryteriów z brief-u) — przechodzi.

Co zaskoczyło: `/api/meta` pierwotnie zwracał właściciela każdej ziemi ze
STATYCZNEGO zapisu scenariusza (`swiat.ziemie[i]["panstwo"]`), a nie z żywej
tablicy `ziemia_panstwo`, którą zmienia podbój. Efekt: gracz łączący się
PO czyimś podboju widział starą własność ziemi, dopóki nie nadszedł kolejny
podbój na jego oczach. Znalezione dopiero przy teście end-to-end w
przeglądarce (Playwright) — konkretnie przy odświeżeniu strony po podboju.
Naprawione: `/api/meta` liczy `panstwo` z `swiat.ziemia_panstwo[i]` na
żywo; klient dostaje już gotowy indeks (nie trzeba mapować klucza państwa
po stronie przeglądarki). Druga rzecz: sandboxowe `bash` w tej sesji potrafiło
zwracać mylący kod wyjścia (144) dla poleceń z `&`/`setsid`/`pkill` mimo że
polecenie faktycznie się wykonało — testowanie przez `ps`/`ls` zamiast ufania
kodowi wyjścia.
