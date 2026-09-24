import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_band import excite_band
from bench_leak import fuite, m, fs, kw, LO, HI, localisation, zone_stats, rugosite, transitoires
print("\n3) Coupe basse asymétrique (flanc bas 24 dB/oct à f0/ratio) — source passe-haut\n")
print(f"{'configuration':34s}{'fuite %':>9s}{'pire raie':>10s}{'% zone':>8s}{'net':>6s}{'rugos.':>8s}{'trans.':>8s}")
for nom, extra in (("2 sections (actuel)", dict(out_sections=2)),
                   ("3 sections", dict(out_sections=3)),
                   ("2 sections + coupe basse f0/1,15", dict(out_sections=2, low_hp_ratio=1.15)),
                   ("2 sections + coupe basse f0/1,3", dict(out_sections=2, low_hp_ratio=1.3)),
                   ("1 section + coupe basse f0/1,3", dict(out_sections=1, low_hp_ratio=1.3)),
                   ("2 sect. + coupe basse f0/1,3 + τ0,3", dict(out_sections=2, low_hp_ratio=1.3, null_tau=0.3))):
    y = excite_band(m, fs, source="hp", **{**kw, **extra})
    p, w = fuite(m, y)
    print(f"{nom:34s}{p:9.1f}{w:10.1f}{localisation(m, y, fs, LO, HI):7.0f}%{zone_stats(m, y, fs, LO, HI)[0]:6.1f}{rugosite(y - m, fs):8.2f}{transitoires(m, y - m, fs):8.2f}")
