"""Trwałe drobne ustawienia aplikacji (np. ostatni katalog zapisu raportu).

Zapisywane w JSON obok aplikacji; gdy katalog aplikacji jest tylko do
odczytu, używany jest plik w katalogu domowym użytkownika.
"""

from __future__ import annotations

import json
from pathlib import Path

from sciezki import katalog_aplikacji

_PLIK_APLIKACJI = katalog_aplikacji() / "ustawienia.json"
_PLIK_DOMOWY = Path.home() / ".raporty_aida64_ustawienia.json"


def wczytaj_ustawienia() -> dict:
    for sciezka in (_PLIK_APLIKACJI, _PLIK_DOMOWY):
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
    try:
        _PLIK_APLIKACJI.write_text(tekst, encoding="utf-8")
    except OSError:
        try:
            _PLIK_DOMOWY.write_text(tekst, encoding="utf-8")
        except OSError:
            pass
