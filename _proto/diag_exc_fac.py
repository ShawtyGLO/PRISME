"""Diagnostic : facteur de normalisation final de l'Exciter (cible / RMS du résidu, borné à 100) sur la prod — un facteur élevé amplifie le bruit du résidu."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
import prisme_exciter_stream as ES
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
FAC = []
_orig_clip = np.clip


def clip_spy(a, lo, hi, *k, **kw):
    r = _orig_clip(a, lo, hi, *k, **kw)
    if hi == 100.0 and lo == 0.0:
        FAC.append(np.array(r))
    return r


ES.np.clip = clip_spy
fs, x = load(SRC)
x = np.ascontiguousarray(x[int(30 * fs): int(40 * fs), 0])
for sh, f0, q, g, drive in (("bell", 3000.0, 0.71, 2.4, 1.5), ("bell", 3000.0, 0.71, 2.4, 0.3), ("bell", 3000.0, 0.71, 2.4, 6.0), ("highshelf", 9600.0, 0.71, 5.0, 1.5)):
    FAC.clear()
    y = ES.exciter_stream(x, fs, shape=sh, f0=f0, q=q, gain_db=g, mode="iron", source="auto", drive=drive)
    f = np.concatenate(FAC)
    f = f[int(1 * fs):]
    d = y[int(1 * fs):]
    print(f"{sh:9s} {f0:6.0f} Hz +{g} dB drive {drive:3.1f} : facteur final médiane {np.median(f):6.2f}  P95 {np.percentile(f, 95):6.2f}  max {f.max():6.1f}  part à 100 : {100 * np.mean(f >= 99.9):5.1f} % ; delta RMS {20 * np.log10(np.sqrt(np.mean(d ** 2))):6.1f} dB, crête/RMS {np.max(np.abs(d)) / np.sqrt(np.mean(d ** 2)):.1f}")
