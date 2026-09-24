"""La recette tient-elle sur tout le spectre ? (2026-09-24) — Iron, +5 dB, cloche Q 2, sortie 3 sections, tranche 30–50 s.

Zone = octave centrée sur f0. Sources : Auto (f0/3), Bande (f0), Fenêtre (passe-haut f0/3 + passe-bas 1,5·f0).
Métriques : % de l'ajout dans la zone, gain net dans la zone, corrélation ajout/original, fidélité aux transitoires DANS LA ZONE,
écart de niveau global (RMS).
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import butter, sosfilt
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
m = x.mean(axis=1)[int(30 * fs): int(50 * fs)]


def fronts(z, lo, hi):
    bp = butter(4, [lo, hi], btype="band", fs=fs, output="sos")
    env = sosfilt(butter(2, max(20.0, lo / 8), btype="low", fs=fs, output="sos"), np.abs(sosfilt(bp, z)))
    return np.maximum(np.diff(env), 0.0)


def transit(dry, delta, lo, hi):
    return float(np.corrcoef(fronts(dry, lo, hi), fronts(delta, lo, hi))[0, 1])


print(f"{'f0':>6s}{'source':>9s}{'net':>6s}{'% zone':>8s}{'corr.':>7s}{'transit.':>9s}{'Δ RMS':>8s}")
for f0 in (60, 120, 250, 500, 1000, 2000, 4000, 8000, 12000):
    lo, hi = f0 / np.sqrt(2), min(f0 * np.sqrt(2), 0.45 * fs)
    for src in ("auto", "band", "window"):
        kw = dict(f0=float(f0), q=2.0, gain_db=5.0, drive=1.5, oversample=2, norm="zone", mode="iron", source=src, out_sections=3)
        y = excite_band(m, fs, **kw)
        net, add, rho = zone_stats(m, y, fs, lo, hi)
        d = 10 * np.log10(np.sum(y ** 2) / np.sum(m ** 2))
        print(f"{f0:6d}{src:>9s}{net:6.1f}{localisation(m, y, fs, lo, hi):7.0f}%{rho:7.2f}{transit(m, y - m, lo, hi):9.2f}{d:+8.2f}")
    print()
