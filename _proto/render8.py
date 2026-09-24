"""Rendus de l'assemblage (2026-09-25) : la configuration type sur ta prod 30–50 s, puis chaque bande seule. Abaissés de 9 dB.

  Bande 1  lowshelf 42 Hz    Shape   sustain −3 dB                       (Stéréo)
  Bande 2  cloche 164 Hz     Exciter Iron +4 dB                          (Stéréo)
  Bande 3  cloche 632 Hz     Tame    −6 dB, largeur 0,5                  (Mid)
  Bande 4  cloche 2,8 kHz    Shape   transitoires +4 dB, durée 40 ms     (Stéréo)
  Bande 5  highshelf 9,6 kHz Exciter Iron +5 dB                          (Side)
"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_engine import process
from tests_engine import config
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
seg = x[int(30 * fs): int(50 * fs)]
d = os.path.join("renders", "assemblage_30s"); os.makedirs(d, exist_ok=True)
pad = 10 ** (-9 / 20)
w = lambda fn, y: wavfile.write(os.path.join(d, fn), int(fs), (y * pad).astype(np.float32))
b = config()
w("00_dry.wav", seg)
w("01_CONFIG_TYPE_5_bandes.wav", process(seg, fs, b))
noms = ["shape_sustain_-3", "exciter_iron_+4", "tame_-6_mid", "shape_transitoires_+4", "exciter_iron_+5_side"]
for i, (s, nom) in enumerate(zip(b, noms), start=2):
    solo = [dict(t, gain_db=0.0) for t in b]; solo[i - 2] = s
    w(f"{i:02d}_bande{i-1}_seule_{nom}.wav", process(seg, fs, solo))
print("ok")
