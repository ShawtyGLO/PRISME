"""Rendus Tame v3 (voisins) contre v4 (courbe de référence) sur la prod, tranche 30–48 s."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_tame import tame_band
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, X = load(SRC)
X = X[int(30 * fs): int(48 * fs)]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "tame_v4")
peak = np.max(np.abs(X))


def ecrit(nom, y):
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


def tame(det, **kw):
    return np.stack([tame_band(np.ascontiguousarray(X[:, c]), fs, detection=det, **kw) for c in (0, 1)], axis=1)


ecrit("00_sec", X)
for tag, kw in (("zone_large_800Hz_-9", dict(shape="bell", f0=800.0, q=0.5, gain_db=-9.0, width=0.5)),
                ("graves_shelf150_-9", dict(shape="lowshelf", f0=150.0, q=0.71, gain_db=-9.0, width=0.5))):
    for det in ("v3", "v4"):
        ecrit(f"{tag}_{det}", tame(det, **kw))
for wd, nom in ((1.0, "fine"), (0.0, "large")):
    ecrit(f"largeur_{nom}_3kHz_-9_v4", tame("v4", shape="bell", f0=3000.0, q=0.71, gain_db=-9.0, width=wd))
print(sorted(os.listdir(out)))
