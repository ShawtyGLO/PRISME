"""Filtres de bande sur le DELTA : écart entre l'effet réel et l'effet « idéal » affiché (gain de la bande × |H| du filtre), selon la pente.
Bande Lift/EQ statique simulée par une cloche RBJ (delta = cloche(x) − x) ; bruit rose ; coupe-bas et coupe-haut Butterworth 12 / 24 dB/oct."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, freqz, butter, sosfreqz
from prisme_dsp import rbj_peaking
sys.stdout.reconfigure(encoding="utf-8")
fs = 48000
f = np.geomspace(30, 20000, 600)
w = 2 * np.pi * f / fs
for g in (+6.0, -9.0):
    b, a = rbj_peaking(fs, 1000.0, g, 0.71)
    Hb = freqz(b, a, worN=w)[1]
    D = Hb - 1.0                                              # delta de la bande
    for kind, fc in (("coupe-bas", 1000.0), ("coupe-haut", 1000.0), ("coupe-bas", 500.0)):
        for ordre, pente in ((2, 12), (4, 24)):
            sos = butter(ordre, fc, btype="highpass" if kind == "coupe-bas" else "lowpass", fs=fs, output="sos")
            Hf = sosfreqz(sos, worN=w)[1]
            reel = 20 * np.log10(np.abs(1 + D * Hf))
            ideal = 20 * np.log10(np.abs(1 + (np.abs(Hb) - 1) * np.abs(Hf)))   # ce que l'interface affiche
            print(f"  bande {g:+.0f} dB à 1 kHz, {kind} {fc:.0f} Hz {pente} dB/oct : écart réel − affiché max {np.max(np.abs(reel - ideal)):.2f} dB ; effet réel extrême {reel[np.argmax(np.abs(reel))]:+.2f} dB")
