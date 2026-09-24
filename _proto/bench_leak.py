"""Fuite sous la zone (raies aux partiels forts du sec) et rôle du stéréo — source passe-haut, Iron, +5 dB."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import welch, butter, sosfiltfilt
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation
from bench_quality import rugosite, transitoires
sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav"
LO, HI = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
fs, x = load(SRC)
st = x[int(30 * fs): int(50 * fs)]
m = st.mean(axis=1)
kw = dict(f0=12000.0, q=2.0, gain_db=5.0, drive=1.5, oversample=2, norm="zone", mode="iron")


def fuite(dry, y):
    f, Pd = welch(y - dry, fs, nperseg=16384); _, P0 = welch(dry, fs, nperseg=16384)
    k = (f > 4000) & (f < 8500)
    part = Pd[k].sum() / Pd.sum() * 100
    worst = np.max(10 * np.log10(Pd[k] + 1e-30) - 10 * np.log10(P0[k] + 1e-30))
    return part, worst


print("1) Fuite sous la zone (mono) : % de l'énergie du delta entre 4 et 8,5 kHz ; pire raie rel. au sec (dB)\n")
print(f"{'source':8s}{'sections':>9s}{'τ proj.':>9s}{'fuite %':>9s}{'pire raie':>10s}{'% zone':>8s}{'net':>6s}{'rugos.':>8s}{'trans.':>8s}")
for src in ("hp", "auto"):
    for sec, nt in ((2, 0.03), (2, 0.3), (3, 0.03), (4, 0.03), (4, 0.3)):
        y = excite_band(m, fs, source=src, out_sections=sec, null_tau=nt, **kw)
        p, w = fuite(m, y)
        print(f"{src:8s}{sec:9d}{nt:9.2f}{p:9.1f}{w:10.1f}{localisation(m, y, fs, LO, HI):7.0f}%{zone_stats(m, y, fs, LO, HI)[0]:6.1f}{rugosite(y - m, fs):8.2f}{transitoires(m, y - m, fs):8.2f}")

print("\n2) Stéréo : indépendant (chaque canal) / lié (delta du Mid ajouté aux deux) — Δ Side/Mid 8–17 kHz et corrélation L/R du delta\n")
sos = butter(4, [8500, 17000], btype="band", fs=fs, output="sos")
def sm(z):
    zz = sosfiltfilt(sos, z, axis=0); M = (zz[:, 0] + zz[:, 1]) / 2; S = (zz[:, 0] - zz[:, 1]) / 2
    return 10 * np.log10(np.sum(S ** 2) / np.sum(M ** 2))
print(f"{'rendu':22s}{'Δ Side/Mid':>12s}{'corr L/R delta':>16s}")
for src in ("hp", "auto", "large"):
    ind = np.stack([excite_band(st[:, c], fs, source=src, **kw) for c in range(2)], axis=1)
    dM = excite_band(m, fs, source=src, **kw) - m
    lie = st + dM[:, None]
    for nom, y in (("indépendant", ind), ("lié (mono)", lie)):
        d = sosfiltfilt(sos, y - st, axis=0)
        r = np.corrcoef(d[:, 0], d[:, 1])[0, 1]
        print(f"{src + ' ' + nom:22s}{sm(y) - sm(st):12.2f}{r:16.2f}")
