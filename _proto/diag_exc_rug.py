import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
import prisme_exciter_stream as ES
from render import load
from bench_leak import SRC
from bench_quality import rugosite
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = np.ascontiguousarray(x[int(30 * fs): int(38 * fs), 0])
print("rugosité du delta (bell 3 kHz +2,4 dB, Auto) — plus bas = plus lisse")
for mode in ("iron", "triode", "diode", "classa", "rect"):
    row = []
    for qs in (2.0, 4.0, 8.0):
        y = ES.exciter_stream(x, fs, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode=mode, source="auto", src_q=qs)
        row.append(f"src_q {qs:.0f}: {rugosite(y[int(fs):], fs):.2f}")
    print(f"  {mode:7s} " + "   ".join(row))
