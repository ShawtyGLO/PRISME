import sys, os
sys.path.append("_libs")
import numpy as np
os.environ.setdefault("TEST_DUR", "4")
import tests_tame as T
from prisme_tame import tame_band
sys.stdout.reconfigure(encoding="utf-8")
fs = 48000.0
print("Position : réduction du pic selon sa fréquence (largeur 1,0, −9 dB), et niveau de réduction dans la bande (moyenne temporelle)")
for u in np.linspace(-0.25, 0.25, 9):
    f = 3000.0 * 2 ** u
    xs = T.sig(fs, res=(f,), dur=4)
    y, d = tame_band(xs, fs, gain_db=-9.0, width=1.0, diag=True, **T.KW)
    k = int(np.argmin(np.abs(d["f"] - f)))
    print(f"  f = {f:7.1f} Hz (u={u:+.3f}) : réduction {T.reduc(xs, y, fs, f):+5.1f} dB ; red_full à la bande la plus proche : moy {d['red_full'][k].mean():.1f} max {d['red_full'][k].max():.1f} dB")
print("\nBruit rose seul : fraction du temps où la réduction dépasse 0,5 dB, par largeur")
xn = T.sig(fs, res=(), dur=4)
for wd in (1.0, 0.5, 0.0):
    y, d = tame_band(xn, fs, gain_db=-9.0, width=wd, diag=True, **T.KW)
    r = d["red_full"]
    print(f"  largeur {wd}: {100*np.mean(r > 0.5):.1f} % des cellules temps-bande ; réduction moyenne {r.mean():.2f} dB ; max {r.max():.1f} dB")
