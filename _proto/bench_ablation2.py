"""Que faut-il pour un effet PRÉVISIBLE avec de vraies harmoniques ? (chaîne corrigée, 2026-09-24)

Compare, sur 3 programmes et 4 niveaux d'entrée, le gain net dans la zone d'air pour :
  N  = adaptatif + normalisation (actuel)      U = adaptatif + gain fixe calibré
  V  = sans adaptatif + normalisation          W = sans adaptatif + gain fixe calibré
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation
from bench_quality import rugosite, transitoires
sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav"
LO, HI = 12000 / np.sqrt(2), 12000 * np.sqrt(2)


def net(m, fs, **kw):
    return zone_stats(m, excite_band(m, fs, **kw), fs, LO, HI)[0]


def calibre(A, fs, target, **kw):
    lo_g, hi_g = 0.0, 60.0
    for _ in range(11):
        mid = (lo_g + hi_g) / 2
        lo_g, hi_g = (mid, hi_g) if net(A, fs, gain_db=mid, **kw) < target else (lo_g, mid)
    return (lo_g + hi_g) / 2


def main():
    fs, x = load(SRC)
    m = x.mean(axis=1)
    T = {"A 30–50 s": m[int(30 * fs): int(50 * fs)], "B 68–84 s": m[int(68 * fs): int(84 * fs)], "C 10–20 s": m[int(10 * fs): int(20 * fs)]}
    A = T["A 30–50 s"]
    base = dict(f0=12000.0, q=2.0, mode="iron", oversample=2, source="hp", deemph=True)
    ad = dict(base, adaptive=True, drive=1.5)
    na = dict(base, adaptive=False, drive=2.0)
    target = net(A, fs, gain_db=5.0, norm="zone", **ad)
    cfg = {
        "N adapt+norm": dict(gain_db=5.0, norm="zone", **ad),
        "V norm seule": dict(gain_db=5.0, norm="zone", **na),
    }
    gU = calibre(A, fs, target, norm=False, **ad)
    gW = calibre(A, fs, target, norm=False, **na)
    cfg["U adapt+fixe"] = dict(gain_db=gU, norm=False, **ad)
    cfg["W fixe seul"] = dict(gain_db=gW, norm=False, **na)
    print(f"cible = gain net {target:.1f} dB sur A ; gain fixe calibré : U (adaptatif) +{gU:.1f} dB, W (sans adaptatif) +{gW:.1f} dB\n")
    print(f"{'programme / niveau d entrée':28s}" + "".join(f"{k:>15s}" for k in cfg))
    for nom, seg in T.items():
        print(f"{nom:28s}" + "".join(f"{net(seg, fs, **c):13.1f}dB" for c in cfg.values()))
    print()
    for db in (-12, -6, 0, 6):
        seg = A * 10 ** (db / 20)
        print(f"{'A, entrée ' + f'{db:+d} dB':28s}" + "".join(f"{net(seg, fs, **c):13.1f}dB" for c in cfg.values()))
    print("\nautres métriques sur A :")
    for k, c in cfg.items():
        y = excite_band(A, fs, **c); d = y - A
        print(f"  {k:14s} % zone {localisation(A, y, fs, LO, HI):3.0f}%  rugosité {rugosite(d, fs):.2f}  transitoires {transitoires(A, d, fs):.2f}")


if __name__ == "__main__":
    main()
