# AIDA Reports Summary

Aplikacja desktopowa (Python + tkinter) do generowania zbiorczego raportu Excel
z wielu raportów konfiguracji komputerów wygenerowanych przez **AIDA64**
(Engineer / Extreme). Zamiast przeglądać dziesiątki osobnych plików `.txt` /
`.html`, wskazujesz folder z raportami, wybierasz interesujące pola, a
program tworzy jeden arkusz Excel: **jeden wiersz = jeden komputer**.

## Funkcje

- **Wiele formatów wejściowych**: `.txt`, `.html` / `.htm`, `.mhtml` / `.mht`,
  `.xml`, `.csv` - w tym prawdziwa (nieco "krzywa") struktura HTML/TXT
  eksportowana realnie przez AIDA64, a nie wyidealizowany format.
- **Przetwarzanie całego folderu naraz** - każdy plik traktowany jest jako
  osobny komputer i staje się jednym wierszem w wynikowej tabeli.
- **Scalanie kolumn PL/EN** - raporty z polskiej i angielskiej wersji AIDA64
  (np. "System operacyjny" i "Operating System") są automatycznie mapowane
  na wspólne, polskie nazwy kolumn (`slownik.py`), więc dane z różnych
  komputerów trafiają do tych samych kolumn zamiast się duplikować.
- **Normalizacja gniazd pamięci** - pola typu `DIMM1: Kingston ...` są
  sprowadzane do wspólnego klucza `DIMM1`, a nazwa modułu trafia do wartości
  (bez utraty informacji).
- **Dynamiczny wybór pól** - GUI buduje listę dostępnych sekcji/pól na
  podstawie tego, co faktycznie znalazło się we wczytanych plikach (nawet
  kilka tysięcy pól przy pełnym raporcie AIDA64 Extreme), z wyszukiwarką i
  ładowaniem listy partiami (żeby nie zawieszać interfejsu).
- **Ulubione pola** - oznaczanie gwiazdką, trwałe między uruchomieniami,
  własny widok z szybkim dodawaniem/usuwaniem całych zestawów naraz.
- **Brakujące dane** oznaczane jako `---`, bez przerywania generowania
  raportu.
- Pasek postępu przy skanowaniu plików i generowaniu raportu, zapamiętywanie
  ostatniego katalogu zapisu.

## Uruchomienie ze źródeł

Wymagany Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

## Gotowy plik .exe (Windows)

Dla współpracowników bez zainstalowanego Pythona wygodniejszy jest
samodzielny plik `.exe` zbudowany narzędziem [PyInstaller](https://pyinstaller.org/):

```bash
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --noconfirm AllReports.spec
```

Gotowy plik pojawi się w `dist\AllReports.exe` - można go skopiować na
pendrive i uruchamiać bez instalacji czegokolwiek na docelowym komputerze.
Plik `ulubione.json` i `ustawienia.json` tworzą się automatycznie obok
`.exe` przy pierwszym uruchomieniu.

## Struktura projektu

| Plik | Odpowiedzialność |
|---|---|
| `main.py` | Punkt wejścia |
| `gui.py` | Interfejs tkinter |
| `parser.py` | Parsowanie plików źródłowych (txt/html/mhtml/xml/csv) |
| `slownik.py` | Słownik nazw sekcji/pól angielski → polski |
| `tabela.py` | Wczytywanie folderu i agregacja profili komputerów |
| `report_builder.py` | Budowanie wynikowego pliku Excel |
| `ulubione.py` | Trwałe ulubione pola |
| `ustawienia.py` | Trwałe drobne ustawienia (ostatni katalog zapisu) |
| `sciezki.py` | Rozwiązywanie ścieżek dla wersji źródłowej i `.exe` |

## Licencja

[Apache License 2.0](LICENSE).
