"""Régularité du wet de l'Exciter v2 selon la porte (seuil, largeur, plancher, relâchement) et le drive — cible : peu de fenêtres de 100 ms « muettes », écart-type du niveau faible."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
from prisme_dsp import classa_f
from prisme_band import zone_filter
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, X = load(SRC)
mid = np.ascontiguousarray(0.5 * (X[int(30 * fs): int(45 * fs), 0] + X[int(30 * fs): int(45 * fs), 1]))
W = int(0.1 * fs)
zf = zone_filter("bell", fs, 1000.0, 2.0)
s = lfilter(*zf, lfilter(*zf, mid))
a = np.abs(s)
env = lambda tau: lfilter([1 - np.exp(-1 / (tau * fs))], [1, -np.exp(-1 / (tau * fs))], a) * (np.pi / 2)
S, e = env(0.4) + 1e-7, env(0.003)
rel = 20 * np.log10((e + 1e-12) / S)
zo = zone_filter("bell", fs, 3000.0, 0.71)


def variante(seuil, larg, plancher, rel_tau, drive):
    v = np.clip((rel - seuil) / larg, 0, 1)
    p = v * v * (3 - 2 * v)
    p = plancher + (1 - plancher) * p
    if rel_tau > 0:                                        # attaque immédiate, relâchement exponentiel
        c = np.exp(-1 / (rel_tau * fs))
        out = np.empty_like(p); y = 0.0
        for i in range(len(p)):
            y = max(p[i], c * y); out[i] = y
        p = out
    u = drive * s / S
    y = classa_f(u + 0.25) - u
    res = y * S * p
    for _ in range(3):
        res = lfilter(*zo, res)
    return p, res


print(f"{'porte : seuil / largeur / plancher / relâchement, drive':58s} porte moy.  fenêtres muettes  écart-type niveau  plage P10…P90 (dB)")
for cfg in ((3, 6, 0.0, 0, 2.5), (0, 12, 0.25, 0.05, 2.5), (-3, 12, 0.3, 0.1, 2.5), (0, 9, 0.5, 0.15, 2.5), (-3, 12, 0.3, 0.1, 5.0), (-3, 12, 0.3, 0.1, 8.0), (-6, 12, 0.5, 0.2, 5.0)):
    p, res = variante(*cfg)
    r = res[int(fs):]
    n = len(r) // W
    lw = 10 * np.log10((r[: n * W].reshape(n, W) ** 2).mean(axis=1) + 1e-20)
    pm = p[int(fs):][: n * W].reshape(n, W).mean(axis=1)
    muet = 100 * np.mean(lw < np.median(lw) - 25)
    print(f"  {str(cfg):56s} {100 * np.mean(pm):5.0f} %    {muet:5.0f} %           {np.std(lw):5.1f} dB          {np.percentile(lw, 10) - np.median(lw):+5.0f} … {np.percentile(lw, 90) - np.median(lw):+4.0f}")
