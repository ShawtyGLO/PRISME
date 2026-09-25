"""Variantes de l'AGC d'entrée de l'Exciter : le delta devient-il moins « crépitant » (crête/RMS, énergie des 1 % les plus forts) ?"""
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


VAR = [("référence", {}), ("AGC 5 ms", dict(env_tau=0.005)), ("AGC 2 ms", dict(env_tau=0.002)), ("AGC 2 ms, gain 0,1…+24", dict(env_tau=0.002, gmin=0.1)),
       ("AGC 2 ms, 0,05…+40 dB", dict(env_tau=0.002, gmin=0.05, gmax_db=40.0)), ("AGC 10 ms, 0,05…+40 dB", dict(env_tau=0.01, gmin=0.05, gmax_db=40.0)),
       ("AGC 2 ms, 0,05…+40 dB, drive 3", dict(env_tau=0.002, gmin=0.05, gmax_db=40.0, drive=3.0))]
for sh, f0 in (("bell", 3000.0), ("bell", 8000.0), ("bell", 250.0)):
    print(f"\n{sh} {f0:.0f} Hz +2,4 dB Iron Auto")
    for nom, kw in VAR:
        y = ES.exciter_stream(x, fs, shape=sh, f0=f0, q=0.71, gain_db=2.4, mode="iron", source="auto", **kw)
        c, t, l = stats(y)
        print(f"  {nom:34s} crête/RMS {c:6.1f}   1 % forts {t:5.1f} %   niveau {l:6.1f} dB")
