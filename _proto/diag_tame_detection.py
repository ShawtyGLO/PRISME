"""Diagnostic de la détection du Tame (retours de llg53, 2026-10-01) :
 A) plus la zone contient de résonances, moins il réagit ?  → N résonances (+12 dB) dans une cloche large, réduction moyenne sur chacune
 B) dans le grave, réduction non constante ?                 → résonance FIXE à 80 Hz sous une ligne de basse qui change de note, réduction dans le temps"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, welch
import importlib
tame_band = importlib.import_module(os.environ.get("TAME_MODULE", "prisme_tame")).tame_band
sys.stdout.reconfigure(encoding="utf-8")
DET = os.environ.get("DET", "v4")
print("détection :", DET)
fs = 48000
rng = np.random.default_rng(2)


def rose(n):
    return lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400], rng.standard_normal(n))


def niveau(v, f):
    fr, P = welch(v, fs, nperseg=16384)
    s = (fr > f * 0.98) & (fr < f * 1.02)
    return 10 * np.log10(P[s].sum())


print("A) N résonances +12 dB dans une cloche 800 Hz, Q 0,5, gain −9 dB, largeur 0,5 : réduction moyenne sur les résonances")
n = int(fs * 6)
t = np.arange(n) / fs
base = rose(n) * 0.05
for N in (1, 2, 4, 8):
    fr = np.geomspace(300, 2200, N) if N > 1 else np.array([800.0])
    x = base.copy()
    for f in fr:
        x += 0.05 * 10 ** (12 / 20) * 0.05 * np.sin(2 * np.pi * f * t + rng.uniform(0, 6))
    y, dg = tame_band(x, fs, shape="bell", f0=800.0, q=0.5, gain_db=-9.0, width=0.5, detection=DET, diag=True)
    red = [niveau(y[fs:], f) - niveau(x[fs:], f) for f in fr]
    R = dg["red_full"][:, fs:].mean(axis=1)
    det = [-float(R[np.argmin(np.abs(dg["f"] - f))]) / max(float(dg["w"][np.argmin(np.abs(dg["f"] - f))]), 1e-3) for f in fr]
    print(f"  N = {N} : effet mesuré moyen {np.mean(red):+.1f} dB (min {max(red):+.1f}) ; détection rapportée au poids de zone : moyenne {np.mean(det):+.1f}, min {max(det):+.1f}")

print("\nB) résonance fixe 80 Hz (+12 dB) + basse qui change de note toutes les 0,5 s ; Tame shelf grave 150 Hz −9 dB")
notes = [55.0, 73.4, 61.7, 82.4, 49.0, 65.4, 98.0, 55.0, 73.4, 61.7, 82.4, 49.0]
x = rose(n) * 0.02
for k, f in enumerate(notes):
    i = int(k * 0.5 * fs); j = int((k + 1) * 0.5 * fs)
    tt = np.arange(j - i) / fs
    x[i:j] += 0.3 * np.sin(2 * np.pi * f * tt) * np.exp(-tt / 0.4)
x += 0.02 * 10 ** (12 / 20) * 0.1 * np.sin(2 * np.pi * 80.0 * t)
y, d = tame_band(x, fs, shape="lowshelf", f0=150.0, q=0.71, gain_db=-9.0, width=0.5, diag=True, detection=DET)
k80 = np.argmin(np.abs(d["f"] - 80.0))
r = -d["red_full"][k80][fs:]
w = int(0.25 * fs)
seg = r[: len(r) // w * w].reshape(-1, w).mean(axis=1)
print(f"  réduction appliquée à 80 Hz par tranche de 250 ms : {np.round(seg, 1)}")
print(f"  moyenne {seg.mean():+.1f} dB, écart-type {seg.std():.1f} dB, plage {seg.min():+.1f} … {seg.max():+.1f}")
