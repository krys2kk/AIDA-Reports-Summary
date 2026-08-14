"""Parsowanie raportów konfiguracji komputera (AIDA64) z plików .txt, .html,
.mhtml, .xml i .csv do ogólnej, hierarchicznej listy rekordów
(sekcja główna › podsekcja › pole = wartość).

W odróżnieniu od wcześniejszej wersji, parser NIE ogranicza się do z góry
ustalonej listy pól - obsługuje pełne raporty AIDA64 Extreme, które mogą
zawierać dowolną liczbę sekcji (Procesor, Pamięć, BIOS, Przetaktowanie,
Czujnik, drzewo sterowników Windows itd.) i pól. To, które pola trafią do
raportu Excel, wybiera użytkownik w GUI spośród wszystkiego, co zostało
znalezione w wczytanych plikach.

Format .txt jest odwzorowany na podstawie realnej struktury raportów AIDA64:
sekcji głównych "--------[ Nazwa ]---..." oraz zagnieżdżonych w nich
podnagłówków zakończonych dwukropkiem (np. "Komputer:", "Właściwości
urządzenia:"). Parsery .html/.mhtml/.xml/.csv są implementacjami najlepszego
przybliżenia (AIDA64 nie ma jednego ustalonego schematu eksportu dla tych
formatów) - jeśli po podłączeniu realnego pliku okaże się, że coś nie jest
wykrywane, wystarczy doprecyzować odpowiednią funkcję parse_* poniżej.
"""

from __future__ import annotations

import csv
import email
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

from bs4 import BeautifulSoup

from slownik import przetlumacz

OBSLUGIWANE_ROZSZERZENIA = (".txt", ".html", ".htm", ".mhtml", ".mht", ".xml", ".csv")


_CHARSET_RE = re.compile(rb"charset\s*=\s*[\"']?([\w-]+)", re.IGNORECASE)
_ALIASY_KODOWAN = {
    "iso-8859-1": "cp1252",
    "iso8859-1": "cp1252",
    "latin1": "cp1252",
    "latin-1": "cp1252",
    "windows-1250": "cp1250",
    "windows-1252": "cp1252",
}


def _zdeklarowane_kodowanie(surowe: bytes) -> str | None:
    """Odczytuje kodowanie zadeklarowane w nagłówku pliku HTML/XML, np.
    <META HTTP-EQUIV="Content-Type" CONTENT="text/html; CHARSET=Windows-1250">
    - AIDA64 eksportuje różne pliki z różnym zadeklarowanym kodowaniem
    (spotykane: iso-8859-1, Windows-1250), więc trzeba je respektować
    zamiast zgadywać po omacku."""
    m = _CHARSET_RE.search(surowe[:4096])
    if not m:
        return None
    nazwa = m.group(1).decode("ascii", errors="ignore").strip().lower()
    return _ALIASY_KODOWAN.get(nazwa, nazwa)


def _wczytaj_tekst(path: Path) -> str:
    """Wczytuje plik wykrywając kodowanie po BOM lub deklaracji w nagłówku.

    Eksporty AIDA64 na polskich Windowsach bywają zapisane w UTF-16
    (typowo z BOM FF FE) albo w jednobajtowym kodowaniu zadeklarowanym w
    nagłówku HTML (iso-8859-1, Windows-1250...) - nie zawsze UTF-8, stąd
    konieczność wykrywania kodowania zamiast zakładania go na sztywno.
    """
    surowe = path.read_bytes()

    if surowe.startswith(b"\xff\xfe") or surowe.startswith(b"\xfe\xff"):
        return surowe.decode("utf-16")
    if surowe.startswith(b"\xef\xbb\xbf"):
        return surowe.decode("utf-8-sig")

    # Jeśli plik SAM deklaruje swoje kodowanie (typowe dla .html/.xml z
    # AIDA64), ufamy tej deklaracji bezpośrednio - to najpewniejsze źródło
    # prawdy. Ktoś, kto ustawia to jako "konkurs" z innymi kodowaniami wg
    # liczby znaków zastępczych, może wybrać NIEWŁAŚCIWE kodowanie tylko
    # dlatego, że plik ma gdzieś pojedynczy uszkodzony bajt: np. plik
    # zadeklarowany jako cp1250 z jednym złym bajtem (1 podstawienie po
    # naprawie) przegrywał z cp1252, który "przypadkiem" miał mniej
    # podstawień ogółem, ale błędnie dekodował inne, poprawne polskie
    # znaki. errors="replace" na deklarowanym kodowaniu naprawia tylko ten
    # pojedynczy zepsuty bajt, nie psując reszty pliku.
    deklarowane = _zdeklarowane_kodowanie(surowe)
    if deklarowane:
        try:
            return surowe.decode(deklarowane)
        except UnicodeDecodeError:
            return surowe.decode(deklarowane, errors="replace")
        except LookupError:
            pass

    for kodowanie in ("utf-8", "cp1250", "cp1252"):
        try:
            return surowe.decode(kodowanie)
        except UnicodeDecodeError:
            continue

    # Żadne kodowanie nie zdekodowało pliku w 100% bezstratnie i brak
    # deklaracji w nagłówku - zamiast poddawać się od razu na rzecz UTF-8
    # z podstawianiem (co zamienia WSZYSTKIE polskie znaki na "�", bo żaden
    # z nich nie jest poprawnym bajtem UTF-8), wybieramy kandydata
    # dającego najmniej takich podstawień.
    def _liczba_zastapien(kodowanie: str) -> int:
        return surowe.decode(kodowanie, errors="replace").count("�")

    najlepsze = min(("utf-8", "cp1250", "cp1252"), key=_liczba_zastapien)
    return surowe.decode(najlepsze, errors="replace")


@dataclass(frozen=True)
class KluczPola:
    """Unikalny identyfikator kolumny: sekcja główna › podsekcja › pole."""

    sekcja: str
    podsekcja: str
    pole: str

    @property
    def etykieta(self) -> str:
        czesci = [c for c in (self.podsekcja, self.pole) if c]
        return " › ".join(czesci) if czesci else self.pole


@dataclass
class Record:
    klucz: KluczPola
    wartosc: str


@dataclass
class ParsedReport:
    zrodlo: Path
    meta: dict = field(default_factory=dict)
    records: list[Record] = field(default_factory=list)


def parse_report(path: str | Path) -> ParsedReport:
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        tekst = _wczytaj_tekst(path)
        meta, surowe = _parse_txt_lines(tekst.splitlines())
    elif suffix in (".html", ".htm"):
        soup = _zbuduj_soup(_wczytaj_tekst(path))
        meta, surowe = _parse_html_soup(soup)
    elif suffix in (".mhtml", ".mht"):
        soup = _zbuduj_soup(_wyciagnij_html_z_mhtml(path))
        meta, surowe = _parse_html_soup(soup)
    elif suffix == ".xml":
        meta, surowe = _parse_xml(_wczytaj_tekst(path))
    elif suffix == ".csv":
        meta, surowe = _parse_csv(_wczytaj_tekst(path))
    else:
        raise ValueError(
            f"Nieobsługiwany format pliku: {suffix}. "
            f"Obsługiwane: {', '.join(OBSLUGIWANE_ROZSZERZENIA)}"
        )

    records = [
        Record(KluczPola(sekcja, podsekcja, pole), wartosc)
        for sekcja, podsekcja, pole, wartosc in map(_normalizuj_gniazda, surowe)
    ]
    return ParsedReport(zrodlo=path, meta=meta, records=records)


# AIDA64 wkleja nazwę zainstalowanego modułu pamięci w NAZWĘ pola lub
# podsekcji (np. pole "DIMM1: Kingston 9905403-170.A00LF", podsekcja
# "[ DIMM1: Lexar LD4BU016G-3200XG ]" w SPD). Przez to każdy komputer
# tworzyłby własny, niescalalny klucz kolumny. Normalizujemy klucz do
# samego gniazda ("DIMM1"), a nazwę modułu przenosimy do wartości -
# żadna informacja nie ginie, a kolumny z różnych komputerów się scalają.
_GNIAZDO_RE = re.compile(r"^((?:SO-?)?DIMM\s*\d+)\s*:\s*(\S.*)$", re.IGNORECASE)


def _normalizuj_gniazda(rekord):
    sekcja, podsekcja, pole, wartosc = rekord

    m = _GNIAZDO_RE.match(podsekcja)
    if m:
        podsekcja = m.group(1)

    m = _GNIAZDO_RE.match(pole)
    if m:
        pole = m.group(1)
        wartosc = f"{m.group(2)} — {wartosc}"

    # Ujednolicenie języka: raporty z angielskiej wersji AIDA64 dostają
    # polskie nazwy, żeby scalały kolumny z raportami polskimi.
    sekcja, podsekcja, pole = przetlumacz(sekcja, podsekcja, pole)

    return sekcja, podsekcja, pole, wartosc


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^-{2,}\[\s*(.*?)\s*\]-{2,}\s*$")
_FIELD_RE = re.compile(r"^\s*(\S.*?)\s{2,}(\S.*?)\s*$")
# Podnagłówek (np. "Komputer:", "Właściwości urządzenia:") zagnieżdżony
# w sekcji głównej - bez wielospacjowej wartości, to odróżnia go od pola.
_PODSEKCJA_RE = re.compile(r"^\s*([^\s].*?):\s*$")


def _parse_txt_lines(lines):
    surowe = []
    meta = {}
    glowna_sekcja = None
    pod_sekcja = ""
    pierwsza_sekcja = None

    for raw in lines:
        linia = raw.rstrip("\n").rstrip("\r")
        if not linia.strip():
            continue

        m = _SECTION_RE.match(linia)
        if m:
            glowna_sekcja = m.group(1).strip()
            pod_sekcja = ""
            if pierwsza_sekcja is None:
                pierwsza_sekcja = glowna_sekcja
            continue

        m = _FIELD_RE.match(linia)
        if m and glowna_sekcja:
            pole, wartosc = m.group(1).strip(), m.group(2).strip()
            surowe.append((glowna_sekcja, pod_sekcja, pole, wartosc))
            if glowna_sekcja == pierwsza_sekcja:
                meta[pole] = wartosc
            continue

        m = _PODSEKCJA_RE.match(linia)
        if m and glowna_sekcja:
            pod_sekcja = m.group(1).strip()

    return meta, surowe


# ---------------------------------------------------------------------------
# HTML / MHTML
# ---------------------------------------------------------------------------

_META_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?[\w-]+", re.IGNORECASE)


def _zbuduj_soup(tekst: str) -> BeautifulSoup:
    """Buduje drzewo BeautifulSoup z już poprawnie zdekodowanego tekstu.

    KRYTYCZNE: trzeba najpierw usunąć deklarację "charset=..." z nagłówka
    <meta>. Tekst przekazywany tu jest CZYSTYM unicode (już poprawnie
    zdekodowanym przez _wczytaj_tekst) - ale lxml/libxml2 samo wykrywa tę
    deklarację i dla części zawartości próbuje ją ponownie zastosować,
    efektywnie dekodując fragmenty tekstu drugi raz. Dla plików z
    deklaracją inną niż UTF-8 (np. Windows-1250) psuje to losowo część
    polskich znaków w wyniku (obserwowane realnie: "Urządzenia" →
    "UrzÄ…dzenia"), tworząc pozornie zdublowane kategorie o tej samej
    treści. Usunięcie deklaracji eliminuje tę drugą, zbędną reinterpretację
    - dokładnie tak samo jak _parse_xml usuwa deklarację encoding z XML.
    """
    tekst_bez_deklaracji = _META_CHARSET_RE.sub("charset=utf-8", tekst, count=1)
    return BeautifulSoup(tekst_bez_deklaracji, "lxml")


def _wyciagnij_html_z_mhtml(path: Path) -> str:
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    czesci = msg.walk() if msg.is_multipart() else [msg]
    for part in czesci:
        if part.get_content_type() == "text/html":
            return part.get_content()

    raise ValueError("Nie znaleziono treści HTML w pliku MHTML.")


def _wyczysc_naglowek_html(tekst: str) -> str:
    tekst = tekst.strip()
    if tekst.startswith("[") and tekst.endswith("]"):
        tekst = tekst[1:-1].strip()
    return tekst.rstrip(":").strip()


def _parse_html_soup(soup: BeautifulSoup):
    # Realny eksport AIDA64 do HTML NIE ma jednej zgrabnej tabeli na sekcję:
    # każdy wiersz to <TR> z kilkoma pustymi <TD> na wcięcie, po których
    # następują dokładnie dwie znaczące komórki (pole, wartość) - np.
    # "<TR><TD><TD><TD>Version&nbsp;&nbsp;<TD>AIDA64 v7.40.7100". Dlatego
    # bierzemy dwie OSTATNIE niepuste komórki, a nie komorki[0] (ta zawsze
    # jest pustym wcięciem, co wcześniej powodowało odrzucanie każdego
    # wiersza jako "pole puste").
    #
    # Sekcje główne są oznaczone komórką <TD CLASS=pt>Nazwa</TD> (odpowiednik
    # "--------[ Nazwa ]---" z .txt). Zarówno podnagłówki w nawiasach
    # ("[ BIOS ]"), jak i pogrubione podnagłówki zakończone dwukropkiem
    # ("BIOS Properties:") trafiają w wierszu jako jedyna niepusta komórka -
    # tak samo jak "Nazwa:" w .txt - i aktualizują (nadpisując) podsekcję.
    #
    # UWAGA: <TD CLASS=pt> w tym (nieprawidłowym) HTML-u NIE jest owinięty
    # w <TR> - parser (lxml) zostawia go jako bezpośrednie dziecko <TABLE>.
    # Dlatego trzeba iterować <tr> i <td> razem, w kolejności dokumentu,
    # zamiast tylko po <tr> (inaczej nagłówki sekcji głównych są niewidoczne).
    surowe = []
    meta = {}
    glowna_sekcja = None
    pod_sekcja = ""
    pierwsza_sekcja = None

    for el in soup.find_all(["tr", "td"]):
        if el.name == "td":
            if el.parent is not None and el.parent.name == "tr":
                continue  # zwykła komórka - obsłużona przy rodzicu <tr>
            if "pt" not in (el.get("class") or []):
                continue
            tekst = el.get_text(strip=True)
            if tekst:
                glowna_sekcja = tekst
                pod_sekcja = ""
                if pierwsza_sekcja is None:
                    pierwsza_sekcja = glowna_sekcja
            continue

        komorki_tagi = el.find_all(["td", "th"])
        if not komorki_tagi:
            continue

        komorki = [c.get_text(strip=True) for c in komorki_tagi]
        niepuste = [c for c in komorki if c]
        if not niepuste:
            continue

        if len(niepuste) == 1:
            pod_sekcja = _wyczysc_naglowek_html(niepuste[0])
            continue

        if not glowna_sekcja:
            continue

        pole, wartosc = niepuste[-2], niepuste[-1]
        surowe.append((glowna_sekcja, pod_sekcja, pole, wartosc))
        if glowna_sekcja == pierwsza_sekcja:
            meta[pole] = wartosc

    return meta, surowe


# ---------------------------------------------------------------------------
# XML
# ---------------------------------------------------------------------------

def _etykieta(el: ET.Element) -> str:
    return el.get("name") or el.get("Name") or el.tag


def _wartosc_elementu(el: ET.Element) -> str:
    if el.text and el.text.strip():
        return el.text.strip()
    return (el.get("value") or el.get("Value") or "").strip()


_XML_DEKLARACJA_RE = re.compile(r"^\s*<\?xml[^>]*\?>")


def _parse_xml(tekst: str):
    # ET.fromstring nie akceptuje deklaracji z "encoding=" w już
    # zdekodowanym stringu (Python zgłasza ValueError), więc ją usuwamy -
    # kodowanie zostało już rozstrzygnięte wcześniej przez _wczytaj_tekst.
    tekst = _XML_DEKLARACJA_RE.sub("", tekst, count=1)
    root = ET.fromstring(tekst)

    surowe = []
    meta = {}
    pierwsza_sekcja = None

    for sekcja_el in root:
        dzieci = list(sekcja_el)
        if not dzieci:
            continue

        sekcja = _etykieta(sekcja_el)
        if pierwsza_sekcja is None:
            pierwsza_sekcja = sekcja

        for item in dzieci:
            if list(item):
                continue
            pole = _etykieta(item)
            wartosc = _wartosc_elementu(item)
            if not wartosc:
                continue
            surowe.append((sekcja, "", pole, wartosc))
            if sekcja == pierwsza_sekcja:
                meta[pole] = wartosc

    return meta, surowe


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def _parse_csv(tekst: str):
    surowe = []
    meta = {}
    aktualna_sekcja = None
    pierwsza_sekcja = None

    probka = tekst[:4096]
    try:
        dialekt = csv.Sniffer().sniff(probka, delimiters=";,\t")
    except csv.Error:
        dialekt = csv.excel
        dialekt.delimiter = ";" if probka.count(";") >= probka.count(",") else ","

    for row in csv.reader(io.StringIO(tekst), dialekt):
        komorki = [c.strip() for c in row]
        niepuste = [c for c in komorki if c]
        if not niepuste:
            continue

        if len(niepuste) == 1:
            aktualna_sekcja = niepuste[0]
            if pierwsza_sekcja is None:
                pierwsza_sekcja = aktualna_sekcja
            continue

        pole = komorki[0]
        wartosc = " ".join(c for c in komorki[1:] if c).strip()
        if not pole or not wartosc:
            continue

        sekcja = aktualna_sekcja or "Inne"
        surowe.append((sekcja, "", pole, wartosc))
        if sekcja == pierwsza_sekcja:
            meta[pole] = wartosc

    return meta, surowe
