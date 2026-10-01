import sys, numpy as np
sys.path.append("_libs")
import soundfile as sf
import shape_detect_lab as lab
from shape_fn2 import strength_Bcap, adaptif, pseudo_onsets, edges, fscore, D
for tag, nm in (("Track1", "Track 1 (consolidated)_35.wav"), ("Track5", "Track 5 (consolidated)_7.wav")):
    x, fs = sf.read(D + nm); m = x.mean(1)[:int(16 * fs)]
    cache = lab.bands_B(m, fs); ref = pseudo_onsets(m, fs, 60.0, 130.0)
    print("## %s : %d attaques de pied (référence HPSS 60–130 Hz)" % (tag, len(ref)))
    for f0, q in ((88.0, 0.7), (88.0, 2.0), (88.0, 4.0), (200.0, 0.7)):
        sA, bz = lab.strength_A(m, fs, "bell", f0, q); sB = strength_Bcap(m, fs, f0, None, cache)
        sC = lab.strength_C(m, fs, "bell", f0, q, b=bz); sD = np.sqrt(np.maximum(sB, 0) * np.maximum(sC, 0) / 3.0)
        for nmv, s, m0, wd in (("A", sA, 2.35, 4.0), ("B", sB, 2.0, 2.0), ("D", sD, 1.0, 2.0), ("D+adapt", sD, np.maximum(1.0, adaptif(sD, fs)), 2.0)):
            w = lab.weights(s, fs, m0, wd, f0, time_ms=30.0); f1, p, r = fscore(edges(w, fs), ref)
            print("  bell %3.0f Hz Q %.1f  %-8s actif %2.0f %% | précision %.2f rappel %.2f (F %.2f) | poids 1–2,5 s %.2f" % (f0, q, nmv, 100 * (w > .5).mean(), p, r, f1, w[int(1 * fs):int(2.5 * fs)].mean()))
