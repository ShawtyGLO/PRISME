"""Rendus CORRIGÉS à +5 dB (chaîne avec de-emphasis exact, 2026-09-24).

    python render3.py [--start 30] [--dur 20] [--gain 5]

Configuration : source passe-haut f0/h (« Harmonique »), gain adaptatif, projection, normalisation par la zone,
cloche 12 kHz Q 2, sortie 24 dB/oct, ADAA ×2. Références : Auto, Bande (« Couleur »), Large.
"""
import argparse, os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=30.0)
    ap.add_argument("--dur", type=float, default=20.0)
    ap.add_argument("--gain", type=float, default=5.0)
    ap.add_argument("--src", default=SRC)
    a = ap.parse_args()
    fs, x = load(a.src)
    seg = x[int(a.start * fs): int((a.start + a.dur) * fs)]
    m = seg.mean(axis=1)
    lo, hi = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
    out_dir = os.path.join("renders", f"corrige_{a.gain:g}dB_{int(a.start)}s")
    os.makedirs(out_dir, exist_ok=True)
    pad = 10 ** (-9 / 20)
    kw = dict(f0=12000.0, q=2.0, gain_db=a.gain, drive=1.5, oversample=2, norm="zone")

    def write(fn, y):
        wavfile.write(os.path.join(out_dir, fn), int(fs), (y * pad).astype(np.float32))

    def per_channel(**k):
        return np.stack([excite_band(seg[:, c], fs, **kw, **k) for c in range(seg.shape[1])], axis=1)

    jobs = [("01_iron_HARMONIQUE_hp", dict(mode="iron", source="hp")),
            ("02_iron_COULEUR_bande", dict(mode="iron", source="band")),
            ("03_iron_auto", dict(mode="iron", source="auto")),
            ("04_iron_large", dict(mode="iron", source="large")),
            ("05_triode_hp", dict(mode="triode", source="hp")),
            ("06_classa_hp", dict(mode="classa", source="hp")),
            ("07_diode_hp", dict(mode="diode", source="hp")),
            ("08_rect_hp", dict(mode="rect", source="hp"))]
    write("00_dry.wav", seg)
    for name, k in jobs:
        y = per_channel(**k)
        write(name + ".wav", y)
        if name in ("01_iron_HARMONIQUE_hp", "08_rect_hp"):
            write("delta_" + name[3:] + ".wav", y - seg)             # ajout réel (non amplifié)
        net, add, rho = zone_stats(m, y.mean(axis=1), fs, lo, hi)
        print(f"{name:26s} net {net:5.1f} dB   ajout {add:6.1f} dB   dans la zone {localisation(m, y.mean(axis=1), fs, lo, hi):3.0f}%")
    print(f"\nRendus dans {out_dir}/ (abaissés de 9 dB ; delta_* = ajout réel)")


if __name__ == "__main__":
    main()
