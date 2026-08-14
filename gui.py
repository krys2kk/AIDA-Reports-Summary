"""Okno tkinter: wybór folderu z wieloma raportami, wybór pól (pogrupowanych
w sekcje, z wyszukiwarką) i generowanie zbiorczej tabeli Excel - jeden
wiersz na komputer."""

from __future__ import annotations

import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from parser import KluczPola
from report_builder import buduj_tabele
from tabela import ProfilKomputera, wczytaj_folder, zbierz_dostepne_pola
from ulubione import wczytaj_ulubione, zapisz_ulubione
from ustawienia import wczytaj_ustawienia, zapisz_ustawienia

SEKCJA_ULUBIONE = "★ Ulubione"
# Ile wierszy checkboxów renderować naraz - tkinter zamiera przy tworzeniu
# tysięcy widgetów jednocześnie (np. sekcja CPUID ma ich ponad 2000).
PACZKA_RENDEROWANIA = 100


class Aplikacja:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Generator zbiorczych raportów konfiguracji komputerów")
        self.root.geometry("800x560+200+50")
        self.root.minsize(500, 480)

        self.folder: Path | None = None
        self.profile: list[ProfilKomputera] = []
        self.wszystkie_klucze: list[KluczPola] = []
        self.klucze_po_sekcji: dict[str, list[KluczPola]] = {}
        self.zmienne: dict[KluczPola, tk.BooleanVar] = {}
        self.aktualnie_wyswietlane: list[KluczPola] = []
        self.aktualna_sekcja: str | None = None
        self._sekcje_widoczne: list[str] = []
        self.ulubione_pola, self.ulubione_sekcje = wczytaj_ulubione()
        # Tłumi aktualizację licznika przy masowym zaznaczaniu (bez tego
        # każdy z tysięcy checkboxów odpalałby pełne przeliczenie licznika).
        self._masowa_zmiana = False
        # Stan renderowania partiami (lazy loading listy pól).
        self._render_klucze: list[KluczPola] = []
        self._render_z_sekcja = False
        self._render_pozycja = 0
        self._przycisk_wiecej: ttk.Button | None = None
        self._render_kontener: ttk.Frame | None = None
        # Rozwinięta sekcja w widoku ★ Ulubione (akordeon - jedna naraz).
        self._rozwinieta_sekcja: str | None = None

        self._zbuduj_gorny_pasek()
        self._zbuduj_srodek()
        self._zbuduj_dolny_pasek()

    # -- budowa UI -----------------------------------------------------

    def _zbuduj_gorny_pasek(self):
        ramka = ttk.Frame(self.root, padding=10)
        ramka.pack(fill="x")

        ttk.Button(
            ramka, text="Wybierz folder z raportami...", command=self.wybierz_folder
        ).pack(side="left")
        self.etykieta_folderu = ttk.Label(ramka, text="Nie wybrano folderu", foreground="#555")
        self.etykieta_folderu.pack(side="left", padx=10)

    def _zbuduj_srodek(self):
        kontener = ttk.PanedWindow(self.root, orient="horizontal")
        kontener.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        lewy = ttk.Frame(kontener, padding=(0, 0, 8, 0))
        kontener.add(lewy, weight=1)

        ttk.Label(lewy, text="Szukaj pola:").pack(anchor="w")
        self.zapytanie = tk.StringVar()
        self.zapytanie.trace_add("write", lambda *_: self._na_zmiane_wyszukiwania())
        ttk.Entry(lewy, textvariable=self.zapytanie).pack(fill="x", pady=(0, 8))

        naglowek_sekcji = ttk.Frame(lewy)
        naglowek_sekcji.pack(fill="x")
        ttk.Label(naglowek_sekcji, text="Sekcje:").pack(side="left")
        ttk.Button(
            naglowek_sekcji, text="Zaznacz wszystko", command=self._zaznacz_wszystko
        ).pack(side="right")

        ramka_listy = ttk.Frame(lewy)
        ramka_listy.pack(fill="both", expand=True)
        self.lista_sekcji = tk.Listbox(ramka_listy, exportselection=False, activestyle="dotbox")
        scroll_lista = ttk.Scrollbar(ramka_listy, orient="vertical", command=self.lista_sekcji.yview)
        self.lista_sekcji.configure(yscrollcommand=scroll_lista.set)
        self.lista_sekcji.pack(side="left", fill="both", expand=True)
        scroll_lista.pack(side="right", fill="y")
        self.lista_sekcji.bind("<<ListboxSelect>>", self._na_wybor_sekcji)

        prawy = ttk.Frame(kontener, padding=(8, 0, 0, 0))
        kontener.add(prawy, weight=3)

        naglowek_prawy = ttk.Frame(prawy)
        naglowek_prawy.pack(fill="x", pady=(0, 4))
        self.etykieta_kontekstu = ttk.Label(
            naglowek_prawy,
            text="Wybierz folder z danymi, aby zobaczyć dostępne pola.",
            foreground="#777",
        )
        self.etykieta_kontekstu.pack(side="left", anchor="w")
        self.przycisk_ulubione = ttk.Button(
            naglowek_prawy, command=self._przelacz_wszystkie_ulubione_widoku
        )
        # pakowany dopiero, gdy wybrana jest konkretna sekcja

        ramka_pol = ttk.Frame(prawy)
        ramka_pol.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(ramka_pol, highlightthickness=0)
        scroll_pol = ttk.Scrollbar(ramka_pol, orient="vertical", command=self.canvas.yview)
        self.wewnetrzna_ramka = ttk.Frame(self.canvas)

        self.wewnetrzna_ramka.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.wewnetrzna_ramka, anchor="nw")
        self.canvas.configure(yscrollcommand=scroll_pol.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll_pol.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._na_scroll)

    def _na_scroll(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _zbuduj_dolny_pasek(self):
        ramka = ttk.Frame(self.root, padding=10)
        ramka.pack(fill="x")

        ttk.Button(
            ramka, text="Zaznacz widoczne", command=lambda: self._zaznacz_widoczne(True)
        ).pack(side="left")
        ttk.Button(
            ramka, text="Odznacz widoczne", command=lambda: self._zaznacz_widoczne(False)
        ).pack(side="left", padx=6)
        ttk.Button(ramka, text="Odznacz wszystko", command=self._odznacz_wszystko).pack(side="left")

        self.etykieta_wybranych = ttk.Label(ramka, text="Wybrano: 0 pól", foreground="#555")
        self.etykieta_wybranych.pack(side="left", padx=16)

        self.przycisk_generuj = ttk.Button(
            ramka, text="Generuj raport...", command=self.generuj_raport, state="disabled"
        )
        self.przycisk_generuj.pack(side="right")

        ramka_statusu = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        ramka_statusu.pack(fill="x")
        self.status = ttk.Label(ramka_statusu, text="", foreground="#555")
        self.status.pack(side="left")
        self.pasek_postepu = ttk.Progressbar(ramka_statusu, length=220, mode="determinate")
        # pasek pojawia się tylko na czas trwania operacji (_pokaz_postep)

    # -- pasek postępu ---------------------------------------------------

    def _pokaz_postep(self, maksimum: int):
        self.pasek_postepu.configure(maximum=max(maksimum, 1), value=0)
        self.pasek_postepu.pack(side="right")

    def _ustaw_postep(self, numer: int, lacznie: int, opis: str):
        self.pasek_postepu.configure(maximum=max(lacznie, 1), value=numer)
        self.status.configure(text=opis, foreground="#555")
        self.root.update_idletasks()

    def _ukryj_postep(self):
        self.pasek_postepu.pack_forget()

    def _ustaw_status(self, tekst: str, kolor: str = "#555"):
        self.status.configure(text=tekst, foreground=kolor)

    # -- logika ----------------------------------------------------------

    def wybierz_folder(self):
        folder = filedialog.askdirectory(title="Wybierz folder z plikami raportów")
        if not folder:
            return
        folder = Path(folder)

        self._pokaz_postep(1)
        try:
            profile, bledy = wczytaj_folder(
                folder,
                postep=lambda n, ile, nazwa: self._ustaw_postep(
                    n, ile, f"Skanowanie {n}/{ile}: {nazwa}"
                ),
            )
        finally:
            self._ukryj_postep()

        if bledy:
            lista_bledow = "\n".join(f"- {sciezka.name}: {komunikat}" for sciezka, komunikat in bledy[:10])
            if len(bledy) > 10:
                lista_bledow += f"\n... i {len(bledy) - 10} więcej"
            messagebox.showwarning(
                "Niektórych plików nie udało się wczytać",
                f"{len(bledy)} plik(ów) pominięto z powodu błędów:\n\n{lista_bledow}",
            )

        if not profile:
            messagebox.showwarning(
                "Brak danych",
                "Nie znaleziono żadnych obsługiwanych plików raportów w wybranym folderze.",
            )
            return

        self.folder = folder
        self.profile = profile
        self.wszystkie_klucze = zbierz_dostepne_pola(profile)
        self.klucze_po_sekcji = {}
        for klucz in self.wszystkie_klucze:
            self.klucze_po_sekcji.setdefault(klucz.sekcja, []).append(klucz)

        self.zmienne = {klucz: tk.BooleanVar(value=False) for klucz in self.wszystkie_klucze}
        for zmienna in self.zmienne.values():
            zmienna.trace_add("write", lambda *_: self._na_zmiane_pola())

        # Migracja starego formatu ulubionych: wpisy całych sekcji zamieniamy
        # na ulubione wszystkich pól danej sekcji (koncepcja "ulubionej
        # sekcji" została zastąpiona masowym dodawaniem pól).
        if self.ulubione_sekcje:
            for sekcja in list(self.ulubione_sekcje):
                if sekcja in self.klucze_po_sekcji:
                    self.ulubione_pola.update(self.klucze_po_sekcji[sekcja])
                    self.ulubione_sekcje.discard(sekcja)
            self._zapisz_ulubione_bezpiecznie()

        self.etykieta_folderu.configure(text=f"{folder.name}  ({len(profile)} komputer(ów))")
        self.status.configure(
            text=f"Wczytano {len(profile)} plików, {len(self.wszystkie_klucze)} unikalnych pól."
        )
        self.przycisk_generuj.configure(state="normal")

        self.aktualna_sekcja = None
        self.zapytanie.set("")
        self._wypelnij_liste_sekcji()
        self._odswiez_widok()
        self._odswiez_licznik()

    def _dostepne_ulubione(self, zapytanie: str = "") -> list[KluczPola]:
        klucze = [k for k in self.wszystkie_klucze if k in self.ulubione_pola]
        if zapytanie:
            klucze = [k for k in klucze if self._pasuje(k, zapytanie)]
        return klucze

    def _ulubione_wg_sekcji(self, zapytanie: str = "") -> dict[str, list[KluczPola]]:
        grupy: dict[str, list[KluczPola]] = {}
        for klucz in self._dostepne_ulubione(zapytanie):
            grupy.setdefault(klucz.sekcja, []).append(klucz)
        return grupy

    def _wypelnij_liste_sekcji(self, zapytanie: str = ""):
        self.lista_sekcji.delete(0, "end")
        self._sekcje_widoczne = []

        ulubione = self._dostepne_ulubione(zapytanie)
        if ulubione:
            self.lista_sekcji.insert("end", f"{SEKCJA_ULUBIONE} ({len(ulubione)})")
            self._sekcje_widoczne.append(SEKCJA_ULUBIONE)

        for sekcja, klucze in self.klucze_po_sekcji.items():
            if zapytanie:
                dopasowane = [k for k in klucze if self._pasuje(k, zapytanie)]
                if not dopasowane:
                    continue
                self.lista_sekcji.insert("end", f"{sekcja} ({len(dopasowane)})")
            else:
                self.lista_sekcji.insert("end", f"{sekcja} ({len(klucze)})")
            self._sekcje_widoczne.append(sekcja)

    @staticmethod
    def _pasuje(klucz: KluczPola, zapytanie: str) -> bool:
        tekst = f"{klucz.sekcja} {klucz.etykieta}".lower()
        return zapytanie.lower() in tekst

    def _na_wybor_sekcji(self, event=None):
        wybor = self.lista_sekcji.curselection()
        if not wybor:
            return
        self.aktualna_sekcja = self._sekcje_widoczne[wybor[0]]
        self._odswiez_widok()

    def _na_zmiane_wyszukiwania(self):
        if not self.profile:
            return
        zapytanie = self.zapytanie.get().strip()
        self._wypelnij_liste_sekcji(zapytanie)

        if self.aktualna_sekcja in self._sekcje_widoczne:
            idx = self._sekcje_widoczne.index(self.aktualna_sekcja)
            self.lista_sekcji.selection_clear(0, "end")
            self.lista_sekcji.selection_set(idx)
        elif not zapytanie:
            self.aktualna_sekcja = None

        self._odswiez_widok()

    def _odswiez_widok(self):
        zapytanie = self.zapytanie.get().strip()

        if self.aktualna_sekcja == SEKCJA_ULUBIONE:
            self._pokaz_ulubione(zapytanie)
            return

        if self.aktualna_sekcja:
            klucze = self.klucze_po_sekcji[self.aktualna_sekcja]
            if zapytanie:
                klucze = [k for k in klucze if self._pasuje(k, zapytanie)]
            self._pokaz_pola(klucze, f"{self.aktualna_sekcja}  —  {len(klucze)} pól")
            return

        if not zapytanie:
            self._pokaz_pola([], "Wybierz sekcję z listy po lewej lub wpisz zapytanie w wyszukiwarce.")
            return

        dopasowane = [k for k in self.wszystkie_klucze if self._pasuje(k, zapytanie)]
        self._pokaz_pola(
            dopasowane, f"Wyniki wyszukiwania: {len(dopasowane)} pól", z_sekcja=True
        )

    def _aktualizuj_przycisk_ulubionych(self):
        """Przycisk "Dodaj/Usuń wszystko do/z ulubionych" nad listą pól -
        działa na aktualnie wyświetlaną listę (sekcję lub wyniki szukania)."""
        if not self.aktualnie_wyswietlane or self.aktualna_sekcja == SEKCJA_ULUBIONE:
            self.przycisk_ulubione.pack_forget()
            return
        wszystkie_ulubione = all(
            k in self.ulubione_pola for k in self.aktualnie_wyswietlane
        )
        self.przycisk_ulubione.configure(
            text="Usuń wszystko z ulubionych" if wszystkie_ulubione
            else "Dodaj wszystko do ulubionych"
        )
        self.przycisk_ulubione.pack(side="right")

    def _wyczysc_liste_pol(self):
        for widget in self.wewnetrzna_ramka.winfo_children():
            widget.destroy()
        self._przycisk_wiecej = None
        self._render_kontener = self.wewnetrzna_ramka

    def _pokaz_pola(self, klucze: list[KluczPola], opis: str, z_sekcja: bool = False):
        self._wyczysc_liste_pol()

        self.etykieta_kontekstu.configure(text=opis)
        self.aktualnie_wyswietlane = klucze
        self._render_klucze = klucze
        self._render_z_sekcja = z_sekcja
        self._render_pozycja = 0

        self._dorenderuj()
        self._aktualizuj_przycisk_ulubionych()
        self.canvas.yview_moveto(0)

    def _pokaz_ulubione(self, zapytanie: str = ""):
        """Widok ★ Ulubione: akordeon - najpierw same sekcje, pola danej
        sekcji dopiero po jej rozwinięciu (jedna rozwinięta naraz)."""
        self._wyczysc_liste_pol()

        grupy = self._ulubione_wg_sekcji(zapytanie)
        wszystkie = [k for klucze in grupy.values() for k in klucze]
        self.etykieta_kontekstu.configure(
            text=f"{SEKCJA_ULUBIONE}  —  {len(grupy)} sekcji, {len(wszystkie)} pól"
        )
        self.aktualnie_wyswietlane = wszystkie
        self._render_klucze = []
        self._render_pozycja = 0

        if self._rozwinieta_sekcja not in grupy:
            self._rozwinieta_sekcja = None

        for sekcja, klucze in grupy.items():
            rozwinieta = sekcja == self._rozwinieta_sekcja
            wiersz = ttk.Frame(self.wewnetrzna_ramka)
            wiersz.pack(fill="x", anchor="w")

            strzalka = tk.Label(
                wiersz, text="▼" if rozwinieta else "▶", cursor="hand2", width=2,
                foreground="#555",
            )
            strzalka.pack(side="left")
            strzalka.bind("<Button-1>", lambda _e, s=sekcja: self._przelacz_rozwiniecie(s))

            zmienna = tk.BooleanVar(value=all(self.zmienne[k].get() for k in klucze))
            ttk.Checkbutton(
                wiersz,
                text=f"{sekcja}  ({len(klucze)} pól)",
                variable=zmienna,
                command=lambda kl=klucze, z=zmienna: self._masowo_ustaw(
                    [self.zmienne[k] for k in kl],
                    z.get(),
                    "Zaznaczanie sekcji" if z.get() else "Odznaczanie sekcji",
                ),
            ).pack(side="left", anchor="w")

            if rozwinieta:
                kontener = ttk.Frame(self.wewnetrzna_ramka, padding=(24, 0, 0, 4))
                kontener.pack(fill="x", anchor="w")
                self._render_kontener = kontener
                self._render_klucze = klucze
                self._render_z_sekcja = False
                self._render_pozycja = 0
                self._dorenderuj()

        self._aktualizuj_przycisk_ulubionych()
        self.canvas.yview_moveto(0)

    def _przelacz_rozwiniecie(self, sekcja: str):
        self._rozwinieta_sekcja = None if self._rozwinieta_sekcja == sekcja else sekcja
        self._pokaz_ulubione(self.zapytanie.get().strip())

    def _dorenderuj(self):
        """Renderuje kolejną paczkę wierszy; przy dużych sekcjach (CPUID ma
        ponad 2000 pól) tworzenie wszystkich widgetów naraz wiesza okno."""
        kontener = self._render_kontener or self.wewnetrzna_ramka
        if self._przycisk_wiecej is not None:
            self._przycisk_wiecej.destroy()
            self._przycisk_wiecej = None

        poczatek = self._render_pozycja
        koniec = min(poczatek + PACZKA_RENDEROWANIA, len(self._render_klucze))
        for klucz in self._render_klucze[poczatek:koniec]:
            tekst = f"{klucz.sekcja} › {klucz.etykieta}" if self._render_z_sekcja else klucz.etykieta
            wiersz = ttk.Frame(kontener)
            wiersz.pack(fill="x", anchor="w")
            ulubiony = klucz in self.ulubione_pola
            gwiazdka = tk.Label(
                wiersz,
                text="★" if ulubiony else "☆",
                foreground="#E8A200" if ulubiony else "#999",
                cursor="hand2",
                width=2,
            )
            gwiazdka.pack(side="left")
            gwiazdka.bind(
                "<Button-1>",
                lambda _e, k=klucz, g=gwiazdka: self._przelacz_ulubione(k, g),
            )
            ttk.Checkbutton(wiersz, text=tekst, variable=self.zmienne[klucz]).pack(
                side="left", anchor="w"
            )
        self._render_pozycja = koniec

        pozostalo = len(self._render_klucze) - koniec
        if pozostalo > 0:
            self._przycisk_wiecej = ttk.Button(
                kontener,
                text=f"Pokaż kolejne {min(PACZKA_RENDEROWANIA, pozostalo)} (pozostało {pozostalo})",
                command=self._dorenderuj,
            )
            self._przycisk_wiecej.pack(pady=6)

    def _zapisz_ulubione_bezpiecznie(self):
        try:
            zapisz_ulubione(self.ulubione_pola, self.ulubione_sekcje)
        except OSError as exc:
            messagebox.showwarning(
                "Ulubione", f"Nie udało się zapisać ulubionych:\n{exc}"
            )

    def _odswiez_liste_sekcji_po_ulubionych(self):
        """Przebudowuje listę sekcji (licznik ★ Ulubione), zachowując wybór."""
        self._wypelnij_liste_sekcji(self.zapytanie.get().strip())
        if self.aktualna_sekcja in self._sekcje_widoczne:
            idx = self._sekcje_widoczne.index(self.aktualna_sekcja)
            self.lista_sekcji.selection_clear(0, "end")
            self.lista_sekcji.selection_set(idx)
        elif self.aktualna_sekcja == SEKCJA_ULUBIONE:
            self.aktualna_sekcja = None
            self._odswiez_widok()

    def _przelacz_ulubione(self, klucz: KluczPola, gwiazdka: tk.Label | None = None):
        if klucz in self.ulubione_pola:
            self.ulubione_pola.discard(klucz)
        else:
            self.ulubione_pola.add(klucz)
        self._zapisz_ulubione_bezpiecznie()

        if self.aktualna_sekcja == SEKCJA_ULUBIONE:
            # Zawartość widoku ulubionych zależy od członkostwa - przebuduj.
            self._odswiez_liste_sekcji_po_ulubionych()
            if self.aktualna_sekcja == SEKCJA_ULUBIONE:
                self._pokaz_ulubione(self.zapytanie.get().strip())
            return

        # W zwykłym widoku pole zostaje na swoim miejscu - aktualizujemy
        # tylko klikniętą gwiazdkę i licznik ulubionych na liście sekcji.
        if gwiazdka is not None:
            ulubiony = klucz in self.ulubione_pola
            gwiazdka.configure(
                text="★" if ulubiony else "☆",
                foreground="#E8A200" if ulubiony else "#999",
            )
        self._odswiez_liste_sekcji_po_ulubionych()
        self._aktualizuj_przycisk_ulubionych()

    def _przelacz_wszystkie_ulubione_widoku(self):
        klucze = self.aktualnie_wyswietlane
        if not klucze:
            return
        if all(k in self.ulubione_pola for k in klucze):
            self.ulubione_pola.difference_update(klucze)
        else:
            self.ulubione_pola.update(klucze)
        self._zapisz_ulubione_bezpiecznie()

        # Przerysuj widok (gwiazdki wielu wierszy się zmieniły), utrzymując
        # liczbę wyrenderowanych wierszy i pozycję przewinięcia.
        pozycja = self.canvas.yview()
        wyrenderowane = self._render_pozycja
        self._odswiez_liste_sekcji_po_ulubionych()
        self._odswiez_widok()
        while self._render_pozycja < wyrenderowane and self._przycisk_wiecej is not None:
            self._dorenderuj()
        self.canvas.yview_moveto(pozycja[0])

    def _masowo_ustaw(self, zmienne: list[tk.BooleanVar], wartosc: bool, opis: str):
        self._masowa_zmiana = True
        self._pokaz_postep(len(zmienne))
        try:
            for i, zmienna in enumerate(zmienne, start=1):
                zmienna.set(wartosc)
                if i % 250 == 0 or i == len(zmienne):
                    self._ustaw_postep(i, len(zmienne), f"{opis}: {i}/{len(zmienne)}")
        finally:
            self._masowa_zmiana = False
            self._ukryj_postep()
        self._odswiez_licznik()
        self._ustaw_status("")

    def _zaznacz_widoczne(self, wartosc: bool):
        zmienne = [self.zmienne[k] for k in self.aktualnie_wyswietlane]
        opis = "Zaznaczanie pól" if wartosc else "Odznaczanie pól"
        self._masowo_ustaw(zmienne, wartosc, opis)

    def _zaznacz_wszystko(self):
        self._masowo_ustaw(list(self.zmienne.values()), True, "Zaznaczanie pól")

    def _odznacz_wszystko(self):
        self._masowo_ustaw(list(self.zmienne.values()), False, "Odznaczanie pól")

    def _na_zmiane_pola(self):
        if not self._masowa_zmiana:
            self._odswiez_licznik()

    def _odswiez_licznik(self):
        ile = sum(1 for zmienna in self.zmienne.values() if zmienna.get())
        self.etykieta_wybranych.configure(text=f"Wybrano: {ile} pól")

    def generuj_raport(self):
        if not self.profile:
            return

        wybrane = [k for k in self.wszystkie_klucze if self.zmienne[k].get()]
        if not wybrane:
            messagebox.showwarning("Brak wyboru", "Zaznacz przynajmniej jedno pole do raportu.")
            return

        # Numerek w proponowanej nazwie musi być sprawdzany w katalogu,
        # w którym użytkownik faktycznie zapisuje raporty - dlatego
        # zapamiętujemy ostatni katalog zapisu (także między uruchomieniami).
        ustawienia = wczytaj_ustawienia()
        domyslny_katalog = Path(ustawienia.get("katalog_zapisu", Path.home()))
        if not domyslny_katalog.is_dir():
            domyslny_katalog = Path.home()
        domyslna_nazwa = self._unikalna_nazwa(domyslny_katalog, "podsumowanie raportów AIDA.xlsx")
        sciezka_docelowa = filedialog.asksaveasfilename(
            title="Zapisz raport jako",
            initialdir=str(domyslny_katalog),
            initialfile=domyslna_nazwa,
            defaultextension=".xlsx",
            filetypes=[("Skoroszyt Excel", "*.xlsx")],
        )
        if not sciezka_docelowa:
            return

        ustawienia["katalog_zapisu"] = str(Path(sciezka_docelowa).parent)
        try:
            zapisz_ustawienia(ustawienia)
        except OSError:
            pass  # brak zapamiętanego katalogu nie może zablokować zapisu raportu

        self._pokaz_postep(len(self.profile))
        try:
            wynik = buduj_tabele(
                sciezka_docelowa,
                self.profile,
                wybrane,
                postep=lambda n, ile, nazwa: self._ustaw_postep(
                    n, ile, f"Generowanie {n}/{ile}: {nazwa}"
                ),
            )
        except Exception as exc:
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać raportu:\n{exc}")
            traceback.print_exc()
            return
        finally:
            self._ukryj_postep()

        self._ustaw_status(f"✔ Raport zapisany: {wynik}", kolor="#1A7F37")

    @staticmethod
    def _unikalna_nazwa(katalog: Path, nazwa: str) -> str:
        if not (katalog / nazwa).exists():
            return nazwa

        rdzen = Path(nazwa).stem
        rozszerzenie = Path(nazwa).suffix
        n = 1
        while (katalog / f"{rdzen}{n}{rozszerzenie}").exists():
            n += 1
        return f"{rdzen}{n}{rozszerzenie}"

    @staticmethod
    def _katalog_raportow() -> Path:
        pulpit = Path.home() / "Desktop"
        if not pulpit.exists():
            pulpit = Path.home() / "Pulpit"
        katalog = pulpit / "Podsumowanie_Raportów_AIDA"
        katalog.mkdir(parents=True, exist_ok=True)
        return katalog


def uruchom():
    root = tk.Tk()
    try:
        from sciezki import zasob
        ikona = tk.PhotoImage(file=str(zasob("logo.png")))
        root.iconphoto(True, ikona)
    except Exception:
        pass  # brak logo nie może blokować startu aplikacji
    Aplikacja(root)
    root.mainloop()


if __name__ == "__main__":
    uruchom()
