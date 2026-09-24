"""Ablation (2026-09-24) : source fenêtre autour de la zone ; que garde-t-on ? Métriques R1–R5 + prévisibilité du niveau.

Tranche A = 30–50 s (zone d'air garnie) ; tranche B = 68–84 s (au-dessus de 8 kHz presque vide).
Prévisibilité (R2) = écart entre le gain net sur A et sur B : plus il est petit, plus le réglage est prévisible.
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation
from bench_quality import rugosite, transitoires
sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav"
LO, HI = 12000 / np.sqrt(2), 12000 * np.sqrt(2)


def evalue(mA, mB, fs, **kw):
    yA = excite_band(mA, fs, **kw); yB = excite_band(mB, fs, **kw)
    dA = yA - mA
    nA, _, rho = zone_stats(mA, yA, fs, LO, HI)
    nB, _, _ = zone_stats(mB, yB, fs, LO, HI)
    return nA, nB, localisation(mA, yA, fs, LO, HI), rugosite(dA, fs), transitoires(mA, dA, fs), rho


def table(mA, mB, fs, titre, configs):
    print(f"\n{titre}")
    print(f"{'configuration':44s}{'net A':>7s}{'net B':>7s}{'|A−B|':>7s}{'% zone':>8s}{'rugos.':>8s}{'trans.':>8s}{'corr.':>7s}")
    for name, kw in configs:
        nA, nB, loc, rug, tr, rho = evalue(mA, mB, fs, **kw)
        print(f"{name:44s}{nA:7.1f}{nB:7.1f}{abs(nA-nB):7.1f}{loc:7.0f}%{rug:8.2f}{tr:8.2f}{rho:7.2f}")


def main():
    fs, x = load(SRC)
    m = x.mean(axis=1)
    mA, mB = m[int(30 * fs): int(50 * fs)], m[int(68 * fs): int(84 * fs)]
    base = dict(f0=12000.0, q=2.0, gain_db=5.0, mode="iron", oversample=2)
    full = dict(drive=1.5, adaptive=True, deemph=True, norm="zone")
    W = dict(source="window")
    print(f"sec : rugosité A {rugosite(mA, fs):.2f} ; fenêtre par défaut = [f0/3 ; 1,5·f0] ; Iron ; +5 dB")
    table(mA, mB, fs, "1) Ablation des artifices (source fenêtre)", [
        ("tout activé (adaptatif+projection+norm)", dict(**base, **W, **full)),
        ("sans adaptatif (drive fixe 2)",           dict(**base, **W, **{**full, "adaptive": False, "drive": 2.0})),
        ("sans adaptatif (drive fixe 4)",           dict(**base, **W, **{**full, "adaptive": False, "drive": 4.0})),
        ("sans projection (soustraction simple)",   dict(**base, **W, **{**full, "deemph": "sub"})),
        ("sans normalisation",                      dict(**base, **W, **{**full, "norm": False})),
        ("minimal : rien des trois (drive 2)",      dict(**base, **W, drive=2.0, adaptive=False, deemph="sub", norm=False)),
        ("minimal : rien des trois (drive 4)",      dict(**base, **W, drive=4.0, adaptive=False, deemph="sub", norm=False)),
    ])
    table(mA, mB, fs, "2) Largeur de la fenêtre (tout activé)", [
        ("bas f0/2, haut 1,5·f0",  dict(**base, **W, **full, win_lo_div=2.0, win_hi_mul=1.5)),
        ("bas f0/3, haut 1,5·f0",  dict(**base, **W, **full, win_lo_div=3.0, win_hi_mul=1.5)),
        ("bas f0/4, haut 1,5·f0",  dict(**base, **W, **full, win_lo_div=4.0, win_hi_mul=1.5)),
        ("bas f0/3, haut 1,2·f0",  dict(**base, **W, **full, win_lo_div=3.0, win_hi_mul=1.2)),
        ("bas f0/3, haut 2·f0",    dict(**base, **W, **full, win_lo_div=3.0, win_hi_mul=2.0)),
        ("bas f0/3, sans limite haute", dict(**base, **W, **full, win_lo_div=3.0, win_hi_mul=None)),
    ])
    table(mA, mB, fs, "3) Références (tout activé)", [
        ("Auto (passe-bande sous la zone)", dict(**base, source="auto", **full)),
        ("Bande (la zone elle-même)",       dict(**base, source="band", **full)),
        ("Passe-haut f0/3",                 dict(**base, source="hp", **full)),
        ("Large (pleine bande)",            dict(**base, source="large", **full)),
    ])


if __name__ == "__main__":
    main()
