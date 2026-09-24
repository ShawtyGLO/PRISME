"""Résonance restante et stéréo des rendus corrigés (renders/corrige_5dB_30s)."""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np, soundfile as sf
from scipy.signal import welch, butter, sosfiltfilt
sys.stdout.reconfigure(encoding="utf-8")
D = os.path.join("renders", "corrige_5dB_30s")
dry, fs = sf.read(os.path.join(D, "00_dry.wav"))
files = {"HP (Harmonique)": "01_iron_HARMONIQUE_hp.wav", "Bande (Couleur)": "02_iron_COULEUR_bande.wav",
         "Auto": "03_iron_auto.wav", "Large": "04_iron_large.wav"}
out = {k: sf.read(os.path.join(D, v))[0] for k, v in files.items()}

print("A) pics du delta (mono) entre 4 et 10 kHz, avec le niveau du sec à la même fréquence\n")
fd, Pdry = welch(dry.mean(axis=1), fs, nperseg=16384)
for k, y in out.items():
    d = (y - dry).mean(axis=1)
    f, P = welch(d, fs, nperseg=16384)
    m = (f > 4000) & (f < 10000)
    db = 10 * np.log10(P + 1e-30)
    idx = np.argsort(db[m])[-3:][::-1]
    txt = ", ".join(f"{f[m][i]:.0f} Hz ({db[m][i]:.0f} dB ; sec {10*np.log10(Pdry[m][i]+1e-30):.0f})" for i in idx)
    tot = P.sum(); fuite = P[(f > 4000) & (f < 8500)].sum() / tot * 100; zone = P[(f > 8485) & (f < 16971)].sum() / tot * 100
    print(f"  {k:16s} fuite 4–8,5 kHz {fuite:4.1f} %  | zone {zone:4.0f} %  | pics : {txt}")

print("\nB) stéréo : corrélation gauche/droite du DELTA, et rapport Side/Mid (dB) du rendu comparé au sec\n")
bands = [("2–4 kHz", 2000, 4000), ("4–8 kHz", 4000, 8000), ("8–17 kHz", 8500, 17000)]
print(f"{'':16s}" + "".join(f"{n:>26s}" for n, _, _ in bands))
print(f"{'':16s}" + "".join(f"{'corr. L/R delta':>14s}{'Δ Side/Mid':>12s}" for _ in bands))
for k, y in out.items():
    row = f"{k:16s}"
    for n, lo, hi in bands:
        sos = butter(4, [lo, hi], btype="band", fs=fs, output="sos")
        d = sosfiltfilt(sos, (y - dry), axis=0)
        r = np.corrcoef(d[:, 0], d[:, 1])[0, 1]
        def sm(z):
            zz = sosfiltfilt(sos, z, axis=0); M = (zz[:, 0] + zz[:, 1]) / 2; S = (zz[:, 0] - zz[:, 1]) / 2
            return 10 * np.log10(np.sum(S ** 2) / np.sum(M ** 2))
        row += f"{r:14.2f}{sm(y) - sm(dry):12.2f}"
    print(row)
print("\ncorrélation L/R du sec lui-même :", ", ".join(
    f"{n} {np.corrcoef(*sosfiltfilt(butter(4,[lo,hi],btype='band',fs=fs,output='sos'),dry,axis=0).T)[0,1]:.2f}" for n, lo, hi in bands))
