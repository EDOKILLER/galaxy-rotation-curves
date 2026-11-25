#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Curve di rotazione 1.0 – la materia che manca nelle galassie
© 2026 Edoardo Battistel · licenza BSD-3

Finestra costruita con la libreria comune finestra_comune.py 1.1.
Uso:
    python3 curve_rotazione.py                      finestra
    python3 curve_rotazione.py --autotest           prove dei calcoli + finestra (controlla_finestra)
    python3 curve_rotazione.py --scala 200          dimensione del testo all'avvio
    python3 curve_rotazione.py --galassia NGC3198   scheda PDF + PNG di una galassia, senza finestra
    python3 curve_rotazione.py --tutte              adattamenti di tutte le galassie (CSV + PDF), senza finestra
"""
import argparse
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

import motore_curve as mc

VERSIONE = mc.VERSIONE
NOME = "Curve di rotazione"

SCELTE_MODELLI = {
    "NFW + Burkert (cuspide e nucleo)": ("NFW", "Burkert"),
    "NFW + Burkert + MOND": ("NFW", "Burkert", "MOND"),
    "Tutti e quattro i modelli": mc.MODELLI,
    "Solo NFW (cuspide)": ("NFW",),
    "Solo Burkert (nucleo)": ("Burkert",),
    "Solo isotermo pISO (nucleo)": ("pISO",),
    "Solo MOND (niente materia oscura)": ("MOND",),
    "Nessun modello (solo le misure)": (),
}
SCELTE_ML = {"Libero (vicino a 0,5)": "libero", "Fisso (dal contatore)": "fisso"}
COMPONENTI = (("gas", "Gas (idrogeno ed elio)"), ("disco", "Disco di stelle"), ("bulbo", "Bulbo"),
              ("barioni", "Tutta la materia visibile"), ("alone", "Alone di materia oscura da solo"),
              ("li", "Adattamenti pubblicati (Li et al. 2020)"), ("residui", "Residui sotto il grafico"))
BASE = dict(galassia="NGC3198", modelli="NFW + Burkert (cuspide e nucleo)", ml="Libero (vicino a 0,5)", yd=0.5,
            componenti=["gas", "disco", "bulbo", "barioni", "residui"], csv_salsa="")


class Programma:
    def __init__(self, autotest=False, scala=None, rete=True):
        import finestra_comune as fc
        from tkinter import ttk
        import tkinter as tk
        self.fc, self.tk, self.ttk = fc, tk, ttk
        self.autotest = autotest
        self.rete = rete
        f = self.f = fc.Finestra("CurveRotazione", f"{NOME} {VERSIONE} – materia visibile e materia oscura",
                                 programma="curve_rotazione", icona="curve_rotazione.png", versione=VERSIONE,
                                 impostazioni_base=BASE, autotest=autotest, scala=scala)
        self.imp = f.impostazioni
        # anche i messaggi della libreria (es. «Grafico salvato: <percorso>») passano dall'accorciamento
        f.stato = lambda testo, _orig=fc.Finestra.stato: _orig(f, self.breve(testo))
        self.cat = None
        self.chiave = None
        self.ris = {}
        self.imgs = {}
        self.tutti = None
        self.etichette = {}          # etichetta della tendina → chiave
        self.cartella = None
        self.calcolo = None
        self.pendente = None
        self.lavoro_immagini = None
        self.lavoro_tutte = None
        self.lavoro_salva = None
        self.lavoro_scheda = None
        self.errori = []
        self._costruisci()
        f.radice.after(200, self.carica)

    # ------------------------------------------------------------------ finestra
    def _costruisci(self):
        fc, ttk, tk, f = self.fc, self.ttk, self.tk, self.f
        pannello = fc.PannelloDiviso(f.corpo)
        pannello.pack(fill="both", expand=True)
        col = self.colonna = fc.ColonnaScorrevole(pannello)
        destra = ttk.Frame(pannello)
        pannello.metti(col, destra)
        i = col.interno
        intro = fc.Etichetta(i, "Scegli una galassia: i punti sono le velocità misurate, le linee quelle che darebbero "
                                "le stelle e il gas visibili. La differenza è la massa che manca.", style="Piccolo.TLabel")
        col.aggiungi(intro)
        f.nascondi_da_scala(intro)
        self.var_cerca = tk.StringVar(f.radice, value="")
        self.cerca = col.aggiungi(fc.RigaCampo(i, "Cerca", self.var_cerca, caratteri=12))
        self.var_cerca.trace_add("write", lambda *a: self._filtra())
        self.t_galassia = col.aggiungi(fc.RigaTendina(i, "Galassia", ["(carico i dati…)"], larga=True,
                                                      comando=self._scelta_galassia))
        self.info = col.aggiungi(fc.Etichetta(i, ""))
        modelli = self.imp.get("modelli") if self.imp.get("modelli") in SCELTE_MODELLI else BASE["modelli"]
        self.t_modelli = col.aggiungi(fc.RigaTendina(i, "Modelli da mostrare", list(SCELTE_MODELLI),
                                                     tk.StringVar(f.radice, value=modelli), larga=True,
                                                     comando=lambda v: self._cambio("modelli", v)))
        ml = self.imp.get("ml") if self.imp.get("ml") in SCELTE_ML else BASE["ml"]
        self.t_ml = col.aggiungi(fc.RigaTendina(i, "Rapporto massa/luce del disco", list(SCELTE_ML),
                                                tk.StringVar(f.radice, value=ml), larga=True,
                                                comando=lambda v: self._cambio("ml", v, ricalcola=True)))
        self.cont = col.aggiungi(fc.Contatore(i, "Massa/luce fissa (a 3,6 µm)", 0.1, 2.0,
                                              float(self.imp.get("yd", 0.5)), passo=0.05,
                                              comando=lambda v: self._cambio("yd", v, ricalcola=True)))
        self.suggerimento = col.aggiungi(fc.Suggerimento(i))
        # spunte delle componenti in una cornice che si può nascondere (regola 13)
        cornice = ttk.LabelFrame(i, text="Cosa mostrare", padding=(8, 4, 8, 4))
        cornice.columnconfigure(0, weight=1)
        self.spunte = {}
        scelte = set(self.imp.get("componenti", BASE["componenti"]))
        for r, (k, testo) in enumerate(COMPONENTI):
            s = fc.Spunta(cornice, testo, tk.BooleanVar(f.radice, value=k in scelte), comando=self._componenti)
            s.grid(row=r, column=0, sticky="ew", pady=(0, 2))
            self.spunte[k] = s
        self.p_opzioni = fc.PulsanteOpzioni(i, cornice)
        col.aggiungi(self.p_opzioni, sticky="w")
        col.aggiungi(cornice)
        riga = fc.RigaPulsanti(i)
        self.b_tutte = riga.pulsante("Tutte le galassie", self.tutte, grande=True)
        col.aggiungi(riga)
        riga2 = fc.RigaPulsanti(i)
        self.b_salsa = riga2.pulsante("Curva SALSA…", self.scegli_salsa)
        col.aggiungi(riga2)
        col.aggiungi(f.tendina_scala(i))
        # schede
        sc = self.schede = fc.Schede(destra)
        sc.pack(fill="both", expand=True)
        self.g_curva = fc.Grafico(sc.aggiungi("Curva"), nome_file="curva_di_rotazione")
        self.g_curva.pack(fill="both", expand=True)
        self.g_insieme = fc.Grafico(sc.aggiungi("Insieme"), nome_file="tully_fisher_accelerazioni")
        self.g_insieme.pack(fill="both", expand=True)
        self.g_immagini = fc.Grafico(sc.aggiungi("Immagini"), nome_file="immagini")
        self.g_immagini.pack(fill="both", expand=True)
        par = sc.aggiungi("Parametri", padding=8)
        par.columnconfigure(0, weight=1)
        par.rowconfigure(1, weight=1)
        self.testo_par = fc.Etichetta(par, "")
        self.testo_par.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.tab_par = fc.Tabella(par, [("m", "Modello", "Burkert"), ("chi", "χ² rid.", "999,99"),
                                        ("ml", "Massa/luce", "0,00 ± 0,00"), ("fdm", "Materia oscura", "100 %"),
                                        ("li", "Li et al. 2020", "χ² 99,99 · M/L 0,00"),
                                        ("p", "Parametri dell'alone", "V200 = 110,5 ± 2,0 km/s, c = 10,3 ± 1,1, M200 = 4,3e11")],
                                  altezza=5)
        self.tab_par.grid(row=1, column=0, sticky="nsew")
        tut = sc.aggiungi("Tutte", padding=8)
        tut.columnconfigure(0, weight=1)
        tut.rowconfigure(1, weight=2)
        tut.rowconfigure(2, weight=3)
        self.testo_tutte = fc.Etichetta(tut, "Premi «Tutte le galassie» per adattare i quattro modelli a tutte le "
                                             "galassie (circa mezzo minuto). Un clic su una riga apre la galassia.")
        self.testo_tutte.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.tab_tutte = fc.Tabella(tut, [("g", "Galassia", "UGC 2885 – galassia di Rubin"), ("q", "Qualità", "Qual."),
                                          ("v", "V piatta", "999 km/s"), ("b", "Migliore", "Burkert"),
                                          ("nfw", "χ² NFW", "999,99"), ("bur", "χ² Burkert", "999,99"),
                                          ("iso", "χ² pISO", "999,99"), ("mond", "χ² MOND", "999,99"),
                                          ("ml", "M/L (Burkert)", "0,00"), ("fdm", "Materia oscura", "100 %")],
                                    altezza=6)
        self.tab_tutte.grid(row=1, column=0, sticky="nsew")
        self.tab_tutte.albero.bind("<<TreeviewSelect>>", self._riga_tutte, add="+")
        self.g_tutte = fc.Grafico(tut, nome_file="riassunto_tutte")
        self.g_tutte.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        note = fc.ColonnaScorrevole(sc.aggiungi("Note"), caratteri=0)
        note.pack(fill="both", expand=True)
        for titolo, testo in mc.NOTE_IT:
            note.aggiungi(fc.Etichetta(note.interno, titolo, style="Titolo.TLabel"), pady=(8, 2))
            note.aggiungi(fc.Etichetta(note.interno, testo), pady=(0, 6))
        self.registro = fc.Registro(sc.aggiungi("Registro"))
        self.registro.pack(fill="both", expand=True)
        # barra in basso
        b = f.barra
        self.b_scheda = b.pulsante("Salva la scheda (PDF + PNG)", self.salva_scheda, grande=True)
        self.b_salva_tutte = b.pulsante("Salva tutte (CSV + PDF)", self.salva_tutte)
        b.pulsante("Apri la cartella dei risultati", self.apri_cartella)
        b.pulsante("Esci", f.chiudi)
        f.radice.after(400, self._aggiorna_suggerimento)

    # ------------------------------------------------------------------ messaggi
    def avvisa(self, testo):
        self.registro.scrivi(f"{time.strftime('%H:%M:%S')}  {testo}")
        self.f.stato(self.breve(testo))
        if self.autotest:
            print("   ·", testo, flush=True)

    @staticmethod
    def breve(testo, massimo=90):
        """Riga di stato corta: una sola riga, percorsi ridotti al nome del file (un percorso lungo andava a capo
        su molte righe e la barra in basso copriva i pulsanti dei grafici – autotest del 25/11)."""
        riga = str(testo).splitlines()[0] if str(testo).strip() else ""
        riga = " ".join(Path(p).name if "/" in p and len(p) > 25 else p for p in riga.split(" "))
        return riga if len(riga) <= massimo else riga[:massimo - 1] + "…"

    def _errore(self, titolo, testo):
        self.errori.append(f"{titolo}: {testo[-500:]}")
        self.registro.scrivi(testo)
        self.f.errore(titolo, testo[-3000:])

    # ------------------------------------------------------------------ dati
    def carica(self):
        self.avvisa("carico il catalogo (SPARC, M 33, Via Lattea, Li et al. 2020)…")
        csv_salsa = self.imp.get("csv_salsa") or None
        self.fc.Lavoro(self.f, lambda avvisa, fermo: mc.carica_catalogo(avvisa, self.rete, csv_salsa),
                       al_termine=self._caricato, al_errore=lambda t: self._errore("Dati non caricati", t),
                       al_messaggio=self.avvisa, pulsanti=[self.b_tutte, self.b_salsa])

    def _caricato(self, cat):
        self.cat = cat
        self.etichette = {cat.etichetta(k): k for k in cat.chiavi_ordinate()}
        self._filtra()
        k = self.imp.get("galassia", "NGC3198")
        if k not in cat.galassie:
            k = "NGC3198" if "NGC3198" in cat.galassie else cat.chiavi_ordinate()[0]
        self.seleziona(k)
        self.g_insieme.disegna(lambda fig: mc.disegna_insieme(fig, cat, self.chiave))
        vl = cat.galassie["VIA_LATTEA"]
        self.avvisa(f"pronto: {len(cat.galassie)} galassie" + (
            f"; Via Lattea con {vl['n_edoardo']} punti SALSA" if vl.get("n_edoardo") else
            "; nessuna curva SALSA trovata (pulsante «Curva SALSA…»)"))

    def _filtra(self):
        if not self.cat:
            return
        testo = self.var_cerca.get().strip().lower().replace(" ", "")
        valori = [e for e, k in self.etichette.items()
                  if not testo or testo in e.lower().replace(" ", "") or testo in k.lower()]
        self.t_galassia.imposta_valori(valori or ["(nessuna galassia)"])
        if len(valori) == 1 and self.etichette[valori[0]] != self.chiave:
            self.seleziona(self.etichette[valori[0]])

    def _scelta_galassia(self, valore):
        k = self.etichette.get(valore)
        if k:
            self.seleziona(k)

    # ------------------------------------------------------------------ calcolo
    def modelli(self):
        return SCELTE_MODELLI.get(self.t_modelli.get(), ("NFW", "Burkert"))

    def ml(self):
        return SCELTE_ML.get(self.t_ml.get(), "libero")

    def componenti(self):
        return tuple(k for k, s in self.spunte.items() if s.get())

    def seleziona(self, k):
        if not self.cat or k not in self.cat.galassie:
            return
        self.chiave = k
        self.t_galassia.set(self.cat.etichetta(k))
        self.imp.imposta("galassia", k)
        self.calcola()
        self.immagini()

    def calcola(self):
        if self.chiave is None:
            return
        if self.calcolo is not None and self.calcolo.attivo:
            self.pendente = True
            return
        self.pendente = False
        g = self.cat.galassie[self.chiave]
        ml, yd = self.ml(), self._yd()
        chiave = self.chiave
        self.f.stato(self.breve(f"adatto i modelli a {g['nome']}…"))
        self.calcolo = self.fc.Lavoro(self.f, lambda avvisa, fermo: (chiave, ml, yd, mc.adatta_tutti(g, ml, yd or mc.ML_DISCO)),
                                      al_termine=self._calcolato,
                                      al_errore=lambda t: self._errore("Calcolo non riuscito", t),
                                      al_messaggio=self.avvisa)

    def _calcolato(self, valore):
        chiave, ml, yd, ris = valore
        self.ris[(chiave, ml, yd)] = ris
        if self.pendente or chiave != self.chiave or ml != self.ml() or yd != self._yd():
            self.calcola()
            return
        self._mostra()

    def _yd(self):
        """Il contatore conta solo con la massa/luce «Fisso»."""
        return self.cont.get() if self.ml() == "fisso" else None

    def risultati_attuali(self):
        return self.ris.get((self.chiave, self.ml(), self._yd()))

    def _mostra(self):
        ris = self.risultati_attuali()
        if ris is None:
            return
        g = self.cat.galassie[self.chiave]
        li = self.cat.li.get(self.chiave) if "li" in self.componenti() else None
        modelli, comp = self.modelli(), self.componenti()
        yd = self.cont.get() if self.ml() == "fisso" else None
        if not modelli:
            yd = self.cont.get()
        residui = "residui" in comp and bool(modelli)
        self.g_curva.nome_file = f"{mc.nome_file(g)}_curva"
        self.g_curva.disegna(lambda fig: mc.disegna_curva(fig, g, ris, modelli, comp, li, yd, residui))
        self.g_insieme.disegna(lambda fig: mc.disegna_insieme(fig, self.cat, self.chiave))
        # testo nella colonna
        descr = mc.FAMOSE.get(self.chiave, (None, ""))[1]
        best = mc.migliore(ris)
        righe = [descr] if descr else []
        if best:
            chi = f"{best['chi2_rid']:.2f}".replace(".", ",")
            righe.append(f"Modello migliore: {best['modello']} (χ² ridotto {chi})")
        if not g.get("senza_barioni"):
            fd = mc.frazione_oscura(g, 1.0 if g.get("massa_fissa") else mc.ML_DISCO)[-1]
            righe.append(f"All'ultimo raggio ({g['Rmax']:.0f} kpc) manca il {100 * fd:.0f} % della massa.")
        self.info.configure(text="\n".join(righe))
        self.testo_par.configure(text=mc.testo_risultati(g, ris, None, "it").split("\n\n")[0])
        self.tab_par.svuota()
        lig = self.cat.li.get(self.chiave, {})
        for m in mc.MODELLI:
            r = ris.get(m)
            if not r:
                continue
            if not r.get("ok"):
                self.tab_par.inserisci([m, "–", "–", "–", "–", "non applicabile: manca il modello della materia visibile"])
                continue
            e = r["err"].get("Yd")
            ml = "–" if g.get("massa_fissa") or g.get("senza_barioni") else (
                f"{r['p']['Yd']:.2f}" + (f" ± {e:.2f}" if e is not None and np.isfinite(e) else "")).replace(".", ",")
            q = lig.get({"NFW": "NFW-Flat", "Burkert": "Burkert-Flat", "pISO": "pISO-Flat"}.get(m, ""))
            tli = f"χ² {q['chi2']:.2f} · M/L {q['Ydisk']:.2f}".replace(".", ",") if q else "–"
            fdm = "–" if g.get("senza_barioni") else f"{100 * r['fdm_ultimo']:.0f} %"
            self.tab_par.inserisci([m, f"{r['chi2_rid']:.2f}".replace(".", ","), ml, fdm, tli, mc.testo_parametri(r)])
        self._aggiorna_suggerimento()

    def _cambio(self, chiave, valore, ricalcola=False):
        self.imp.imposta(chiave, valore)
        self._aggiorna_suggerimento()
        if ricalcola:
            if self.risultati_attuali() is None:
                self.calcola()
            else:
                self._mostra()
        else:
            self._mostra()

    def _componenti(self):
        self.imp.imposta("componenti", list(self.componenti()))
        self._mostra()

    def _aggiorna_suggerimento(self):
        testo = ""
        g = self.cat.galassie.get(self.chiave) if self.cat and self.chiave else None
        if g is not None and g.get("massa_fissa"):
            testo = "Via Lattea: le masse delle stelle vengono dal modello di Pouliasis et al. 2017, il contatore non serve."
        elif g is not None and g.get("senza_barioni"):
            testo = "M 33: mancano le componenti visibili, tutta la massa va all'alone; il contatore non serve."
        elif self.ml() == "libero":
            testo = "Con «Libero» il programma sceglie il rapporto massa/luce migliore vicino a 0,5; il contatore conta solo con «Fisso»."
        self.suggerimento.mostra(testo)

    # ------------------------------------------------------------------ immagini
    def immagini(self):
        if not self.cat or self.chiave is None:
            return
        k = self.chiave
        g = self.cat.galassie[k]
        if k in self.imgs:
            self._mostra_immagini()
            return
        if self.lavoro_immagini is not None and self.lavoro_immagini.attivo:
            self.f.radice.after(500, self.immagini)
            return
        rete = self.rete and not self.autotest          # regola 15: niente scaricamenti nell'autotest
        self.lavoro_immagini = self.fc.Lavoro(self.f, lambda avvisa, fermo: (k, mc.immagini(g, avvisa, rete)),
                                              al_termine=self._immagini_pronte,
                                              al_errore=lambda t: self.avvisa("immagini non disponibili: " + t.splitlines()[-1]),
                                              al_messaggio=self.avvisa)

    def _immagini_pronte(self, valore):
        k, imgs = valore
        self.imgs[k] = imgs
        if k == self.chiave:
            self._mostra_immagini()
        else:
            self.immagini()

    def _mostra_immagini(self):
        g = self.cat.galassie[self.chiave]
        imgs = self.imgs.get(self.chiave, [])
        self.g_immagini.nome_file = f"{mc.nome_file(g)}_immagini"
        self.g_immagini.disegna(lambda fig: mc.disegna_immagini(fig, g, imgs))

    # ------------------------------------------------------------------ tutte le galassie
    def tutte(self, al_termine=None):
        if not self.cat or (self.lavoro_tutte is not None and self.lavoro_tutte.attivo):
            return
        ml = self.ml()

        def fine(tutti):
            self.tutti = tutti
            self._riempi_tutte()
            self.schede.select(self.schede.tabs()[4])
            if al_termine:
                al_termine()
        self.avvisa("adatto i quattro modelli a tutte le galassie…")
        self.lavoro_tutte = self.fc.Lavoro(
            self.f, lambda avvisa, fermo: mc.adatta_catalogo(self.cat, ml, avvisa, fermo), al_termine=fine,
            al_errore=lambda t: self._errore("Calcolo non riuscito", t), al_messaggio=self.avvisa,
            pulsanti=[self.b_tutte, self.b_salva_tutte, self.b_salsa])

    def _riempi_tutte(self):
        tutti, cat = self.tutti, self.cat
        alb = self.tab_tutte.albero
        alb.delete(*alb.get_children())
        for k, ris in tutti.items():
            g = cat.galassie[k]
            b = mc.migliore(ris)

            def chi(m):
                r = ris.get(m)
                return f"{r['chi2_rid']:.2f}".replace(".", ",") if r and r.get("ok") else "–"
            bur = ris.get("Burkert", {})
            ml = "–" if g.get("massa_fissa") or g.get("senza_barioni") or not bur.get("ok") else \
                f"{bur['p']['Yd']:.2f}".replace(".", ",")
            fdm = "–" if g.get("senza_barioni") or not bur.get("ok") else f"{100 * bur['fdm_ultimo']:.0f} %"
            alb.insert("", "end", iid=k, values=[cat.etichetta(k), g["Q"],
                                                 f"{g['Vflat']:.0f} km/s" if g["Vflat"] > 0 else "–",
                                                 b["modello"] if b else "–", chi("NFW"), chi("Burkert"), chi("pISO"),
                                                 chi("MOND"), ml, fdm])
        st = mc.statistiche_tutte(cat, tutti)
        v = st["vincitori"]
        self.testo_tutte.configure(text=(
            f"{st['n']} galassie SPARC. Il modello migliore è NFW per {v['NFW']}, Burkert per {v['Burkert']}, "
            f"isotermo per {v['pISO']}, MOND per {v['MOND']}. χ² ridotto mediano: "
            + ", ".join(f"{m} {c:.2f}".replace(".", ",") for m, c in st["chi2_mediano"].items())
            + ". Un clic su una riga apre la galassia."))
        self.g_tutte.disegna(lambda fig: mc.disegna_riassunto_tutte(fig, cat, tutti))

    def _riga_tutte(self, _evento=None):
        sel = self.tab_tutte.albero.selection()
        if sel and sel[0] != self.chiave:
            self.seleziona(sel[0])

    # ------------------------------------------------------------------ salvataggi
    def _cartella(self):
        if self.cartella is None:
            self.cartella = mc.cartella_risultati()
        return self.cartella

    def salva_scheda(self):
        ris = self.risultati_attuali()
        if ris is None:
            self.f.messaggio("Scheda", "Aspetta che il calcolo sia finito.")
            return
        g = self.cat.galassie[self.chiave]
        li = self.cat.li.get(self.chiave)
        imgs = self.imgs.get(self.chiave, [])
        modelli = self.modelli() or ("NFW", "Burkert", "MOND")
        cartella = self._cartella()

        def fine(file):
            self.avvisa("scheda salvata: " + ", ".join(str(p) for p in file))
            if not self.autotest:
                self.f.messaggio("Scheda salvata", "Ho salvato:\n" + "\n".join(str(p) for p in file))
        self.lavoro_scheda = self.fc.Lavoro(self.f, lambda avvisa, fermo: mc.salva_scheda(g, ris, li, imgs, cartella, modelli),
                       al_termine=fine, al_errore=lambda t: self._errore("Scheda non salvata", t),
                       al_messaggio=self.avvisa, pulsanti=[self.b_scheda])

    def salva_tutte(self):
        if self.tutti is None:
            self.tutte(al_termine=self.salva_tutte)
            return
        cartella = self._cartella()

        def lavoro(avvisa, fermo):
            return [mc.salva_csv_tutte(self.cat, self.tutti, cartella), mc.salva_pdf_tutte(self.cat, self.tutti, cartella)]

        def fine(file):
            self.avvisa("salvati: " + ", ".join(str(p) for p in file))
            if not self.autotest:
                self.f.messaggio("Risultati salvati", "Ho salvato:\n" + "\n".join(str(p) for p in file))
        self.lavoro_salva = self.fc.Lavoro(self.f, lavoro, al_termine=fine,
                                           al_errore=lambda t: self._errore("Risultati non salvati", t),
                                           al_messaggio=self.avvisa, pulsanti=[self.b_salva_tutte])

    def apri_cartella(self):
        p = self.cartella or mc.RISULTATI
        p.mkdir(parents=True, exist_ok=True)
        if not self.fc.apri_con_sistema(p):
            self.f.messaggio("Cartella dei risultati", str(p))

    def scegli_salsa(self):
        iniziale = mc.IDROGENO_RISULTATI if mc.IDROGENO_RISULTATI.exists() else Path.home()
        p = self.f.scegli_file("Scegli curva_di_rotazione.csv (programma Idrogeno)", iniziale,
                               [("Curva di rotazione (CSV)", "*.csv")])
        if not p or not self.cat:
            return
        try:
            vl = mc.carica_via_lattea(p, self.avvisa)
        except Exception as e:
            self.f.errore("Curva SALSA non letta", f"{type(e).__name__}: {e}")
            return
        if not vl.get("n_edoardo"):
            self.f.errore("Curva SALSA non letta", f"Nel file {p} non ci sono punti affidabili (colonne R_kpc, V_kms, reliable).")
            return
        self.cat.galassie["VIA_LATTEA"] = vl
        self.imp.imposta("csv_salsa", p)
        self.ris = {k: v for k, v in self.ris.items() if k[0] != "VIA_LATTEA"}
        self.seleziona("VIA_LATTEA")

    def avvia(self):
        self.f.avvia()


# =========================================================================== senza finestra
def senza_finestra(args):
    cat = mc.carica_catalogo(print, True)
    cartella = Path(args.cartella) if args.cartella else mc.cartella_risultati()
    cartella.mkdir(parents=True, exist_ok=True)
    if args.galassia:
        k = args.galassia.replace(" ", "").upper()
        trovate = [c for c in cat.galassie if c.upper().replace("_", "") == k.replace("_", "")
                   or cat.galassie[c]["nome"].replace(" ", "").upper() == k]
        if not trovate:
            print(f"Galassia {args.galassia} non trovata. Esempi: NGC3198, DDO154, M33, VIA_LATTEA")
            return 1
        g = cat.galassie[trovate[0]]
        ris = mc.adatta_tutti(g, args.ml)
        print(mc.testo_risultati(g, ris, cat.li.get(g["chiave"]), "en"))
        imgs = mc.immagini(g, print, True)
        for p in mc.salva_scheda(g, ris, cat.li.get(g["chiave"]), imgs, cartella):
            print("salvato:", p)
    if args.tutte:
        tutti = mc.adatta_catalogo(cat, args.ml, print)
        print("salvato:", mc.salva_csv_tutte(cat, tutti, cartella))
        print("salvato:", mc.salva_pdf_tutte(cat, tutti, cartella))
    return 0


# =========================================================================== autotest
def autotest(scala=None):
    print(f"=== AUTOTEST {NOME} {VERSIONE} – {time.strftime('%d/%m/%Y %H:%M:%S')}")
    import matplotlib
    import scipy
    print(f"Python {sys.version.split()[0]}, numpy {np.__version__}, scipy {scipy.__version__}, matplotlib {matplotlib.__version__}")
    esiti = []
    print("--- 1. Calcoli (senza dati)")
    ok, n = mc.autotest_motore()
    esiti.append(("calcoli", ok == n, f"{ok}/{n}"))
    # risultati in una cartella temporanea: l'autotest non tocca quelli di Edoardo
    temp = Path(tempfile.mkdtemp(prefix="curve_rotazione_autotest_"))
    mc.RISULTATI = temp
    print("--- 2. Finestra e dati veri")
    p = Programma(autotest=True, scala=scala)
    import finestra_comune as fc
    r = p.f.radice
    r.deiconify()

    def attendi(condizione, secondi, nome):
        fine = time.time() + secondi
        while time.time() < fine:
            r.update()
            if condizione():
                return True
            time.sleep(0.03)
        print(f"  NO   tempo scaduto: {nome}")
        return False
    if not attendi(lambda: p.cat is not None or p.errori, 240, "caricamento del catalogo") or p.cat is None:
        esiti.append(("catalogo", False, "; ".join(p.errori)))
    else:
        ok, n = mc.autotest_motore(cat=p.cat)
        esiti.append(("calcoli sui dati veri", ok == n, f"{ok}/{n}"))
        for k in ("NGC3198", "VIA_LATTEA", "M33", "DDO154", "NGC7331"):
            if k not in p.cat.galassie:
                continue
            p.seleziona(k)
            buono = attendi(lambda: p.risultati_attuali() is not None and not p.calcolo.attivo, 60, f"calcolo di {k}")
            fc.aspetta(r, 0.4)
            esiti.append((f"galassia {k}", buono and p.g_curva.disegnato_a is not None, ""))
        # massa/luce fissa e tutte le combinazioni di modelli
        p.t_ml.set("Fisso (dal contatore)")
        p._cambio("ml", p.t_ml.get(), ricalcola=True)
        p.cont.cambia(+1)
        esiti.append(("massa/luce fissa", attendi(lambda: p.risultati_attuali() is not None, 60, "Υ fisso"),
                      f"Υ = {p.cont.get()}"))
        for nome in SCELTE_MODELLI:
            p.t_modelli.set(nome)
            p._cambio("modelli", nome)
            fc.aspetta(r, 0.15)
        p.t_ml.set(BASE["ml"])
        p._cambio("ml", BASE["ml"], ricalcola=True)
        p.t_modelli.set(BASE["modelli"])
        p._cambio("modelli", BASE["modelli"])
        p.var_cerca.set("ddo 154")
        fc.aspetta(r, 0.3)
        esiti.append(("ricerca «ddo 154»", p.chiave == "DDO154", p.chiave))
        p.var_cerca.set("")
        p.seleziona("NGC3198")
        attendi(lambda: p.risultati_attuali() is not None, 60, "NGC 3198")
        # scheda PDF
        p.salva_scheda()
        attendi(lambda: p.lavoro_scheda is not None and not p.lavoro_scheda.attivo, 60, "scheda PDF")
        pdf = list(p.cartella.glob("*.pdf")) if p.cartella else []
        esiti.append(("scheda PDF + PNG", bool(pdf) and pdf[0].stat().st_size > 20000,
                      f"{pdf[0].name} {pdf[0].stat().st_size // 1024} kB" if pdf else "manca"))
        # tutte le galassie + CSV + PDF
        t0 = time.time()
        p.salva_tutte()
        buono = attendi(lambda: p.lavoro_salva is not None and not p.lavoro_salva.attivo, 400, "tutte le galassie")
        buono = buono and (p.cartella / "rotation_curves_summary.pdf").exists() and \
            (p.cartella / "halo_fits_all_galaxies.csv").exists()
        esiti.append(("tutte le galassie (CSV + PDF)", buono and p.tutti is not None and len(p.tutti) >= 170,
                      f"{len(p.tutti or {})} galassie in {time.time() - t0:.0f} s"))
        if p.tutti:
            st = mc.statistiche_tutte(p.cat, p.tutti)
            print(f"  modello migliore: {st['vincitori']}; χ² mediani "
                  + ", ".join(f"{m} {c:.2f}" for m, c in st["chi2_mediano"].items()))
            c = st["confronto_li"]
            if c is not None and len(c):
                d = np.log10(c[:, 0] / c[:, 1])
                print(f"  confronto Υ (Burkert) con Li+2020: {len(c)} galassie, differenza mediana {np.median(d):+.3f} dex, "
                      f"dispersione {np.std(d):.3f} dex")
                esiti.append(("Υ come Li+2020 (entro 0,15 dex in mediana)", abs(np.median(d)) < 0.15, ""))
        # finestra a 100/150/200 %
        print("--- 3. Controllo della finestra (libreria comune)")
        p.schede.select(p.schede.tabs()[0])
        fc.aspetta(r, 0.5)
        controlli, problemi = fc.controlla_finestra(p.f)
        esiti.append(("finestra", not problemi, f"{controlli} controlli, {len(problemi)} problemi"))
    esiti.append(("nessun errore nella finestra", not p.errori, "; ".join(p.errori)[:300]))
    print("--- RIASSUNTO")
    for nome, ok, nota in esiti:
        print(f"  {'OK  ' if ok else 'NO  '} {nome}" + (f"  – {nota}" if nota else ""))
    tutti_ok = all(e[1] for e in esiti)
    print(f"{sum(e[1] for e in esiti)}/{len(esiti)} – " + ("AUTOTEST SUPERATO" if tutti_ok else "AUTOTEST NON SUPERATO"))
    try:
        p.f.chiudi()
    except Exception:
        pass
    return 0 if tutti_ok else 1


def main():
    ap = argparse.ArgumentParser(description=f"{NOME} {VERSIONE} – © 2026 Edoardo Battistel")
    ap.add_argument("--autotest", action="store_true")
    ap.add_argument("--scala", type=int, choices=(100, 125, 150, 175, 200))
    ap.add_argument("--galassia")
    ap.add_argument("--tutte", action="store_true")
    ap.add_argument("--ml", choices=("libero", "fisso"), default="libero")
    ap.add_argument("--cartella")
    args = ap.parse_args()
    scala = args.scala / 100 if args.scala else None
    if args.autotest:
        try:
            return autotest(scala)
        except Exception:
            traceback.print_exc()
            print("AUTOTEST NON SUPERATO (eccezione)")
            return 1
    if args.galassia or args.tutte:
        import matplotlib
        matplotlib.use("Agg")
        return senza_finestra(args)
    Programma(scala=scala).avvia()
    return 0


if __name__ == "__main__":
    sys.exit(main())
