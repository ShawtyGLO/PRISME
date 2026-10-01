import sys, numpy as np, time
sys.path.append("_libs")
import soundfile as sf
import prisme_shape5 as s5
from shape_fn2 import pseudo_onsets, edges, fscore, D
fs = 44100
x, _ = sf.read(D + "Track 5 (consolidated)_7.wav"); m = x.mean(1)[:int(6 * fs)]
def run(blk, look=192):
    s = s5.Shape5(fs, "transitoires", "bell", 200.0, 0.7, 9.0, look=look)
    out = [s.process(m[i:i + blk]) for i in range(0, len(m), blk)]
    return np.concatenate(out)
y1, y2 = run(8192), run(777)
print("invariance au découpage en blocs : écart max %.2e" % np.abs(y1 - y2).max())
t0 = time.time(); run(8192); print("temps pour 6 s (Python) : %.1f s" % (time.time() - t0))
for nm, tag in (("Track 1 (consolidated)_35.wav", "Track1"), ("Track 5 (consolidated)_7.wav", "Track5")):
    xx, _ = sf.read(D + nm); mm = xx.mean(1)[:int(16 * fs)]
    s = s5.Shape5(fs, "transitoires", "bell", 200.0, 0.7, 9.0, look=0)
    Tl = np.concatenate([s.detecte(mm[i:i + 8192])[1] for i in range(0, len(mm), 8192)])
    ref = pseudo_onsets(mm, fs, 70.0, 560.0)
    f1, p, r = fscore(edges(Tl, fs), ref)
    print("%s zone 200 Hz : poids moyen %.2f | actif %.0f %% | précision %.2f rappel %.2f F %.2f | poids 1–2,5 s %.2f" % (tag, Tl.mean(), 100 * (Tl > .5).mean(), p, r, f1, Tl[int(1 * fs):int(2.5 * fs)].mean()))
