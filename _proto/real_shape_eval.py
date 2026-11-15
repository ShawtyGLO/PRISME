import sys, time, numpy as np
sys.path.append("_libs")
import soundfile as sf
from scipy.signal import stft
from scipy.ndimage import median_filter
import shape_detect_lab as lab
from prisme_tame5 import _zone_lo_hi

D = "C:/Users/llg53/Desktop/FL Studio/FL Studio/Audio/Rendered/"
FILES = ["Track 1 (consolidated)_35.wav", "Track 3 (consolidated)_12.wav", "Track 5 (consolidated)_7.wav"]
SEG = float(sys.argv[1]) if len(sys.argv) > 1 else 16.0


def pseudo_onsets(m, fs, lo, hi):
    """Référence indépendante : séparation harmonique/percussif hors ligne (médianes sur spectrogramme) ; attaques = fortes montées de l'énergie PERCUSSIVE de la zone."""
    nper, hop = 1024, 128
    fr, tt, Z = stft(m, fs, nperseg=nper, noverlap=nper - hop)
    P = np.abs(Z) ** 2
    H = median_filter(P, size=(1, 17)); Pc = median_filter(P, size=(17, 1))
    mp = Pc ** 2 / (H ** 2 + Pc ** 2 + 1e-30)
    Pp = P * mp
    k = (fr >= lo) & (fr <= hi)
    Ep = 10 * np.log10(Pp[k].sum(0) + 1e-14); Et = 10 * np.log10(P[k].sum(0) + 1e-14)
    frac = Pp[k].sum(0) / (P[k].sum(0) + 1e-14)
    lag = 6
    rise = np.concatenate([np.zeros(lag), Ep[lag:] - Ep[:-lag]])
    ok = (rise > 6.0) & (frac > 0.5) & (Et > Et.max() - 60)
    on = []
    last = -1
    for i in np.where(ok)[0]:
        if last < 0 or tt[i] - last > 0.06:
            j = i + np.argmax(Ep[i:i + 8] - 0)               # pic proche
            on.append(tt[i]); last = tt[i]
    return np.array(on)


def edges(w, fs, thr=0.5, refrac=0.05):
    up = np.where((w[1:] >= thr) & (w[:-1] < thr))[0] / fs
    out = []
    for u in up:
        if not out or u - out[-1] > refrac: out.append(u)
    return np.array(out)


def fscore(det, ref, tol=0.02):
    if len(det) == 0 or len(ref) == 0: return 0.0, 0.0, 0.0
    tp_d = sum(np.min(np.abs(ref - d)) <= tol for d in det); tp_r = sum(np.min(np.abs(det - r)) <= tol for r in ref)
    p, r = tp_d / len(det), tp_r / len(ref)
    return (2 * p * r / (p + r) if p + r else 0.0), p, r


for nm in FILES:
    x, fs = sf.read(D + nm); m = x.mean(1)[:int(SEG * fs)]
    print("\n##", nm, "(%d Hz, %.0f s)" % (fs, len(m) / fs))
    cacheB = lab.bands_B(m, fs)
    for fz, nz in ((60.0, "60 Hz"), (200.0, "200 Hz"), (1000.0, "1 kHz"), (5000.0, "5 kHz")):
        lo, hi = _zone_lo_hi("bell", fz, 0.7, fs, 0.5)
        ref = pseudo_onsets(m, fs, lo, hi)
        sA, bz = lab.strength_A(m, fs, "bell", fz, 0.7); sB = lab.strength_B(m, fs, "bell", fz, 0.7, cache=cacheB)
        sC = lab.strength_C(m, fs, "bell", fz, 0.7, b=bz)
        print(" zone bell %s : %d attaques de référence (HPSS hors ligne, %.1f /s)" % (nz, len(ref), len(ref) / (len(m) / fs)))
        for k, s, g, wd in (("A", sA, [2, 3, 4, 6, 8, 10, 12], 4.0), ("B", sB, [0.5, 1, 1.5, 2, 3, 4, 6], 2.0), ("C", sC, [2, 4, 6, 8, 10, 14, 18, 24], 4.0), ("D", np.sqrt(np.maximum(sB, 0) * np.maximum(sC, 0) / 3.0), [0.5, 0.8, 1, 1.5, 2, 3, 4], 2.0)):
            best = max(((fscore(edges(lab.weights(s, fs, m0, wd, fz, time_ms=30.0), fs), ref), m0) for m0 in g), key=lambda z: z[0][0])
            (f1, p, r), m0 = best
            print("    %s (m0 %-4s) : F %.2f  (précision %.2f, rappel %.2f)" % (k, m0, f1, p, r))
