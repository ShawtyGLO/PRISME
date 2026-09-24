"""Compromis précision / débordement spectral du Shape selon la vitesse d'attaque du gain (en périodes de la fréquence centrale)."""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import butter, sosfilt
import tests_shape as T
from prisme_shape import shape_band
sys.stdout.reconfigure(encoding="utf-8")
fs = 48000.0
def debordement(x, y, f0):
    d = y - x
    lo = sosfilt(butter(4, [f0 / 2, f0 * 2], btype="band", fs=fs, output="sos"), d)
    ein = np.sum(lo ** 2); eout = np.sum(d ** 2) - ein
    return 10 * np.log10(max(eout, 1e-30) / ein)
print(f"{'att (périodes)':>15s}" + "".join(f"{f'{int(f0)} Hz : préc./déborde':>28s}" for f0 in (60.0, 250.0, 1000.0, 4000.0)))
for att in (0.3, 0.45, 0.8, 1.3, 2.0):
    row = f"{att:15.2f}"
    for f0 in (60.0, 250.0, 1000.0, 4000.0):
        x = T.salves(f0, fs)
        y = shape_band(x, fs, cible="transitoires", f0=f0, gain_db=12.0, att_periods=att)
        a, s = T.mesures(x, y, f0, fs)
        row += f"{a:12.1f} dB /{debordement(x, y, f0):8.1f} dB "
    print(row)
