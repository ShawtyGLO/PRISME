"""Essai « parallèle » : gain d'entrée FIXE (pas d'AGC) et wet = harmoniques réellement produites (pas de normalisation par la zone).
Le wet suit alors le contenu : il disparaît quand rien ne dépasse le coude de la courbe (comme un exciter à seuil)."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
import prisme_exciter_stream as ES
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = np.ascontiguousarray(x[int(30 * fs): int(40 * fs), 0])
rmsdb = lambda v: 20 * np.log10(np.sqrt(np.mean(v[int(fs):] ** 2)) + 1e-12)
# zone de référence (bell 3 kHz Q 0,71) pour exprimer le wet en dB sous le contenu de la zone
from prisme_band import zone_filter
from scipy.signal import lfilter
zone = lfilter(*zone_filter("bell", fs, 3000.0, 0.71), x)
print(f"contenu de la zone 3 kHz : {rmsdb(zone):.1f} dBFS")
def stats(y):
    y = y[int(fs):]
    e = np.sort(y ** 2)[::-1]
    frac_silence = np.mean(np.abs(y) < 10 ** (-70 / 20) * 1.0)
    return np.max(np.abs(y)) / np.sqrt(np.mean(y ** 2)), 100 * e[: len(e) // 100].sum() / e.sum(), 100 * frac_silence
print("référence actuelle (AGC + normalisation, +2,4 dB) : wet", end=" ")
y = ES.exciter_stream(x, fs, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode="iron", source="auto")
print(f"{rmsdb(y):.1f} dBFS = {rmsdb(y) - rmsdb(zone):.1f} dB sous la zone ; crête/RMS {stats(y)[0]:.1f} ; échantillons < −70 dBFS : {stats(y)[2]:.0f} %")
for g0 in (2.0, 4.0, 8.0, 16.0):
    y = ES.exciter_stream(x, fs, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode="iron", source="auto", gmin=g0, gmax_db=20 * np.log10(g0), raw_mix=1.0)
    c, t, q = stats(y)
    print(f"gain d'entrée fixe ×{g0:4.0f} (+{20 * np.log10(g0):.0f} dB), wet brut : {rmsdb(y):6.1f} dBFS = {rmsdb(y) - rmsdb(zone):6.1f} dB sous la zone ; crête/RMS {c:5.1f} ; 1 % forts {t:4.0f} % ; échantillons < −70 dBFS : {q:3.0f} %")
