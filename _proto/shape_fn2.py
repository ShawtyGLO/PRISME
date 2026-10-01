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

