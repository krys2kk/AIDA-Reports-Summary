"""Trwałe drobne ustawienia aplikacji (np. ostatni katalog zapisu raportu).

Zapisywane w jednym stałym katalogu w profilu użytkownika (zobacz
sciezki.katalog_aplikacji) - niezależnie od tego, gdzie aktualnie leży
uruchamiany plik .exe. Przy odczycie sprawdzane są też stare lokalizacje
(obok .exe), w których poprzednia wersja programu trzymała te dane.
"""

from __future__ import annotations

import json
from pathlib import Path

from sciezki import katalog_aplikacji, stare_lokalizacje_danych

_NAZWA_PLIKU = "ustawienia.json"
_PLIK_APLIKACJI = katalog_aplikacji() / _NAZWA_PLIKU


def wczytaj_ustawienia() -> dict:
    kandydaci: list[Path] = [_PLIK_APLIKACJI]
    kandydaci += [k / _NAZWA_PLIKU for k in stare_lokalizacje_danych()]

    for sciezka in kandydaci:
        try:
            if sciezka.exists():
                dane = json.loads(sciezka.read_text(encoding="utf-8"))
                if isinstance(dane, dict):
                    return dane
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def zapisz_ustawienia(ustawienia: dict) -> None:
    tekst = json.dumps(ustawienia, ensure_ascii=False, indent=2)
    _PLIK_APLIKACJI.write_text(tekst, encoding="utf-8")
