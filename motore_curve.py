#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Curve di rotazione 1.0 – motore
© 2026 Edoardo Battistel · licenza BSD-3

Curve di rotazione di 175 galassie (SPARC, Lelli+2016) con le componenti visibili
(gas, disco e bulbo dalle immagini Spitzer a 3,6 µm), M 33 (Kam+2017), la Via Lattea
(misura SALSA di Edoardo + Eilers+2019, stelle dal modello I di Pouliasis+2017).
Adattamenti di aloni di materia oscura NFW, Burkert e isotermo (pISO) e della formula
di MOND; confronto con gli adattamenti pubblicati da Li+2020. Grafici d'insieme:
Tully-Fisher barionica, relazione delle accelerazioni radiali, frazione di materia oscura.
Risultati (grafici, PDF, CSV) in inglese.
"""
import csv
import io
import json
import math
import os
import re
import socket
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np

VERSIONE = "1.1"
FIRMA = "© 2026 Edoardo Battistel"
UA = "CurveRotazione/1.1 (Python urllib)"
TEMPO_MAX = 60

G = 4.30091e-6            # kpc (km/s)² / Msun
H0 = 0.073                # km/s/kpc (73 km/s/Mpc, come Li+2020)
A0 = 1.2e-10              # m/s² (MOND / relazione delle accelerazioni)
KMS2_KPC_IN_MS2 = 1e6 / 3.0857e19   # 1 (km/s)²/kpc in m/s²
A0_INT = A0 / KMS2_KPC_IN_MS2       # ≈ 3703 (km/s)²/kpc
ML_DISCO = 0.5            # rapporto massa/luce a 3,6 µm (Lelli+2016, McGaugh+2016)
ML_BULBO = 0.7
RAPPORTO_BULBO = ML_BULBO / ML_DISCO
PRIORE_DEX = 0.1          # larghezza del priore log-normale su M/L (come Li+2020)
GAS_SU_HI = 1.33          # elio
D_M33_KPC = 840.0         # distanza di M 33 usata da Kam+2015/2017

# --------------------------------------------------------------------------- cartelle
_base = Path.home() / "Scrivania" / "Astronomia"
if not _base.exists() and (Path.home() / "Desktop" / "Astronomia").exists():
    _base = Path.home() / "Desktop" / "Astronomia"
CARTELLA_DATI = _base / "Curve_rotazione"
CACHE = CARTELLA_DATI / "cache"
RISULTATI = CARTELLA_DATI / "Risultati"
IDROGENO_RISULTATI = _base / "Idrogeno" / "Risultati"
CARTELLE_SEME = [CARTELLA_DATI / "prova_rete",
                 Path.home() / "Claude" / "Astropy" / "programma_curve_rotazione" / "dati_prova"]

HARVARD = "https://vizier.cfa.harvard.edu/viz-bin/asu-tsv"
SPARC_SITO = "https://astroweb.case.edu/SPARC/"

MODELLI = ("NFW", "Burkert", "pISO", "Einasto", "MOND")
NOMI_MODELLI_EN = {"NFW": "NFW halo (cuspy)", "Burkert": "Burkert halo (cored)",
                   "pISO": "pseudo-isothermal halo (cored)",
                   "Einasto": "Einasto halo (simulations, rolling slope)", "MOND": "MOND (no halo)"}
COLORI = {"NFW": "#d62728", "Burkert": "#1f77b4", "pISO": "#9467bd", "Einasto": "#8c564b", "MOND": "#e69f00",
          "oss": "#111111", "gas": "#2ca02c", "disco": "#1f9bd1", "bulbo": "#c2185b", "barioni": "#6b7280",
          "edoardo": "#f97316", "eilers": "#0f766e"}

# ------------------------------------------------------------------- nomi italiani dei casi famosi
FAMOSE = {
    "VIA_LATTEA": ("Via Lattea", "la nostra Galassia: misura SALSA di Edoardo + Eilers et al. 2019"),
    "NGC3198": ("NGC 3198", "il caso classico: la curva piatta che convinse molti della materia oscura (van Albada et al. 1985)"),
    "NGC2403": ("NGC 2403", "spirale vicina nella Giraffa, curva molto precisa"),
    "DDO154": ("DDO 154", "galassia nana dominata dalla materia oscura"),
    "UGC00128": ("UGC 128", "galassia a bassa luminosità superficiale: poche stelle, tanta materia oscura"),
    "M33": ("M 33", "Galassia del Triangolo (Kam et al. 2017; senza componenti visibili)"),
    "NGC5055": ("M 63", "Galassia Girasole (NGC 5055)"),
    "NGC6946": ("NGC 6946", "Galassia Fuochi d'artificio"),
    "NGC3992": ("M 109", "spirale barrata nell'Orsa Maggiore (NGC 3992)"),
    "NGC0891": ("NGC 891", "spirale vista di taglio, simile alla Via Lattea"),
    "NGC7331": ("NGC 7331", "spirale con bulbo, spesso detta «gemella» della Via Lattea"),
    "NGC2841": ("NGC 2841", "grande spirale velocissima (quasi 300 km/s)"),
    "UGC02885": ("UGC 2885", "«galassia di Rubin», una delle spirali più grandi conosciute"),
    "NGC6503": ("NGC 6503", "spirale solitaria ai margini del Vuoto Locale"),
    "NGC0300": ("NGC 300", "spirale del gruppo dello Scultore"),
    "IC2574": ("IC 2574", "galassia nana irregolare con un grande nucleo di materia oscura"),
    "NGC3031": ("M 81", "Galassia di Bode (THINGS; senza componenti visibili)"),
    "NGC4826": ("M 64", "Galassia Occhio Nero (THINGS; senza componenti visibili)"),
    "NGC4736": ("M 94", "spirale con un anello di stelle giovani (THINGS; senza componenti visibili)"),
    "NGC3627": ("M 66", "spirale del Tripletto del Leone (THINGS; senza componenti visibili)"),
    "WLM": ("WLM", "nana irregolare del Gruppo Locale (LITTLE THINGS; senza componenti visibili)"),
    "IC1613": ("IC 1613", "nana irregolare del Gruppo Locale (LITTLE THINGS; senza componenti visibili)"),
}
ORDINE_FAMOSE = ["VIA_LATTEA", "NGC3198", "NGC2403", "DDO154", "UGC00128", "M33", "NGC5055", "NGC6946",
                 "NGC3992", "NGC0891", "NGC7331", "NGC2841", "UGC02885", "NGC6503", "NGC0300", "IC2574",
                 "NGC3031", "NGC4826", "NGC4736", "NGC3627", "WLM", "IC1613"]

# ------------------------------------------------------------------ Via Lattea: Eilers+2019 (tabella 1)
EILERS_2019 = np.array([
    (5.27, 226.83, 1.91, 1.90), (5.74, 230.80, 1.43, 1.35), (6.23, 231.20, 1.70, 1.10),
    (6.73, 229.88, 1.44, 1.32), (7.22, 229.61, 1.37, 1.11), (7.82, 229.91, 0.92, 0.88),
    (8.19, 228.86, 0.80, 0.67), (8.78, 226.50, 1.07, 0.95), (9.27, 226.20, 0.72, 0.62),
    (9.76, 225.94, 0.42, 0.52), (10.26, 225.68, 0.44, 0.40), (10.75, 224.73, 0.38, 0.41),
    (11.25, 224.02, 0.33, 0.54), (11.75, 223.86, 0.40, 0.39), (12.25, 222.23, 0.51, 0.37),
    (12.74, 220.77, 0.54, 0.46), (13.23, 220.92, 0.57, 0.40), (13.74, 217.47, 0.64, 0.51),
    (14.24, 217.31, 0.77, 0.66), (14.74, 217.60, 0.65, 0.68), (15.22, 217.07, 1.06, 0.80),
    (15.74, 217.38, 0.84, 1.07), (16.24, 216.14, 1.20, 1.48), (16.74, 212.52, 1.39, 1.43),
    (17.25, 216.41, 1.44, 1.85), (17.75, 213.70, 2.22, 1.65), (18.24, 207.89, 1.76, 1.88),
    (18.74, 209.60, 2.31, 2.77), (19.22, 206.45, 2.54, 2.36), (19.71, 201.91, 2.99, 2.26),
    (20.27, 199.84, 3.15, 2.89), (20.78, 198.14, 3.33, 3.37), (21.24, 195.30, 5.99, 6.50),
    (21.80, 213.67, 15.38, 12.18), (22.14, 176.97, 28.58, 18.57), (22.73, 193.11, 27.64, 19.05),
    (23.66, 176.63, 18.67, 16.74), (24.82, 198.42, 6.50, 6.12)])
SISTEMATICO_EILERS = 0.03     # 3 % di errore sistematico aggiunto (come Eilers+2019, fig. 3)
# Pouliasis et al. 2017, modello I (usato da Eilers+2019): bulbo di Plummer + due dischi di Miyamoto-Nagai
MW_BULBO = (1.067e10, 0.30)                     # Msun, b (kpc)
MW_DISCHI = ((3.944e10, 5.30, 0.25), (3.944e10, 2.60, 0.80))   # Msun, a, b (kpc)
MW_MASSA_STELLE = MW_BULBO[0] + sum(d[0] for d in MW_DISCHI)
# gas della Via Lattea (McMillan 2017, MNRAS 465, 76): Σ(R) = Σ0 exp(−Rm/R − R/Rd), elio compreso
MW_GAS = (("HI", 53.1, 7.0, 4.0), ("H2", 2180.0, 1.5, 12.0))     # nome, Σ0 (Msun/pc²), Rd, Rm (kpc)
R_SOLE_EILERS = 8.122


# =========================================================================== rete
_gai = socket.getaddrinfo


def _solo_ipv4(host, port, family=0, *a, **k):
    """Solo IPv4 (lezione di batse.msfc.nasa.gov: dalla rete di Edoardo l'IPv6 può bloccarsi 90 s)."""
    return _gai(host, port, socket.AF_INET, *a, **k)


socket.getaddrinfo = _solo_ipv4


def scarica(url, tempo=TEMPO_MAX, tentativi=2, attesa=3.0):
    ultimo = None
    for k in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=tempo) as r:
                corpo = r.read()
            if corpo[:2] == b"\x1f\x8b":
                import gzip
                corpo = gzip.decompress(corpo)
            return corpo
        except Exception as e:  # noqa
            ultimo = e
            if k + 1 < tentativi:
                time.sleep(attesa)
    raise ultimo


def url_vizier(**k):
    return HARVARD + "?" + urllib.parse.urlencode(k, safe="*/,=")


def leggi_tsv(testo):
    """Risposta asu-tsv di VizieR → lista di dict (salta commenti, riga delle unità e trattini)."""
    if isinstance(testo, bytes):
        testo = testo.decode("utf-8", "replace")
    righe = [r for r in testo.splitlines() if r.strip() and not r.startswith("#")]
    if len(righe) < 3:
        return []
    testata = [c.strip() for c in righe[0].split("\t")]
    uscita = []
    for r in righe[3:]:
        campi = [c.strip() for c in r.split("\t")]
        if len(campi) < len(testata) - 2:
            continue
        uscita.append(dict(zip(testata, campi)))
    return uscita


def numero(x, predefinito=np.nan):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return predefinito


def nome_bello(nome):
    """«NGC3198» → «NGC 3198», «UGC00128» → «UGC 128», «DDO154» → «DDO 154»."""
    m = re.match(r"^(UGCA|NGC|UGC|IC|DDO|PGC|KK98)0*(\d+)(.*)$", nome)
    if m:
        return f"{m.group(1)} {int(m.group(2))}{m.group(3)}"
    return nome


# =========================================================================== cache e dati
def _file_cache(nome, url=None, avvisa=print, rete=True, minimo=200, controllo=None):
    """Restituisce i byte di un file della cache; se manca lo prende dalle cartelle della prova di rete
    o lo scarica. controllo(byte) → True se il contenuto è buono."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / nome
    if p.exists() and p.stat().st_size >= minimo:
        return p.read_bytes()
    for c in CARTELLE_SEME:
        for alt in (nome, nome.replace("li2020", "li2020"), ):
            q = c / alt
            if q.exists() and q.stat().st_size >= minimo:
                b = q.read_bytes()
                if controllo is None or controllo(b):
                    p.write_bytes(b)
                    avvisa(f"{nome}: copiato da {c}")
                    return b
    if not rete or url is None:
        return None
    avvisa(f"scarico {nome} …")
    b = scarica(url, tempo=120)
    if len(b) < minimo or (controllo is not None and not controllo(b)):
        raise RuntimeError(f"{nome}: risposta non valida ({len(b)} byte)")
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(b)
    os.replace(tmp, p)
    return b


def _ok_tsv(minimo_righe):
    return lambda b: len(leggi_tsv(b)) >= minimo_righe


SEMI = {"sparc_table1.tsv": "sparc_table1.tsv", "sparc_table2.tsv": "sparc_table2.tsv",
        "m33_kam2017_table9.tsv": "m33_kam2017_table9.tsv"}


def _sparc_da_harvard(avvisa, rete):
    b1 = _file_cache("sparc_table1.tsv", url_vizier(**{"-source": "J/AJ/152/157/table1", "-out": "**",
                                                     "-out.max": "500"}), avvisa, rete, controllo=_ok_tsv(170))
    b2 = _file_cache("sparc_table2.tsv", url_vizier(**{"-source": "J/AJ/152/157/table2", "-out": "**",
                                                     "-out.max": "10000"}), avvisa, rete, controllo=_ok_tsv(3300))
    if b1 is None or b2 is None:
        return None
    t1, t2 = leggi_tsv(b1), leggi_tsv(b2)
    if "Vbulge" not in t2[0]:
        raise RuntimeError("tabella 2 di SPARC senza Vbulge (serve -out=**)")
    gal = {}
    for r in t1:
        n = r["Name"]
        gal[n] = dict(
            chiave=n, nome=nome_bello(n), fonte="SPARC (Lelli+2016)", tipo=int(numero(r.get("Type"), -1)),
            D=numero(r["Dist"]), e_D=numero(r.get("e_Dist")), inc=numero(r["i"]), e_inc=numero(r.get("e_i")),
            L36=numero(r["L3.6"]), Reff=numero(r.get("Reff")), Rdisk=numero(r.get("Rdisk")),
            MHI=numero(r["MHI"]), RHI=numero(r.get("RHI")), Vflat=numero(r["Vflat"]),
            e_Vflat=numero(r.get("e_Vflat")), Q=int(numero(r.get("Qual"), 3)),
            ra=numero(r.get("_RA")), dec=numero(r.get("_DE")), righe=[])
    for r in t2:
        g = gal.get(r["Name"])
        if g is not None:
            g["righe"].append([numero(r[c]) for c in ("Rad", "Vobs", "e_Vobs", "Vgas", "Vdisk", "Vbulge")])
    return gal


def _leggi_mrt_tabella1(testo):
    """Table1 di SPARC dal sito originale (formato MRT): una riga per galassia, campi separati da spazi."""
    righe = testo.splitlines()
    inizio = max(i for i, r in enumerate(righe) if r.startswith("----")) + 1
    gal = {}
    for r in righe[inizio:]:
        c = r.split()
        if len(c) < 18:
            continue
        n = c[0]
        f = [numero(x) for x in c[1:18]]
        gal[n] = dict(chiave=n, nome=nome_bello(n), fonte="SPARC (Lelli+2016)", tipo=int(f[0]), D=f[1], e_D=f[2],
                      inc=f[4], e_inc=f[5], L36=f[6], Reff=f[8], Rdisk=f[10], MHI=f[12], RHI=f[13], Vflat=f[14],
                      e_Vflat=f[15], Q=int(f[16]), ra=np.nan, dec=np.nan, righe=[])
    return gal


def _sparc_dal_sito(avvisa, rete):
    b1 = _file_cache("SPARC_Lelli2016c.mrt", SPARC_SITO + "SPARC_Lelli2016c.mrt", avvisa, rete)
    bz = _file_cache("Rotmod_LTG.zip", SPARC_SITO + "Rotmod_LTG.zip", avvisa, rete, minimo=50000)
    if b1 is None or bz is None:
        return None
    gal = _leggi_mrt_tabella1(b1.decode("utf-8", "replace"))
    z = zipfile.ZipFile(io.BytesIO(bz))
    for nome in z.namelist():
        n = nome.replace("_rotmod.dat", "")
        if n not in gal:
            continue
        for r in z.read(nome).decode("utf-8", "replace").splitlines():
            if r.startswith("#") or not r.strip():
                continue
            v = [numero(x) for x in r.split()[:6]]
            gal[n]["righe"].append(v)
    return gal


def _li2020(avvisa, rete):
    try:
        b = _file_cache("li2020_table1.tsv", url_vizier(**{"-source": "J/ApJS/247/31/table1", "-out": "**",
                                                         "-out.max": "5000"}), avvisa, rete,
                        controllo=_ok_tsv(1500))
    except Exception as e:
        avvisa(f"Li+2020 non disponibile ({type(e).__name__}: {e})")
        return {}
    if b is None:
        return {}
    li = {}
    for r in leggi_tsv(b):
        li.setdefault(r["Name"], {})[r["Model"]] = {k: numero(v) for k, v in r.items() if k not in ("Name", "Model")}
    return li


ZENODO_CORPUS = "https://zenodo.org/records/19563417/files/rotation_curve_corpus_v7.json?download=1"
SURVEY_NOMI = {"THINGS": "THINGS (de Blok+2008)", "LITTLE_THINGS": "LITTLE THINGS (Oh+2015)",
               "WALLABY": "WALLABY DR2 (Deg+2022)"}
ERRORE_WALLABY = (5.0, 0.05)      # WALLABY non dà errori: 5 km/s + 5 % (stima prudente)


def chiave_normale(nome):
    """«DDO_154» → «DDO154», «NGC_2366» → «NGC2366», «DDO_87» → «DDO087» (come SPARC)."""
    n = nome.replace("_", "").replace(" ", "").upper()
    m = re.match(r"^(DDO|NGC|UGC|IC|UGCA)(\d+)(.*)$", n)
    if m:
        cifre = {"DDO": 3, "UGC": 5, "NGC": 4, "IC": 4, "UGCA": 3}[m.group(1)]
        n = f"{m.group(1)}{int(m.group(2)):0{cifre}d}{m.group(3)}"
    return n


def _raccolta(avvisa, rete):
    """Raccolta di curve di rotazione 2026 (Flynn, Zenodo 19563417, CC BY 4.0): THINGS, LITTLE THINGS,
    WALLABY DR2 (SPARC c'è già). Restituisce la lista delle galassie lette."""
    try:
        b = _file_cache("rotation_curve_corpus_v7.json", ZENODO_CORPUS, avvisa, rete, minimo=500000,
                        controllo=lambda x: x[:1] == b"{")
    except Exception as e:
        avvisa(f"raccolta Zenodo non disponibile ({type(e).__name__}: {e})")
        return []
    if b is None:
        return []
    try:
        dati = json.loads(b.decode("utf-8"))
    except Exception as e:
        avvisa(f"raccolta Zenodo non leggibile: {type(e).__name__}: {e}")
        return []
    uscita = []
    for x in dati.get("galaxies", []):
        survey = x.get("survey")
        if survey not in SURVEY_NOMI:
            continue
        righe = []
        if survey == "WALLABY":
            for q in x.get("rotation_curve") or []:
                R, V = numero(q.get("rad_kpc")), numero(q.get("vrot_kms"))
                if np.isfinite(R) and np.isfinite(V) and R > 0:
                    righe.append([R, V, ERRORE_WALLABY[0] + ERRORE_WALLABY[1] * V, 0, 0, 0])
        else:
            for q in x.get("data") or []:
                R = numero(q.get("Rad"))
                V = numero(q.get("Vobs", q.get("Vrot")))
                e = numero(q.get("errV", q.get("e_Vrot")))
                if np.isfinite(R) and np.isfinite(V) and R > 0:
                    righe.append([R, V, e if np.isfinite(e) and e > 0 else 5.0, 0, 0, 0])
        if len(righe) < 3:
            continue
        nome = x["galaxy"]
        D = numero(x.get("distance_mpc", x.get("distance_Mpc")))
        uscita.append(dict(
            chiave=chiave_normale(nome) if survey != "WALLABY" else nome,
            nome=(nome_bello(chiave_normale(nome)) if re.match(r"^(DDO|NGC|UGC|IC)_?\d", nome) else
                  nome.replace("WALLABY_", "WALLABY ").replace("_", " ")),
            fonte=SURVEY_NOMI[survey], survey=survey, tipo=-1, D=D, e_D=np.nan, inc=numero(x.get("inc_deg")),
            e_inc=np.nan, L36=np.nan, Reff=np.nan, Rdisk=np.nan, MHI=np.nan, RHI=np.nan,
            Vflat=float(np.median([r[1] for r in righe[-3:]])), e_Vflat=np.nan,
            Q=1 if survey != "WALLABY" else 2, ra=numero(x.get("ra_deg")), dec=numero(x.get("dec_deg")),
            righe=righe, senza_barioni=True))
    return uscita


def _m33(avvisa, rete):
    try:
        b = _file_cache("m33_kam2017_table9.tsv", url_vizier(**{"-source": "J/AJ/154/41/table9", "-out": "**",
                                                              "-out.max": "5000"}), avvisa, rete,
                        controllo=_ok_tsv(300))
    except Exception as e:
        avvisa(f"M 33 non disponibile ({type(e).__name__}: {e})")
        return None
    if b is None:
        return None
    t = leggi_tsv(b)
    R_arcsec = np.exp([numero(r["lnR"]) for r in t])
    R = R_arcsec / 206264.8 * D_M33_KPC
    V = np.array([numero(r["Vrot"]) for r in t])
    eV = np.array([numero(r["e_Vrot"]) for r in t])
    o = np.argsort(R)
    zero = np.zeros(len(R))
    righe = np.column_stack([R[o], V[o], eV[o], zero, zero, zero]).tolist()
    return dict(chiave="M33", nome="M 33", fonte="Kam+2017 (Halpha + HI)", tipo=6, D=D_M33_KPC / 1000, e_D=0.04,
                inc=np.nan, e_inc=np.nan, L36=np.nan, Reff=np.nan, Rdisk=1.8, MHI=np.nan, RHI=np.nan,
                Vflat=float(np.median(V[R > 8])) if np.any(R > 8) else np.nan, e_Vflat=np.nan, Q=2,
                ra=23.46204, dec=30.66022, righe=righe, senza_barioni=True)


# ------------------------------------------------------------------- Via Lattea
def v_plummer(R, M, b):
    return np.sqrt(G * M * R ** 2 / (R ** 2 + b ** 2) ** 1.5)


def v_miyamoto_nagai(R, M, a, b):
    return np.sqrt(G * M * R ** 2 / (R ** 2 + (a + b) ** 2) ** 1.5)


def v2_disco_sottile(R, sigma, r_max=80.0, n_r=4000, k_max=40.0, n_k=6000):
    """V² nel piano di un disco sottile con densità superficiale sigma(R) (Msun/kpc²), dalla soluzione con le
    funzioni di Bessel: dΦ/dR = 2πG ∫ k J1(kR) [∫ Σ(R') J0(kR') R' dR'] dk. Con il segno: V² < 0 dove il
    disco tira verso l'esterno (buco centrale)."""
    from scipy.special import j0, j1
    R = np.atleast_1d(np.asarray(R, float))
    rp = np.linspace(1e-4, r_max, n_r)
    k = np.linspace(1e-4, k_max, n_k)
    S = np.trapezoid(sigma(rp)[None, :] * j0(np.outer(k, rp)) * rp[None, :], rp, axis=1)
    dphi = 2 * math.pi * G * np.trapezoid((k * S)[None, :] * j1(np.outer(R, k)), k, axis=1)
    return R * dphi


def _sigma_gas(sigma0_pc2, rd, rm):
    return lambda r: sigma0_pc2 * 1e6 * np.exp(-rm / np.maximum(r, 1e-3) - r / rd)


def massa_gas_via_lattea():
    r = np.linspace(1e-3, 80, 20000)
    return float(sum(np.trapezoid(2 * math.pi * r * _sigma_gas(s0, rd, rm)(r), r) for _n, s0, rd, rm in MW_GAS))


MW_MASSA_GAS = massa_gas_via_lattea()      # ≈ 1,2e10 Msun


def barioni_via_lattea(R, gas=False):
    """Velocità del disco di stelle (sottile + spesso) e del bulbo; con gas=True anche del gas (con il segno)."""
    R = np.asarray(R, float)
    vb = v_plummer(R, *MW_BULBO)
    vd = np.sqrt(sum(v_miyamoto_nagai(R, *d) ** 2 for d in MW_DISCHI))
    if not gas:
        return vd, vb
    v2g = sum(v2_disco_sottile(R, _sigma_gas(s0, rd, rm)) for _n, s0, rd, rm in MW_GAS)
    return vd, vb, np.sign(v2g) * np.sqrt(np.abs(v2g))


def trova_csv_salsa(preferito=None):
    """L'ultimo curva_di_rotazione.csv salvato dal programma Idrogeno (o quello scelto)."""
    if preferito and Path(preferito).exists():
        return Path(preferito)
    tutti = []
    for radice in (IDROGENO_RISULTATI.parent, Path.home() / "Scaricati", Path.home() / "Downloads"):
        if radice.exists():
            try:
                tutti += list(radice.rglob("curva_di_rotazione.csv"))
            except OSError:
                pass
    tutti = sorted(set(tutti), key=lambda p: p.stat().st_mtime)
    return tutti[-1] if tutti else None


def leggi_csv_salsa(percorso):
    """Punti affidabili (R ≥ 3 kpc) della curva SALSA di Idrogeno: l_deg, R_kpc, V_kms, reliable."""
    punti = []
    with open(percorso, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if str(r.get("reliable", "1")).strip() in ("1", "True", "true"):
                punti.append((numero(r["R_kpc"]), numero(r["V_kms"]), numero(r.get("l_deg"))))
    punti = [p for p in punti if np.isfinite(p[0]) and np.isfinite(p[1])]
    return sorted(punti)


def via_lattea(csv_salsa=None, avvisa=print):
    """La Via Lattea come galassia: punti SALSA di Edoardo (se c'è il CSV) + Eilers+2019; stelle
    dal modello I di Pouliasis+2017 (massa, non luce: M/L = 1 fisso)."""
    righe, sorgenti = [], []
    p = trova_csv_salsa(csv_salsa)
    edoardo = []
    if p is not None:
        try:
            edoardo = leggi_csv_salsa(p)
        except Exception as e:
            avvisa(f"curva SALSA non letta ({p}): {type(e).__name__}: {e}")
    if len(edoardo) >= 2:
        V = np.array([x[1] for x in edoardo])
        err = max(5.0, float(np.std(V, ddof=1)))     # dispersione dei punti (≈ 7 km/s il 15/11)
        for R, v, _l in edoardo:
            righe.append([R, v, err, 0.0, 0.0, 0.0, 1])
        sorgenti.append(f"SALSA (Edoardo, {len(edoardo)} points, {p.parent.name})")
        avvisa(f"Via Lattea: {len(edoardo)} punti SALSA da {p}")
    else:
        avvisa("Via Lattea: nessun curva_di_rotazione.csv di Idrogeno trovato in " + str(IDROGENO_RISULTATI.parent))
    for R, v, sm, sp in EILERS_2019:
        e = math.hypot(0.5 * (sm + sp), SISTEMATICO_EILERS * v)
        righe.append([R, v, e, 0.0, 0.0, 0.0, 2])
    sorgenti.append("Eilers+2019 (38 points)")
    sorgenti.append("stars: Pouliasis+2017 model I, gas: McMillan 2017")
    righe.sort()
    R = np.array([r[0] for r in righe])
    vd, vb, vg = barioni_via_lattea(R, gas=True)
    for r, d, b, gg in zip(righe, vd, vb, vg):
        r[3], r[4], r[5] = float(gg), float(d), float(b)
    V_edo = [x[1] for x in edoardo]
    return dict(chiave="VIA_LATTEA", nome="Via Lattea", fonte="; ".join(sorgenti), tipo=4, D=np.nan, e_D=np.nan,
                inc=np.nan, e_inc=np.nan, L36=np.nan, Reff=np.nan, Rdisk=2.6, MHI=np.nan, RHI=np.nan,
                Vflat=float(np.mean(V_edo)) if V_edo else 229.0, e_Vflat=np.nan, Q=1, ra=np.nan, dec=np.nan,
                righe=[r[:6] for r in righe], origine=[r[6] for r in righe], massa_fissa=True,
                csv_salsa=str(p) if p else "", n_edoardo=len(edoardo))


def carica_via_lattea(csv_salsa=None, avvisa=print):
    vl = via_lattea(csv_salsa, avvisa)
    origine = np.array(vl["origine"])
    g = prepara(vl)
    g["origine"] = origine          # le righe erano già ordinate per raggio (ordinamento stabile)
    return g


def prepara(g):
    """Trasforma le righe in array (R, V, eV, Vgas, Vdisk, Vbul) ordinati per raggio."""
    a = np.array(g["righe"], float).reshape(-1, 6)
    a = a[np.argsort(a[:, 0], kind="stable")]
    g["R"], g["V"], g["eV"], g["Vgas"], g["Vdisk"], g["Vbul"] = (a[:, i] for i in range(6))
    g["eV"] = np.where(g["eV"] > 0, g["eV"], np.nanmedian(g["eV"][g["eV"] > 0]) if np.any(g["eV"] > 0) else 5.0)
    g["ha_bulbo"] = bool(np.any(g["Vbul"] > 0))
    g.setdefault("senza_barioni", False)
    g.setdefault("massa_fissa", False)
    g["Rmax"] = float(g["R"].max()) if len(g["R"]) else np.nan
    return g


class Catalogo:
    def __init__(self):
        self.galassie = {}
        self.li = {}
        self.fonte_sparc = ""
        self.quando = datetime.now()

    def chiavi_ordinate(self):
        famose = [k for k in ORDINE_FAMOSE if k in self.galassie]
        altre = sorted((k for k in self.galassie if k not in famose), key=lambda k: self.galassie[k]["nome"])
        return famose + altre

    def etichetta(self, k):
        g = self.galassie[k]
        if k in FAMOSE:
            nome, _ = FAMOSE[k]
            breve = {"VIA_LATTEA": "Via Lattea (SALSA + Eilers)", "M33": "M 33 – Galassia del Triangolo",
                     "NGC5055": "M 63 – Girasole", "NGC3992": "M 109", "NGC3198": "NGC 3198 – il caso classico",
                     "DDO154": "DDO 154 – nana oscura", "UGC00128": "UGC 128 – poco luminosa",
                     "NGC6946": "NGC 6946 – Fuochi d'artificio",
                     "UGC02885": "UGC 2885 – galassia di Rubin", "NGC3031": "M 81 – Galassia di Bode",
                     "NGC4826": "M 64 – Occhio Nero", "NGC4736": "M 94", "NGC3627": "M 66"}.get(k, nome)
            return breve
        return g["nome"]

    def sparc(self):
        return [g for g in self.galassie.values() if g["fonte"].startswith("SPARC")]


def carica_catalogo(avvisa=print, rete=True, csv_salsa=None):
    cat = Catalogo()
    gal = None
    try:
        gal = _sparc_da_harvard(avvisa, rete)
        cat.fonte_sparc = "VizieR (Harvard mirror) J/AJ/152/157"
    except Exception as e:
        avvisa(f"SPARC da Harvard non riuscito: {type(e).__name__}: {e}")
    if not gal:
        try:
            gal = _sparc_dal_sito(avvisa, rete)
            cat.fonte_sparc = "astroweb.case.edu/SPARC"
        except Exception as e:
            avvisa(f"SPARC dal sito originale non riuscito: {type(e).__name__}: {e}")
    if not gal:
        raise RuntimeError("Non riesco a leggere SPARC né dalla cache né dalla rete.")
    for g in gal.values():
        if g["righe"]:
            cat.galassie[g["chiave"]] = prepara(g)
    avvisa(f"SPARC: {len(cat.galassie)} galassie, {sum(len(g['R']) for g in cat.galassie.values())} punti "
           f"({cat.fonte_sparc})")
    nuove, doppie = 0, 0
    for g in _raccolta(avvisa, rete):
        k = g["chiave"]
        if k in cat.galassie:
            # già in SPARC: la curva THINGS / LITTLE THINGS diventa una seconda misura da confrontare
            a = np.array(g["righe"], float)
            cat.galassie[k].setdefault("altre", []).append(dict(R=a[:, 0], V=a[:, 1], eV=a[:, 2], fonte=g["fonte"]))
            doppie += 1
        else:
            cat.galassie[k] = prepara(g)
            nuove += 1
    if nuove or doppie:
        avvisa(f"raccolta Zenodo 2026: {nuove} galassie nuove (solo curva), {doppie} curve in più per galassie SPARC")
    m33 = _m33(avvisa, rete)
    if m33:
        cat.galassie["M33"] = prepara(m33)
        avvisa(f"M 33: {len(cat.galassie['M33']['R'])} punti (Kam+2017)")
    cat.galassie["VIA_LATTEA"] = carica_via_lattea(csv_salsa, avvisa)
    cat.li = _li2020(avvisa, rete)
    if cat.li:
        avvisa(f"Li+2020: adattamenti pubblicati per {len(cat.li)} galassie")
    return cat


# =========================================================================== modelli di massa
def v2_firmato(v):
    return v * np.abs(v)


def v2_barioni(g, Yd, Yb=None):
    """Velocità² delle componenti visibili (gas + Υ·disco + Υ_b·bulbo), con il segno (Vgas < 0 = spinta
    verso l'esterno, buco centrale del gas)."""
    if g.get("senza_barioni"):
        return np.zeros_like(g["R"])
    if Yb is None:
        Yb = RAPPORTO_BULBO * Yd
    return v2_firmato(g["Vgas"]) + Yd * g["Vdisk"] ** 2 + Yb * g["Vbul"] ** 2


def v2_nfw(r, V200, c):
    r200 = V200 / (10 * H0)
    x = np.maximum(r, 1e-6) / r200
    m = lambda y: np.log1p(y) - y / (1 + y)  # noqa: E731
    return V200 ** 2 * m(c * x) / (x * m(c))


def massa_burkert(r, r0, rho0_kpc3):
    x = r / r0
    return math.pi * rho0_kpc3 * r0 ** 3 * (np.log1p(x ** 2) + 2 * np.log1p(x) - 2 * np.arctan(x))


def v2_burkert(r, r0, logrho_pc3):
    rho = 10 ** logrho_pc3 * 1e9
    r = np.maximum(r, 1e-6)
    return G * massa_burkert(r, r0, rho) / r


def v2_piso(r, rc, logrho_pc3):
    rho = 10 ** logrho_pc3 * 1e9
    r = np.maximum(r, 1e-6)
    return 4 * math.pi * G * rho * rc ** 2 * (1 - rc / r * np.arctan(r / rc))


def g_mond(gbar):
    """Funzione della relazione delle accelerazioni (McGaugh+2016): g = gbar / (1 − exp(−√(gbar/a0)))."""
    gb = np.maximum(gbar, 1e-12)
    return gb / (-np.expm1(-np.sqrt(gb / A0_INT)))


def massa_einasto(r, rs, rho_kpc3, alfa):
    """Massa entro r per ρ(r) = ρs exp{−2/α [(r/rs)^α − 1]} (rs = r₋₂, ρs = ρ(rs), come Li+2020)."""
    from scipy.special import gamma, gammainc
    a = 3.0 / alfa
    z = (2.0 / alfa) * (np.asarray(r, float) / rs) ** alfa
    return 4 * math.pi * rho_kpc3 * rs ** 3 * math.exp(2.0 / alfa) / alfa * (alfa / 2.0) ** a * gamma(a) * gammainc(a, z)


def v2_einasto(r, rs, logrho_pc3, alfa):
    r = np.maximum(r, 1e-6)
    return G * massa_einasto(r, rs, 10 ** logrho_pc3 * 1e9, alfa) / r


def v2_alone(r, modello, p):
    if modello == "NFW":
        return v2_nfw(r, p["V200"], p["c"])
    if modello == "Burkert":
        return v2_burkert(r, p["r0"], p["logrho"])
    if modello == "pISO":
        return v2_piso(r, p["r0"], p["logrho"])
    if modello == "Einasto":
        return v2_einasto(r, p["r0"], p["logrho"], p["alfa"])
    return np.zeros_like(np.asarray(r, float))


def v_modello(g, modello, p):
    """p: dict con Yd, i parametri dell'alone e (facoltativi) D_fit, i_fit. Restituisce (V del modello
    riportata alla distanza e all'inclinazione pubblicate, V² dell'alone).
    Con distanza D' = δ·D: raggi × δ, V² delle componenti visibili × δ (massa ∝ D², raggio ∝ D);
    con inclinazione i': la velocità vera è V_pubblicata · sin i / sin i' (come Li+2020)."""
    delta = p.get("D_fit", g.get("D")) / g["D"] if p.get("D_fit") else 1.0
    fattore_i = 1.0
    if p.get("i_fit"):
        fattore_i = math.sin(math.radians(p["i_fit"])) / math.sin(math.radians(g["inc"]))
    r = g["R"] * delta
    vb2 = v2_barioni(g, p["Yd"]) * delta
    if modello == "MOND":
        gb = np.maximum(vb2, 0) / np.maximum(r, 1e-6)
        v2 = r * g_mond(gb) * (vb2 > 0)
        vh2 = v2 - vb2
    else:
        vh2 = v2_alone(r, modello, p)
        v2 = vb2 + vh2
    return np.sqrt(np.maximum(v2, 0)) * fattore_i, vh2


def alone_pubblicato(g, modello, p):
    """V dell'alone da solo ai raggi pubblicati (con la distanza e l'inclinazione dell'adattamento)."""
    delta = p["D_fit"] / g["D"] if p.get("D_fit") else 1.0
    fi = math.sin(math.radians(p["i_fit"])) / math.sin(math.radians(g["inc"])) if p.get("i_fit") else 1.0
    return v_alone_su(g["R"] * delta, modello, p) * fi


def v_alone_su(r, modello, p):
    r = np.asarray(r, float)
    if modello == "MOND":
        return np.zeros_like(r)
    return np.sqrt(np.maximum(v2_alone(r, modello, p), 0))


# ------------------------------------------------------------------- adattamento
PARAMETRI_ALONE = {"NFW": ("V200", "c"), "Burkert": ("r0", "logrho"), "pISO": ("r0", "logrho"),
                   "Einasto": ("r0", "logrho", "alfa"), "MOND": ()}
NOMI_LI = {"NFW": "NFW-Flat", "Burkert": "Burkert-Flat", "pISO": "pISO-Flat", "Einasto": "Einasto-Flat"}


def _nomi_parametri(modello):
    return PARAMETRI_ALONE[modello]


def parametri_li(q, modello):
    """Parametri di una riga di Li+2020 nello stesso formato di p."""
    p = dict(Yd=q["Ydisk"])
    if modello == "NFW":
        p.update(V200=q["V200"], c=q["C200"])
    else:
        p.update(r0=q["rs"], logrho=q["log(rhos)"])
        if modello == "Einasto":
            p["alfa"] = q["alpha"]
    return p


def puo_liberare_Di(g):
    return (g["fonte"].startswith("SPARC") and np.isfinite(g.get("e_D", np.nan)) and g.get("e_D", 0) > 0
            and np.isfinite(g.get("e_inc", np.nan)) and g.get("e_inc", 0) > 0 and 0 < g.get("inc", 0) <= 90)


def adatta(g, modello, ml="libero", Yd_fisso=ML_DISCO, inizi=None, libere_Di=False):
    """Adatta un modello alla curva della galassia g.
    ml = "libero": Υ_disco libero con priore log-normale (0,5 ± 0,1 dex, come Li+2020); Υ_bulbo = 1,4 Υ_disco.
    ml = "fisso": Υ_disco = Yd_fisso. Per la Via Lattea (masse già in Msun) Υ = 1 fisso; per le galassie
    senza componenti visibili (M 33, THINGS/LITTLE THINGS/WALLABY non SPARC) tutta la massa va nell'alone.
    libere_Di: distanza e inclinazione libere con priori gaussiani sugli errori pubblicati (solo SPARC)."""
    from scipy.optimize import least_squares
    R, V, eV = g["R"], g["V"], g["eV"]
    if g.get("senza_barioni"):
        if modello == "MOND":
            return dict(modello=modello, ok=False, nota="no baryonic model: MOND cannot be applied")
        ml = "fisso"
        Yd_fisso = 0.0
    if g.get("massa_fissa"):
        ml, Yd_fisso = "fisso", 1.0
    libero = ml == "libero"
    libere_Di = bool(libere_Di) and puo_liberare_Di(g)
    rif = ML_DISCO
    nomi = _nomi_parametri(modello)
    basso, alto = [], []
    if libero:
        basso.append(math.log10(0.05))
        alto.append(math.log10(5.0))
    if modello == "NFW":
        basso += [1.0, 0.0]
        alto += [math.log10(500), 2.0]
    elif modello in ("Burkert", "pISO"):
        basso += [math.log10(0.05), -5.0]
        alto += [math.log10(300), 2.0]
    elif modello == "Einasto":
        basso += [math.log10(0.05), -6.0, 0.05]
        alto += [math.log10(300), 2.0, 1.5]
    if libere_Di:
        D, eD, i0, ei = g["D"], g["e_D"], g["inc"], g["e_inc"]
        basso += [max(0.2 * D, D - 5 * eD), max(10.0, i0 - 5 * ei)]
        alto += [D + 5 * eD, min(90.0, i0 + 5 * ei)]

    def da_vettore(x):
        p = {}
        i = 0
        if libero:
            p["Yd"] = 10 ** x[0]
            i = 1
        else:
            p["Yd"] = Yd_fisso
        if modello == "NFW":
            p["V200"], p["c"] = 10 ** x[i], 10 ** x[i + 1]
            i += 2
        elif modello in ("Burkert", "pISO"):
            p["r0"], p["logrho"] = 10 ** x[i], x[i + 1]
            i += 2
        elif modello == "Einasto":
            p["r0"], p["logrho"], p["alfa"] = 10 ** x[i], x[i + 1], x[i + 2]
            i += 3
        if libere_Di:
            p["D_fit"], p["i_fit"] = float(x[i]), float(x[i + 1])
        return p

    def residui(x):
        p = da_vettore(x)
        vm, _ = v_modello(g, modello, p)
        r = (vm - V) / eV
        extra = []
        if libero:
            extra.append((x[0] - math.log10(rif)) / PRIORE_DEX)
        if libere_Di:
            extra += [(p["D_fit"] - g["D"]) / g["e_D"], (p["i_fit"] - g["inc"]) / g["e_inc"]]
        return np.append(r, extra) if extra else r

    if inizi is None:
        Rm = max(g["Rmax"], 1.0)
        Vm = max(float(np.nanmax(V)), 10.0)
        rho = Vm ** 2 / (G * Rm ** 2) / 1e9
        if modello == "NFW":
            inizi = [(math.log10(Vm * f), math.log10(c)) for f in (0.7, 1.0, 1.5) for c in (3, 8, 20)]
        elif modello in ("Burkert", "pISO"):
            # densità che dà circa Vmax a Rmax
            inizi = [(math.log10(Rm * f), math.log10(rho * k)) for f in (0.1, 0.3, 1.0) for k in (1, 10, 100)]
        elif modello == "Einasto":
            inizi = [(math.log10(Rm * f), math.log10(rho * k), a) for f in (0.3, 1.0) for k in (1, 10, 100)
                     for a in (0.17, 0.5)]
        else:
            inizi = [()]
    migliore = None
    for x0 in inizi:
        x0 = ([math.log10(rif)] if libero else []) + list(x0)
        if libere_Di:
            x0 += [g["D"], g["inc"]]
        x0 = np.clip(x0, np.array(basso) + 1e-6, np.array(alto) - 1e-6) if basso else np.array(x0)
        try:
            if len(x0) == 0:
                fit = None
                res = residui(np.array([]))
                costo = 0.5 * float(np.sum(res ** 2))
                x = np.array([])
            else:
                fit = least_squares(residui, x0, bounds=(basso, alto), method="trf", x_scale="jac", max_nfev=3000)
                x, costo = fit.x, fit.cost
        except Exception:
            continue
        if migliore is None or costo < migliore[1]:
            migliore = (x, costo, fit)
    if migliore is None:
        return dict(modello=modello, ok=False, nota="fit failed")
    x, costo, fit = migliore
    p = da_vettore(x)
    vm, vh2 = v_modello(g, modello, p)
    res = (vm - V) / eV
    k = len(x)
    gradi = max(1, len(R) - k)
    chi2 = float(np.sum(res ** 2))
    # errori dai jacobiani (scalati con il χ² ridotto se > 1)
    err = {}
    if fit is not None and len(x):
        try:
            J = fit.jac
            cov = np.linalg.pinv(J.T @ J) * max(1.0, chi2 / gradi)
            s = np.sqrt(np.maximum(np.diag(cov), 0))
            i = 0
            if libero:
                err["Yd"] = p["Yd"] * math.log(10) * s[0]
                i = 1
            for nome in nomi:
                si = s[i]
                err[nome] = si if nome in ("logrho", "alfa") else p[nome] * math.log(10) * si
                i += 1
            if libere_Di:
                err["D_fit"], err["i_fit"] = s[i], s[i + 1]
        except Exception:
            pass
    delta = p["D_fit"] / g["D"] if libere_Di else 1.0
    vb2 = v2_barioni(g, p["Yd"]) * delta
    vtot2 = vb2 + vh2 if modello != "MOND" else vb2 + vh2
    ris = dict(modello=modello, ok=True, p=p, err=err, chi2=chi2, chi2_rid=chi2 / gradi, n=len(R), k=k,
               ml=ml if not g.get("massa_fissa") else "fisso (masse del modello)", V=vm, res=res,
               libere_Di=libere_Di,
               fdm_ultimo=float(1 - max(vb2[-1], 0) / max(vtot2[-1], 1e-9)))
    Rf = R[-1] * delta
    if modello == "NFW":
        ris["M200"] = p["V200"] ** 3 / (10 * G * H0)
        ris["r200"] = p["V200"] / (10 * H0)
        ris["rs"] = ris["r200"] / p["c"]
    elif modello in ("Burkert", "pISO", "Einasto"):
        ris["Malone_Rmax"] = float(max(vh2[-1], 0) * Rf / G)
    ris["Mvis_Rmax"] = float(max(vb2[-1], 0) * Rf / G)
    ris["Mtot_Rmax"] = float(max(vtot2[-1], 0) * Rf / G)
    return ris


def adatta_tutti(g, ml="libero", Yd_fisso=ML_DISCO, modelli=None, libere_Di=False):
    modelli = MODELLI if modelli is None else modelli
    return {m: adatta(g, m, ml, Yd_fisso, libere_Di=libere_Di) for m in modelli}


def frazione_oscura(g, Yd=ML_DISCO):
    """Frazione di materia oscura 1 − Vbar²/Vobs² a ogni raggio."""
    return 1 - np.maximum(v2_barioni(g, Yd), 0) / np.maximum(g["V"] ** 2, 1e-9)


# =========================================================================== relazioni d'insieme
def dati_tully_fisher(cat):
    pts = []
    for g in cat.sparc():
        if g["Vflat"] > 0 and g["L36"] > 0 and g["inc"] >= 30:
            Mb = (ML_DISCO * g["L36"] + GAS_SU_HI * g["MHI"]) * 1e9
            pts.append((g["chiave"], g["Vflat"], Mb, g["Q"], g.get("e_Vflat", np.nan)))
    return pts


def retta_tully_fisher(pts):
    """Retta log Mb = a log Vf + b (minimi quadrati sulle galassie di qualità 1–2)."""
    v = np.array([p[1] for p in pts if p[3] <= 2])
    m = np.array([p[2] for p in pts if p[3] <= 2])
    if len(v) < 5:
        return None
    a, b = np.polyfit(np.log10(v), np.log10(m), 1)
    sc = float(np.std(np.log10(m) - (a * np.log10(v) + b)))
    return float(a), float(b), sc


def dati_accelerazioni(cat, Yd=ML_DISCO):
    """Accelerazione osservata e dei barioni (m/s²) per tutti i punti SPARC (qualità < 3, i ≥ 30°)."""
    gb, go, chi = [], [], []
    for g in cat.sparc():
        if g["Q"] >= 3 or not (g["inc"] >= 30):
            continue
        vb2 = v2_barioni(g, Yd)
        ok = (vb2 > 0) & (g["R"] > 0) & (g["V"] > 0)
        gb.append(vb2[ok] / g["R"][ok] * KMS2_KPC_IN_MS2)
        go.append(g["V"][ok] ** 2 / g["R"][ok] * KMS2_KPC_IN_MS2)
        chi += [g["chiave"]] * int(ok.sum())
    if not gb:
        return np.array([]), np.array([]), []
    return np.concatenate(gb), np.concatenate(go), chi


# =========================================================================== immagini
def campo_arcsec(g):
    """Lato dell'immagine: 1,3 × il diametro dell'ultimo raggio misurato (tra 3' e 60')."""
    if g["chiave"] == "VIA_LATTEA" or not np.isfinite(g.get("D", np.nan)) or not np.isfinite(g.get("ra", np.nan)):
        return None
    theta = g["Rmax"] / (g["D"] * 1000) * 206264.8
    return float(min(3600.0, max(180.0, 2.6 * theta)))


def _leggi_fits_2d(b):
    testo = b[:2880 * 10].decode("latin1")
    h, pos = {}, 0
    while pos < len(b):
        blocco = b[pos:pos + 2880].decode("latin1")
        pos += 2880
        fine = False
        for i in range(0, 2880, 80):
            c = blocco[i:i + 80]
            k = c[:8].strip()
            if k == "END":
                fine = True
                break
            if c[8:10] == "= ":
                h[k] = c[10:].split("/")[0].strip().strip("'").strip()
        if fine:
            break
    del testo
    nx, ny, bp = int(h["NAXIS1"]), int(h["NAXIS2"]), int(h["BITPIX"])
    tipo = {-32: ">f4", -64: ">f8", 16: ">i2", 32: ">i4", 8: "u1"}[bp]
    a = np.frombuffer(b[pos:pos + nx * ny * abs(bp) // 8], dtype=tipo).astype(float).reshape(ny, nx)
    return a[::-1] * float(h.get("BSCALE", 1)) + float(h.get("BZERO", 0))


def _vuota(img):
    a = np.asarray(img, float)
    return a.size == 0 or float(np.nanstd(a)) < 2.0 or float(np.mean(a < 3)) > 0.85


def immagini(g, avvisa=print, rete=True):
    """Ottico (Legacy Survey DR10, altrimenti DSS2 da SkyView) e infrarosso (unWISE W1/W2).
    Restituisce lista di dict(titolo, immagine RGB o 2D, campo in arcsec, fonte). Cache su disco."""
    campo = campo_arcsec(g)
    if campo is None:
        return []
    from PIL import Image
    cartella = CACHE / "immagini"
    cartella.mkdir(parents=True, exist_ok=True)
    px = 512
    uscita = []
    richieste = [
        ("optical", "Legacy Survey DR10 (g, r, z)", "jpg",
         "https://www.legacysurvey.org/viewer/jpeg-cutout?" + urllib.parse.urlencode(
             dict(ra=f"{g['ra']:.5f}", dec=f"{g['dec']:.5f}", layer="ls-dr10", pixscale=f"{campo / px:.3f}", size=px))),
        ("infrared", "unWISE (W1 3.4 µm, W2 4.6 µm)", "jpg",
         "https://www.legacysurvey.org/viewer/jpeg-cutout?" + urllib.parse.urlencode(
             dict(ra=f"{g['ra']:.5f}", dec=f"{g['dec']:.5f}", layer="unwise-neo7",
                  pixscale=f"{max(campo / px, 0.5):.3f}", size=px))),
    ]
    for tipo, fonte, est, url in richieste:
        p = cartella / f"{g['chiave']}_{tipo}_{int(campo)}.{est}"
        img = None
        if p.exists():
            try:
                img = np.asarray(Image.open(p).convert("RGB"))
            except Exception:
                img = None
        if img is None and rete:
            try:
                avvisa(f"immagine {tipo} di {g['nome']} …")
                b = scarica(url, tempo=45, tentativi=2)
                img = np.asarray(Image.open(io.BytesIO(b)).convert("RGB"))
                if not _vuota(img):
                    p.write_bytes(b)
            except Exception as e:
                avvisa(f"immagine {tipo} non scaricata: {type(e).__name__}: {e}")
                img = None
        if tipo == "optical" and (img is None or _vuota(img)):
            # fuori dall'area di Legacy Survey: DSS2 rosso da SkyView (FITS)
            p2 = cartella / f"{g['chiave']}_dss2_{int(campo)}.npy"
            a = None
            if p2.exists():
                a = np.load(p2)
            elif rete:
                try:
                    url2 = "https://skyview.gsfc.nasa.gov/cgi-bin/images?" + urllib.parse.urlencode(
                        {"Position": f"{g['ra']:.5f},{g['dec']:.5f}", "Survey": "DSS2 Red", "Pixels": "500",
                         "Size": f"{campo / 3600:.4f}", "Return": "FITS"})
                    b = scarica(url2, tempo=60, tentativi=2, attesa=8)
                    if b[:6] == b"SIMPLE":
                        a = _leggi_fits_2d(b).astype(np.float32)
                        if a.shape[0] > 1:
                            np.save(p2, a)
                        else:
                            a = None
                except Exception as e:
                    avvisa(f"DSS2 non scaricata: {type(e).__name__}: {e}")
            if a is not None:
                img, fonte = a, "DSS2 red (SkyView)"
        if img is not None and not (img.ndim == 3 and _vuota(img)):
            uscita.append(dict(titolo=tipo, immagine=img, campo=campo, fonte=fonte))
    return uscita


# =========================================================================== grafici (in inglese)
def _titolo(g):
    t = g["nome"]
    if g["chiave"] in FAMOSE and FAMOSE[g["chiave"]][0] != g["nome"]:
        t = f"{FAMOSE[g['chiave']][0]} ({g['nome']})"
    if g["chiave"] == "VIA_LATTEA":
        t = "Milky Way"
    if g["chiave"] == "NGC5055":
        t = "M 63 (NGC 5055)"
    if g["chiave"] == "NGC3992":
        t = "M 109 (NGC 3992)"
    return t


def _info_galassia(g):
    parti = []
    if np.isfinite(g.get("D", np.nan)):
        parti.append(f"D = {g['D']:.2f} Mpc" if g["D"] < 10 else f"D = {g['D']:.1f} Mpc")
    if np.isfinite(g.get("inc", np.nan)):
        parti.append(f"i = {g['inc']:.0f}°")
    if g.get("Q") and g["fonte"].startswith("SPARC"):
        parti.append(f"quality {g['Q']}")
    parti.append(g["fonte"])
    return ", ".join(parti)


def disegna_curva(fig, g, risultati, modelli=("NFW", "Burkert"), componenti=("gas", "disco", "bulbo", "barioni"),
                  li=None, Yd_mostra=None, mostra_residui=True, scala=1.0):
    """Curva di rotazione con componenti visibili e modelli; sotto i residui."""
    fig.clf()
    if mostra_residui:
        gs = fig.add_gridspec(2, 1, height_ratios=(3.2, 1), hspace=0.05)
        ax = fig.add_subplot(gs[0])
        axr = fig.add_subplot(gs[1], sharex=ax)
    else:
        ax = fig.add_subplot(111)
        axr = None
    R, V, eV = g["R"], g["V"], g["eV"]
    if g["chiave"] == "VIA_LATTEA" and "origine" in g:
        o = np.asarray(g["origine"])
        for cod, col, et in ((1, COLORI["edoardo"], "SALSA – Edoardo (tangent points)"),
                             (2, COLORI["eilers"], "Eilers et al. 2019 (Gaia + APOGEE)")):
            s = o == cod
            if s.any():
                ax.errorbar(R[s], V[s], eV[s], fmt="o", ms=5 if cod == 2 else 7, color=col, ecolor=col, elinewidth=1,
                            capsize=2, label=et, zorder=5)
    else:
        ax.errorbar(R, V, eV, fmt="o", ms=4, color=COLORI["oss"], ecolor="#9ca3af", elinewidth=1, capsize=2,
                    label="observed" + (f" ({g['fonte'].split(' (')[0]})" if g.get("altre") else ""), zorder=5)
    for alt in g.get("altre", []) if "altre" in componenti else []:
        ax.errorbar(alt["R"], alt["V"], alt["eV"], fmt="^", ms=4, color="#0ea5e9", ecolor="#7dd3fc", elinewidth=0.8,
                    alpha=0.8, label=f"also measured by {alt['fonte']}", zorder=4)
    rr = R
    ris_ref = None
    for m in modelli:
        r = risultati.get(m)
        if r and r.get("ok"):
            ris_ref = ris_ref or r
    Yd = Yd_mostra if Yd_mostra is not None else (ris_ref["p"]["Yd"] if ris_ref else ML_DISCO)
    if g.get("massa_fissa"):
        Yd = 1.0
    if not g.get("senza_barioni"):
        Yb = RAPPORTO_BULBO * Yd
        if "gas" in componenti and np.any(g["Vgas"] != 0):
            ax.plot(rr, g["Vgas"], ":", color=COLORI["gas"], lw=2, label="gas (HI + He)")
        if "disco" in componenti:
            et = "stellar disc" + (f" (Υ = {Yd:.2f})" if not g.get("massa_fissa") else " (thin + thick)")
            ax.plot(rr, np.sqrt(Yd) * g["Vdisk"], "--", color=COLORI["disco"], lw=1.8, label=et)
        if "bulbo" in componenti and g["ha_bulbo"]:
            ax.plot(rr, np.sqrt(Yb) * g["Vbul"], "-.", color=COLORI["bulbo"], lw=1.8, label="bulge")
        vb = np.sqrt(np.maximum(v2_barioni(g, Yd), 0))
        if "barioni" in componenti:
            ax.plot(rr, vb, "-", color=COLORI["barioni"], lw=2.6, label="all visible matter")
            ax.fill_between(rr, vb, V, where=V > vb, color="#a78bfa", alpha=0.13, lw=0,
                            label="missing mass (dark matter?)")
    for m in modelli:
        r = risultati.get(m)
        if not r or not r.get("ok"):
            continue
        et = f"{m}: χ²ᵣ = {r['chi2_rid']:.2f}"
        if not g.get("massa_fissa") and not g.get("senza_barioni"):
            et += f", Υ = {r['p']['Yd']:.2f}"
        ax.plot(rr, r["V"], "-", color=COLORI[m], lw=2.2, label=et, zorder=6)
        if m != "MOND" and "alone" in componenti:
            ax.plot(rr, alone_pubblicato(g, m, r["p"]), "-", color=COLORI[m], lw=1, alpha=0.6)
    if li:
        for m in modelli:
            nome = NOMI_LI.get(m)
            q = li.get(nome) if nome else None
            if q:
                p = parametri_li(q, m)
                if puo_liberare_Di(g) and np.isfinite(q.get("Dist", np.nan)) and np.isfinite(q.get("inc", np.nan)):
                    p.update(D_fit=q["Dist"], i_fit=q["inc"])        # Li+2020 hanno adattato anche D e i
                vli, _ = v_modello(g, m, p)
                ax.plot(rr, vli, ls=(0, (1, 1.5)), color=COLORI[m], lw=1.6, alpha=0.9,
                        label=f"{m} Li et al. 2020 (Υ = {q['Ydisk']:.2f}, χ²ᵣ = {q['chi2']:.2f})")
    ax.set_xlim(0, max(R) * 1.04)
    ax.set_ylim(0, max(np.nanmax(V + eV), 10) * 1.15)
    ax.set_ylabel("rotation velocity V (km/s)")
    ax.grid(alpha=0.25)
    ax.set_title(f"{_titolo(g)} – rotation curve and mass model\n{_info_galassia(g)}", fontsize="medium")
    ax.legend(loc="lower right", fontsize="x-small", ncol=2 if len(ax.get_legend_handles_labels()[0]) > 6 else 1,
              framealpha=0.85)
    if g.get("senza_barioni"):
        ax.text(0.02, 0.96, "no baryonic model available: the halo fit attributes all the mass to dark matter",
                transform=ax.transAxes, fontsize="x-small", color="#92400e", va="top")
    if axr is not None:
        axr.axhline(0, color="k", lw=0.8)
        for m in modelli:
            r = risultati.get(m)
            if r and r.get("ok"):
                axr.plot(R, (V - r["V"]), "o-", ms=3, lw=0.8, color=COLORI[m])
        axr.set_ylabel("obs − model\n(km/s)", fontsize="small")
        axr.set_xlabel("radius R (kpc)")
        axr.grid(alpha=0.25)
        for t in ax.get_xticklabels():
            t.set_visible(False)
    else:
        ax.set_xlabel("radius R (kpc)")


def _assi_velocita(ax):
    from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter
    ax.xaxis.set_major_locator(FixedLocator([20, 30, 50, 100, 200, 300]))
    ax.xaxis.set_major_formatter(ScalarFormatter())
    ax.xaxis.set_minor_formatter(NullFormatter())


def disegna_insieme(fig, cat, evidenzia=None, tutte=None):
    """Tully-Fisher barionica, relazione delle accelerazioni radiali, frazione di materia oscura."""
    fig.clf()
    axs = fig.subplots(1, 3)
    # --- Tully-Fisher
    ax = axs[0]
    pts = dati_tully_fisher(cat)
    for q, col, et in ((1, "#1d4ed8", "SPARC quality 1"), (2, "#60a5fa", "quality 2"), (3, "#cbd5e1", "quality 3")):
        s = [p for p in pts if p[3] == q]
        ax.scatter([p[1] for p in s], [p[2] for p in s], s=12, color=col, label=et, zorder=3)
    tf = retta_tully_fisher(pts)
    if tf:
        vv = np.logspace(1.3, 2.6, 50)
        ax.plot(vv, 10 ** (tf[0] * np.log10(vv) + tf[1]), "k-", lw=1.2,
                label=f"fit: $M \\propto V^{{{tf[0]:.2f}}}$ (scatter {tf[2]:.2f} dex)")
    vl = cat.galassie.get("VIA_LATTEA")
    if vl:
        ax.scatter([vl["Vflat"]], [MW_MASSA_STELLE + MW_MASSA_GAS], marker="*", s=260, color=COLORI["edoardo"],
                   edgecolor="k", zorder=6, label=f"Milky Way (V = {vl['Vflat']:.0f} km/s, SALSA)")
    if evidenzia and evidenzia in cat.galassie and evidenzia != "VIA_LATTEA":
        g = cat.galassie[evidenzia]
        if g["Vflat"] > 0 and np.isfinite(g["L36"]):
            ax.scatter([g["Vflat"]], [(ML_DISCO * g["L36"] + GAS_SU_HI * g["MHI"]) * 1e9], s=140, facecolor="none",
                       edgecolor="#dc2626", lw=2, zorder=7, label=_titolo(g))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("flat rotation velocity V$_{flat}$ (km/s)")
    ax.set_ylabel("baryonic mass (stars + gas, M$_\\odot$)")
    _assi_velocita(ax)
    ax.set_title("Baryonic Tully-Fisher relation (i ≥ 30°)", fontsize="medium")
    ax.legend(fontsize="x-small", loc="upper left")
    ax.grid(alpha=0.25, which="both")
    # --- relazione delle accelerazioni
    ax = axs[1]
    gb, go, chi = dati_accelerazioni(cat)
    if len(gb):
        ax.hexbin(np.log10(gb), np.log10(go), gridsize=45, cmap="Blues", mincnt=1, bins="log", extent=(-12.5, -8.5, -12, -8.5))
        x = np.linspace(-12.5, -8.5, 100)
        ax.plot(x, x, "k:", lw=1, label="no dark matter (g$_{obs}$ = g$_{bar}$)")
        ax.plot(x, np.log10(g_mond(10 ** x / KMS2_KPC_IN_MS2) * KMS2_KPC_IN_MS2), "-", color="#e69f00", lw=2,
                label="McGaugh et al. 2016 / MOND")
        if evidenzia and evidenzia in cat.galassie:
            s = np.array([c == evidenzia for c in chi])
            if s.any():
                ax.plot(np.log10(gb[s]), np.log10(go[s]), "o", ms=4, color="#dc2626", label=_titolo(cat.galassie[evidenzia]))
    if vl:
        gbar = np.maximum(v2_barioni(vl, 1.0), 1e-9) / vl["R"] * KMS2_KPC_IN_MS2      # stelle + gas
        gobs = vl["V"] ** 2 / vl["R"] * KMS2_KPC_IN_MS2
        o = np.asarray(vl.get("origine", np.full(len(vl["R"]), 2)))
        ax.plot(np.log10(gbar[o == 2]), np.log10(gobs[o == 2]), "s", ms=3, color=COLORI["eilers"], label="Milky Way (Eilers+2019)")
        if np.any(o == 1):
            ax.plot(np.log10(gbar[o == 1]), np.log10(gobs[o == 1]), "*", ms=11, color=COLORI["edoardo"], mec="k",
                    label="Milky Way (SALSA, Edoardo)")
    ax.set_xlim(-12.5, -8.5)
    ax.set_ylim(-12, -8.5)
    ax.set_xlabel("log g$_{bar}$ (m/s²)  – from visible matter")
    ax.set_ylabel("log g$_{obs}$ (m/s²)  – from V²/R")
    ax.set_title(f"Radial acceleration relation ({len(gb)} points)", fontsize="medium")
    ax.legend(fontsize="x-small", loc="upper left")
    ax.grid(alpha=0.25)
    # --- frazione di materia oscura all'ultimo raggio
    ax = axs[2]
    vf, fd, q = [], [], []
    for g in cat.sparc():
        if g["Vflat"] > 0:
            vf.append(g["Vflat"])
            fd.append(frazione_oscura(g)[-1])
            q.append(g["Q"])
    vf, fd, q = np.array(vf), np.array(fd), np.array(q)
    sc = ax.scatter(vf, fd, c=q, cmap="Blues_r", vmin=0.5, vmax=3.5, s=14)
    if vl:
        ax.scatter([vl["Vflat"]], [frazione_oscura(vl, 1.0)[-1]], marker="*", s=260,
                   color=COLORI["edoardo"], edgecolor="k", zorder=6, label="Milky Way (at 25 kpc)")
    if evidenzia and evidenzia in cat.galassie:
        g = cat.galassie[evidenzia]
        if g["fonte"].startswith("SPARC") and g["Vflat"] > 0:
            ax.scatter([g["Vflat"]], [frazione_oscura(g)[-1]], s=140, facecolor="none", edgecolor="#dc2626", lw=2,
                       zorder=7, label=_titolo(g))
    ax.set_xscale("log")
    ax.set_ylim(-0.2, 1.02)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("V$_{flat}$ (km/s)")
    ax.set_ylabel("dark-matter fraction at the last radius\n1 − V²$_{bar}$/V²$_{obs}$ (Υ = 0.5)")
    _assi_velocita(ax)
    ax.set_title("How much mass is missing?", fontsize="medium")
    ax.legend(fontsize="x-small", loc="lower left")
    ax.grid(alpha=0.25, which="both")
    del sc


def disegna_immagini(fig, g, imgs):
    fig.clf()
    if not imgs:
        ax = fig.add_subplot(111)
        ax.axis("off")
        testo = ("No image for the Milky Way: we are inside it!" if g["chiave"] == "VIA_LATTEA"
                 else "No image available (offline, or position unknown).")
        ax.text(0.5, 0.5, testo, ha="center", va="center", fontsize="large", transform=ax.transAxes)
        return
    axs = fig.subplots(1, len(imgs))
    axs = np.atleast_1d(axs)
    for ax, im in zip(axs, imgs):
        a = im["immagine"]
        mezzo = im["campo"] / 2 / 60
        est = (-mezzo, mezzo, -mezzo, mezzo)
        if a.ndim == 2:
            lo, hi = np.nanpercentile(a, (1, 99.7))
            ax.imshow(np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1) ** 0.6, cmap="gray", origin="lower", extent=est)
        else:
            ax.imshow(a, extent=est)
        if np.isfinite(g.get("D", np.nan)):
            raggio = g["Rmax"] / (g["D"] * 1000) * 206264.8 / 60
            t = np.linspace(0, 2 * np.pi, 200)
            ax.plot(raggio * np.cos(t), raggio * np.sin(t), "--", color="#fde047", lw=1.4)
            ax.text(0, raggio * 1.03, f"last measured radius {g['Rmax']:.1f} kpc", color="#fde047", ha="center",
                    va="bottom", fontsize="x-small")
            # barra da 10 kpc (o 1 kpc per le galassie piccole)
            lung_kpc = 10 if g["Rmax"] > 8 else 1
            lung = lung_kpc / (g["D"] * 1000) * 206264.8 / 60
            x0, y0 = -mezzo * 0.9, -mezzo * 0.88
            ax.plot([x0, x0 + lung], [y0, y0], "-", color="w", lw=3)
            ax.text(x0 + lung / 2, y0 + mezzo * 0.03, f"{lung_kpc} kpc", color="w", ha="center", va="bottom",
                    fontsize="x-small")
        ax.set_xlim(est[0], est[1])
        ax.set_ylim(est[2], est[3])
        ax.set_xlabel("arcmin (east ←)")
        ax.set_title(f"{_titolo(g)} – {im['fonte']}", fontsize="small")
    axs[0].set_ylabel("arcmin")


# =========================================================================== testi
def testo_parametri(r):
    if not r.get("ok"):
        return r.get("nota", "")
    p, e = r["p"], r.get("err", {})

    def pm(k, fmt):
        return f"{p[k]:{fmt}}" + (f" ± {e[k]:{fmt}}" if k in e and np.isfinite(e[k]) else "")
    if r["modello"] == "NFW":
        return (f"V200 = {pm('V200', '.1f')} km/s, c = {pm('c', '.1f')}, rs = {r['rs']:.1f} kpc, "
                f"M200 = {r['M200']:.2e} Msun" + (f", D = {pm('D_fit', '.2f')} Mpc, i = {pm('i_fit', '.1f')}°"
                                                   if r.get("libere_Di") else ""))
    extra = ""
    if r.get("libere_Di"):
        extra = f", D = {pm('D_fit', '.2f')} Mpc, i = {pm('i_fit', '.1f')}°"
    if r["modello"] in ("Burkert", "pISO"):
        return (f"r0 = {pm('r0', '.2f')} kpc, log ρ0 = {pm('logrho', '.2f')} (Msun/pc³), "
                f"halo mass inside Rmax = {r['Malone_Rmax']:.2e} Msun" + extra)
    if r["modello"] == "Einasto":
        return (f"rs = {pm('r0', '.2f')} kpc, log ρs = {pm('logrho', '.2f')} (Msun/pc³), α = {pm('alfa', '.2f')}, "
                f"halo mass inside Rmax = {r['Malone_Rmax']:.2e} Msun" + extra)
    return "a0 = 1.2e-10 m/s² (fixed), no dark matter" + extra


def testo_risultati(g, ris, li=None, lingua="en"):
    """Riassunto testuale (inglese per il PDF, italiano per la finestra)."""
    it = lingua == "it"
    righe = []
    righe.append(f"{_titolo(g) if not it else g['nome']}  –  {_info_galassia(g)}")
    if g["chiave"] in FAMOSE and it:
        righe.append(FAMOSE[g["chiave"]][1])
    righe.append((f"{len(g['R'])} punti da {g['R'][0]:.2f} a {g['Rmax']:.1f} kpc" if it else
                  f"{len(g['R'])} points from {g['R'][0]:.2f} to {g['Rmax']:.1f} kpc"))
    if np.isfinite(g.get("Vflat", np.nan)) and g["Vflat"] > 0:
        righe.append(("velocità piatta" if it else "flat velocity") + f" V_flat = {g['Vflat']:.0f} km/s")
    if not g.get("senza_barioni"):
        fd = frazione_oscura(g, 1.0 if g.get("massa_fissa") else ML_DISCO)[-1]
        righe.append((f"all'ultimo raggio la materia visibile spiega il {100 * (1 - fd):.0f} % della massa "
                      f"(Υ = 0,5): manca il {100 * fd:.0f} %" if it else
                      f"at the last radius visible matter accounts for {100 * (1 - fd):.0f} % of the mass "
                      f"(Υ = 0.5): {100 * fd:.0f} % is missing"))
    righe.append("")
    for m in MODELLI:
        r = ris.get(m)
        if not r:
            continue
        if not r.get("ok"):
            righe.append(f"{m:8s} {r.get('nota', '')}")
            continue
        ml = "" if g.get("massa_fissa") or g.get("senza_barioni") else f"Υ_disc = {r['p']['Yd']:.2f}" + (
            f" ± {r['err']['Yd']:.2f}" if "Yd" in r.get("err", {}) else "") + ", "
        righe.append(f"{m:8s} χ²_red = {r['chi2_rid']:6.2f}   {ml}{testo_parametri(r)}")
        if li:
            nome = NOMI_LI.get(m)
            q = li.get(nome) if nome else None
            if q:
                righe.append(f"{'':8s} Li+2020: χ²_red = {q['chi2']:6.2f}   Υ_disc = {q['Ydisk']:.2f}"
                             + (f", V200 = {q['V200']:.1f}, c = {q['C200']:.1f}" if m == "NFW" else
                                f", r0 = {q['rs']:.2f} kpc, log ρ0 = {q['log(rhos)']:.2f}"
                                + (f", α = {q['alpha']:.2f}" if m == "Einasto" else ""))
                             + f", D = {q['Dist']:.2f} Mpc, i = {q['inc']:.1f}°")
    ok = [r for r in ris.values() if r.get("ok")]
    if ok:
        best = min(ok, key=lambda r: r["chi2_rid"])
        righe.append("")
        righe.append(("modello migliore: " if it else "best model: ") + f"{best['modello']} (χ²_red = {best['chi2_rid']:.2f})")
    return "\n".join(righe)


NOTE_IT = [
    ("Che cos'è una curva di rotazione",
     "Le stelle e il gas di una galassia a disco girano attorno al centro. La curva di rotazione dice quanto "
     "vanno veloci a ogni distanza dal centro. La velocità dipende da quanta massa c'è dentro quell'orbita: "
     "V² = G·M(<R)/R. Se quasi tutta la massa fosse nelle stelle che vediamo, lontano dal centro la velocità "
     "dovrebbe scendere come nel Sistema solare (Keplero: V ∝ 1/√R)."),
    ("Che cosa si vede invece",
     "Quasi sempre la curva resta piatta ben oltre la fine delle stelle. Nel grafico la linea grigia è la "
     "velocità che darebbero da sole le stelle e il gas (la «materia visibile»); i punti neri sono la velocità "
     "misurata. La zona viola tra le due è la massa che manca: la materia oscura, oppure una gravità diversa."),
    ("Da dove vengono i dati",
     "SPARC (Lelli, McGaugh e Schombert 2016): 175 galassie con la curva misurata dal gas (riga a 21 cm "
     "dell'idrogeno, come SALSA, e riga Hα) e la luce delle stelle misurata da Spitzer a 3,6 µm. Per ogni raggio "
     "ci sono la velocità del gas, del disco e del bulbo. Il disco e il bulbo sono dati per Υ = 1 (una massa "
     "solare per ogni luminosità solare): il rapporto massa/luce vero a 3,6 µm è circa 0,5, ed è il numero "
     "che si regola con il contatore. Dalla versione 1.1 ci sono anche le curve della raccolta di Flynn (2026, Zenodo): "
     "THINGS (de Blok et al. 2008), LITTLE THINGS (Oh et al. 2015, galassie nane) e WALLABY (Deg et al. 2022, 203 "
     "galassie del cielo australe, misure automatiche meno precise sotto i 50 km/s). Per queste c'è solo la curva "
     "misurata: senza la materia visibile tutta la massa viene data all'alone. Quando una galassia SPARC è anche in "
     "THINGS, la seconda curva compare con triangoli azzurri."),
    ("I modelli di materia oscura",
     "NFW: il profilo che esce dalle simulazioni al computer dell'universo (Navarro, Frenk e White 1996), con "
     "una densità che cresce senza limite verso il centro («cuspide»). Burkert e isotermo (pISO): aloni con un "
     "«nucleo» di densità costante al centro. Molte galassie nane preferiscono un nucleo: è il problema "
     "«cuspide o nucleo». Einasto: il profilo che descrive meglio gli aloni delle simulazioni più recenti, con una "
     "pendenza che cambia piano piano (il parametro α). MOND (Milgrom 1983) non usa materia oscura: cambia la gravità quando l'accelerazione "
     "è più piccola di a0 = 1,2·10⁻¹⁰ m/s²."),
    ("Come leggere χ²",
     "χ² ridotto (χ²ᵣ) misura quanto il modello passa vicino ai punti, tenendo conto degli errori: circa 1 = "
     "buono; molto più di 1 = il modello non segue la curva. Sotto il grafico ci sono i residui (misura − modello). "
     "La linea a puntini «Li et al. 2020» è l'adattamento pubblicato da specialisti (che regolano anche distanza "
     "e inclinazione): serve per controllare i nostri risultati. Con «Distanza e inclinazione: libere» il programma "
     "fa lo stesso, entro gli errori pubblicati: una galassia un po' più lontana ha stelle e gas più massicci, una "
     "più inclinata ruota un po' più piano. Così i χ² diventano confrontabili con quelli di Li et al. 2020."),
    ("La Via Lattea",
     "I punti arancioni sono la misura di Edoardo con SALSA (metodo del punto tangente, R₀ = 8,5 kpc, tra 3,6 e "
     "8,5 kpc). I punti verdi sono Eilers et al. 2019 (stelle giganti rosse con Gaia e APOGEE, da 5 a 25 kpc, "
     "R₀ = 8,12 kpc). Le stelle della Via Lattea vengono dal modello I di Pouliasis et al. 2017 (bulbo + disco "
     "sottile + disco spesso), lo stesso usato da Eilers; dalla 1.1 c'è anche il gas (idrogeno atomico e molecolare, "
     "McMillan 2017, circa 12 miliardi di masse solari). Qui le masse sono già in masse solari, quindi niente "
     "rapporto massa/luce."),
    ("I grafici d'insieme",
     "Tully-Fisher barionica: la massa visibile cresce come la velocità alla quarta potenza circa, con pochissima "
     "dispersione. Relazione delle accelerazioni radiali (McGaugh et al. 2016): in tutte le galassie l'accelerazione "
     "misurata dipende solo da quella della materia visibile; dove questa è grande (centri) non serve materia "
     "oscura, dove è piccola (periferie, galassie nane) ne serve molta. Frazione di materia oscura: le galassie "
     "lente e piccole sono quasi tutte materia oscura."),
]


# =========================================================================== uscite: PDF e CSV
def cartella_risultati():
    p = RISULTATI / datetime.now().strftime("%Y-%m-%d_%H-%M")
    p.mkdir(parents=True, exist_ok=True)
    return p


def nome_file(g):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", _titolo(g)).strip("_")


def salva_scheda(g, ris, li, imgs, cartella, modelli=("NFW", "Burkert", "MOND")):
    """Scheda PDF (2 pagine) + PNG della curva, in inglese."""
    import matplotlib
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure
    cartella = Path(cartella)
    base = cartella / f"{nome_file(g)}_rotation_curve"
    with matplotlib.rc_context({"font.size": 10}):
        f1 = Figure(figsize=(11.69, 8.27), layout="constrained")
        disegna_curva(f1, g, ris, modelli=modelli, componenti=("gas", "disco", "bulbo", "barioni", "alone"), li=li)
        f1.text(0.995, 0.003, FIRMA + f" · Curve di rotazione {VERSIONE}", ha="right", va="bottom", fontsize=7,
                color="#6b7280")
        f1.savefig(str(base) + ".png", dpi=150)
        with PdfPages(str(base) + ".pdf") as pdf:
            pdf.savefig(f1)
            f2 = Figure(figsize=(11.69, 8.27), layout="constrained")
            if imgs:
                sub = f2.subfigures(2, 1, height_ratios=(1.25, 1))
                disegna_immagini(sub[0], g, imgs)
                ax = sub[1].add_subplot(111)
            else:
                ax = f2.add_subplot(111)
            ax.axis("off")
            ax.text(0, 1, testo_risultati(g, ris, li, "en"), family="DejaVu Sans Mono", fontsize=7.6, va="top")
            f2.text(0.995, 0.003, FIRMA, ha="right", va="bottom", fontsize=7, color="#6b7280")
            pdf.savefig(f2)
            info = pdf.infodict()
            info["Title"] = f"{_titolo(g)} – rotation curve"
            info["Author"] = "Edoardo Battistel"
    return [Path(str(base) + ".pdf"), Path(str(base) + ".png")]


def adatta_catalogo(cat, ml="libero", avvisa=print, fermo=None, modelli=None, libere_Di=False):
    """Adatta tutti i modelli a tutte le galassie. Restituisce {chiave: {modello: risultato}}."""
    tutti = {}
    chiavi = cat.chiavi_ordinate()
    t0 = time.time()
    for i, k in enumerate(chiavi):
        if fermo is not None and fermo.is_set():
            break
        g = cat.galassie[k]
        tutti[k] = adatta_tutti(g, ml, modelli=modelli, libere_Di=libere_Di)
        if i % 10 == 0:
            avvisa(f"adattamenti: {i + 1}/{len(chiavi)} galassie ({time.time() - t0:.0f} s)")
    avvisa(f"adattamenti finiti: {len(tutti)} galassie in {time.time() - t0:.0f} s")
    return tutti


def migliore(ris):
    ok = [r for r in ris.values() if r.get("ok")]
    return min(ok, key=lambda r: r["chi2_rid"]) if ok else None


def salva_csv_tutte(cat, tutti, cartella):
    p = Path(cartella) / "halo_fits_all_galaxies.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["galaxy", "source", "quality", "distance_Mpc", "inclination_deg", "Vflat_kms", "n_points",
                    "Rmax_kpc", "model", "ml_mode", "Ydisk", "e_Ydisk", "V200_kms", "c200", "rs_kpc", "log_M200",
                    "r0_kpc", "log_rho0_Msun_pc3", "einasto_alpha", "distance_fit_Mpc", "inclination_fit_deg",
                    "chi2_red", "dm_fraction_last_radius", "best_model", "Li2020_Ydisk", "Li2020_chi2_red"])
        for k, ris in tutti.items():
            g = cat.galassie[k]
            b = migliore(ris)
            for m, r in ris.items():
                if not r.get("ok"):
                    continue
                p_ = r["p"]
                li = cat.li.get(k, {}).get(NOMI_LI.get(m, ""), {})
                w.writerow([_titolo(g), g["fonte"], g["Q"], g["D"], g["inc"], g["Vflat"], r["n"], f"{g['Rmax']:.2f}",
                            m, r["ml"], f"{p_['Yd']:.3f}", f"{r['err'].get('Yd', float('nan')):.3f}",
                            f"{p_.get('V200', float('nan')):.2f}", f"{p_.get('c', float('nan')):.2f}",
                            f"{r.get('rs', float('nan')):.2f}",
                            f"{math.log10(r['M200']):.3f}" if "M200" in r else "",
                            f"{p_.get('r0', float('nan')):.3f}" if m != "NFW" else "",
                            f"{p_.get('logrho', float('nan')):.3f}" if m != "NFW" else "",
                            f"{p_['alfa']:.3f}" if "alfa" in p_ else "",
                            f"{p_['D_fit']:.3f}" if "D_fit" in p_ else "", f"{p_['i_fit']:.2f}" if "i_fit" in p_ else "",
                            f"{r['chi2_rid']:.3f}", f"{r['fdm_ultimo']:.3f}", b["modello"] if b else "",
                            li.get("Ydisk", ""), li.get("chi2", "")])
    return p


def statistiche_tutte(cat, tutti):
    """Quante galassie preferiscono ciascun modello, χ² mediani, confronto Υ con Li+2020."""
    st = {}
    sparc = [k for k in tutti if cat.galassie[k]["fonte"].startswith("SPARC")]
    vincitori = {m: 0 for m in MODELLI}
    for k in sparc:
        b = migliore(tutti[k])
        if b:
            vincitori[b["modello"]] += 1
    st["vincitori"] = vincitori
    st["chi2_mediano"] = {m: float(np.median([tutti[k][m]["chi2_rid"] for k in sparc if tutti[k][m].get("ok")]))
                          for m in MODELLI if any(tutti[k][m].get("ok") for k in sparc)}
    conf = []
    for k in sparc:
        q = cat.li.get(k, {}).get("Burkert-Flat")
        r = tutti[k].get("Burkert")
        if q and r and r.get("ok"):
            conf.append((r["p"]["Yd"], q["Ydisk"], r["chi2_rid"], q["chi2"]))
    st["confronto_li"] = np.array(conf) if conf else None
    st["n"] = len(sparc)
    return st


def disegna_riassunto_tutte(fig, cat, tutti):
    fig.clf()
    st = statistiche_tutte(cat, tutti)
    axs = fig.subplots(1, 3)
    ax = axs[0]
    nomi = list(st["vincitori"])
    ax.bar(nomi, [st["vincitori"][m] for m in nomi], color=[COLORI[m] for m in nomi])
    ax.set_ylabel("number of SPARC galaxies")
    ax.set_title(f"Best model (lowest χ²ᵣ) for {st['n']} galaxies", fontsize="medium")
    for i, m in enumerate(nomi):
        ax.text(i, st["vincitori"][m], f"{st['vincitori'][m]}", ha="center", va="bottom")
    ax = axs[1]
    bins = np.logspace(-1.3, 2, 30)
    for m in MODELLI:
        v = [tutti[k][m]["chi2_rid"] for k in tutti if cat.galassie[k]["fonte"].startswith("SPARC") and tutti[k][m].get("ok")]
        ax.hist(v, bins=bins, histtype="step", lw=2, color=COLORI[m],
                label=f"{m} (median {np.median(v):.2f})" if v else m)
    ax.set_xscale("log")
    ax.axvline(1, color="k", lw=0.8, ls=":")
    ax.set_xlabel("reduced χ²")
    ax.set_ylabel("galaxies")
    ax.set_title("Goodness of fit", fontsize="medium")
    ax.legend(fontsize="x-small")
    ax = axs[2]
    c = st["confronto_li"]
    if c is not None and len(c):
        ax.scatter(c[:, 1], c[:, 0], s=12, color=COLORI["Burkert"])
        ax.plot([0.1, 2], [0.1, 2], "k:", lw=1)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("Υ_disc, Li et al. 2020 (Burkert)")
        ax.set_ylabel("Υ_disc, this program (Burkert)")
        ax.set_title(f"Check against Li et al. 2020 ({len(c)} galaxies)", fontsize="medium")
        ax.grid(alpha=0.25, which="both")
    else:
        ax.axis("off")
        ax.text(0.5, 0.5, "Li et al. 2020 table not available", ha="center", transform=ax.transAxes)


def salva_pdf_tutte(cat, tutti, cartella):
    import matplotlib
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure
    p = Path(cartella) / "rotation_curves_summary.pdf"
    with matplotlib.rc_context({"font.size": 9}):
        with PdfPages(p) as pdf:
            for disegna in (lambda f: disegna_insieme(f, cat), lambda f: disegna_riassunto_tutte(f, cat, tutti)):
                f = Figure(figsize=(16.5, 6.2), layout="constrained")
                disegna(f)
                f.text(0.995, 0.003, FIRMA, ha="right", va="bottom", fontsize=7, color="#6b7280")
                pdf.savefig(f)
            # una pagina con le curve delle galassie famose (4 × 4)
            famose = [k for k in ORDINE_FAMOSE if k in tutti][:16]
            f = Figure(figsize=(16.5, 11.7), layout="constrained")
            axs = f.subplots(4, 4).ravel()
            for ax, k in zip(axs, famose):
                g = cat.galassie[k]
                ax.errorbar(g["R"], g["V"], g["eV"], fmt="o", ms=2, color="k", elinewidth=0.6)
                Yd = 1.0 if g.get("massa_fissa") else tutti[k]["Burkert"]["p"]["Yd"] if tutti[k]["Burkert"].get("ok") else ML_DISCO
                ax.plot(g["R"], np.sqrt(np.maximum(v2_barioni(g, Yd), 0)), "-", color=COLORI["barioni"], lw=1.6)
                for m in ("NFW", "Burkert"):
                    if tutti[k][m].get("ok"):
                        ax.plot(g["R"], tutti[k][m]["V"], "-", color=COLORI[m], lw=1.2)
                ax.set_title(_titolo(g), fontsize=9)
                ax.set_ylim(0, None)
                ax.tick_params(labelsize=7)
            for ax in axs[len(famose):]:
                ax.axis("off")
            f.suptitle("Famous rotation curves – black: observed, grey: visible matter, red: NFW, blue: Burkert",
                       fontsize=11)
            f.text(0.995, 0.003, FIRMA, ha="right", va="bottom", fontsize=7, color="#6b7280")
            pdf.savefig(f)
            info = pdf.infodict()
            info["Title"] = "Galaxy rotation curves – summary"
            info["Author"] = "Edoardo Battistel"
    return p


# =========================================================================== autotest del motore
def galassia_finta(V200=150.0, c=8.0, Yd=0.6, rumore=3.0, seme=3):
    """Galassia simulata: disco esponenziale + gas + alone NFW noti."""
    rng = np.random.default_rng(seme)
    R = np.linspace(0.5, 30, 40)
    Rd = 3.0
    y = R / (2 * Rd)
    from scipy.special import i0, i1, k0, k1
    Md = 4e10
    vd2_1 = 2 * G * Md / Rd * y ** 2 * (i0(y) * k0(y) - i1(y) * k1(y))     # disco di Freeman per Υ = 1
    vdisk = np.sqrt(vd2_1)
    vgas = 30 * (1 - np.exp(-R / 8))
    v_vera = np.sqrt(vgas ** 2 + Yd * vd2_1 + v2_nfw(R, V200, c))
    e = np.full_like(R, rumore)
    V = v_vera + rng.normal(0, rumore, len(R))
    g = dict(chiave="FINTA", nome="Finta", fonte="SPARC (simulata)", tipo=5, D=10.0, inc=60, L36=40, MHI=5,
             Vflat=float(V[-5:].mean()), Q=1, ra=np.nan, dec=np.nan, Rdisk=Rd,
             righe=np.column_stack([R, V, e, vgas, vdisk, np.zeros_like(R)]).tolist())
    return prepara(g)


def autotest_motore(stampa=print, cat=None):
    """Prove dei calcoli. Restituisce (riuscite, totale, messaggi)."""
    prove = []

    def prova(nome, ok, dettaglio=""):
        prove.append(ok)
        stampa(f"  {'OK  ' if ok else 'NO  '} {nome}" + (f"  – {dettaglio}" if dettaglio else ""))
    # 1. massa di Burkert contro integrale numerico della densità
    from scipy.integrate import quad
    r0, rho = 4.0, 1e7
    m_num = quad(lambda r: 4 * math.pi * r ** 2 * rho / ((1 + r / r0) * (1 + (r / r0) ** 2)), 0, 10)[0]
    m_an = massa_burkert(10.0, r0, rho)
    prova("massa di Burkert (formula contro integrale)", abs(m_an / m_num - 1) < 1e-6, f"{m_an:.4e} / {m_num:.4e}")
    # 2. pISO contro integrale
    rc = 2.0
    m_num = quad(lambda r: 4 * math.pi * r ** 2 * rho / (1 + (r / rc) ** 2), 0, 10)[0]
    v_an = math.sqrt(v2_piso(np.array([10.0]), rc, math.log10(rho / 1e9))[0])
    prova("velocità pISO (formula contro integrale)", abs(v_an / math.sqrt(G * m_num / 10) - 1) < 1e-6)
    # 3. NFW: V(r200) = V200
    v = math.sqrt(v2_nfw(np.array([150 / (10 * H0)]), 150.0, 10.0)[0])
    prova("NFW: V(r200) = V200", abs(v - 150) < 1e-6, f"{v:.6f}")
    # 4. MOND: limite profondo g = √(gN a0) e limite newtoniano
    gN = A0_INT * 1e-4
    prova("MOND, regime profondo", abs(g_mond(np.array([gN]))[0] / math.sqrt(gN * A0_INT) - 1) < 0.02)
    prova("MOND, regime newtoniano", abs(g_mond(np.array([A0_INT * 1e3]))[0] / (A0_INT * 1e3) - 1) < 1e-6)
    # 5. Via Lattea: velocità delle stelle al Sole tra 170 e 200 km/s
    vd, vb = barioni_via_lattea([R_SOLE_EILERS])
    vs = math.hypot(vd[0], vb[0])
    prova("Via Lattea: stelle del modello I al Sole", 170 < vs < 200, f"{vs:.1f} km/s")
    # 5b. Einasto: massa contro integrale della densità
    rs, rhos, alfa = 5.0, 3e6, 0.3
    m_num = quad(lambda r: 4 * math.pi * r ** 2 * rhos * math.exp(-2 / alfa * ((r / rs) ** alfa - 1)), 0, 20)[0]
    prova("massa di Einasto (formula contro integrale)", abs(massa_einasto(20.0, rs, rhos, alfa) / m_num - 1) < 1e-6)
    # 5c. disco sottile numerico contro la formula esatta di Freeman (disco esponenziale)
    from scipy.special import i0, i1, k0, k1
    Md, Rd = 4e10, 3.0
    Rt = np.array([1.0, 3.0, 8.0, 20.0])
    y = Rt / (2 * Rd)
    esatta = 2 * G * Md / Rd * y ** 2 * (i0(y) * k0(y) - i1(y) * k1(y))
    num = v2_disco_sottile(Rt, lambda r: Md / (2 * math.pi * Rd ** 2) * np.exp(-r / Rd))
    prova("disco sottile numerico contro Freeman", float(np.max(np.abs(num / esatta - 1))) < 1e-3,
          f"scarto massimo {np.max(np.abs(num / esatta - 1)):.1e}")
    prova("gas della Via Lattea (McMillan 2017) tra 0,8 e 1,6e10 Msun", 0.8e10 < MW_MASSA_GAS < 1.6e10,
          f"{MW_MASSA_GAS:.2e} Msun")
    # 6. galassia simulata: l'adattamento NFW ritrova i parametri
    gf = galassia_finta()
    r = adatta(gf, "NFW", "libero")
    ok = r["ok"] and abs(r["p"]["V200"] / 150 - 1) < 0.15 and abs(r["p"]["Yd"] / 0.6 - 1) < 0.25 and r["chi2_rid"] < 2
    prova("galassia simulata: NFW ritrovato", ok,
          f"V200 {r['p']['V200']:.1f} (150), c {r['p']['c']:.1f} (8), Υ {r['p']['Yd']:.2f} (0,6), χ²ᵣ {r['chi2_rid']:.2f}")
    r2 = adatta(gf, "NFW", "fisso", 0.6)
    prova("galassia simulata: NFW con Υ fisso", r2["ok"] and r2["chi2_rid"] < 2, f"χ²ᵣ {r2['chi2_rid']:.2f}")
    rm = adatta(gf, "MOND", "libero")
    prova("galassia simulata: MOND gira", rm["ok"], f"χ²ᵣ {rm['chi2_rid']:.2f}")
    # 7. dati veri (se ci sono)
    if cat is not None:
        prova("catalogo SPARC: 175 galassie", len(cat.sparc()) >= 170, f"{len(cat.sparc())}")
        g = cat.galassie.get("NGC3198")
        if g is not None:
            prova("NGC 3198: 43 punti fino a 44 kpc", len(g["R"]) == 43 and abs(g["Rmax"] - 44.08) < 0.1)
            ris = adatta_tutti(g, "libero")
            b = ris["Burkert"]
            n = ris["NFW"]
            prova("NGC 3198 Burkert: Υ tra 0,4 e 0,9 e χ²ᵣ < 3", b["ok"] and 0.4 < b["p"]["Yd"] < 0.9 and b["chi2_rid"] < 3,
                  f"Υ {b['p']['Yd']:.2f} (Li+2020 0,66), χ²ᵣ {b['chi2_rid']:.2f} (Li 1,47)")
            prova("NGC 3198 NFW: Υ tra 0,3 e 0,7 e χ²ᵣ < 3", n["ok"] and 0.3 < n["p"]["Yd"] < 0.7 and n["chi2_rid"] < 3,
                  f"Υ {n['p']['Yd']:.2f} (Li 0,47), V200 {n['p']['V200']:.0f} (Li 110), c {n['p']['c']:.1f} (Li 10,4), "
                  f"χ²ᵣ {n['chi2_rid']:.2f} (Li 1,46)")
            e = ris["Einasto"]
            prova("NGC 3198 Einasto come Li+2020 (rs 13,6 kpc, α 0,36)", e["ok"] and abs(e["p"]["r0"] / 13.59 - 1) < 0.2
                  and abs(e["p"]["alfa"] - 0.36) < 0.08, f"rs {e['p']['r0']:.2f}, α {e['p']['alfa']:.2f}, χ²ᵣ {e['chi2_rid']:.2f}")
            bl = adatta(g, "Burkert", "libero", libere_Di=True)
            prova("NGC 3198 Burkert con D e i libere come Li+2020 (D 14,69, i 73,8, Υ 0,66)",
                  bl["ok"] and abs(bl["p"]["D_fit"] - 14.69) < 0.8 and abs(bl["p"]["i_fit"] - 73.8) < 2
                  and abs(bl["p"]["Yd"] - 0.66) < 0.08,
                  f"D {bl['p']['D_fit']:.2f} Mpc, i {bl['p']['i_fit']:.1f}°, Υ {bl['p']['Yd']:.2f}, χ²ᵣ {bl['chi2_rid']:.2f}")
            if g.get("altre"):
                prova("NGC 3198: seconda curva da THINGS", True, g["altre"][0]["fonte"])
        nr = sum(1 for x in cat.galassie.values() if x.get("survey"))
        if nr:
            prova("raccolta Zenodo: più di 200 galassie nuove", nr > 200, f"{nr} (THINGS, LITTLE THINGS, WALLABY)")
        g = cat.galassie.get("DDO154")
        if g is not None:
            fd = frazione_oscura(g)[-1]
            prova("DDO 154 dominata dalla materia oscura (> 85 % all'ultimo raggio)", fd > 0.85, f"{100 * fd:.0f} %")
        tf = retta_tully_fisher(dati_tully_fisher(cat))
        prova("Tully-Fisher: pendenza tra 3,3 e 4,3", tf is not None and 3.3 < tf[0] < 4.3,
              f"{tf[0]:.2f}, dispersione {tf[2]:.2f} dex" if tf else "")
        gb, go, _ = dati_accelerazioni(cat)
        if len(gb):
            res = np.log10(go) - np.log10(g_mond(gb / KMS2_KPC_IN_MS2) * KMS2_KPC_IN_MS2)
            prova("relazione delle accelerazioni: dispersione < 0,2 dex", float(np.std(res)) < 0.2,
                  f"{len(gb)} punti, media {np.mean(res):+.3f}, dispersione {np.std(res):.3f} dex")
        if "M33" in cat.galassie:
            g = cat.galassie["M33"]
            prova("M 33: curva fino a 20–25 kpc", 20 < g["Rmax"] < 25, f"{len(g['R'])} punti, Rmax {g['Rmax']:.1f} kpc")
        vl = cat.galassie["VIA_LATTEA"]
        r = adatta(vl, "NFW")
        prova("Via Lattea: NFW sui dati (χ²ᵣ < 3)", r["ok"] and r["chi2_rid"] < 3,
              f"V200 {r['p']['V200']:.0f} km/s, c {r['p']['c']:.1f}, M200 {r['M200']:.2e} Msun (Eilers: Mvir 7,25e11)")
    return sum(prove), len(prove)
