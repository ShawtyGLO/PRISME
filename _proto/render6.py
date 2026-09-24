"""Rendus n°4 (2026-09-24) : Tame et Shape sur ta prod (30–50 s). Tous abaissés de 9 dB, même quantité pour tous.

  Tame  (cloche 3 kHz, Q 0,7) : 01 fin −9 dB · 02 moyen −9 dB · 03 large −9 dB · 04 fin +6 dB (RÉHAUSSE les résonances)
  Shape (cloche 60 Hz, Q 1, mode Mid) : 05 kick net = transitoires +6 dB & sustain −6 dB · 06 sustain −6 dB seul · 07 transitoires +6 dB seul
"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_tame import tame_band
from prisme_shape import shape_band
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
seg = x[int(30 * fs): int(50 * fs)]
out_dir = os.path.join("renders", "tame_shape_30s")
os.makedirs(out_dir, exist_ok=True)
pad = 10 ** (-9 / 20)
w = lambda fn, y: wavfile.write(os.path.join(out_dir, fn), int(fs), (y * pad).astype(np.float32))
w("00_dry.wav", seg)
tame = lambda z, **k: np.stack([tame_band(z[:, c], fs, shape="bell", f0=3000.0, q=0.7, **k) for c in range(2)], axis=1)
for fn, k in (("01_tame_FIN_-9dB", dict(gain_db=-9.0, width=1.0)), ("02_tame_MOYEN_-9dB", dict(gain_db=-9.0, width=0.5)),
              ("03_tame_LARGE_-9dB", dict(gain_db=-9.0, width=0.0)), ("04_tame_FIN_+6dB_REHAUSSE", dict(gain_db=6.0, width=1.0))):
    y = tame(seg, **k); w(fn + ".wav", y)
    print(f"{fn:30s} niveau global {10*np.log10(np.sum(y**2)/np.sum(seg**2)):+.2f} dB")
M = seg.mean(axis=1)
def mid(f):
    d = f(M) - M
    return seg + np.stack([d, d], axis=1)
kw = dict(shape="bell", f0=60.0, q=1.0)
w("05_shape_KICK_NET_trans+6_sust-6.wav", mid(lambda z: shape_band(z, fs, cible="transitoires", gain_db=6.0, **kw) + shape_band(z, fs, cible="sustain", gain_db=-6.0, **kw) - z))
w("06_shape_sustain_-6.wav", mid(lambda z: shape_band(z, fs, cible="sustain", gain_db=-6.0, **kw)))
w("07_shape_transitoires_+6.wav", mid(lambda z: shape_band(z, fs, cible="transitoires", gain_db=6.0, **kw)))
print("\nRendus dans", out_dir)
