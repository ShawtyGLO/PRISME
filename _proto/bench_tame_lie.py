"""Détection LIÉE (milieu) contre INDÉPENDANTE (L et R séparés) : écart sur la prod et cas d'une résonance placée à gauche seulement."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, welch
from render import load
from bench_leak import SRC
from prisme_tame import tame_band, tame_stereo

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = np.ascontiguousarray(x[int(30 * fs): int(36 * fs)])
CFG = [("bell", 3000.0, 0.7, -9.0, 0.5), ("bell", 632.0, 1.2, -4.0, 1.0), ("highshelf", 9600.0, 0.71, -6.0, 0.5)]


def rms_db(v): return 20 * np.log10(np.sqrt(np.mean(v ** 2)) + 1e-30)


print("PROD (6 s, stéréo) : delta lié vs indépendant, tous deux avec gain interpolé")
for sh, f0, q, g, wd in CFG:
    kw = dict(shape=sh, f0=f0, q=q, gain_db=g, width=wd)
    ind = np.stack([tame_band(x[:, c], fs, interp=True, **kw) for c in (0, 1)], axis=1)
    lie = tame_stereo(x, fs, interp=True, **kw)
    dI, dL = ind - x, lie - x
    err = rms_db(dL - dI) - rms_db(dI)
    M = lambda d: (d[:, 0] + d[:, 1]) / 2
    S = lambda d: (d[:, 0] - d[:, 1]) / 2
    print(f"  {sh:10s} {f0:6.0f} Hz {g:+.0f} dB : écart delta lié/indép {err:6.1f} dB ; Side/Mid du delta : indép {rms_db(S(dI)) - rms_db(M(dI)):+.1f} dB, lié {rms_db(S(dL)) - rms_db(M(dL)):+.1f} dB ; niveau delta lié − indép {rms_db(dL) - rms_db(dI):+.2f} dB")

print("\nCAS DIFFICILE : bruit rose stéréo identique + résonance 3,1 kHz (+15 dB) à GAUCHE seulement, cloche 3 kHz −9 dB")
rng = np.random.default_rng(3); n = int(fs * 5)
b, a = [1, -1.7, 0.72], None
w = rng.standard_normal(n)
p = lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400], w) * 0.3
t = np.arange(n) / fs
res = 10 ** (-24 / 20) * np.sin(2 * np.pi * 3100 * t)
L, R = p + res * 1.0, p.copy()
X = np.stack([L, R], axis=1)
kw = dict(shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=0.5)
ind = np.stack([tame_band(X[:, c], fs, interp=True, **kw) for c in (0, 1)], axis=1)
lie = tame_stereo(X, fs, interp=True, **kw)


def bande(v, f0=3100.0):
    fr, P = welch(v[int(1.5 * fs):], fs, nperseg=16384)
    s = (fr > f0 * 0.97) & (fr < f0 * 1.03)
    return 10 * np.log10(P[s].sum())


for nom, y in (("indépendant", ind), ("lié (milieu)", lie)):
    print(f"  {nom:14s} : L à 3,1 kHz {bande(y[:, 0]) - bande(X[:, 0]):+.1f} dB ; R à 3,1 kHz {bande(y[:, 1]) - bande(X[:, 1]):+.1f} dB (R ne portait pas la résonance)")
