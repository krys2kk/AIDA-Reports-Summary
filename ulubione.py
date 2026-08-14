"""Trwałe przechowywanie ulubionych pól i ulubionych całych sekcji.

Ulubione zapisywane są w pliku JSON obok aplikacji (narzędzie jest
instalowane na stałe na komputerach firmowych, więc ulubione są wspólne
dla danej instalacji). Gdy katalog aplikacji jest tylko do odczytu,
używany jest plik w katalogu domowym użytkownika.

Format pliku: lista wpisów; wpis z kluczem "pole" to ulubione pojedyncze
pole, wpis z samą "sekcja" to ulubiona cała sekcja.
"""

from __future__ import annotations

import json
from pathlib import Path

from parser import KluczPola
from sciezki import katalog_aplikacji

_NAZWA_PLIKU = "ulubione.json"
_PLIK_APLIKACJI = katalog_aplikacji() / _NAZWA_PLIKU
_PLIK_DOMOWY = Path.home() / ".raporty_aida64_ulubione.json"


def _plik_do_odczytu() -> Path | None:
    for sciezka in (_PLIK_APLIKACJI, _PLIK_DOMOWY):
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
    try:
        _PLIK_APLIKACJI.write_text(tekst, encoding="utf-8")
    except OSError:
        _PLIK_DOMOWY.write_text(tekst, encoding="utf-8")
