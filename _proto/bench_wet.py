"""Chemin wet pur vs architectures Auto/Bande/Large ; effet du désaccord de raies."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_band import excite_band
from prisme_wet import wet_band
from render import load
from bench_band import zone_stats, localisation
from bench_quality import rugosite, transitoires

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav"
G = 5.0


def main():
    fs, x = load(SRC)
    m = x.mean(axis=1)[int(30 * fs): int(50 * fs)]
    lo, hi = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
    print(f"tranche 30–50 s sans clipper, cloche 12 kHz Q 2, +{G:g} dB, sortie 24 dB/oct — sec : rugosité {rugosite(m, fs):.2f}\n")
    print(f"{'rendu':26s}{'net':>6s}{'ajout':>7s}{'% zone':>8s}{'rugos.':>8s}{'transit.':>9s}")
    def row(name, y):
        d = y - m
        net, add, rho = zone_stats(m, y, fs, lo, hi)
        print(f"{name:26s}{net:6.1f}{add:7.1f}{localisation(m, y, fs, lo, hi):7.0f}%{rugosite(d, fs):8.2f}{transitoires(m, d, fs):9.2f}")
    kw = dict(f0=12000.0, q=2.0, gain_db=G, drive=1.5, oversample=2, norm="zone")
    row("iron  Auto (actuel)", excite_band(m, fs, mode="iron", source="auto", **kw))
    row("iron  Bande (actuel)", excite_band(m, fs, mode="iron", source="band", **kw))
    row("iron  Large (actuel)", excite_band(m, fs, mode="iron", source="large", **kw))
    print()
    for mode, drives in (("iron", (1.0, 2.0, 4.0)), ("triode", (2.0,)), ("classa", (2.0,)), ("rect", (1.0,))):
        for dr in drives:
            row(f"WET pur {mode} d={dr:g}", wet_band(m, fs, mode=mode, gain_db=G, drive=dr))
    print("\nDésaccord de raies (décalage de fréquence lent aléatoire, 3 Hz) :")
    for sp in (0, 15, 40, 100):
        row(f"iron Auto  ±{sp} Hz", excite_band(m, fs, mode="iron", source="auto", spread_hz=sp, **kw))
    for sp in (0, 15, 40, 100):
        row(f"WET iron d=2 ±{sp} Hz", wet_band(m, fs, mode="iron", gain_db=G, drive=2.0, spread_hz=sp))


if __name__ == "__main__":
    main()
