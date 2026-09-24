"""Source hybride : mélange de la sortie Auto (harmoniques du corps) et Bande (suit la zone)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation
from bench_quality import rugosite, transitoires

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(os.path.join("renders", "___Test_PRISME_VST_231_L0V3MUSI__125_BPM_30s_q2_s2", "00_dry.wav"))
x = x * 10 ** (9 / 20)
m = x.mean(axis=1)[: int(20 * fs)]
lo, hi = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
print("hybride = w·Auto + (1−w)·Bande  (cloche 12 kHz Q 2, +6 dB)\n")
print(f"{'rendu':18s}{'net':>6s}{'% zone':>8s}{'rugosité':>10s}{'transit.':>10s}")
for mode in ("iron", "triode"):
    kw = dict(f0=12000.0, q=2.0, gain_db=6.0, mode=mode, drive=1.5, oversample=2, norm="zone")
    da = excite_band(m, fs, source="auto", **kw) - m
    db = excite_band(m, fs, source="band", **kw) - m
    for w in (1.0, 0.75, 0.5, 0.25, 0.0):
        d = w * da + (1 - w) * db
        y = m + d
        net, _, _ = zone_stats(m, y, fs, lo, hi)
        print(f"{mode + f' w={w:g}':18s}{net:6.1f}{localisation(m, y, fs, lo, hi):7.0f}%{rugosite(d, fs):10.2f}{transitoires(m, d, fs):10.2f}")
