"""Qu'est-ce qui change entre le sec et chaque rendu ? niveau, sonie K, crête, équilibre par octave, stéréo par octave."""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np, soundfile as sf
from scipy.signal import butter, sosfiltfilt, lfilter
sys.stdout.reconfigure(encoding="utf-8")
D = os.path.join("renders", "corrige2_5dB_30s")
dry, fs = sf.read(os.path.join(D, "00_dry.wav"))
R = {"01 Auto réf.": "01_iron_auto_REFERENCE.wav", "02 Auto flanc raide": "02_iron_auto_flanc_raide.wav",
     "03 HP propre": "03_iron_HP_propre.wav", "04 Auto lié": "04_iron_auto_stereo_LIE.wav",
     "05 Auto 50 %": "05_iron_auto_stereo_50pct.wav", "06 Bande": "06_iron_COULEUR_bande.wav"}
out = {k: sf.read(os.path.join(D, v))[0] for k, v in R.items()}
assert fs == 48000

def kw(x):   # pondération K (BS.1770) à 48 kHz
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585], x, axis=0)
    return lfilter([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621], y, axis=0)
def lufs(x):
    return -0.691 + 10 * np.log10(np.sum(np.mean(kw(x) ** 2, axis=0)))
def db(v): return 20 * np.log10(v + 1e-12)

print("1) Niveau global (relatif au sec)\n")
print(f"{'rendu':22s}{'sonie K (LU)':>14s}{'RMS (dB)':>10s}{'crête (dB)':>12s}{'facteur de crête':>18s}")
r0 = np.sqrt(np.mean(dry ** 2)); p0 = np.abs(dry).max()
print(f"{'sec':22s}{lufs(dry):14.2f}{db(r0):10.2f}{db(p0):12.2f}{db(p0 / r0):18.2f}")
for k, y in out.items():
    r = np.sqrt(np.mean(y ** 2)); p = np.abs(y).max()
    print(f"{k:22s}{lufs(y) - lufs(dry):+14.2f}{db(r) - db(r0):+10.2f}{db(p) - db(p0):+12.2f}{db(p / r) - db(p0 / r0):+18.2f}")

edges = [(31, 63), (63, 125), (125, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000)]
def band(x, lo, hi):
    return sosfiltfilt(butter(4, [lo, hi], btype="band", fs=fs, output="sos"), x, axis=0)
def energie(x): return np.sum(x ** 2)
def sm(x):
    M = (x[:, 0] + x[:, 1]) / 2; S = (x[:, 0] - x[:, 1]) / 2
    return 10 * np.log10(energie(S) / energie(M))

print("\n2) Niveau par octave (Δ dB vs sec)\n")
print(f"{'octave (Hz)':>13s}" + "".join(f"{k[:2]:>8s}" for k in out))
for lo, hi in edges:
    b0 = band(dry, lo, hi)
    print(f"{lo:5d}–{hi:<6d}  " + "".join(f"{10 * np.log10(energie(band(y, lo, hi)) / energie(b0)):+8.2f}" for y in out.values()))

print("\n3) Stéréo par octave : Δ Side/Mid (dB vs sec)\n")
print(f"{'octave (Hz)':>13s}" + "".join(f"{k[:2]:>8s}" for k in out))
for lo, hi in edges:
    s0 = sm(band(dry, lo, hi))
    print(f"{lo:5d}–{hi:<6d}  " + "".join(f"{sm(band(y, lo, hi)) - s0:+8.2f}" for y in out.values()))

print("\n4) Facteur de crête de la bande 8,5–17 kHz (dry / rendus) — lisibilité des percussions aiguës\n")
b0 = band(dry, 8500, 17000)
print(f"  sec {db(np.abs(b0).max() / np.sqrt(np.mean(b0 ** 2))):.2f} dB   " + "   ".join(
    f"{k[:2]} {db(np.abs(band(y, 8500, 17000)).max() / np.sqrt(np.mean(band(y, 8500, 17000) ** 2))):.2f}" for k, y in out.items()))
