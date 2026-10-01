import sys, os, numpy as np
sys.path.append("_libs")
import soundfile as sf
from scipy.signal import lfilter
import shape_detect_lab as lab
from shape_fn2 import strength_Bcap, adaptif, D
from prisme_band import zone_filter
OUT = "renders/shape_lab_D"; os.makedirs(OUT, exist_ok=True)
FILES = {"Track1": "Track 1 (consolidated)_35.wav", "Track3": "Track 3 (consolidated)_12.wav", "Track5": "Track 5 (consolidated)_7.wav"}
LAYOUTS = {"D_cloche_large_200Hz": [(200.0, 0.7), (5000.0, 0.7)], "D_cloche_fine_pied_88Hz": [(88.0, 3.0), (5000.0, 0.7)]}
A9 = 10 ** (9.0 / 20)
for tag, nm in FILES.items():
    x, fs = sf.read(D + nm); x = x[:int(16 * fs)]; m = x.mean(1); cache = lab.bands_B(m, fs)
    outs = {"original": x}
    for lay, zones in LAYOUTS.items():
        y = x.copy()
        for f0, q in zones:
            sA, bz = lab.strength_A(m, fs, "bell", f0, q); sB = strength_Bcap(m, fs, f0, None, cache); sC = lab.strength_C(m, fs, "bell", f0, q, b=bz)
            sD = np.sqrt(np.maximum(sB, 0) * np.maximum(sC, 0) / 3.0)
            w = lab.weights(sD, fs, np.maximum(1.0, adaptif(sD, fs)), 2.0, f0, time_ms=30.0, look_ms=4.0)
            bs = np.stack([lfilter(*zone_filter("bell", fs, f0, q), x[:, c]) for c in range(2)], axis=1)
            y += ((A9 - 1.0) * w)[:, None] * bs
        outs[lay] = y
    old, _ = sf.read("renders/shape_lab/%s_A_v4_tenue30ms.wav" % tag); outs["A_v4_tenue30ms_ref"] = old
    peak = max(np.abs(o).max() for k, o in outs.items() if k != "A_v4_tenue30ms_ref"); k = 0.95 / peak if peak > 0.95 else 1.0
    for v, o in outs.items():
        if v == "A_v4_tenue30ms_ref": continue
        sf.write("%s/%s_%s.wav" % (OUT, tag, v), (o * k).astype(np.float32), fs, subtype="FLOAT")
    print(tag, "ok (gain commun %.3f)" % k)
