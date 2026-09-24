"""Qualité perçue (étape 1b) : rugosité tonale du delta et fidélité aux transitoires.

  rugosité  : écart-type (dB) entre le spectre fin du delta et son enveloppe lissée (300 Hz),
              8,5–16 kHz. Plus c'est grand, plus le delta est fait de RAIES (impression de résonance).
              Référence : la même mesure sur le signal sec.
  transitoires : corrélation entre les fronts montants de l'enveloppe HF (8,5–17 kHz) du sec et du
              delta. 1 = le delta suit les percussions ; bas = il les étale (« liquide »).
"""
import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import welch, butter, sosfilt
from scipy.ndimage import uniform_filter1d
from prisme_band import excite_band
from render import load
from bench_band import zone_stats, localisation

sys.stdout.reconfigure(encoding="utf-8")


def rugosite(x, fs, lo=8500, hi=16000, nper=16384):
    f, P = welch(x, fs, nperseg=nper, noverlap=nper // 2)
    db = 10 * np.log10(P + 1e-30)
    sm = uniform_filter1d(db, size=max(int(300 / (fs / nper)), 3))
    m = (f >= lo) & (f <= hi)
    return float(np.std((db - sm)[m]))


def fronts(x, fs):
    bp = butter(4, [8500, 17000], btype="band", fs=fs, output="sos")
    lp = butter(2, 500, btype="low", fs=fs, output="sos")
    env = sosfilt(lp, np.abs(sosfilt(bp, x)))
    return np.maximum(np.diff(env), 0.0)


def transitoires(dry, delta, fs):
    a, b = fronts(dry, fs), fronts(delta, fs)
    return float(np.corrcoef(a, b)[0, 1])


def run(path, start=30.0, dur=20.0, gain=6.0, q=2.0, scale=1.0):
    fs, x = load(path)
    x = x * scale
    seg = x[int(start * fs): int((start + dur) * fs)]
    m = seg.mean(axis=1) if seg.ndim == 2 else seg
    lo, hi = 12000 / np.sqrt(2), 12000 * np.sqrt(2)
    print(f"{os.path.basename(path)} {start:.0f}–{start + dur:.0f} s, cloche 12 kHz Q {q:g}, +{gain} dB")
    print(f"rugosité du sec (8,5–16 kHz) : {rugosite(m, fs):.2f} dB\n")
    print(f"{'rendu':22s}{'net':>6s}{'% zone':>8s}{'rugosité':>10s}{'transit.':>10s}")
    for mode in ("iron", "rect"):
        for src in ("auto", "large"):
            for tag, nt in (("", 0.2), ("+t50ms", 0.05), ("+t10ms", 0.01)):
                y = excite_band(m, fs, f0=12000.0, q=q, gain_db=gain, mode=mode, source=src, drive=1.5,
                                oversample=2, norm="zone", norm_tau=nt)
                d = y - m
                net, add, rho = zone_stats(m, y, fs, lo, hi)
                print(f"{mode + '_' + src + tag:22s}{net:6.1f}{localisation(m, y, fs, lo, hi):7.0f}%"
                      f"{rugosite(d, fs):10.2f}{transitoires(m, d, fs):10.2f}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run(sys.argv[1])
    else:   # tranche 30-50 s SANS clipper, conservée dans les rendus (abaissée de 9 dB -> on remonte)
        run(os.path.join("renders", "___Test_PRISME_VST_231_L0V3MUSI__125_BPM_30s_q2_s2", "00_dry.wav"),
            start=0.0, dur=20.0, scale=10 ** (9 / 20))
