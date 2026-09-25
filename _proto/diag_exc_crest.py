"""Diagnostic : « crépitement » de l'Exciter selon la fréquence — crête/RMS du delta, part de l'énergie portée par les 1 % d'échantillons les plus forts."""
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
    top = e[: len(e) // 100].sum() / e.sum()
    return np.max(np.abs(y)) / np.sqrt(np.mean(y ** 2)), 100 * top, 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)


print(f"{'réglage':44s} crête/RMS  énergie des 1 % + forts  niveau delta")
for sh, f0 in (("bell", 250.0), ("bell", 1000.0), ("bell", 3000.0), ("bell", 8000.0), ("bell", 12000.0)):
    for mode in ("iron", "triode"):
        y = ES.exciter_stream(x, fs, shape=sh, f0=f0, q=0.71, gain_db=2.4, mode=mode, source="auto")
        c, t, l = stats(y)
        print(f"{sh:5s} {f0:6.0f} Hz +2,4 dB {mode:7s}                  {c:6.1f}   {t:6.1f} %              {l:6.1f} dB")
print("\nVariantes sur bell 3 kHz Iron :")
for nom, kw in (("référence (τ norm 0,2 s)", {}), ("norm 0,05 s", dict(norm_tau=0.05)), ("norm 0,02 s", dict(norm_tau=0.02)), ("norm 0,6 s", dict(norm_tau=0.6))):
    y = ES.exciter_stream(x, fs, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode="iron", source="auto", **kw)
    c, t, l = stats(y)
    print(f"  {nom:28s} crête/RMS {c:6.1f}   1 % forts : {t:5.1f} %   niveau {l:6.1f} dB")
