"""Wczytywanie folderu z wieloma raportami i agregacja ich w profile komputerów
(jeden plik = jeden komputer = jeden przyszły wiersz tabeli Excel)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from parser import KluczPola, OBSLUGIWANE_ROZSZERZENIA, parse_report

# AIDA64 nazywa te pola w nagłówku raportu różnie w zależności od języka
# interfejsu, z jakiego wygenerowano plik (np. polski eksport .txt vs
# angielski eksport .htm) - stąd kilka wariantów do sprawdzenia po kolei.
_KLUCZE_NAZWY_KOMPUTERA = ("Komputer", "Computer")
_KLUCZE_SYSTEMU = ("System operacyjny", "Operating System")


def _pierwsza_pasujaca(meta: dict, klucze: tuple[str, ...], domyslna: str) -> str:
    for klucz in klucze:
        if meta.get(klucz):
            return meta[klucz]
    return domyslna


@dataclass
class ProfilKomputera:
    zrodlo: Path
    nazwa_komputera: str
    system_operacyjny: str
    wartosci: dict[KluczPola, str] = field(default_factory=dict)


def wczytaj_folder(
    folder: Path, postep=None
) -> tuple[list[ProfilKomputera], list[tuple[Path, str]]]:
    """Parsuje wszystkie obsługiwane pliki bezpośrednio w danym folderze
    (bez zagłębiania się w podfoldery).

    Zwraca (profile, bledy). Błąd pojedynczego pliku nie przerywa wczytywania
    pozostałych - jest zbierany do listy `bledy` jako (ścieżka, komunikat).

    `postep` (opcjonalny) to funkcja (numer, lacznie, nazwa_pliku) wywoływana
    przed parsowaniem każdego pliku - do aktualizacji paska postępu w GUI.
    """
    profile: list[ProfilKomputera] = []
    bledy: list[tuple[Path, str]] = []

    pliki = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in OBSLUGIWANE_ROZSZERZENIA
    )

    for numer, sciezka in enumerate(pliki, start=1):
        if postep:
            postep(numer, len(pliki), sciezka.name)
        try:
            parsed = parse_report(sciezka)
        except Exception as exc:
            bledy.append((sciezka, str(exc)))
            continue

        wartosci_listy: dict[KluczPola, list[str]] = {}
        for rec in parsed.records:
            wartosci_listy.setdefault(rec.klucz, []).append(rec.wartosc)

        # Wiele wystąpień tego samego pola (np. kilka kart sieciowych) trafia
        # do jednej komórki, połączone średnikiem - bez powtarzania identycznych
        # wartości, ale z zachowaniem kolejności wystąpienia w pliku.
        wartosci = {
            klucz: "; ".join(dict.fromkeys(lista))
            for klucz, lista in wartosci_listy.items()
        }

        profile.append(
            ProfilKomputera(
                zrodlo=sciezka,
                nazwa_komputera=_pierwsza_pasujaca(parsed.meta, _KLUCZE_NAZWY_KOMPUTERA, sciezka.stem),
                system_operacyjny=_pierwsza_pasujaca(parsed.meta, _KLUCZE_SYSTEMU, ""),
                wartosci=wartosci,
            )
        )

    return profile, bledy


def zbierz_dostepne_pola(profile: list[ProfilKomputera]) -> list[KluczPola]:
    """Zwraca listę unikalnych kluczy pól napotkanych w co najmniej jednym
    profilu, w kolejności pierwszego wystąpienia w plikach."""
    widziane: dict[KluczPola, None] = {}
    for profil in profile:
        for klucz in profil.wartosci:
            widziane.setdefault(klucz, None)
    return list(widziane.keys())
