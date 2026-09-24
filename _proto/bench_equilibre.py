"""Idée de llg53 : « si on pousse le wet, on baisse le dry de façon équivalente pour garder la balance ».

A) Échange local à la bande (« équilibre ») : sortie = sec creusé (cloche négative exacte) + ajout ; le creux est choisi pour que
   l'énergie de la zone d'air reste égale à celle du sec.
B) Sonie K par mode de canal à +5 et +12 dB, et compensation globale qui rendrait la sonie identique.
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import butter, sosfiltfilt, lfilter
from prisme_channels import process_channels
from prisme_dsp import rbj_peaking
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
seg = x[int(30 * fs): int(50 * fs)]
kw = dict(source="auto", out_sections=3, f0=12000.0, q=2.0, gain_db=5.0, drive=1.5, oversample=2, norm="zone", mode="iron")


def kwt(z):
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585], z, axis=0)
    y = lfilter([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621], y, axis=0)
    return -0.691 + 10 * np.log10(np.sum(np.mean(y ** 2, axis=0)))


sos = butter(4, [8500, 17000], btype="band", fs=fs, output="sos")
band = lambda z: sosfiltfilt(sos, z, axis=0)


def crest(z):
    b = band(z)
    return 20 * np.log10(np.abs(b).max() / np.sqrt(np.mean(b ** 2)))


def sm(z):
    b = band(z)
    M = (b[:, 0] + b[:, 1]) / 2
    S = (b[:, 0] - b[:, 1]) / 2
    return 10 * np.log10(np.sum(S ** 2) / np.sum(M ** 2))


def zen(z):
    return 10 * np.log10(np.sum(band(z) ** 2))


print("A) Échange local à la bande (Auto flanc raide, Stéréo, +5 dB) — creux en cloche exacte (RBJ négatif) sur le sec\n")
y = process_channels(seg, fs, "stereo", **kw)


def creux(D):
    return lfilter(*rbj_peaking(fs, 12000.0, -D, 2.0), seg, axis=0)


lo_d, hi_d = 0.0, 24.0
for _ in range(20):
    D = (lo_d + hi_d) / 2
    ys_ = y - seg + creux(D)
    lo_d, hi_d = (D, hi_d) if zen(ys_) > zen(seg) else (lo_d, D)
D = (lo_d + hi_d) / 2
ys = y - seg + creux(D)
print(f"creux nécessaire pour garder l'énergie de la zone d'air = {D:.1f} dB au centre de la cloche\n")
print(f"{'':22s}{'niveau air':>12s}{'crête bande':>13s}{'Δ Side/Mid':>12s}{'Δ sonie K':>11s}")
for nom, z in (("additif (actuel)", y), ("échange (équilibre)", ys)):
    print(f"{nom:22s}{zen(z) - zen(seg):+12.2f}{crest(z) - crest(seg):+13.2f}{sm(z) - sm(seg):+12.2f}{kwt(z) - kwt(seg):+11.2f}")

print("\nB) Sonie K par mode de canal, et compensation globale qui rendrait la sonie identique au sec\n")
print(f"{'':12s}" + "".join(f"{'+' + str(g) + ' dB':>28s}" for g in (5, 12)))
for c in ("stereo", "mid", "side"):
    row = f"{c:12s}"
    for g in (5, 12):
        z = process_channels(seg, fs, c, **{**kw, "gain_db": float(g)})
        d = kwt(z) - kwt(seg)
        row += f"   Δ {d:+6.2f} LU  comp. {-d:+6.2f} dB"
    print(row)
