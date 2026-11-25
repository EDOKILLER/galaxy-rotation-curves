#!/usr/bin/env bash
# =============================================================================
# Curve di rotazione 1.0 – crea l'eseguibile per Ubuntu, lo prova e lo installa (menu + Scrivania)
# © 2026 Edoardo Battistel
#
# Uso:  cd ~/Claude/Astropy/programma_curve_rotazione/versione_1.0
#       bash crea_eseguibile_ubuntu.sh 2>&1 | tee ~/Claude/Astropy/curve_rotazione_compila.txt
# Usa il venv ~/Claude/Astropy/venv_compila (PyInstaller), che vede numpy, scipy,
# matplotlib e Pillow di sistema. Astropy non serve.
# =============================================================================
set -e
cd "$(dirname "$(readlink -f "$0")")"
PY="$HOME/Claude/Astropy/venv_compila/bin/python"

for f in curve_rotazione.py motore_curve.py finestra_comune.py curve_rotazione.png; do
    [ -f "$f" ] || { echo "ERRORE: manca $f in questa cartella ($(pwd))."; exit 1; }
done
[ -x "$PY" ] || { echo "ERRORE: non trovo $PY"; exit 1; }
grep -q 'VERSIONE_FINESTRA = "1.1"' finestra_comune.py || { echo "ERRORE: finestra_comune.py non è la 1.1"; exit 1; }

echo "=== 1/4  Autotest dallo script (apre la finestra; con i dati circa 1–2 minuti) ==="
if ! "$PY" curve_rotazione.py --autotest; then
    echo "L'autotest dello script è FALLITO: mandami il testo qui sopra."
    exit 1
fi

META=""
for m in numpy scipy pillow matplotlib packaging; do
    if "$PY" -c "import importlib.metadata as im, sys; im.version(sys.argv[1])" "$m" 2>/dev/null; then
        META="$META --copy-metadata $m"
    fi
done

echo "=== 2/4  Creazione dell'eseguibile (qualche minuto) ==="
"$PY" -m PyInstaller --noconfirm --clean --onefile --windowed \
    --name CurveRotazione \
    --add-data "curve_rotazione.png:." \
    $META \
    --hidden-import motore_curve \
    --hidden-import finestra_comune \
    --hidden-import matplotlib.backends.backend_tkagg \
    --hidden-import matplotlib.backends.backend_pdf \
    --hidden-import matplotlib.backends.backend_agg \
    --hidden-import PIL._tkinter_finder \
    --hidden-import scipy.optimize \
    --hidden-import scipy.special \
    --hidden-import scipy.integrate \
    --exclude-module astropy --exclude-module sklearn --exclude-module IPython --exclude-module pandas \
    --exclude-module healpy --exclude-module h5py --exclude-module lal \
    curve_rotazione.py

echo "=== 3/4  Verifica dell'eseguibile (autotest) ==="
if ! ./dist/CurveRotazione --autotest > autotest.txt 2>&1; then
    cat autotest.txt
    echo
    echo "L'autotest dell'eseguibile è FALLITO: i dettagli sono in $(pwd)/autotest.txt"
    echo "L'eseguibile non è stato installato."
    rm -rf build CurveRotazione.spec
    exit 1
fi
cat autotest.txt

echo "=== 4/4  Installazione nella home e icona nel menu ==="
DEST="$HOME/.local/bin"
ICONE="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$DEST" "$HOME/.local/share/applications" "$ICONE"
cp curve_rotazione.png "$ICONE/curve_rotazione.png"
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
cp dist/CurveRotazione "$DEST/CurveRotazione"
chmod +x "$DEST/CurveRotazione"

# tk.Tk(className="CurveRotazione") -> classe della finestra "Curverotazione" (solo l'iniziale maiuscola)
SCRIVANIA="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Scrivania")"
cat > "$HOME/.local/share/applications/curve_rotazione.desktop" <<FINE
[Desktop Entry]
Type=Application
Name=Curve di rotazione
Comment=Curve di rotazione delle galassie: materia visibile e materia oscura (SPARC, Via Lattea SALSA) – © 2026 Edoardo Battistel
Exec=$DEST/CurveRotazione
Icon=$ICONE/curve_rotazione.png
StartupWMClass=Curverotazione
Terminal=false
Categories=Science;Astronomy;Education;
FINE
chmod +x "$HOME/.local/share/applications/curve_rotazione.desktop"
update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
if [ -d "$SCRIVANIA" ]; then
    cp "$HOME/.local/share/applications/curve_rotazione.desktop" "$SCRIVANIA/"
    chmod +x "$SCRIVANIA/curve_rotazione.desktop"
    gio set "$SCRIVANIA/curve_rotazione.desktop" metadata::trusted true 2>/dev/null || true
fi

rm -rf build CurveRotazione.spec
echo
echo "FATTO."
echo "  Eseguibile:  $DEST/CurveRotazione   (copia anche in $(pwd)/dist/)"
echo "  Avvio:       'Curve di rotazione' nel menu o doppio clic sull'icona sulla Scrivania"
echo "               (la prima volta: tasto destro -> 'Consenti avvio')."
echo "  Controllo dell'icona nella barra: xwininfo -root -tree | grep -i curverotazione"
