"""Écart des variantes allégées du Tame par rapport à la v3 (24 bandes/oct, gain plein débit) sur la prod : niveau du delta et erreur relative du delta."""
import os, sys, time
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from render import load
from bench_leak import SRC
from prisme_tame import tame_band

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = np.ascontiguousarray(x[int(30 * fs): int(36 * fs), 0])
CFG = [("bell", 3000.0, 0.7, -9.0, 0.5), ("bell", 632.0, 1.2, -4.0, 1.0), ("bell", 250.0, 0.71, 6.0, 0.2), ("highshelf", 9600.0, 0.71, -6.0, 0.5), ("lowshelf", 120.0, 0.71, -6.0, 0.8)]
VAR = {"A ra24 interp": dict(ra=24, interp=True), "B ra12": dict(ra=12, interp=False), "C ra12 interp": dict(ra=12, interp=True), "D ra16 interp": dict(ra=16, interp=True)}
print(f"{'config':32s} " + " | ".join(f"{k:>22s}" for k in VAR))
tot = {k: [] for k in VAR}
for sh, f0, q, g, wd in CFG:
    kw = dict(shape=sh, f0=f0, q=q, gain_db=g, width=wd)
    ref = tame_band(x, fs, ra=24, interp=False, **kw) - x
    row = []
    for k, v in VAR.items():
        d = tame_band(x, fs, **v, **kw) - x
        err = 20 * np.log10(np.sqrt(np.mean((d - ref) ** 2)) / np.sqrt(np.mean(ref ** 2)) + 1e-30)
        lev = 20 * np.log10(np.sqrt(np.mean(d ** 2)) / np.sqrt(np.mean(ref ** 2)) + 1e-30)
        row.append(f"err {err:6.1f} dB niv {lev:+.2f}")
        tot[k].append(err)
    print(f"{sh:10s} {f0:6.0f} Hz {g:+.0f} dB w{wd:.1f}   " + " | ".join(f"{r:>22s}" for r in row))
print("\ndelta de référence : niveau relatif au signal :", 20 * np.log10(np.sqrt(np.mean(ref ** 2)) / np.sqrt(np.mean(x ** 2))), "dB (dernière config)")
