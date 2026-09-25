"""Rendus du Lift sur la prod (30–60 s) : 00 sec, puis Lift seul à des réglages typiques (sortie + delta), et mesure du gain moyen."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from render import load
from bench_leak import SRC
from prisme_engine import process

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = x[int(30 * fs): int(60 * fs)]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "lift_30s")
peak = np.max(np.abs(x))


def ecrit(nom, y):
    wavfile.write(os.path.join(out, nom), fs, (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


def lift(f, sh, g, amount, rel=150.0, canal="stereo"):
    return dict(type="lift", shape=sh, f0=f, q=0.7, gain_db=g, amount=amount, release_ms=rel, canal=canal)


cfgs = {
    "01_air_highshelf_8k_+6_am60": [lift(8000, "highshelf", 6.0, 60)],
    "02_air_highshelf_8k_+9_am80": [lift(8000, "highshelf", 9.0, 80)],
    "03_detail_bell_3k_+6_am60": [lift(3000, "bell", 6.0, 60)],
    "04_corps_bell_250_+6_am60": [lift(250, "bell", 6.0, 60)],
    "05_expandeur_bell_3k_-6_am60": [lift(3000, "bell", -6.0, 60)],
    "06_air_8k_+6_am60_relache_50ms": [lift(8000, "highshelf", 6.0, 60, 50.0)],
    "07_trois_bandes_air_detail_corps": [lift(8000, "highshelf", 6.0, 60), lift(3000, "bell", 4.0, 60), lift(250, "bell", 4.0, 60)],
}
ecrit("00_dry.wav", x)
for nom, b in cfgs.items():
    y = process(x, fs, b)
    ecrit(nom + ".wav", y)
    d = y - x
    print(f"{nom:40s} RMS delta {20 * np.log10(np.sqrt(np.mean(d ** 2)) / np.sqrt(np.mean(x ** 2))):6.1f} dB sous le signal ; crête sortie/entrée {np.max(np.abs(y)) / peak:.2f}")
