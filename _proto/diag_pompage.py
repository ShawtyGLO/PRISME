"""Régularité de la détection : variation du gain appliqué dans le temps et ÉCART ENTRE L ET R (instabilité d'image), par type de bande, sur la prod (stéréo)."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_lift import lift_band
from prisme_shape import shape_band
from prisme_tame import tame_band
import prisme_exciter_v2_stream as V2
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, X = load(SRC)
X = np.ascontiguousarray(X[int(30 * fs): int(45 * fs)])
L, R = X[:, 0], X[:, 1]
W = int(0.1 * fs)


def fen(v):                                    # moyenne par fenêtres de 100 ms
    n = len(v) // W
    return v[: n * W].reshape(n, W).mean(axis=1)


def rapport(nom, gL, gR):
    a, b = fen(gL[int(fs):]), fen(gR[int(fs):])
    print(f"{nom:36s} gain moyen {np.mean(a):6.2f} dB | variation (écart-type sur 100 ms) {np.std(a):5.2f} dB | actif < 0,25 dB : {100 * np.mean(np.abs(a) < 0.25):4.0f} % du temps | écart L−R (RMS) {np.sqrt(np.mean((a - b) ** 2)):5.2f} dB")


db = lambda g: 20 * np.log10(np.maximum(g, 1e-9))
_, dL = lift_band(L, fs, "bell", 3000.0, 0.7, 6.0, 90.0, 150.0, diag=True)
_, dR = lift_band(R, fs, "bell", 3000.0, 0.7, 6.0, 90.0, 150.0, diag=True)
rapport("Lift cloche 3 k +6 (Amount 90)", db(dL["g"]), db(dR["g"]))
_, sL = shape_band(L, fs, "transitoires", "bell", 3000.0, 1.0, 6.0, diag=True)
_, sR = shape_band(R, fs, "transitoires", "bell", 3000.0, 1.0, 6.0, diag=True)
rapport("Shape transitoires cloche 3 k +6", db(sL["g"]), db(sR["g"]))
_, tL = tame_band(L, fs, "bell", 3000.0, 0.7, -9.0, 0.5, diag=True)
_, tR = tame_band(R, fs, "bell", 3000.0, 0.7, -9.0, 0.5, diag=True)
rapport("Tame cloche 3 k −9 (réduction max/bande)", -tL["red_full"].max(axis=0), -tR["red_full"].max(axis=0))

# Exciter v2 : porte (0 … 1) et niveau du wet par fenêtre de 100 ms, sur le milieu
mid = 0.5 * (L + R)
class Spy(V2.ExciterV2Stream):
    pass
import scipy.signal as ss
ex = V2.ExciterV2Stream(fs, shape="bell", f0=3000.0, q=0.71, gain_db=6.0, profil="mordant_chaud")
n = len(mid)
s = mid
for i in range(len(ex.z_src)):
    s, _ = ss.lfilter(*ex.zf, s, zi=np.zeros(2)) if False else (ss.lfilter(*ex.zf, s), None)
a = np.abs(s)
S = ss.lfilter([1 - ex.cS], [1, -ex.cS], a) * (np.pi / 2) + 1e-7
e = ss.lfilter([1 - ex.cE], [1, -ex.cE], a) * (np.pi / 2)
rel = 20 * np.log10((e + 1e-12) / S)
v = np.clip((rel - 3.0) / 6.0, 0, 1)
porte = v * v * (3 - 2 * v)
wet = V2.exciter_v2_stream(mid, fs, shape="bell", f0=3000.0, q=0.71, gain_db=6.0, profil="mordant_chaud")
pw = fen(porte[int(fs):]); lw = 10 * np.log10(fen(wet[int(fs):] ** 2) + 1e-20)
print(f"\nExciter v2 : porte ouverte en moyenne {100 * np.mean(pw):.0f} % ; part du temps où la porte est presque fermée (< 5 % en moyenne sur 100 ms) : {100 * np.mean(pw < 0.05):.0f} %")
print(f"            niveau du wet par fenêtre de 100 ms : écart-type {np.std(lw[lw > -120]):.1f} dB ; plage (P10 … P90) {np.percentile(lw[lw > -120], 10):.0f} … {np.percentile(lw[lw > -120], 90):.0f} dBFS")
