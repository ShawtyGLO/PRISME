"""Rendus : Exciter actuel (K = 1 source large) contre Exciter à K sous-bandes étroites saturées séparément (moins d'intermodulation)."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
import prisme_exciter_stream as ES
from diag_exc_multi import multi
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = x[int(30 * fs): int(48 * fs)]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_multi")
peak = np.max(np.abs(x))
D = ES.D_OS
dry = np.concatenate([np.zeros((D, 2)), x[:-D]])


def wet(**kw):
    return np.stack([multi(np.ascontiguousarray(x[:, c]), fs, **kw) for c in (0, 1)], axis=1)


def ecrit(nom, y):
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


ecrit("00_sec", dry)
for tag, kw, Ks in (("bell3k_iron_+2,4", dict(f0=3000.0, mode="iron", gain=2.4), (1, 4, 8)), ("bell1k_iron_+2,4", dict(f0=1000.0, mode="iron", gain=2.4), (1, 4)),
                    ("shelf9,6k_iron_+5", dict(f0=9600.0, mode="iron", gain=5.0, shape="highshelf"), (1, 4)), ("bell3k_triode_+2,4", dict(f0=3000.0, mode="triode", gain=2.4), (1, 4)),
                    ("bell3k_rect_+2,4", dict(f0=3000.0, mode="rect", gain=2.4), (1, 4))):
    for K in Ks:
        d = wet(K=K, **kw)
        ecrit(f"{tag}_K{K}", dry + d)
        if tag == "bell3k_iron_+2,4" and K in (1, 4):
            ecrit(f"{tag}_K{K}_DELTA_seul", d)
print(sorted(os.listdir(out)))
