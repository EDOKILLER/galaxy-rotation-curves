#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finestra_comune.py – libreria comune per le finestre Tk dei programmi Astropy
© 2026 Edoardo Battistel · licenza BSD-3

Tutte le lezioni sulle finestre (regole 1–20 di progetti/00_riepilogo.md) in un modulo solo.
Il file si COPIA nella cartella di ogni programma (PyInstaller lo include da solo);
controlla_versioni_finestra.sh dice quali programmi hanno una copia vecchia.

Uso minimo:

    import finestra_comune as fc
    f = fc.Finestra("NomeProgramma", "Nome programma 1.0 – sottotitolo",
                    programma="nome_programma", icona="icona.png", versione="1.0")
    ...mattoni dentro f.corpo...
    f.barra.pulsante("Esci", f.chiudi)
    f.avvia()

Regole che la libreria applica da sola:
  - classe della finestra = tk.Tk(className=…): in StartupWMClass va classe_finestra(nome)
    (solo l'iniziale maiuscola);
  - prima apertura all'88 % dello schermo (Tk vede quello di Edoardo come 3072×1728);
  - testo 100–200 % (predefinito 150 %) su una base FISSA di 13 punti; tema «clam»; frecce,
    quadratini, barre di scorrimento, righe delle tabelle e linguette crescono con il testo;
  - barra in basso impacchettata PRIMA del contenuto; niente place() né pack(in_=);
  - finestre di messaggio proprie, ridimensionabili, con il testo che va a capo;
  - zenity per scegliere file e cartelle (LD_LIBRARY_PATH ripristinato), ripiego su Tk;
  - grafici matplotlib con dpi legato al testo, misura della scheda visibile, after(60),
    figura minima 7 × 4,5 pollici, constrained_layout, barra di matplotlib nascosta e
    pulsanti italiani;
  - impostazioni in ~/.config/<programma>/impostazioni.json; in autotest solo quelle di base;
  - controlla_finestra(): l'autotest comune delle finestre.
"""

VERSIONE_FINESTRA = "1.1"

import contextlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
from pathlib import Path

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

# --------------------------------------------------------------------------- costanti
FIRMA = "© 2026 Edoardo Battistel"
SCALE = (1.0, 1.25, 1.5, 1.75, 2.0)
SCALA_PREDEFINITA = 1.5
PUNTI_BASE = 13                 # regola 17: base del 100 % fissa, mai dal carattere di Tk
CARATTERI_COLONNA = 34          # regole 8 e 18: larghezza delle colonne = font.measure("0" * 34)
CARATTERI_TENDINA_LARGA = 48    # 1.1: una tendina larga può allargare la colonna fino a 48 «0»
SCALA_NASCONDI_INTRO = 1.8      # regola 13: frase introduttiva nascosta dal 180 %
PUNTI_MINIMI_SCHEDE = 9         # regola 19
FRAZIONE_SCHERMO = 0.88         # regola 11
FIGURA_MINIMA = (7.0, 4.5)      # regola 20, in pollici
RITARDO_GRAFICO = 60            # regola 20, millisecondi
GRIGIO = "#6b7280"
BLU = "#1d4ed8"

_finestra_attuale = None


# =========================================================================== utilità senza finestra
def risorsa(nome):
    """Percorso di un file che sta accanto al programma (o dentro l'eseguibile PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        principale = getattr(sys.modules.get("__main__"), "__file__", None)
        base = os.path.dirname(os.path.abspath(principale)) if principale else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, nome)


def classe_finestra(nome_classe):
    """La classe che Tk dichiara davvero (verificato con xwininfo il 9/11): solo l'iniziale maiuscola.
    È il valore da scrivere in StartupWMClass del file .desktop."""
    return nome_classe[:1].upper() + nome_classe[1:].lower()


def ambiente_esterno():
    """Ambiente per programmi esterni (zenity, ffmpeg, xdg-open) senza le librerie di PyInstaller (regola 16)."""
    env = dict(os.environ)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
    elif getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)
    return env


def avvia_esterno(comando, attendi=False, timeout=None, **opzioni):
    """Avvia un programma esterno con LD_LIBRARY_PATH ripristinato.
    attendi=True → subprocess.run (testo catturato), altrimenti subprocess.Popen."""
    opzioni.setdefault("env", ambiente_esterno())
    if attendi:
        opzioni.setdefault("capture_output", True)
        opzioni.setdefault("text", True)
        return subprocess.run(comando, timeout=timeout, **opzioni)
    return subprocess.Popen(comando, **opzioni)


@contextlib.contextmanager
def ambiente_esterno_attivo():
    """Per le librerie che lanciano programmi da sole (matplotlib → ffmpeg per gli MP4):
        with fc.ambiente_esterno_attivo():
            animazione.save("film.mp4")"""
    vecchio = os.environ.get("LD_LIBRARY_PATH")
    nuovo = ambiente_esterno().get("LD_LIBRARY_PATH")
    try:
        if nuovo is None:
            os.environ.pop("LD_LIBRARY_PATH", None)
        else:
            os.environ["LD_LIBRARY_PATH"] = nuovo
        yield
    finally:
        if vecchio is None:
            os.environ.pop("LD_LIBRARY_PATH", None)
        else:
            os.environ["LD_LIBRARY_PATH"] = vecchio


def apri_con_sistema(percorso):
    """Apre un file o una cartella con il programma predefinito (xdg-open su Ubuntu)."""
    percorso = str(percorso)
    try:
        if sys.platform.startswith("win"):
            os.startfile(percorso)          # noqa: (solo Windows)
            return True
        prog = "open" if sys.platform == "darwin" else "xdg-open"
        if not shutil.which(prog):
            return False
        avvia_esterno([prog, percorso], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def ha_emoji(testo):
    """True se il testo ha caratteri che Linux può disegnare a colori (possono far chiudere la finestra Tk)."""
    for ch in str(testo):
        c = ord(ch)
        if c >= 0x1F000 or 0x2600 <= c <= 0x27BF or 0x2B00 <= c <= 0x2BFF or c in (0xFE0F, 0x200D, 0x20E3):
            return True
    return False


def ha_accenti_combinanti(testo):
    """True se il testo ha accenti combinanti (es. R̂): in Tk si vedono spostati."""
    return any(unicodedata.combining(ch) for ch in str(testo))


def cartella_impostazioni(programma):
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / programma
    return Path.home() / ".config" / programma


class Impostazioni(dict):
    """Impostazioni del programma in ~/.config/<programma>/impostazioni.json.
    Con autotest=True restano quelle di base e non si scrive niente (regola 15)."""

    def __init__(self, programma, base=None, autotest=False, cartella=None):
        self.base = dict(base or {})
        self.base.setdefault("scala", SCALA_PREDEFINITA)
        self.autotest = autotest
        self.file = Path(cartella or cartella_impostazioni(programma)) / "impostazioni.json"
        super().__init__(self.base)
        if not autotest:
            try:
                letto = json.loads(self.file.read_text(encoding="utf-8"))
                if isinstance(letto, dict):
                    self.update(letto)
            except Exception:
                pass

    def salva(self):
        if self.autotest:
            return False
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(dict(self), ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.file)
            return True
        except Exception:
            return False

    def imposta(self, chiave, valore):
        self[chiave] = valore
        return self.salva()


# =========================================================================== nascondere e rimostrare
_pack_nascosti = {}
_grid_nascosti = set()


def nascondi(widget):
    """Toglie un widget dalla finestra ricordando dove stava (grid o pack)."""
    gestore = widget.winfo_manager()
    if gestore == "grid":
        widget.grid_remove()
        _grid_nascosti.add(str(widget))
    elif gestore == "pack":
        fratelli = widget.master.pack_slaves()
        i = fratelli.index(widget) if widget in fratelli else -1
        dopo = fratelli[i + 1] if 0 <= i < len(fratelli) - 1 else None
        info = widget.pack_info()
        info.pop("in", None)
        _pack_nascosti[str(widget)] = (info, dopo)
        widget.pack_forget()


def mostra(widget):
    """Rimette un widget tolto con nascondi() nello stesso posto."""
    if widget.winfo_manager():
        return
    nome = str(widget)
    if nome in _pack_nascosti:
        info, dopo = _pack_nascosti.pop(nome)
        if dopo is not None and dopo.winfo_exists() and dopo.winfo_manager() == "pack":
            widget.pack(before=dopo, **info)
        else:
            widget.pack(**info)
    elif nome in _grid_nascosti:
        _grid_nascosti.discard(nome)
        widget.grid()


def aspetta(radice, secondi):
    """Lascia lavorare la finestra (timer after compresi) per qualche istante: serve agli autotest."""
    fine = time.time() + secondi
    while time.time() < fine:
        radice.update()
        time.sleep(0.02)


def _f(finestra):
    f = finestra or _finestra_attuale
    if f is None:
        raise RuntimeError("Crea prima la Finestra (finestra_comune.Finestra)")
    return f


# =========================================================================== la finestra
class Finestra:
    """Finestra principale. Contiene f.radice (tk.Tk), f.barra (BarraInBasso, già in basso)
    e f.corpo (ttk.Frame che si espande) dove mettere il contenuto."""

    NOMI_CARATTERI_TK = ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkFixedFont",
                         "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont")

    def __init__(self, nome_classe, titolo, programma=None, icona=None, versione="", impostazioni_base=None,
                 autotest=False, scala=None, firma=None, cartella_impostazioni=None):
        global _finestra_attuale
        _finestra_attuale = self
        self.autotest = autotest
        self.nome_classe = nome_classe
        self.programma = programma or nome_classe.lower()
        self.versione = versione
        self.radice = tk.Tk(className=nome_classe)
        self.radice.title(titolo)
        self.impostazioni = Impostazioni(self.programma, impostazioni_base, autotest, cartella_impostazioni)
        s = scala if scala is not None else self.impostazioni.get("scala", SCALA_PREDEFINITA)
        try:
            s = float(s)
        except (TypeError, ValueError):
            s = SCALA_PREDEFINITA
        self.scala = min(SCALE, key=lambda v: abs(v - s))
        self._al_cambio_scala = []
        self._alla_chiusura = []
        self._sopra_scala = []          # (widget, soglia): nascosto quando scala >= soglia
        self.grafici, self.schede, self.colonne, self.importanti = [], [], [], []
        self._dialogo_aperto = False
        self._icona(icona)
        self._crea_caratteri()
        self.stile = ttk.Style(self.radice)
        try:
            self.stile.theme_use("clam")
        except tk.TclError:
            pass
        self._stile_fisso()
        self.applica_scala(self.scala, salva=False)
        self._geometria_iniziale()
        # regola 1: la parte bassa fissa PRIMA del contenuto che si espande
        if firma is None:
            nome = titolo.split(" – ")[0]
            firma = f"{nome} · {FIRMA}"
        self.barra = BarraInBasso(self.radice, self, firma)
        self.barra.pack(side="bottom", fill="x")
        ttk.Separator(self.radice, orient="horizontal").pack(side="bottom", fill="x")
        self.corpo = ttk.Frame(self.radice)
        self.corpo.pack(side="top", fill="both", expand=True)
        self.radice.protocol("WM_DELETE_WINDOW", self.chiudi)

    # ------------------------------------------------------------------ avvio
    def _icona(self, icona):
        self._immagine_icona = None
        if not icona:
            return
        try:
            percorso = icona if os.path.isabs(str(icona)) else risorsa(icona)
            self._immagine_icona = tk.PhotoImage(master=self.radice, file=percorso)
            self.radice.iconphoto(True, self._immagine_icona)
        except Exception:
            pass

    def _geometria_iniziale(self):
        """Regola 11: prima apertura all'88 % dello schermo, al centro."""
        sw, sh = self.radice.winfo_screenwidth(), self.radice.winfo_screenheight()
        w, h = int(sw * FRAZIONE_SCHERMO), int(sh * FRAZIONE_SCHERMO)
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        self.radice.geometry(f"{w}x{h}+{x}+{y}")
        self.radice.minsize(max(400, int(sw * 0.35)), max(300, int(sh * 0.35)))

    def _carattere(self, nome, **opzioni):
        try:
            return tkfont.Font(root=self.radice, name=nome, exists=False, **opzioni)
        except tk.TclError:
            c = tkfont.nametofont(nome, root=self.radice)
            c.configure(**opzioni)
            return c

    def _crea_caratteri(self):
        base = tkfont.nametofont("TkDefaultFont", root=self.radice).actual()
        famiglia = base.get("family", "TkDefaultFont")
        self.carattere_titolo = self._carattere("FCTitolo", family=famiglia, weight="bold")
        self.carattere_grande = self._carattere("FCGrande", family=famiglia, weight="bold")
        self.carattere_piccolo = self._carattere("FCPiccolo", family=famiglia)
        self.carattere_mono = self._carattere("FCMono", family="DejaVu Sans Mono")

    def _stile_fisso(self):
        st, r = self.stile, self.radice
        st.configure(".", font="TkDefaultFont")
        st.configure("Grande.TButton", font="FCGrande", foreground="#ffffff", background=BLU)
        st.map("Grande.TButton", background=[("disabled", "#9ca3af"), ("active", "#2563eb")],
               foreground=[("disabled", "#f3f4f6")])
        st.configure("Attivo.TButton", background="#fde68a")
        st.configure("Titolo.TLabel", font="FCTitolo")
        st.configure("Piccolo.TLabel", font="FCPiccolo", foreground=GRIGIO)
        st.configure("Suggerimento.TLabel", foreground="#92400e")
        st.configure("TLabelframe.Label", font="FCGrande")
        st.configure("Treeview", font="TkDefaultFont")
        st.configure("Treeview.Heading", font="FCGrande")
        for chiave, valore in (("*TCombobox*Listbox.font", "TkDefaultFont"), ("*Listbox.font", "TkDefaultFont"),
                               ("*Text.font", "TkTextFont"), ("*Menu.font", "TkMenuFont")):
            r.option_add(chiave, valore)

    # ------------------------------------------------------------------ scala del testo
    def altezza_riga(self):
        """Altezza in pixel di una riga di testo normale (linespace)."""
        return tkfont.nametofont("TkDefaultFont", root=self.radice).metrics("linespace")

    def larghezza_colonna(self, caratteri=CARATTERI_COLONNA):
        """Regole 8 e 18: larghezza legata al carattere, mai alle etichette che vanno a capo."""
        return tkfont.nametofont("TkDefaultFont", root=self.radice).measure("0" * caratteri)

    def misura(self, testo, carattere="TkDefaultFont"):
        if isinstance(carattere, str):
            carattere = tkfont.nametofont(carattere, root=self.radice)
        return carattere.measure(testo)

    def dpi_grafici(self):
        """Regola 7: testo dei grafici ≈ 85 % di quello dei pulsanti (372 dpi al 150 % sul PC di Edoardo)."""
        return self.altezza_riga() / 1.2 * 0.85 * 72 / 10

    def applica_scala(self, scala, salva=True):
        """Cambia la dimensione di testo e comandi (1.0 – 2.0) e avvisa tutti i mattoni."""
        scala = min(SCALE, key=lambda v: abs(v - float(scala)))
        self.scala = scala
        punti = int(round(PUNTI_BASE * scala))
        for nome in self.NOMI_CARATTERI_TK:
            try:
                tkfont.nametofont(nome, root=self.radice).configure(size=punti)
            except tk.TclError:
                pass
        self.carattere_titolo.configure(size=int(round(punti * 1.25)))
        self.carattere_grande.configure(size=int(round(punti * 1.05)))
        self.carattere_piccolo.configure(size=max(PUNTI_MINIMI_SCHEDE, int(round(punti * 0.85))))
        self.carattere_mono.configure(size=punti)
        r = self.altezza_riga()
        p = max(2, round(r * 0.22))
        freccia = max(12, round(r * 0.75))
        quadratino = max(12, round(r * 0.7))
        barra = max(12, round(r * 0.65))
        st = self.stile
        st.configure("TButton", padding=(round(r * 0.45), p))
        st.configure("Grande.TButton", padding=(round(r * 0.6), round(r * 0.3)))
        st.configure("TEntry", padding=p)
        st.configure("TCombobox", arrowsize=freccia, padding=p)
        st.configure("TSpinbox", arrowsize=freccia, padding=p)
        for nome in ("TCheckbutton", "TRadiobutton"):
            st.configure(nome, indicatorsize=quadratino, indicatormargin=(0, 0, p, 0), padding=p)
        for nome in ("TScrollbar", "Vertical.TScrollbar", "Horizontal.TScrollbar"):
            st.configure(nome, arrowsize=barra)
        st.configure("Treeview", rowheight=round(r * 1.3) + 2)
        st.configure("Treeview.Heading", padding=p)
        st.configure("TNotebook.Tab", padding=(round(r * 0.6), p))
        st.configure("Sash", sashthickness=max(6, round(r * 0.3)))
        for widget, soglia in list(self._sopra_scala):
            try:
                (nascondi if scala >= soglia else mostra)(widget)
            except tk.TclError:
                pass
        for funzione in list(self._al_cambio_scala):
            try:
                funzione(scala)
            except Exception:
                traceback.print_exc()
        if salva:
            self.impostazioni.imposta("scala", scala)

    def al_cambio_scala(self, funzione):
        """funzione(scala) viene chiamata a ogni cambio della dimensione del testo."""
        self._al_cambio_scala.append(funzione)

    def nascondi_da_scala(self, widget, soglia=SCALA_NASCONDI_INTRO):
        """Regola 13: il widget sparisce quando il testo è grande (es. frase introduttiva dal 180 %)."""
        self._sopra_scala.append((widget, soglia))
        if self.scala >= soglia:
            self.radice.after_idle(lambda: nascondi(widget))

    def tendina_scala(self, padre, comando=None):
        """La tendina «Dimensione testo» 100–200 %, salvata nelle impostazioni."""
        valori = [f"{int(round(s * 100))} %" for s in SCALE]
        var = tk.StringVar(self.radice, value=f"{int(round(self.scala * 100))} %")

        def scelta(valore):
            try:
                self.applica_scala(float(valore.split()[0]) / 100)
            except ValueError:
                return
            if comando:
                comando(self.scala)
        riga = RigaTendina(padre, "Dimensione testo", valori, var, comando=scelta, finestra=self)
        self.al_cambio_scala(lambda s: var.set(f"{int(round(s * 100))} %"))
        return riga

    def importante(self, widget):
        """Segna un comando da controllare nell'autotest (regola 4). I pulsanti lo sono tutti comunque."""
        self.importanti.append(widget)
        return widget

    # ------------------------------------------------------------------ messaggi
    def _dialogo(self, titolo, testo, pulsanti, predefinito=0, alla_chiusura=None):
        if self.autotest:
            print(f"[finestra «{titolo}»] {testo}  → {pulsanti[predefinito]}", flush=True)
            return pulsanti[predefinito]
        r = self.radice
        w = tk.Toplevel(r)
        w.title(titolo)
        w.transient(r)
        riga = self.altezza_riga()
        larg = self.larghezza_colonna(62) + 4 * riga
        righe_testo = sum(1 + len(x) // 60 for x in str(testo).split("\n"))
        alt = riga * (min(16, max(4, righe_testo)) + 5)
        r.update_idletasks()
        x = r.winfo_rootx() + max(0, (r.winfo_width() - larg) // 2)
        y = r.winfo_rooty() + max(0, (r.winfo_height() - alt) // 3)
        w.geometry(f"{larg}x{alt}+{x}+{y}")
        w.minsize(larg // 2, riga * 6)
        risultato = [alla_chiusura if alla_chiusura is not None else pulsanti[-1]]
        basso = ttk.Frame(w, padding=(12, 8, 12, 12))
        basso.pack(side="bottom", fill="x")            # regola 1
        sfondo = self.stile.lookup("TFrame", "background") or None
        cornice = ttk.Frame(w, padding=(12, 12, 12, 0))
        cornice.pack(side="top", fill="both", expand=True)
        t = tk.Text(cornice, wrap="word", font="TkDefaultFont", relief="flat", borderwidth=0,
                    highlightthickness=0, padx=8, pady=6, width=1, height=1, background=sfondo)
        sb = ttk.Scrollbar(cornice, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        t.insert("1.0", str(testo))
        t.configure(state="disabled")

        def premi(valore):
            risultato[0] = valore
            w.destroy()
        bottoni = []
        for i, nome in reversed(list(enumerate(pulsanti))):
            b = ttk.Button(basso, text=nome, style="Grande.TButton" if i == predefinito else "TButton",
                           command=lambda v=nome: premi(v))
            b.pack(side="right", padx=(8, 0))
            bottoni.append(b)
        w.bind("<Escape>", lambda e: w.destroy())
        w.bind("<Return>", lambda e: premi(pulsanti[predefinito]))
        w.protocol("WM_DELETE_WINDOW", w.destroy)
        try:
            w.wait_visibility()
            w.grab_set()
        except tk.TclError:
            pass
        bottoni[len(bottoni) - 1 - predefinito].focus_set()      # bottoni è in ordine inverso
        r.wait_window(w)
        return risultato[0]

    def messaggio(self, titolo, testo):
        """Messaggio informativo (al posto di messagebox.showinfo)."""
        self._dialogo(titolo, testo, ("Chiudi",))

    def errore(self, titolo, testo):
        """Messaggio d'errore: il testo si può selezionare e copiare."""
        self._dialogo(titolo, testo, ("Chiudi",))

    def domanda(self, titolo, testo, si="Sì", no="No", predefinito_si=True):
        """Domanda sì/no (al posto di messagebox.askyesno). Chiudere la finestra = «no»."""
        return self._dialogo(titolo, testo, (si, no), 0 if predefinito_si else 1, alla_chiusura=no) == si

    # ------------------------------------------------------------------ file e cartelle (zenity)
    def _zenity(self, argomenti):
        """None = zenity assente o fallito (→ ripiego su Tk); "" = annullato; altrimenti la risposta."""
        if self.autotest or sys.platform.startswith("win") or not shutil.which("zenity"):
            return None
        esito = {}

        def lavoro():
            try:
                esito["p"] = subprocess.run(["zenity", *argomenti], capture_output=True, text=True,
                                            env=ambiente_esterno(), timeout=3600)
            except Exception as e:
                esito["e"] = e
        filo = threading.Thread(target=lavoro, daemon=True)
        filo.start()
        fatto = tk.BooleanVar(self.radice, value=False)

        def controlla():
            if filo.is_alive():
                self.radice.after(100, controlla)
            else:
                fatto.set(True)
        self.radice.after(100, controlla)
        self.radice.wait_variable(fatto)       # la finestra continua a ridisegnarsi
        p = esito.get("p")
        if p is None:
            return None
        if p.returncode == 0:
            return p.stdout.rstrip("\n")
        if p.returncode == 1:
            return ""
        return None

    @staticmethod
    def _filtri_zenity(filtri):
        uscita = [f"--file-filter={nome} | {modelli}" for nome, modelli in (filtri or ())]
        if filtri:
            uscita.append("--file-filter=Tutti i file | *")
        return uscita

    def scegli_file(self, titolo="Scegli un file", iniziale=None, filtri=None, multipli=False):
        """filtri = [("FITS", "*.fits *.fit *.fts"), …]. Restituisce il percorso (o la lista), None se annullato."""
        if self._dialogo_aperto:
            return [] if multipli else None
        self._dialogo_aperto = True
        try:
            arg = ["--file-selection", f"--title={titolo}"] + self._filtri_zenity(filtri)
            if iniziale:
                ini = str(iniziale)
                arg.append(f"--filename={ini.rstrip('/')}/" if os.path.isdir(ini) else f"--filename={ini}")
            if multipli:
                arg += ["--multiple", "--separator=\n"]
            r = self._zenity(arg)
            if r is not None:
                if not r:
                    return [] if multipli else None
                return r.split("\n") if multipli else r
            from tkinter import filedialog
            tipi = [(n, m) for n, m in (filtri or ())] + [("Tutti i file", "*")]
            ini_dir = str(iniziale) if iniziale and os.path.isdir(str(iniziale)) else (
                os.path.dirname(str(iniziale)) if iniziale else None)
            if multipli:
                return list(filedialog.askopenfilenames(parent=self.radice, title=titolo, filetypes=tipi,
                                                        initialdir=ini_dir) or [])
            return filedialog.askopenfilename(parent=self.radice, title=titolo, filetypes=tipi,
                                              initialdir=ini_dir) or None
        finally:
            self._dialogo_aperto = False

    def salva_file(self, titolo="Salva", iniziale=None, filtri=None):
        """Restituisce il percorso scelto (con l'estensione del primo filtro se manca) o None."""
        if self._dialogo_aperto:
            return None
        self._dialogo_aperto = True
        try:
            arg = ["--file-selection", "--save", "--confirm-overwrite", f"--title={titolo}"] + self._filtri_zenity(filtri)
            if iniziale:
                arg.append(f"--filename={iniziale}")
            r = self._zenity(arg)
            if r is None:
                from tkinter import filedialog
                tipi = [(n, m) for n, m in (filtri or ())] + [("Tutti i file", "*")]
                ini = Path(str(iniziale)) if iniziale else None
                r = filedialog.asksaveasfilename(parent=self.radice, title=titolo, filetypes=tipi,
                                                 initialdir=str(ini.parent) if ini else None,
                                                 initialfile=ini.name if ini else None) or ""
            if not r:
                return None
            if filtri and not Path(r).suffix:
                primo = filtri[0][1].split()[0]
                if primo.startswith("*."):
                    r += primo[1:]
            return r
        finally:
            self._dialogo_aperto = False

    def scegli_cartella(self, titolo="Scegli una cartella", iniziale=None):
        if self._dialogo_aperto:
            return None
        self._dialogo_aperto = True
        try:
            arg = ["--file-selection", "--directory", f"--title={titolo}"]
            if iniziale:
                arg.append(f"--filename={str(iniziale).rstrip('/')}/")
            r = self._zenity(arg)
            if r is not None:
                return r or None
            from tkinter import filedialog
            return filedialog.askdirectory(parent=self.radice, title=titolo,
                                           initialdir=str(iniziale) if iniziale else None) or None
        finally:
            self._dialogo_aperto = False

    # ------------------------------------------------------------------ altro
    def stato(self, testo):
        """Scrive nella riga di stato della barra in basso."""
        self.barra.stato(testo)

    def alla_chiusura(self, funzione):
        self._alla_chiusura.append(funzione)

    def chiudi(self):
        for funzione in self._alla_chiusura:
            try:
                funzione()
            except Exception:
                traceback.print_exc()
        try:
            self.radice.destroy()
        except tk.TclError:
            pass

    def avvia(self):
        self.radice.mainloop()


# =========================================================================== mattoni
class RigaACapo(ttk.Frame):
    """Fila di pulsanti che va a capo da sola quando non ci sta (1.1: al 150–200 % i pulsanti
    in fondo alla fila venivano tagliati). I pulsanti sono figli DIRETTI della fila e messi con
    grid riga/colonna (regola 3: niente place() né pack(in_=))."""

    def __init__(self, padre, finestra=None, spazio=8):
        super().__init__(padre)
        self.finestra = _f(finestra)
        self.spazio = spazio
        self.elementi = []            # widget, oppure None = a capo forzato
        self._ultima = 0
        self._attesa = None
        self.bind("<Configure>", self._configura, add="+")
        self.finestra.al_cambio_scala(lambda s: self.after(40, self.disponi))

    def pulsante(self, testo, comando, grande=False, **opzioni):
        b = ttk.Button(self, text=testo, command=comando, style="Grande.TButton" if grande else "TButton", **opzioni)
        return self.aggiungi(b)

    def aggiungi(self, widget):
        """widget deve essere figlio di questa fila."""
        self.elementi.append(widget)
        if isinstance(widget, (ttk.Button, tk.Button)):
            self.finestra.importante(widget)
        self._programma()
        return widget

    def a_capo(self):
        self.elementi.append(None)
        self._programma()

    def _configura(self, evento):
        if abs(evento.width - self._ultima) > 3:
            self._ultima = evento.width
            self._programma()

    def _programma(self):
        if self._attesa is None:
            self._attesa = self.after_idle(self.disponi)

    def disponi(self):
        self._attesa = None
        try:
            larg = self.winfo_width()
        except tk.TclError:
            return
        if larg < 20:                               # non ancora disposta: tutto su una fila
            larg = 10 ** 6
        r = c = x = 0
        for w in self.elementi:
            if w is None:
                r, c, x = r + 1, 0, 0
                continue
            try:
                lw = w.winfo_reqwidth() + self.spazio
            except tk.TclError:
                continue
            if c > 0 and x + lw > larg:
                r, c, x = r + 1, 0, 0
            w.grid(row=r, column=c, sticky="w", padx=(0, self.spazio), pady=(0, 4))
            c, x = c + 1, x + lw


class BarraInBasso(ttk.Frame):
    """Parte bassa fissa: riga di stato, pulsanti (che vanno a capo da soli) e firma.
    Creata da Finestra e impacchettata prima del contenuto (regola 1)."""

    def __init__(self, padre, finestra, firma=FIRMA):
        super().__init__(padre, padding=(10, 4, 10, 6))
        self.finestra = finestra
        self.columnconfigure(0, weight=1)
        self.var_stato = tk.StringVar(finestra.radice, value="")
        self.etichetta_stato = Etichetta(self, textvariable=self.var_stato, finestra=finestra, foreground="#374151")
        self.etichetta_stato.grid(row=0, column=0, columnspan=2, sticky="ew")
        nascondi_presto = self.etichetta_stato
        self.after_idle(lambda: nascondi(nascondi_presto) if not self.var_stato.get() else None)
        self.fila = RigaACapo(self, finestra)
        self.fila.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.etichetta_firma = ttk.Label(self, text=firma, style="Piccolo.TLabel")
        self.etichetta_firma.grid(row=1, column=1, sticky="se", padx=(12, 0))

    def nuova_riga(self):
        """I pulsanti dopo questa chiamata cominciano su una fila nuova."""
        self.fila.a_capo()

    def pulsante(self, testo, comando, grande=False):
        return self.fila.pulsante(testo, comando, grande)

    def stato(self, testo):
        self.var_stato.set(testo or "")
        (mostra if testo else nascondi)(self.etichetta_stato)


class Etichetta(ttk.Label):
    """Etichetta che va a capo seguendo la larghezza che ha davvero (regole del 15/11).
    Chiede all'inizio la larghezza di una colonna (font.measure("0"*34)), così non viene schiacciata."""

    def __init__(self, padre, testo="", finestra=None, larghezza=None, **opzioni):
        opzioni.setdefault("justify", "left")
        if testo:
            opzioni["text"] = testo
        super().__init__(padre, **opzioni)
        f = _f(finestra)
        self._ultima = int(larghezza or f.larghezza_colonna())
        self.configure(wraplength=self._ultima)
        self.bind("<Configure>", self._adatta, add="+")

    def _adatta(self, evento):
        w = max(40, evento.width - 2)
        if abs(w - self._ultima) > 2:
            self._ultima = w
            self.configure(wraplength=w)


class Suggerimento(Etichetta):
    """Riga di suggerimento che compare solo quando serve (regola 13)."""

    def __init__(self, padre, finestra=None, **opzioni):
        opzioni.setdefault("style", "Suggerimento.TLabel")
        super().__init__(padre, "", finestra, **opzioni)
        self.after_idle(lambda: nascondi(self))

    def mostra(self, testo):
        self.configure(text=testo)
        (mostra if testo else nascondi)(self)

    def nascondi(self):
        nascondi(self)


class Spunta(ttk.Frame):
    """Regola 9: quadratino senza testo + etichetta che va a capo (i Checkbutton non vanno a capo).
    Anche il clic sull'etichetta cambia la spunta."""

    def __init__(self, padre, testo, variabile=None, comando=None, finestra=None):
        super().__init__(padre)
        f = _f(finestra)
        self.variabile = variabile if variabile is not None else tk.BooleanVar(f.radice, value=False)
        self.casella = ttk.Checkbutton(self, variable=self.variabile, command=comando)
        self.casella.grid(row=0, column=0, sticky="nw")
        self.etichetta = Etichetta(self, testo, f)
        self.etichetta.grid(row=0, column=1, sticky="ew")
        self.columnconfigure(1, weight=1)
        self.etichetta.bind("<Button-1>", self._clic, add="+")

    def _clic(self, _evento=None):
        if not self.casella.instate(["disabled"]):
            self.casella.invoke()

    def get(self):
        return bool(self.variabile.get())

    def set(self, valore):
        self.variabile.set(bool(valore))

    def state(self, *argomenti):
        return self.casella.state(*argomenti)


class RigaTendina(ttk.Frame):
    """Regola 12: una griglia per riga.
    larga=False: etichetta (va a capo) + tendina a larghezza fissa = valore più lungo + 2;
    larga=True: etichetta sopra e tendina sotto che si allarga con la colonna (testi lunghi).
    comando(valore) viene chiamato alla scelta."""

    def __init__(self, padre, testo, valori, variabile=None, larga=False, comando=None, finestra=None):
        super().__init__(padre)
        f = _f(finestra)
        valori = [str(v) for v in valori]
        self.larga = larga
        self.variabile = variabile if variabile is not None else tk.StringVar(f.radice, value=valori[0] if valori else "")
        self.etichetta = Etichetta(self, testo, f)
        self.tendina = ttk.Combobox(self, textvariable=self.variabile, values=valori, state="readonly",
                                    font="TkDefaultFont")
        if larga:
            self.columnconfigure(0, weight=1)
            self.etichetta.grid(row=0, column=0, sticky="ew")
            self.tendina.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        else:
            self.columnconfigure(0, weight=1)
            self.etichetta.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.tendina.grid(row=0, column=1, sticky="e")
        self._larghezza(valori)
        if comando:
            self.tendina.bind("<<ComboboxSelected>>", lambda e: comando(self.variabile.get()), add="+")

    def _larghezza(self, valori):
        if not self.larga:
            self.tendina.configure(width=max([len(v) for v in valori] + [len(self.variabile.get()), 3]) + 2)

    def imposta_valori(self, valori):
        valori = [str(v) for v in valori]
        self.tendina.configure(values=valori)
        self._larghezza(valori)
        if self.larga:
            c = _f(None)
            for col in c.colonne:
                col.after(40, col.aggiorna_larghezza)

    def larghezza_testo(self):
        """Pixel che servono alla tendina per mostrare il valore più lungo (stessa formula dell'autotest)."""
        car = tkfont.nametofont("TkDefaultFont", root=_f(None).radice)
        valori = [str(v) for v in self.tk.splitlist(self.tendina.cget("values"))] + [self.variabile.get()]
        alto = max(self.tendina.winfo_reqheight(), _f(None).altezza_riga())
        return max(car.measure(v) for v in valori) + alto + 16

    def get(self):
        return self.variabile.get()

    def set(self, valore):
        self.variabile.set(str(valore))


class RigaCampo(ttk.Frame):
    """Etichetta che va a capo + campo di testo a larghezza fissa (in caratteri)."""

    def __init__(self, padre, testo, variabile=None, caratteri=8, finestra=None, **opzioni):
        super().__init__(padre)
        f = _f(finestra)
        self.variabile = variabile if variabile is not None else tk.StringVar(f.radice, value="")
        self.columnconfigure(0, weight=1)
        self.etichetta = Etichetta(self, testo, f)
        self.etichetta.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.campo = ttk.Entry(self, textvariable=self.variabile, width=caratteri, font="TkDefaultFont", **opzioni)
        self.campo.grid(row=0, column=1, sticky="e")

    def get(self):
        return self.variabile.get()

    def numero(self, predefinito=None):
        """Il valore come numero (accetta la virgola); predefinito se non è un numero."""
        try:
            return float(self.variabile.get().replace(",", ".").strip())
        except ValueError:
            return predefinito


class Contatore(ttk.Frame):
    """Numero con due pulsanti grandi «−» e «+» (le frecce dello Spinbox restano minuscole)."""

    def __init__(self, padre, testo, minimo, massimo, valore=None, passo=1, variabile=None, comando=None,
                 finestra=None):
        super().__init__(padre)
        f = _f(finestra)
        self.minimo, self.massimo, self.passo, self.comando = minimo, massimo, passo, comando
        self.intero = all(float(x).is_integer() for x in (minimo, massimo, passo))
        iniziale = minimo if valore is None else valore
        self.variabile = variabile if variabile is not None else tk.StringVar(f.radice, value=self._testo(iniziale))
        self.columnconfigure(0, weight=1)
        self.etichetta = Etichetta(self, testo, f)
        self.etichetta.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        comandi = ttk.Frame(self)
        comandi.grid(row=0, column=1, sticky="e")
        self.meno = ttk.Button(comandi, text="−", width=3, command=lambda: self.cambia(-1))
        self.meno.pack(side="left")
        cifre = max(len(self._testo(minimo)), len(self._testo(massimo))) + 1
        self.campo = ttk.Entry(comandi, textvariable=self.variabile, width=cifre, justify="center", font="FCGrande")
        self.campo.pack(side="left", padx=4)
        self.piu = ttk.Button(comandi, text="+", width=3, command=lambda: self.cambia(+1))
        self.piu.pack(side="left")

    def _testo(self, v):
        return str(int(round(v))) if self.intero else f"{v:g}"

    def get(self):
        try:
            v = float(self.variabile.get().replace(",", "."))
        except ValueError:
            v = self.minimo
        v = min(self.massimo, max(self.minimo, v))
        return int(round(v)) if self.intero else v

    def cambia(self, verso):
        v = min(self.massimo, max(self.minimo, self.get() + verso * self.passo))
        self.variabile.set(self._testo(v))
        if self.comando:
            self.comando(self.get())


class RigaPulsanti(ttk.Frame):
    """Una riga fissa di pulsanti creati dentro la riga (regola 3). La sua larghezza serve
    a calcolare quella della colonna (regola 18)."""

    def __init__(self, padre, finestra=None):
        super().__init__(padre)
        self.finestra = _f(finestra)
        self.pulsanti = []

    def pulsante(self, testo, comando, grande=False):
        b = ttk.Button(self, text=testo, command=comando, style="Grande.TButton" if grande else "TButton")
        b.pack(side="left", padx=(0, 8))
        self.pulsanti.append(b)
        self.finestra.importante(b)
        return b


class ColonnaScorrevole(ttk.Frame):
    """Regola 10: colonna di comandi in una tela scorrevole, barra visibile solo quando serve.
    I mattoni vanno creati dentro .interno e messi con .aggiungi(widget) (grid, una riga ciascuno).
    Larghezza = max(font.measure("0"*34), righe di pulsanti e comandi fissi) (regole 8 e 18).
    Con caratteri=0 è una pagina scorrevole (testi lunghi in una scheda): nessuna larghezza minima."""

    def __init__(self, padre, finestra=None, caratteri=CARATTERI_COLONNA):
        super().__init__(padre)
        f = self.finestra = _f(finestra)
        self.caratteri = caratteri
        self.pannello = None
        self._riga = 0
        self._barra_visibile = False
        sfondo = f.stile.lookup("TFrame", "background") or None
        self.tela = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=sfondo)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.tela.yview)
        self.tela.configure(yscrollcommand=self.barra.set)
        self.interno = ttk.Frame(self.tela, padding=(10, 8, 10, 8))
        self.interno.columnconfigure(0, weight=1)
        self._id = self.tela.create_window(0, 0, window=self.interno, anchor="nw")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tela.grid(row=0, column=0, sticky="nsew")
        self.barra.grid(row=0, column=1, sticky="ns")
        self.barra.grid_remove()
        self.interno.bind("<Configure>", lambda e: self._controlla_barra(), add="+")
        self.tela.bind("<Configure>", self._tela_cambiata, add="+")
        self.tela.bind("<Enter>", lambda e: self._rotella(True), add="+")
        self.tela.bind("<Leave>", lambda e: self._rotella(False), add="+")
        f.colonne.append(self)
        f.al_cambio_scala(lambda s: self.after(40, self.aggiorna_larghezza))
        self.after_idle(self.aggiorna_larghezza)

    def aggiungi(self, widget, **opzioni):
        opzioni.setdefault("sticky", "ew")
        opzioni.setdefault("pady", (0, 8))
        widget.grid(row=self._riga, column=0, **opzioni)
        self._riga += 1
        return widget

    def _discendenti(self, w):
        for c in w.winfo_children():
            yield c
            yield from self._discendenti(c)

    def larghezza_richiesta(self):
        """Mai dalle etichette che vanno a capo (chiedono la larghezza che hanno già)."""
        f = self.finestra
        larg = f.larghezza_colonna(self.caratteri)
        for w in self._discendenti(self.interno):
            if isinstance(w, (RigaPulsanti, Contatore, RigaCampo)):
                larg = max(larg, w.winfo_reqwidth())
            elif isinstance(w, RigaTendina) and not w.larga:
                larg = max(larg, w.tendina.winfo_reqwidth() + f.larghezza_colonna(8))
            elif isinstance(w, RigaTendina):
                # 1.1: la tendina larga deve mostrare il valore più lungo (fino a 48 caratteri «0»)
                larg = max(larg, min(w.larghezza_testo(), f.larghezza_colonna(CARATTERI_TENDINA_LARGA)))
        spessore = max(12, round(f.altezza_riga() * 0.65))
        return larg + 20 + spessore + 6

    def aggiorna_larghezza(self):
        try:
            self.update_idletasks()
            self.tela.configure(width=self.larghezza_richiesta())
        except tk.TclError:
            return
        if self.pannello is not None:
            self.pannello.sistema_divisore()
        self._controlla_barra()

    def _tela_cambiata(self, evento):
        self.tela.itemconfigure(self._id, width=evento.width)
        self._controlla_barra()

    def _controlla_barra(self):
        try:
            alto = self.interno.winfo_reqheight()
            visibile = self.tela.winfo_height()
            self.tela.configure(scrollregion=(0, 0, max(1, self.tela.winfo_width()), alto))
        except tk.TclError:
            return
        if visibile < 10:
            return
        if not self._barra_visibile and alto > visibile + 1:
            self._barra_visibile = True
            self.barra.grid()
        elif self._barra_visibile and alto < visibile - 20:
            self._barra_visibile = False
            self.barra.grid_remove()
            self.tela.yview_moveto(0)

    def _rotella(self, attiva):
        r = self.finestra.radice
        if attiva:
            r.bind_all("<MouseWheel>", self._rotola)
            r.bind_all("<Button-4>", lambda e: self._scorri(-1))
            r.bind_all("<Button-5>", lambda e: self._scorri(1))
        else:
            for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                r.unbind_all(ev)

    def _rotola(self, evento):
        self._scorri(-1 if evento.delta > 0 else 1)

    def _scorri(self, verso):
        if self._barra_visibile:
            self.tela.yview_scroll(verso * 3, "units")

    def mostra(self, widget):
        """Fa scorrere la colonna finché il widget è visibile (usato anche dall'autotest)."""
        if not self._barra_visibile:
            return
        self.update_idletasks()
        y = widget.winfo_rooty() - self.interno.winfo_rooty()
        tot = max(1, self.interno.winfo_height())
        self.tela.yview_moveto(max(0.0, (y - 20) / tot))
        self.update_idletasks()


class PannelloDiviso(ttk.PanedWindow):
    """Colonna a sinistra + contenuto a destra. Dopo la prima disposizione il PanedWindow non segue
    più la larghezza richiesta: il divisore si sposta con sashpos (regola 18)."""

    def __init__(self, padre, finestra=None):
        super().__init__(padre, orient="horizontal")
        self.finestra = _f(finestra)
        self.colonna = None
        self._sistemato = False
        self.bind("<Map>", self._prima_volta, add="+")

    def metti(self, colonna, contenuto):
        self.add(colonna, weight=0)
        self.add(contenuto, weight=1)
        self.colonna = colonna
        colonna.pannello = self

    def _prima_volta(self, _evento=None):
        if not self._sistemato:
            self._sistemato = True
            self.after(60, self.sistema_divisore)

    def sistema_divisore(self):
        if self.colonna is None:
            return
        try:
            self.update_idletasks()
            w = self.colonna.larghezza_richiesta()
            tot = self.winfo_width()
            if tot > 50:
                w = min(w, int(tot * 0.6))
            self.sashpos(0, w)
        except tk.TclError:
            pass


class PulsanteOpzioni(ttk.Button):
    """Regola 13: «Nascondi opzioni / Mostra opzioni», ricordato nelle impostazioni.
    La cornice delle opzioni va messa (grid o pack) prima che la finestra si apra."""

    def __init__(self, padre, cornice, finestra=None, chiave="opzioni_nascoste"):
        f = self.finestra = _f(finestra)
        self.cornice, self.chiave = cornice, chiave
        self.nascoste = bool(f.impostazioni.get(chiave, False))
        super().__init__(padre, command=self.cambia, text=self._testo())
        f.importante(self)
        if self.nascoste:
            self.after_idle(lambda: nascondi(self.cornice))

    def _testo(self):
        return "Mostra opzioni" if self.nascoste else "Nascondi opzioni"

    def cambia(self):
        self.nascoste = not self.nascoste
        (nascondi if self.nascoste else mostra)(self.cornice)
        self.configure(text=self._testo())
        self.finestra.impostazioni.imposta(self.chiave, self.nascoste)
        for c in self.finestra.colonne:
            c.after_idle(c._controlla_barra)


class Schede(ttk.Notebook):
    """Regola 19: linguette con nomi corti e carattere che si rimpicciolisce finché ci stanno
    (minimo 9 punti). Al cambio di scheda i grafici della scheda nuova si ridisegnano (regola 20)."""

    _numero = 0

    def __init__(self, padre, finestra=None):
        Schede._numero += 1
        self.nome_stile = f"FC{Schede._numero}.TNotebook"
        f = self.finestra = _f(finestra)
        super().__init__(padre, style=self.nome_stile)
        famiglia = tkfont.nametofont("TkDefaultFont", root=f.radice).actual().get("family")
        self.carattere = f._carattere(f"FCSchede{Schede._numero}", family=famiglia,
                                      size=int(round(PUNTI_BASE * f.scala)))
        self._ultima_larghezza = 0
        self._adatta_linguette_stile()
        self.bind("<Configure>", self._configura, add="+")
        self.bind("<<NotebookTabChanged>>", self._cambio, add="+")
        f.schede.append(self)
        f.al_cambio_scala(lambda s: self.after(40, self.adatta_linguette))

    def aggiungi(self, testo, cornice=None, **opzioni):
        """Aggiunge una scheda (nome CORTO) e restituisce la cornice dove mettere il contenuto."""
        cornice = cornice if cornice is not None else ttk.Frame(self, **opzioni)
        self.add(cornice, text=testo)
        self.after_idle(self.adatta_linguette)
        return cornice

    def _pad(self):
        """1.1: lo spazio attorno ai nomi segue il carattere delle LINGUETTE, non quello della finestra
        (al 200 % con le linguette a 9 punti lo spazio da solo valeva ~700 pixel)."""
        r = self.carattere.metrics("linespace")
        return max(4, round(r * 0.5)), max(2, round(r * 0.22))

    def _adatta_linguette_stile(self):
        self.finestra.stile.configure(self.nome_stile + ".Tab", font=self.carattere, padding=self._pad())

    def larghezza_linguette(self):
        px, _ = self._pad()
        tot = 0
        for t in self.tabs():
            tot += self.carattere.measure(self.tab(t, "text")) + 2 * px + 8
        return tot + 6

    def adatta_linguette(self):
        try:
            larg = self.winfo_width()
        except tk.TclError:
            return
        dim = int(round(PUNTI_BASE * self.finestra.scala))
        self.carattere.configure(size=dim)
        if larg > 50:
            while dim > PUNTI_MINIMI_SCHEDE and self.larghezza_linguette() > larg - 4:
                dim -= 1
                self.carattere.configure(size=dim)
        self._adatta_linguette_stile()

    def _configura(self, evento):
        if abs(evento.width - self._ultima_larghezza) > 4:
            self._ultima_larghezza = evento.width
            self.after_idle(self.adatta_linguette)

    def _cambio(self, _evento=None):
        for g in self.finestra.grafici:
            g.richiedi()


class Grafico(ttk.Frame):
    """Grafico matplotlib dentro Tk (regole 7, 14, 20 e del 17/11).
    - disegna(funzione): funzione(figura) disegna da capo; si richiama a ogni cambio di misura/scala;
    - dpi = linespace / 1,2 × 0,85 × 72 / 10, ≤ min(larghezza/7, altezza/4,5), misura della parte VISIBILE;
    - ridisegno con after(60); constrained_layout; firma in basso a destra;
    - barra di matplotlib nascosta, pulsanti italiani: Inizio, Indietro, Avanti, Sposta, Ingrandisci, Salva."""

    def __init__(self, padre, finestra=None, disegna=None, pulsanti=True, nome_file="grafico", firma=True):
        super().__init__(padre)
        f = self.finestra = _f(finestra)
        import matplotlib
        if matplotlib.get_backend().lower() != "tkagg":
            try:
                matplotlib.use("TkAgg")
            except Exception:
                pass
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        self.nome_file = nome_file
        self.con_firma = firma
        self.figura = Figure(figsize=FIGURA_MINIMA, dpi=f.dpi_grafici(), layout="constrained")
        self.tela = FigureCanvasTkAgg(self.figura, master=self)
        self.barra_mpl = NavigationToolbar2Tk(self.tela, self, pack_toolbar=False)   # mai mostrata
        self.riga = RigaACapo(self, f, spazio=6)       # va a capo se il grafico è stretto
        self.pulsanti = {}
        if pulsanti:
            self.riga.pack(side="bottom", fill="x", pady=(4, 0))                   # regola 1
            for chiave, testo, comando in (("inizio", "Inizio", self.barra_mpl.home),
                                           ("indietro", "Indietro", self.barra_mpl.back),
                                           ("avanti", "Avanti", self.barra_mpl.forward),
                                           ("sposta", "Sposta", self._sposta),
                                           ("ingrandisci", "Ingrandisci", self._ingrandisci),
                                           ("salva", "Salva…", self.salva)):
                self.pulsanti[chiave] = self.riga.pulsante(testo, comando)
        self.widget = self.tela.get_tk_widget()
        self.widget.configure(width=200, height=150)    # niente richieste enormi alla finestra
        self.widget.pack(side="top", fill="both", expand=True)
        self.widget.bind("<Configure>", lambda e: self.richiedi(), add="+")
        self.widget.bind("<Map>", lambda e: self.richiedi(), add="+")
        self._funzione = disegna
        self._attesa = None
        self.disegnato_a = None          # (larghezza, altezza, dpi) dell'ultimo disegno
        f.grafici.append(self)
        f.al_cambio_scala(lambda s: self.richiedi())

    # -------------------------------------------------- disegno
    def disegna(self, funzione):
        """Imposta la funzione di disegno (funzione(figura)) e ridisegna appena possibile."""
        self._funzione = funzione
        self.disegnato_a = None
        self.richiedi()

    def richiedi(self):
        try:
            if self._attesa is not None:
                self.after_cancel(self._attesa)
            self._attesa = self.after(RITARDO_GRAFICO, self.ridisegna)
        except tk.TclError:
            pass

    def visibile(self):
        try:
            return bool(self.widget.winfo_viewable()) and self.widget.winfo_width() > 20 and self.widget.winfo_height() > 20
        except tk.TclError:
            return False

    def dpi_per(self, larghezza, altezza):
        return max(30.0, min(self.finestra.dpi_grafici(), larghezza / FIGURA_MINIMA[0], altezza / FIGURA_MINIMA[1]))

    def ridisegna(self):
        self._attesa = None
        if not self.visibile():
            return                       # una scheda nascosta misura 1×1: si disegna quando si vede
        w, h = self.widget.winfo_width(), self.widget.winfo_height()
        dpi = self.dpi_per(w, h)
        if self.disegnato_a is not None and self.disegnato_a[:2] == (w, h) and abs(self.disegnato_a[2] - dpi) < 0.01 \
                and self._funzione is None:
            return
        self.figura.set_dpi(dpi)
        self.figura.set_size_inches(w / dpi, h / dpi, forward=False)
        if self._funzione is not None:
            self.figura.clf()
            try:
                self._funzione(self.figura)
            except Exception as e:
                self.figura.clf()
                self.figura.text(0.5, 0.5, f"Errore nel grafico:\n{type(e).__name__}: {e}", ha="center",
                                 va="center", color="#b91c1c", wrap=True)
                traceback.print_exc()
            if self.con_firma:
                firma_figura(self.figura)
        self.tela.draw_idle()
        self.disegnato_a = (w, h, dpi)

    # -------------------------------------------------- pulsanti
    def _modo(self):
        modo = str(getattr(self.barra_mpl, "mode", "") or "")
        if self.pulsanti:
            self.pulsanti["sposta"].configure(style="Attivo.TButton" if "pan" in modo else "TButton")
            self.pulsanti["ingrandisci"].configure(style="Attivo.TButton" if "zoom" in modo else "TButton")

    def _sposta(self):
        self.barra_mpl.pan()
        self._modo()

    def _ingrandisci(self):
        self.barra_mpl.zoom()
        self._modo()

    def salva(self):
        p = self.finestra.salva_file("Salva il grafico", f"{self.nome_file}.png",
                                     [("Immagine PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")])
        if not p:
            return None
        try:
            self.figura.savefig(p, dpi="figure")
            self.finestra.stato(f"Grafico salvato: {p}")
        except Exception as e:
            self.finestra.errore("Grafico non salvato", f"{type(e).__name__}: {e}")
            return None
        return p


def firma_figura(figura, testo=FIRMA):
    figura.text(0.995, 0.004, testo, ha="right", va="bottom", fontsize="x-small", color=GRIGIO, alpha=0.8)


def legenda_fuori(asse, **opzioni):
    """Regola 20: legenda dei grafici affollati fuori a destra (con constrained_layout)."""
    opzioni.setdefault("loc", "upper left")
    opzioni.setdefault("bbox_to_anchor", (1.01, 1.0))
    opzioni.setdefault("borderaxespad", 0.0)
    opzioni.setdefault("fontsize", "small")
    return asse.legend(**opzioni)


class Tabella(ttk.Frame):
    """Treeview con righe alte quanto il testo e colonne larghe quanto un testo d'esempio.
    colonne = [(chiave, titolo, esempio), …]; l'ultima prende lo spazio che resta."""

    def __init__(self, padre, colonne, finestra=None, altezza=8):
        super().__init__(padre)
        f = self.finestra = _f(finestra)
        self.colonne = [(c[0], c[1], c[2] if len(c) > 2 else c[1]) for c in colonne]
        self.albero = ttk.Treeview(self, columns=[c[0] for c in self.colonne], show="headings", height=altezza)
        for chiave, titolo, _ in self.colonne:
            self.albero.heading(chiave, text=titolo, anchor="w")
        sv = ttk.Scrollbar(self, orient="vertical", command=self.albero.yview)
        so = ttk.Scrollbar(self, orient="horizontal", command=self.albero.xview)
        self.albero.configure(yscrollcommand=sv.set, xscrollcommand=so.set)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.albero.grid(row=0, column=0, sticky="nsew")
        sv.grid(row=0, column=1, sticky="ns")
        so.grid(row=1, column=0, sticky="ew")
        self.larghezze()
        f.al_cambio_scala(lambda s: self.larghezze())

    def larghezze(self):
        f = self.finestra
        r = f.altezza_riga()
        for i, (chiave, titolo, esempio) in enumerate(self.colonne):
            larg = max(f.misura(esempio), f.misura(titolo, "FCGrande")) + r
            ultima = i == len(self.colonne) - 1
            self.albero.column(chiave, width=larg, minwidth=max(30, larg // 2), stretch=ultima, anchor="w")

    def inserisci(self, valori):
        return self.albero.insert("", "end", values=list(valori))

    def svuota(self):
        self.albero.delete(*self.albero.get_children())

    def righe(self):
        return self.albero.get_children()


class Registro(ttk.Frame):
    """Registro di testo a sola lettura; scrivi() si può chiamare anche da un altro thread."""

    def __init__(self, padre, finestra=None, altezza=8, massimo_righe=5000):
        super().__init__(padre)
        self.finestra = _f(finestra)
        self.massimo = massimo_righe
        self.coda = queue.Queue()
        self.testo = tk.Text(self, wrap="word", font="FCMono", height=altezza, width=1, padx=10, pady=8,
                             relief="flat", state="disabled")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.testo.yview)
        self.testo.configure(yscrollcommand=sb.set)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.testo.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.righe_scritte = 0
        self.after(100, self._leggi)

    def scrivi(self, riga):
        self.coda.put(str(riga))

    def _leggi(self):
        nuove = []
        try:
            while True:
                nuove.append(self.coda.get_nowait())
        except queue.Empty:
            pass
        if nuove:
            self.testo.configure(state="normal")
            for r in nuove:
                self.testo.insert("end", r + "\n")
            self.righe_scritte += len(nuove)
            if self.righe_scritte > self.massimo:
                self.testo.delete("1.0", f"{self.righe_scritte - self.massimo + 1}.0")
                self.righe_scritte = self.massimo
            self.testo.configure(state="disabled")
            self.testo.see("end")
        try:
            self.after(100, self._leggi)
        except tk.TclError:
            pass

    def svuota(self):
        self.testo.configure(state="normal")
        self.testo.delete("1.0", "end")
        self.testo.configure(state="disabled")
        self.righe_scritte = 0


class Lavoro:
    """Calcolo in sottofondo: funzione(avvisa, fermo) gira in un thread; avvisa(testo) manda messaggi
    alla finestra; fermo è un threading.Event da controllare per fermarsi. I pulsanti indicati
    restano spenti finché il lavoro non è finito."""

    def __init__(self, finestra, funzione, al_termine=None, al_errore=None, al_messaggio=None, pulsanti=()):
        self.finestra = _f(finestra)
        self.al_termine, self.al_errore = al_termine, al_errore
        self.al_messaggio = al_messaggio or self.finestra.stato
        self.pulsanti = list(pulsanti)
        self.fermo = threading.Event()
        self.coda = queue.Queue()
        self.attivo = True
        self.risultato = None
        for b in self.pulsanti:
            b.state(["disabled"])

        def lavoro():
            try:
                self.coda.put(("fine", funzione(self.avvisa, self.fermo)))
            except Exception:
                self.coda.put(("errore", traceback.format_exc()))
        threading.Thread(target=lavoro, daemon=True).start()
        self.finestra.radice.after(100, self._leggi)

    def avvisa(self, testo):
        self.coda.put(("msg", testo))

    def ferma(self):
        self.fermo.set()

    def _leggi(self):
        try:
            while True:
                tipo, valore = self.coda.get_nowait()
                if tipo == "msg":
                    self.al_messaggio(valore)
                    continue
                self.attivo = False
                for b in self.pulsanti:
                    try:
                        b.state(["!disabled"])
                    except tk.TclError:
                        pass
                if tipo == "fine":
                    self.risultato = valore
                    if self.al_termine:
                        self.al_termine(valore)
                else:
                    if self.al_errore:
                        self.al_errore(valore)
                    else:
                        self.finestra.errore("Errore", valore[-3000:])
                return
        except queue.Empty:
            pass
        try:
            self.finestra.radice.after(100, self._leggi)
        except tk.TclError:
            pass


# =========================================================================== autotest comune
def _discendenti(w):
    for c in w.winfo_children():
        if isinstance(c, tk.Toplevel):
            continue
        yield c
        yield from _discendenti(c)


def _testo_di(w):
    try:
        return str(w.cget("text"))
    except (tk.TclError, AttributeError):
        return ""


def _nome(w, radice=None):
    if w is None or w == "":
        return "niente"
    if isinstance(w, str):
        try:
            w = radice.nametowidget(w)
        except Exception:
            return w
    t = _testo_di(w).replace("\n", " ")
    classe = w.winfo_class()
    return f"{classe} «{t[:40]}»" if t else f"{classe} {str(w)[-40:]}"


def _carattere_widget(w, radice):
    nome = ""
    try:
        nome = str(w.cget("font"))
    except (tk.TclError, AttributeError):
        pass
    if not nome:
        try:
            stile = str(w.cget("style")) or w.winfo_class()
            nome = str(ttk.Style(radice).lookup(stile, "font")) or ""
        except (tk.TclError, AttributeError):
            nome = ""
    if not nome:
        nome = "TkTextFont" if w.winfo_class() in ("TCombobox", "TEntry") else "TkDefaultFont"
    try:
        return tkfont.nametofont(nome, root=radice)
    except tk.TclError:
        return tkfont.Font(root=radice, font=nome)


def _colonna_di(w, finestra):
    for c in finestra.colonne:
        if str(w) == str(c.interno) or str(w).startswith(str(c.interno) + "."):
            return c
    return None


def _giro_schede(finestra):
    """Mostra a turno ogni scheda di ogni Schede visibile; restituisce la descrizione della vista."""
    if not finestra.schede:
        yield "finestra"
        return
    for sc in finestra.schede:
        try:
            if not sc.winfo_viewable():
                continue
            originale = sc.select()
        except tk.TclError:
            continue
        for t in sc.tabs():
            sc.select(t)
            yield f"scheda «{sc.tab(t, 'text')}»"
        try:
            sc.select(originale)
        except tk.TclError:
            pass


def _controlla_vista(finestra, dove):
    r = finestra.radice
    r.update_idletasks()
    rx, ry, rw, rh = r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height()
    n, problemi = 0, []

    def problema(testo):
        problemi.append(f"[{dove}] {testo}")

    comandi = ("TButton", "Button", "TCheckbutton", "TRadiobutton", "TCombobox", "TEntry", "TMenubutton")
    for w in list(_discendenti(r)):
        try:
            if not w.winfo_viewable():
                continue
            classe = w.winfo_class()
        except tk.TclError:
            continue
        testo = _testo_di(w)
        if testo:
            n += 1
            if ha_emoji(testo):
                problema(f"{_nome(w)}: emoji nel testo (su Linux possono far chiudere la finestra)")
            if ha_accenti_combinanti(testo):
                problema(f"{_nome(w)}: accento combinante nel testo (in Tk si vede spostato)")
        colonna = _colonna_di(w, finestra)
        if colonna is not None and (classe in comandi or w in finestra.importanti):
            colonna.mostra(w)
        x, y, ww, hh = w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height()
        if colonna is None:
            n += 1
            if x + ww > rx + rw + 2 or y + hh > ry + rh + 2 or x < rx - 2 or y < ry - 2:
                problema(f"{_nome(w)} esce dal bordo della finestra ({x - rx},{y - ry} {ww}×{hh} "
                         f"in una finestra {rw}×{rh})")
        if classe in comandi or w in finestra.importanti:
            n += 1
            if ww < 8 or hh < 8:
                problema(f"{_nome(w)} schiacciato ({ww}×{hh} pixel)")
                continue
            cx, cy = x + ww // 2, y + hh // 2
            try:
                sopra = str(r.tk.call("winfo", "containing", cx, cy))
            except tk.TclError:
                sopra = ""
            if not (sopra == str(w) or sopra.startswith(str(w) + ".")):
                problema(f"{_nome(w)}: al centro ({cx - rx},{cy - ry}) c'è {_nome(sopra, r)}")
            if testo and classe in ("TButton", "Button"):
                n += 1
                if _carattere_widget(w, r).measure(testo) > ww - 4:
                    problema(f"{_nome(w)}: testo tagliato (serve {_carattere_widget(w, r).measure(testo)} px, "
                             f"il pulsante è largo {ww})")
        if classe == "TCombobox":
            n += 1
            car = _carattere_widget(w, r)
            testi = [str(w.get())] + [str(v) for v in r.tk.splitlist(w.cget("values"))]
            lungo = max(testi, key=car.measure)
            if car.measure(lungo) >= ww - hh - 8:
                problema(f"tendina «{lungo}»: il testo non ci sta (serve {car.measure(lungo)} px, "
                         f"ci sono {ww - hh - 8} px)")
    for sc in finestra.schede:
        try:
            if not sc.winfo_viewable():
                continue
        except tk.TclError:
            continue
        n += 1
        for t in sc.tabs():
            if ha_emoji(sc.tab(t, "text")):
                problema(f"linguetta «{sc.tab(t, 'text')}»: emoji")
        if sc.larghezza_linguette() > sc.winfo_width() + 2:
            problema(f"linguette: servono {sc.larghezza_linguette()} px, ce ne sono {sc.winfo_width()} "
                     f"(carattere {sc.carattere.actual('size')} punti): accorciare i nomi")
    for c in finestra.colonne:
        try:
            if not c.winfo_viewable():
                continue
        except tk.TclError:
            continue
        if not c.caratteri:              # pagina scorrevole (caratteri=0): larga quanto la scheda
            continue
        n += 1
        minimo = finestra.larghezza_colonna(c.caratteri)
        if c.winfo_width() < minimo * 0.95:
            problema(f"colonna dei comandi schiacciata ({c.winfo_width()} px, ne servono almeno {minimo})")
    for g in finestra.grafici:
        if not g.visibile():
            continue
        n += 1
        w, h = g.widget.winfo_width(), g.widget.winfo_height()
        fw, fh = g.figura.bbox.width, g.figura.bbox.height
        if g.disegnato_a is None or abs(fw - w) > 3 or abs(fh - h) > 3:
            problema(f"grafico non ridisegnato alla misura vera (scheda {w}×{h}, figura {fw:.0f}×{fh:.0f})")
        if g.figura.dpi > finestra.dpi_grafici() + 0.5:
            problema(f"grafico con dpi {g.figura.dpi:.0f} oltre quelli del testo ({finestra.dpi_grafici():.0f})")
    return n, problemi


def controlla_finestra(finestra, scale=(1.0, 1.5, 2.0), stampa=print, pausa=0.35):
    """Autotest comune (regole 4, 12, 19, 20 e niente emoji): alla dimensione vera della finestra,
    per ogni scala e ogni scheda controlla che al centro di ogni comando ci sia quel comando,
    che il testo di tendine e pulsanti ci stia, che niente esca dal bordo, che i grafici abbiano la
    misura della scheda visibile. Stampa chi copre chi. Restituisce (controlli, problemi)."""
    r = finestra.radice
    r.deiconify()
    r.lift()
    aspetta(r, 0.8)
    iniziale = finestra.scala
    tutti, totale = {}, 0
    for s in scale:
        finestra.applica_scala(s, salva=False)
        aspetta(r, pausa + 0.3)
        stampa(f"  scala {int(round(s * 100))} %: finestra {r.winfo_width()}×{r.winfo_height()} pixel, "
               f"riga {finestra.altezza_riga()} px, dpi grafici {finestra.dpi_grafici():.0f}")
        sh = r.winfo_screenheight()
        if r.winfo_rooty() + r.winfo_height() > sh + 2:
            tutti.setdefault(f"[{int(s * 100)} %] la finestra esce dal fondo dello schermo", None)
        for dove in _giro_schede(finestra):
            aspetta(r, pausa)
            n, problemi = _controlla_vista(finestra, f"{int(round(s * 100))} % · {dove}")
            totale += n
            for p in problemi:
                tutti.setdefault(p, None)
    finestra.applica_scala(iniziale, salva=False)
    aspetta(r, pausa)
    for p in tutti:
        stampa("  PROBLEMA " + p)
    stampa(f"  {totale} controlli della finestra, {len(tutti)} problemi")
    return totale, list(tutti)
