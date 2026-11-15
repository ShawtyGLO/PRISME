"""Liaison partielle (par activité) : stabilité d'image (écart L−R du gain) et cas d'une résonance à gauche seulement."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, welch
from prisme_tame import Tame
from prisme_lift import Lift
from prisme_shape import Shape
from prisme_band import zone_filter
from prisme_link import tame_pair, lift_pair, shape_pair
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, X = load(SRC)
X = np.ascontiguousarray(X[int(30 * fs): int(42 * fs)])
L, R = X[:, 0], X[:, 1]
W = int(0.1 * fs)
fen = lambda v: v[: len(v) // W * W].reshape(-1, W).mean(axis=1)
db = lambda g: 20 * np.log10(np.maximum(g, 1e-9))


def run(paire, mk, lam, L, R, block=8192):
    a, b = mk(), mk()
    yl, yr = np.empty(len(L)), np.empty(len(L))
    for i in range(0, len(L), block):
        yl[i:i + block], yr[i:i + block] = paire(a, b, L[i:i + block], R[i:i + block], lam)
    return yl, yr


def ecart_gain(yl, yr):
    # gain apparent de la bande : rapport d'énergie sortie/entrée sur 100 ms
    zb = zone_filter("bell", fs, 3000.0, 1.0)
    bp = lambda v: lfilter(*zb, v)[int(fs):]
    gl = 10 * np.log10(fen(bp(yl) ** 2) / (fen(bp(L) ** 2) + 1e-30) + 1e-30)
    gr = 10 * np.log10(fen(bp(yr) ** 2) / (fen(bp(R) ** 2) + 1e-30) + 1e-30)
    return np.sqrt(np.mean((gl - gr) ** 2))


print("Écart L−R du GAIN APPARENT (dB RMS, fenêtres 100 ms) selon la liaison λ")
for nom, paire, mk in (("Tame cloche 3 k −9", tame_pair, lambda: Tame(fs, "bell", 3000.0, 0.7, -9.0, 0.5)),
                       ("Lift cloche 3 k +6 (Amount 90)", lift_pair, lambda: Lift(fs, "bell", 3000.0, 0.7, 6.0, 90.0, 150.0)),
                       ("Shape transitoires 3 k +6", shape_pair, lambda: Shape(fs, "transitoires", "bell", 3000.0, 1.0, 6.0, None, None, 0.85))):
    print(f"  {nom:32s}", "  ".join(f"λ={lam:.1f}: {ecart_gain(*run(paire, mk, lam, L, R)):5.2f}" for lam in (0.0, 0.5, 1.0)))

rng = np.random.default_rng(3)
n = int(fs * 5)
p = lfilter([0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400], rng.standard_normal(n)) * 0.3
t = np.arange(n) / fs
Lr, Rr = p + 10 ** (-24 / 20) * np.sin(2 * np.pi * 3100 * t), p.copy()


def bande(v):
    fr, P = welch(v[int(1.5 * fs):], fs, nperseg=16384)
    s = (fr > 3100 * 0.97) & (fr < 3100 * 1.03)
    return 10 * np.log10(P[s].sum())


print("Résonance 3,1 kHz à GAUCHE seulement (Tame −9 dB) : effet sur L (visé) / sur R (parasite)")
for lam in (0.0, 0.25, 0.5, 0.75, 1.0):
    yl, yr = run(tame_pair, lambda: Tame(fs, "bell", 3000.0, 0.7, -9.0, 0.5), lam, Lr, Rr)
    print(f"  λ = {lam:.2f} : L {bande(yl) - bande(Lr):+5.1f} dB ; R {bande(yr) - bande(Rr):+5.1f} dB")
