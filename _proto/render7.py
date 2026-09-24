"""Rendus Shape v4 (2026-09-25) sur ta prod 30–50 s, bande 60 Hz Q 1 en mode Mid ; abaissés de 9 dB comme le reste de renders/tame_shape_30s/."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_shape import shape_band
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
seg = x[int(30 * fs): int(50 * fs)]
d = os.path.join("renders", "tame_shape_30s"); os.makedirs(d, exist_ok=True)
pad = 10 ** (-9 / 20)
M = seg.mean(axis=1)
kw = dict(shape="bell", f0=60.0, q=1.0)
def mid(f):
    dd = f(M) - M
    return seg + np.stack([dd, dd], axis=1)
w = lambda fn, y: wavfile.write(os.path.join(d, fn), int(fs), (y * pad).astype(np.float32))
w("05_shape_KICK_NET_trans+6_sust-6.wav", mid(lambda z: shape_band(z, fs, cible="transitoires", gain_db=6.0, **kw) + shape_band(z, fs, cible="sustain", gain_db=-6.0, **kw) - z))
w("06_shape_sustain_-6.wav", mid(lambda z: shape_band(z, fs, cible="sustain", gain_db=-6.0, **kw)))
w("07_shape_transitoires_+6.wav", mid(lambda z: shape_band(z, fs, cible="transitoires", gain_db=6.0, **kw)))
w("08_shape_transitoires_+6_duree200ms.wav", mid(lambda z: shape_band(z, fs, cible="transitoires", gain_db=6.0, time_ms=200.0, **kw)))
print("ok")
