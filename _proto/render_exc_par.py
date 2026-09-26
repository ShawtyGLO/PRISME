"""Rendus « parallèle » : le wet de l'Exciter actuel (–10 dB sous le contenu de la zone) redescendu à –18 / –24 / –30 dB, avec et sans diffusion (passe-tout)."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
import prisme_exciter_stream as ES
from diag_exc_diffuse import dispersion
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = x[int(30 * fs): int(48 * fs)]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_parallele")
peak = np.max(np.abs(x))
D = ES.D_OS
dry = np.concatenate([np.zeros((D, 2)), x[:-D]])


def ecrit(nom, y):
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


ecrit("00_sec", dry)
for tag, kw in (("bell3k_iron", dict(shape="bell", f0=3000.0, gain_db=2.4)), ("shelf9,6k_iron", dict(shape="highshelf", f0=9600.0, gain_db=5.0))):
    w = np.stack([ES.exciter_stream(np.ascontiguousarray(x[:, c]), fs, q=0.71, mode="iron", source="auto", **kw) for c in (0, 1)], axis=1)
    for cible in (0, -8, -14, -20):                                   # dB relatifs au wet actuel
        k = 10 ** (cible / 20)
        nom = f"{tag}_wet_actuel" if cible == 0 else f"{tag}_wet_{cible}dB"
        ecrit(nom, dry + k * w)
        if cible in (-8, -14):
            dd = np.stack([dispersion(w[:, c], fs, n=12, q=0.7, decal=0.25 * c) for c in (0, 1)], axis=1)
            ecrit(nom + "_diffus_large", dry + k * dd)
print(sorted(os.listdir(out)))
