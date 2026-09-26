"""Autour du profil « mordant » (préféré de llg53 à −14 dB) : plus de niveau, drive, seuil, et une version asymétrique dure ; bell 3 kHz et shelf 9,6 kHz."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter
import prisme_exciter_v2 as V2
from prisme_exciter_v2 import exc_v2
from prisme_band import zone_filter
import prisme_exciter_stream as ES
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
# profil supplémentaire : « mordant chaud » = cubique borné asymétrique (harmoniques paires ET impaires, dur)
V2.CURVES["mordant_chaud"] = lambda u: (lambda c: c - c ** 3 / 3.0)(np.clip(u + 0.25, -1.0, 1.0))
V2.CURVES["mordant_dur"] = lambda u: np.clip(u, -0.8, 0.8) * 1.0                      # écrêtage franc (plus de rangs)
fs, X = load(SRC)
X = X[int(30 * fs): int(48 * fs)]
mid = np.ascontiguousarray(0.5 * (X[:, 0] + X[:, 1]))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_mordant")
peak = np.max(np.abs(X))
D = ES.D_OS
dry = np.concatenate([np.zeros((D, 2)), X[:-D]])
rmsdb = lambda v: 20 * np.log10(np.sqrt(np.mean(v[int(fs):] ** 2)) + 1e-12)


def ecrit(nom, y):
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


ecrit("00_sec", dry)
for tag, f0, shape in (("bell3k", 3000.0, "bell"), ("shelf9,6k", 9600.0, "highshelf")):
    zone = lfilter(*zone_filter(shape, fs, f0, 0.71), mid)

    def cal(w, c):
        return (w * 10 ** ((c + rmsdb(zone) - rmsdb(w)) / 20))[:, None] if False else (w * 10 ** ((c + rmsdb(zone) - rmsdb(w)) / 20))

    def rend(nom, c, **kw):
        w = exc_v2(mid, fs, f0, shape=shape, niveau_db=0.0, **kw)
        ecrit(f"{tag}_{nom}_{c}dB", dry + cal(w, c)[:, None])

    for c in (-14, -10, -6):                                             # 1) le niveau
        rend("mordant_d2,5_s3", c, curve="mordant", seuil_db=3.0, drive=2.5)
    for dr in (4.0, 6.0):                                                # 2) le drive (dureté)
        rend(f"mordant_d{dr}_s3", -10, curve="mordant", seuil_db=3.0, drive=dr)
    for sd in (0.0, 6.0):                                                # 3) le seuil
        rend(f"mordant_d2,5_s{sd:.0f}", -10, curve="mordant", seuil_db=sd, drive=2.5)
    rend("mordant_chaud_d2,5_s3", -10, curve="mordant_chaud", seuil_db=3.0, drive=2.5)     # 4) asymétrique
    rend("ecretage_franc_d3_s3", -10, curve="mordant_dur", seuil_db=3.0, drive=3.0)
print(len(os.listdir(out)), "fichiers")
