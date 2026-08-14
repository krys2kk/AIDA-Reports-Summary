"""Ścieżki aplikacji działające zarówno przy uruchomieniu ze źródeł,
jak i ze zbudowanego pliku .exe (PyInstaller).

Dane trwałe (ulubione, ustawienia) NIE są zapisywane obok pliku .exe, bo
użytkownicy kopiują sam .exe (np. na pulpit, na pendrive) - gdyby dane
trwałe trzymały się katalogu, w którym akurat leży .exe, każda taka kopia
zaczynałaby z pustymi ulubionymi/ustawieniami zamiast korzystać z tych już
zapisanych. Zamiast tego używany jest jeden stały katalog w profilu
użytkownika (%LOCALAPPDATA%), niezależny od tego, gdzie użytkownik aktualnie
trzyma/uruchamia sam plik .exe.

W trybie .exe (onefile) pliki źródłowe są dodatkowo rozpakowywane do
katalogu tymczasowego kasowanego po zamknięciu programu - zasoby dołączone
do paczki (logo) czyta się stamtąd (sys._MEIPASS), co nie ma nic wspólnego
z lokalizacją danych trwałych opisaną wyżej.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_NAZWA_KATALOGU = "RaportyAIDA64"


def katalog_aplikacji() -> Path:
    """Stały katalog na dane trwałe (ulubione, ustawienia) - ten sam
    niezależnie od tego, skąd aktualnie uruchamiany jest program."""
    baza = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    katalog = baza / _NAZWA_KATALOGU
    katalog.mkdir(parents=True, exist_ok=True)
    return katalog


def stare_lokalizacje_danych() -> list[Path]:
    """Miejsca, w których poprzednia wersja programu trzymała dane trwałe
    (obok uruchamianego pliku) - sprawdzane jako fallback przy odczycie,
    żeby istniejące ulubione/ustawienia nie "zniknęły" po tej zmianie."""
    if getattr(sys, "frozen", False):
        return [Path(sys.executable).resolve().parent]
    return [Path(__file__).resolve().parent]


def zasob(nazwa: str) -> Path:
    """Ścieżka do zasobu dołączonego do aplikacji (np. logo)."""
    baza = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return baza / nazwa
