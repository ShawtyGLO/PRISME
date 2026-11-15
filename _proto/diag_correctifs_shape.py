import sys, numpy as np
sys.path.append("_libs")
import soundfile as sf
from scipy.ndimage import maximum_filter1d, percentile_filter
import shape_detect_lab as lab
from prisme_tame5 import _zone_lo_hi
from shape_eval_fn import pseudo_onsets, edges, fscore   # (exécute aussi l'évaluation du module : on évite en important seulement les fonctions)

D="C:/Users/llg53/Desktop/FL Studio/FL Studio/Audio/Rendered/"
def strength_Bcap(m, fs, f0, cap=None, cache=None):
    f, idx, L = cache
    lo, hi = _zone_lo_hi("bell", f0, 0.7, fs, 1.5); c = np.where((f >= lo) & (f <= hi))[0]
    lag = max(2, int(round(np.clip(3.0 / f0, 0.005, 0.03) * fs / lab.DEC)))
    ref = maximum_filter1d(np.concatenate([np.repeat(L[:, :1], lag, axis=1), L[:, :-lag]], axis=1), size=3, axis=0, mode="nearest")
    up = np.maximum(L - ref, 0.0)
    if cap: up = np.minimum(up, cap)
    s = np.maximum(up[c].mean(0), up[np.searchsorted(f, 60.0):].mean(0))
    return np.interp(np.arange(len(m)), idx, s)

def adaptif(s, fs, q=90, win=2.0):
    st = 64
    r = percentile_filter(s[::st], q, size=int(win * fs / st), mode="nearest")
    return np.repeat(r, st)[:len(s)]

for tag, nm in (("Track1", "Track 1 (consolidated)_35.wav"), ("Track5", "Track 5 (consolidated)_7.wav")):
    x, fs = sf.read(D + nm); m = x.mean(1)[:int(16 * fs)]
    cache = lab.bands_B(m, fs)
    for f0 in (200.0, 60.0):
        lo, hi = _zone_lo_hi("bell", f0, 0.7, fs, 0.5); ref = pseudo_onsets(m, fs, lo, hi)
        sA, bz = lab.strength_A(m, fs, "bell", f0, 0.7); sB = strength_Bcap(m, fs, f0, None, cache); sBc = strength_Bcap(m, fs, f0, 12.0, cache)
        sC = lab.strength_C(m, fs, "bell", f0, 0.7, b=bz); sD = np.sqrt(np.maximum(sB, 0) * np.maximum(sC, 0) / 3.0)
        print("##", tag, "zone bell %d Hz" % f0, "(%d attaques de référence)" % len(ref))
        variants = [("A actuel (m0 2,35)", sA, 2.35, 4.0), ("B actuel (m0 2)", sB, 2.0, 2.0), ("B + plafond de montée 12 dB", sBc, 2.0, 2.0),
                    ("B + seuil adaptatif (q90 / 2 s)", sB, np.maximum(2.0, adaptif(sB, fs)), 2.0), ("B + plafond + adaptatif", sBc, np.maximum(2.0, adaptif(sBc, fs)), 2.0),
                    ("D = B × résidu NLMS (veto tonal)", sD, 1.0, 2.0), ("D + adaptatif", sD, np.maximum(1.0, adaptif(sD, fs)), 2.0)]
        for nmv, s, m0, wd in variants:
            w = lab.weights(s, fs, m0, wd, f0, time_ms=30.0)
            f1, p, r = fscore(edges(w, fs), ref)
            print("  %-34s poids moyen %.2f | actif (>0,5) %2.0f %% du temps | précision %.2f rappel %.2f (F %.2f) | poids 1–2,5 s : %.2f" % (nmv, w.mean(), 100 * (w > 0.5).mean(), p, r, f1, w[int(1 * fs):int(2.5 * fs)].mean()))
