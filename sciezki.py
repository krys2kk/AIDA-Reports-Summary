"""Ścieżki aplikacji działające zarówno przy uruchomieniu ze źródeł,
jak i ze zbudowanego pliku .exe (PyInstaller).

W trybie .exe (onefile) pliki źródłowe są rozpakowywane do katalogu
tymczasowego kasowanego po zamknięciu programu - dlatego dane trwałe
(ulubione, ustawienia) muszą trafiać do katalogu, w którym leży sam
plik .exe, a zasoby dołączone do paczki (logo) czyta się z katalogu
rozpakowania (sys._MEIPASS).
"""

from __future__ import annotations

import sys
from pathlib import Path


def katalog_aplikacji() -> Path:
    """Katalog na dane trwałe: obok .exe (frozen) lub obok źródeł."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def zasob(nazwa: str) -> Path:
    """Ścieżka do zasobu dołączonego do aplikacji (np. logo)."""
    baza = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return baza / nazwa
