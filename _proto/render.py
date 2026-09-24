"""Rendus comparatifs PRISME sur un fichier réel (WAV ou MP3) — étape 1 : bande Exciter, cloche.

    python render.py "chemin\\vers\\mix.mp3" [--start S] [--dur 20] [--f0 12000] [--gain 6]

Écrit dans renders/<nom>_<start>s/ : dry, un rendu par (mode, source) en phase normale et « _q »
(injection en quadrature), et un fichier « delta » (ce que l'exciter ajoute, seul, +12 dB).
Tous les fichiers sont abaissés de 9 dB de la même quantité (marge, A/B relatif conservé).
Stéréo : chaque canal traité séparément (adaptatif non lié, à corriger plus tard).
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from prisme_band import excite_band
from bench_band import zone_stats, localisation

sys.stdout.reconfigure(encoding="utf-8")


def load(path):
    if path.lower().endswith((".mp3", ".flac", ".ogg")):
        import soundfile as sf
        x, sr = sf.read(path, always_2d=False)
        return sr, x.astype(np.float64)
    sr, x = wavfile.read(path)
    if x.dtype == np.int16:
        x = x / 32768.0
    elif x.dtype == np.int32:
        x = x / 2147483648.0
    elif x.dtype == np.uint8:
        x = (x - 128) / 128.0
    return sr, x.astype(np.float64)


def process(x, fs, **kw):
    if x.ndim == 1:
        return excite_band(x, fs, **kw)
    return np.stack([excite_band(x[:, c], fs, **kw) for c in range(x.shape[1])], axis=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=20.0)
    ap.add_argument("--f0", type=float, default=12000.0)
    ap.add_argument("--gain", type=float, default=6.0)
    ap.add_argument("--q", type=float, default=2.0)
    ap.add_argument("--sections", type=int, default=2)
    ap.add_argument("--drive", type=float, default=1.5)
    ap.add_argument("--noquad", action="store_true")
    a = ap.parse_args()

    fs, x = load(a.audio)
    seg = x[int(a.start * fs): int((a.start + a.dur) * fs)]
    name = os.path.splitext(os.path.basename(a.audio))[0]
    name = "".join(c if c.isalnum() else "_" for c in name)[:40]
    out_dir = os.path.join("renders", f"{name}_{int(a.start)}s_q{a.q:g}_s{a.sections}_g{a.gain:g}")
    os.makedirs(out_dir, exist_ok=True)
    pad = 10 ** (-9 / 20)

    def write(fn, y):
        wavfile.write(os.path.join(out_dir, fn), int(fs), (y * pad).astype(np.float32))

    write("00_dry.wav", seg)
    lo, hi = a.f0 / np.sqrt(2), a.f0 * np.sqrt(2)
    mseg = seg.mean(axis=1) if seg.ndim == 2 else seg
    print(f"{os.path.basename(a.audio)} {a.start:.0f}–{a.start + a.dur:.0f} s, {fs} Hz — cloche {a.f0:.0f} Hz Q {a.q:g} (sortie {a.sections} section(s)) +{a.gain} dB, "
          f"zone {lo:.0f}–{hi:.0f} Hz, drive {a.drive}, norm zone, ADAA×2")
    print(f"{'rendu':18s}{'gain net':>9s}{'ajout':>8s}{'corrél.':>9s}{'% zone':>8s}   (dB rel. contenu de la zone ; corrél. ajout/original)")
    jobs = [(m_, "auto") for m_ in ("triode", "diode", "iron", "classa", "rect")] + [("iron", "band"), ("iron", "large")]
    phases = ("none",) if a.noquad else ("none", "quad")
    for k, (mode, src) in enumerate(jobs, start=1):
        for ph in phases:
            y = process(seg, fs, f0=a.f0, q=a.q, out_sections=a.sections, gain_db=a.gain, mode=mode, source=src, drive=a.drive,
                        oversample=2, norm="zone", phase=ph)
            ym = y.mean(axis=1) if y.ndim == 2 else y
            tag = "" if ph == "none" else "_q"
            write(f"{k:02d}_{mode}_{src}{tag}.wav", y)
            if (mode, src, ph) == ("iron", "auto", "none"):
                write("delta_iron_auto.wav", (y - seg) * 4.0)
            net, add, rho = zone_stats(mseg, ym, fs, lo, hi)
            print(f"{mode + '_' + src + tag:18s}{net:9.1f}{add:8.1f}{rho:9.2f}{localisation(mseg, ym, fs, lo, hi):7.0f}%")
    print(f"\nRendus dans {out_dir}/")


if __name__ == "__main__":
    main()
