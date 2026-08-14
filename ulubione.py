"""Trwałe przechowywanie ulubionych pól i ulubionych całych sekcji.

Ulubione zapisywane są w jednym stałym katalogu w profilu użytkownika
(zobacz sciezki.katalog_aplikacji) - niezależnie od tego, gdzie aktualnie
leży uruchamiany plik .exe, więc kopiowanie/przenoszenie .exe (np. na
pulpit, na pendrive) nie zeruje ulubionych. Przy odczycie sprawdzane są
też stare lokalizacje (obok .exe), w których poprzednia wersja programu
trzymała te dane, żeby nic nie "zniknęło" po tej zmianie.

Format pliku: lista wpisów; wpis z kluczem "pole" to ulubione pojedyncze
pole, wpis z samą "sekcja" to ulubiona cała sekcja (starszy, nieużywany już
do zapisu format - zachowany tylko dla wstecznej zgodności odczytu).
"""

from __future__ import annotations

import json
from pathlib import Path

from parser import KluczPola
from sciezki import katalog_aplikacji, stare_lokalizacje_danych

_NAZWA_PLIKU = "ulubione.json"
_PLIK_APLIKACJI = katalog_aplikacji() / _NAZWA_PLIKU


def _plik_do_odczytu() -> Path | None:
    if _PLIK_APLIKACJI.exists():
        return _PLIK_APLIKACJI
    for katalog in stare_lokalizacje_danych():
        sciezka = katalog / _NAZWA_PLIKU
        if sciezka.exists():
            return sciezka
    return None


def wczytaj_ulubione() -> tuple[set[KluczPola], set[str]]:
    """Zwraca (ulubione_pola, ulubione_sekcje)."""
    sciezka = _plik_do_odczytu()
    if sciezka is None:
        return set(), set()
    try:
        dane = json.loads(sciezka.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(), set()

    pola: set[KluczPola] = set()
    sekcje: set[str] = set()
    for w in dane:
        if not isinstance(w, dict) or "sekcja" not in w:
            continue
        if "pole" in w:
            pola.add(KluczPola(w["sekcja"], w.get("podsekcja", ""), w["pole"]))
        else:
            sekcje.add(w["sekcja"])
    return pola, sekcje


def zapisz_ulubione(pola: set[KluczPola], sekcje: set[str]) -> None:
    dane: list[dict] = [{"sekcja": s} for s in sorted(sekcje)]
    dane += [
        {"sekcja": k.sekcja, "podsekcja": k.podsekcja, "pole": k.pole}
        for k in sorted(pola, key=lambda k: (k.sekcja, k.podsekcja, k.pole))
    ]
    tekst = json.dumps(dane, ensure_ascii=False, indent=2)
    _PLIK_APLIKACJI.write_text(tekst, encoding="utf-8")
