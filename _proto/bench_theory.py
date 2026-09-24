"""Vérifications théoriques (2026-09-24) — règle de modulation : le non-linéaire ne doit voir que ce qui est proche de la zone visée.

(1) Deux tons : basse 80 Hz (grosse) + partiel aigu 10 kHz (petit). Saturation pleine bande vs après passe-haut 4 kHz.
    Mesure : bandes latérales autour de 10 kHz (±160 Hz, ±320 Hz) rel. à la porteuse, et perte de gain de la porteuse.
(2) Vrai mix : sources Auto / Bande / Large / HP (passe-haut) — même métriques que bench_quality.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_dsp import saturate
from prisme_band import excite_band, rbj_highpass
from scipy.signal import lfilter
from render import load
from bench_band import zone_stats, localisation
from bench_quality import rugosite, transitoires
sys.stdout.reconfigure(encoding="utf-8")

def deux_tons():
    fs = 192000; n = fs; t = np.arange(n) / fs
    print("(1) basse 80 Hz + partiel 10 kHz (amplitude 0,05), courbe Iron\n")
    print(f"{'amp. basse':>11s}{'chemin':>14s}{'gain porteuse':>15s}{'bandes latérales':>18s}")
    for ab in (0.25, 0.5, 1.0):
        x = ab * np.cos(2 * np.pi * 80 * t) + 0.05 * np.cos(2 * np.pi * 10000 * t)
        for nom, xin in (("pleine bande", x), ("HP 4 kHz", lfilter(*rbj_highpass(fs, 4000.0), lfilter(*rbj_highpass(fs, 4000.0), x)))):
            y = saturate(xin, "iron", adaa=False)
            X = np.abs(np.fft.rfft(y * np.hanning(n))) / (n / 4)
            k = 10000
            car = X[k - 1: k + 2].max()
            side = np.sqrt(sum(X[k + d - 1: k + d + 2].max() ** 2 for d in (-320, -160, 160, 320)))
            print(f"{ab:11.2f}{nom:>14s}{20*np.log10(car/0.05):12.1f} dB{20*np.log10(side/car+1e-12):15.1f} dB")

def vrai_mix():
    fs, x = load(r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav")
    m = x.mean(axis=1)[int(30 * fs): int(50 * fs)]
    lo, hi = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
    print("\n(2) vrai mix 30–50 s, cloche 12 kHz Q 2, +5 dB\n")
    print(f"{'rendu':16s}{'net':>6s}{'% zone':>8s}{'rugos.':>8s}{'transit.':>9s}")
    kw = dict(f0=12000.0, q=2.0, gain_db=5.0, drive=1.5, oversample=2, norm="zone")
    for mode in ("iron", "rect"):
        for src in ("auto", "band", "large", "hp"):
            y = excite_band(m, fs, mode=mode, source=src, **kw); d = y - m
            net, add, rho = zone_stats(m, y, fs, lo, hi)
            print(f"{mode + ' ' + src:16s}{net:6.1f}{localisation(m, y, fs, lo, hi):7.0f}%{rugosite(d, fs):8.2f}{transitoires(m, d, fs):9.2f}")

if __name__ == "__main__":
    deux_tons(); vrai_mix()
