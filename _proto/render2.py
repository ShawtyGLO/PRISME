"""Rendus comparatifs à +5 dB (2026-09-24) : architectures Auto/Bande/Large, wet pur recalé, désaccord de raies.

    python render2.py [--start 30] [--dur 20] [--gain 5]
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_band import excite_band
from prisme_wet import wet_band
from render import load
from bench_band import zone_stats

sys.stdout.reconfigure(encoding="utf-8")
SRC = r"D:\1 Plugin Vibecodding\PRISME VST\!! Test PRISME VST_231_L0V3MUSI(_125_BPM.wav"


def per_channel(fn, x, **kw):
    if x.ndim == 1:
        return fn(x, **kw)
    return np.stack([fn(x[:, c], seed=c, **kw) for c in range(x.shape[1])], axis=1)


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
    out_dir = os.path.join("renders", f"5dB_{int(a.start)}s" if a.gain == 5 else f"g{a.gain:g}_{int(a.start)}s")
    os.makedirs(out_dir, exist_ok=True)
    pad = 10 ** (-9 / 20)
    kw = dict(f0=12000.0, q=2.0, gain_db=a.gain, drive=1.5, oversample=2, norm="zone")

    def write(fn, y):
        wavfile.write(os.path.join(out_dir, fn), int(fs), (y * pad).astype(np.float32))

    # niveau visé pour le wet pur = effet net d'Iron Large au même réglage
    ref = excite_band(m, fs, mode="iron", source="large", **kw)
    target = zone_stats(m, ref, fs, lo, hi)[0]
    lo_g, hi_g = 0.0, 40.0
    for _ in range(9):
        mid = (lo_g + hi_g) / 2
        net = zone_stats(m, wet_band(m, fs, mode="iron", gain_db=mid, drive=2.0), fs, lo, hi)[0]
        lo_g, hi_g = (mid, hi_g) if net < target else (lo_g, mid)
    g_wet = (lo_g + hi_g) / 2
    print(f"Effet net visé (Iron Large à +{a.gain:g} dB) : {target:.1f} dB dans la zone d'air")
    print(f"Wet pur (drive 2) : réglage de courbe équivalent = +{g_wet:.1f} dB\n")

    jobs = [
        ("01_iron_auto",           lambda v, **k: excite_band(v, fs, mode="iron", source="auto", **kw, **k)),
        ("02_iron_band",           lambda v, **k: excite_band(v, fs, mode="iron", source="band", **kw, **k)),
        ("03_iron_large",          lambda v, **k: excite_band(v, fs, mode="iron", source="large", **kw, **k)),
        ("04_iron_WET_pur",        lambda v, **k: wet_band(v, fs, mode="iron", gain_db=g_wet, drive=2.0, **k)),
        ("05_iron_auto_desaccord", lambda v, **k: excite_band(v, fs, mode="iron", source="auto", spread_hz=15, **kw, **k)),
        ("06_iron_WET_desaccord",  lambda v, **k: wet_band(v, fs, mode="iron", gain_db=g_wet, drive=2.0, spread_hz=15, **k)),
        ("07_triode_auto",         lambda v, **k: excite_band(v, fs, mode="triode", source="auto", **kw, **k)),
        ("08_rect_auto",           lambda v, **k: excite_band(v, fs, mode="rect", source="auto", **kw, **k)),
        ("09_rect_auto_desaccord", lambda v, **k: excite_band(v, fs, mode="rect", source="auto", spread_hz=15, **kw, **k)),
    ]
    write("00_dry.wav", seg)
    for name, fn in jobs:
        y = per_channel(fn, seg)
        write(name + ".wav", y)
        if name in ("01_iron_auto", "04_iron_WET_pur", "05_iron_auto_desaccord"):
            write("delta_" + name[3:] + ".wav", y - seg)             # delta au niveau réel (pas de +12 dB)
        ym = y.mean(axis=1)
        net, add, rho = zone_stats(m, ym, fs, lo, hi)
        print(f"{name:26s} net {net:5.1f} dB   ajout {add:6.1f} dB")
    print(f"\nRendus dans {out_dir}/ (tous abaissés de 9 dB ; delta_* = ajout réel, non amplifié)")


if __name__ == "__main__":
    main()
