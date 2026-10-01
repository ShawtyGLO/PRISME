import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, welch
import prisme_tame as PT
sys.stdout.reconfigure(encoding="utf-8")
fs=48000; rng=np.random.default_rng(2); n=fs*5; t=np.arange(n)/fs
base=lfilter([0.049922035,-0.095993537,0.050612699,-0.004408786],[1,-2.494956002,2.017265875,-0.522189400],rng.standard_normal(n))*0.05
def niv(v,f):
    fr,P=welch(v,fs,nperseg=16384); s=(fr>f*.98)&(fr<f*1.02); return 10*np.log10(P[s].sum())
def testA(N):
    fr=np.geomspace(300,2200,N) if N>1 else np.array([800.0]); x=base.copy()
    for f in fr: x+=0.05*10**(12/20)*0.05*np.sin(2*np.pi*f*t+1.3*f)
    y,d=PT.tame_band(x,fs,"bell",800.0,0.5,-9.0,0.5,diag=True)
    R=d["red_full"][:,fs:].mean(axis=1)
    # réduction CALCULÉE rapportée au poids de zone (détection pure)
    return [(-float(R[np.argmin(np.abs(d["f"]-f))]) / max(float(d["w"][np.argmin(np.abs(d["f"]-f))]),1e-3)) for f in fr]
for pct in (30, 15, 10):
    for octv in (1.0, 2.0):
        PT.V4_PCT, PT.V4_OCT = pct, octv
        r8 = testA(8); r1 = testA(1)
        print(f"pct {pct:2d} fenêtre ±{octv/2:.1f} oct : 1 résonance {r1[0]:+.1f} ; 8 résonances (détection/zone) {np.round(r8,1)}")
