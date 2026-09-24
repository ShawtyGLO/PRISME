import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from bench_tame import signal, FS, pic_db
from prisme_tame import tame_band
sys.stdout.reconfigure(encoding="utf-8")
x = signal()
for wd in (1.0, 0.5):
    y, d = tame_band(x, FS, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=wd, diag=True)
    print(f"largeur {wd} : {len(d['f'])} bandes ; réduction obtenue à 3,1 kHz : {pic_db(y, 3100.0) - pic_db(x, 3100.0):+.1f} dB")
    k = np.argmin(np.abs(d["f"] - 3100.0))
    for i in range(max(0, k - 3), min(len(d["f"]), k + 4)):
        print(f"   bande {d['f'][i]:7.0f} Hz  poids {d['w'][i]:.2f}  S {d['S'][i]:.2f}  excès moyen {d['exces'][i]:5.2f} dB  réduction moyenne {d['red'][i]:6.2f} dB")
