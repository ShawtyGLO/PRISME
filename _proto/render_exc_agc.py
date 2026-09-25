"""Rendus comparatifs de l'AGC d'entrée de l'Exciter : référence (gain ≤ +24 dB) contre AGC élargie (10 ms, jusqu'à +40 dB) et le réglage Saturation."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
import prisme_exciter_stream as ES
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = x[int(30 * fs): int(50 * fs)]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_agc")
peak = np.max(np.abs(x))
D = ES.D_OS
NEW = dict(env_tau=0.01, gmin=0.05, gmax_db=40.0)


def wet(**kw):
    return np.stack([ES.exciter_stream(np.ascontiguousarray(x[:, c]), fs, **kw) for c in (0, 1)], axis=1)


def ecrit(nom, y):
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


dry = np.concatenate([np.zeros((D, 2)), x[:-D]])
ecrit("00_sec", dry)
for tag, sh, f0, g, kw in (("bell3k_+2,4", "bell", 3000.0, 2.4, {}), ("bell1k_+2,4", "bell", 1000.0, 2.4, {}), ("shelf9,6k_+5", "highshelf", 9600.0, 5.0, {})):
    for nom, extra in (("ref", {}), ("agc", NEW)):
        d = wet(shape=sh, f0=f0, q=0.71, gain_db=g, mode="iron", source="auto", **extra)
        ecrit(f"{tag}_{nom}", dry + d)
        if tag == "bell3k_+2,4":
            ecrit(f"{tag}_{nom}_DELTA_seul", d)
for nom, drive in (("doux_0,5", 0.5), ("defaut_1,5", 1.5), ("sature_4", 4.0)):
    d = wet(shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode="iron", source="auto", drive=drive, **NEW)
    ecrit(f"bell3k_+2,4_agc_saturation_{nom}", dry + d)
print(sorted(os.listdir(out)))
