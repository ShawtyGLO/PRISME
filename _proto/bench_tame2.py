"""Balayage de la force de détection du Tame (seuil, rapport) — largeur fine et moyenne."""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from bench_tame import signal, FS, pic_db, rapport
from prisme_tame import tame_band
sys.stdout.reconfigure(encoding="utf-8")
x = signal()
xn = signal(avec_res=False)
print(f"{'largeur':>8s}{'seuil':>7s}{'rapport':>9s}{'1,7k':>7s}{'2,4k':>7s}{'3,1k':>7s}{'5,3k':>7s}{'collat. moy/max':>18s}{'bruit seul |Δ|max':>20s}")
for wd in (1.0, 0.75, 0.5):
    for T, r in ((3.0, 1.0), (3.0, 2.0), (2.0, 2.0), (1.5, 3.0)):
        y = tame_band(x, FS, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=wd, thresh_db=T, ratio=r)
        red = [pic_db(y, f) - pic_db(x, f) for f in (1700.0, 2400.0, 3100.0, 5300.0)]
        mo, mx, _ = rapport(x, y)
        yn = tame_band(xn, FS, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=wd, thresh_db=T, ratio=r)
        from bench_tame import bandes_tiers, CENTRES
        dn = np.max(np.abs(bandes_tiers(yn, CENTRES) - bandes_tiers(xn, CENTRES)))
        print(f"{wd:8.2f}{T:7.1f}{r:9.1f}" + "".join(f"{v:+7.1f}" for v in red) + f"{mo:11.2f}/{mx:5.2f} dB{dn:14.2f} dB")
