"""Loi d'échelle : de vraies harmoniques d'ordre 3 varient comme A³, donc le rapport ajout/zone comme A² (2 dB par dB)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_band import excite_band
from render import load
from bench_band import zone_stats
sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav"
LO, HI = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
fs, x = load(SRC)
A = x.mean(axis=1)[int(30 * fs): int(50 * fs)]
base = dict(f0=12000.0, q=2.0, mode="iron", oversample=2, source="hp", drive=2.0, adaptive=False, norm=False, gain_db=14.0)
cfgs = [("projection (de-emphasis actuel)", dict(deemph=True)),
        ("soustraction simple (y − s)",     dict(deemph="sub")),
        ("aucune (wet complet y)",          dict(deemph=False))]
print("Niveau ajouté dans la zone (dB rel. contenu de la zone), gain fixe +14 dB, Iron, source passe-haut f0/3, drive 2")
print(f"{'entrée':>8s}" + "".join(f"{n:>34s}" for n, _ in cfgs))
prev = {}
for db in (-18, -12, -6, 0, 6):
    row = f"{db:+5d} dB"
    for n, c in cfgs:
        y = excite_band(A * 10 ** (db / 20), fs, **base, **c)
        add = zone_stats(A * 10 ** (db / 20), y, fs, LO, HI)[1]
        row += f"{add:34.1f}"
        prev[(n, db)] = add
    print(row)
print("\npente (dB d'ajout par dB d'entrée, de −18 à 0) — attendu 2,0 pour de vraies harmoniques d'ordre 3 :")
for n, _ in cfgs:
    print(f"  {n:34s} {(prev[(n, 0)] - prev[(n, -18)]) / 18:5.2f}")
