import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
import prisme_exciter_stream as ES
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = np.ascontiguousarray(x[int(30 * fs): int(40 * fs), 0])
def stats(y):
    y = y[int(1 * fs):]
    e = np.sort(y ** 2)[::-1]
    return np.max(np.abs(y)) / np.sqrt(np.mean(y ** 2)), 100 * e[: len(e) // 100].sum() / e.sum(), 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
VAR = [("réf", {}), ("10 ms .05/+40", dict(env_tau=0.01, gmin=0.05, gmax_db=40.0)), ("10 ms .1/+40", dict(env_tau=0.01, gmin=0.1, gmax_db=40.0)), ("10 ms .3/+40", dict(env_tau=0.01, gmin=0.3, gmax_db=40.0)),
       ("10 ms .05/+30", dict(env_tau=0.01, gmin=0.05, gmax_db=30.0)), ("10 ms .05/+50", dict(env_tau=0.01, gmin=0.05, gmax_db=50.0)), ("20 ms .05/+40", dict(env_tau=0.02, gmin=0.05, gmax_db=40.0)),
       ("5 ms .05/+40", dict(env_tau=0.005, gmin=0.05, gmax_db=40.0))]
for sh, f0, mode in (("bell", 3000.0, "iron"), ("bell", 1000.0, "iron"), ("highshelf", 9600.0, "iron"), ("lowshelf", 120.0, "iron"), ("bell", 3000.0, "triode")):
    print(f"\n{sh} {f0:.0f} Hz +2,4 dB {mode}")
    for nom, kw in VAR:
        y = ES.exciter_stream(x, fs, shape=sh, f0=f0, q=0.71, gain_db=2.4, mode=mode, source="auto", **kw)
        c, t, l = stats(y)
        print(f"  {nom:16s} crête/RMS {c:6.1f}   1 % forts {t:5.1f} %   niveau {l:6.1f} dB")
