"""Rendus n°2 corrigés (2026-09-24) : fuite sous la zone et stéréo, à +5 dB.

  01 Iron Auto (référence, celui que llg53 aime)     02 Auto + flanc bas raide (3 sections, plus propre)
  03 Iron passe-haut « propre » (2 sections + coupe basse f0/1,3 + projection lente)
  04 Auto stéréo LIÉ (delta du Mid ajouté aux deux canaux)    05 Auto stéréo 50 % (moitié lié, moitié indépendant)
  06 Iron Bande (Couleur)
"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation
from bench_leak import fuite, SRC

sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
seg = x[int(30 * fs): int(50 * fs)]
m = seg.mean(axis=1)
lo, hi = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
out_dir = os.path.join("renders", "corrige2_5dB_30s")
os.makedirs(out_dir, exist_ok=True)
pad = 10 ** (-9 / 20)
kw = dict(f0=12000.0, q=2.0, gain_db=5.0, drive=1.5, oversample=2, norm="zone", mode="iron")
write = lambda fn, y: wavfile.write(os.path.join(out_dir, fn), int(fs), (y * pad).astype(np.float32))
indep = lambda **k: np.stack([excite_band(seg[:, c], fs, **kw, **k) for c in range(2)], axis=1)

write("00_dry.wav", seg)
auto = indep(source="auto")
write("01_iron_auto_REFERENCE.wav", auto)
write("02_iron_auto_flanc_raide.wav", indep(source="auto", out_sections=3))
write("03_iron_HP_propre.wav", indep(source="hp", out_sections=2, low_hp_ratio=1.3, null_tau=0.3))
dM = excite_band(m, fs, source="auto", **kw) - m
lie = seg + dM[:, None]
write("04_iron_auto_stereo_LIE.wav", lie)
write("05_iron_auto_stereo_50pct.wav", 0.5 * auto + 0.5 * lie)
write("06_iron_COULEUR_bande.wav", indep(source="band"))
for n, y in (("01 auto (réf.)", auto), ("04 auto lié", lie), ("05 auto 50 %", 0.5 * auto + 0.5 * lie)):
    ym = y.mean(axis=1)
    print(f"{n:16s} net {zone_stats(m, ym, fs, lo, hi)[0]:4.1f} dB  fuite/pire raie {fuite(m, ym)[0]:4.1f} % / {fuite(m, ym)[1]:5.1f} dB")
print(f"\nRendus dans {out_dir}/ (abaissés de 9 dB)")
