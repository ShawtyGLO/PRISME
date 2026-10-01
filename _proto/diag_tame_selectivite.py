import sys, numpy as np
from scipy.signal import welch, lfilter, iirpeak
import prisme_tame as t4
fs=48000; rng=np.random.default_rng(2); n=fs*12
pink=lfilter([0.049922035,-0.095993537,0.050612699,-0.004408786],[1,-2.494956002,2.017265875,-0.522189400],rng.standard_normal(n)); pink/=pink.std()
freqs=(60,85,120,170,240,480,1000)
x=pink*0.02
t=np.arange(n)/fs
for f in freqs:
    x=x+0.02*np.sin(2*np.pi*f*t)*(1+0.0*t)
def niveau(sig,f):
    fr,P=welch(sig,fs,nperseg=32768); k=(fr>=f/2**(1/24))&(fr<=f*2**(1/24)); return 10*np.log10(P[k].max()+1e-20)
print("résonances de bruit rose à", freqs, "Hz ; réduction mesurée (dB) à chaque fréquence, bande bell 120 Hz −9 dB")
for q,wd in ((2.0,0.5),(4.0,0.5),(6.0,0.5),(8.0,0.5),(10.0,0.5),(12.0,0.5)):
    y=t4.tame_band(x,fs,"bell",120.0,q,-9.0,wd)
    print("  Q %4.1f largeur %.1f : "%(q,wd)+"  ".join("%d Hz: %+.1f"%(f,niveau(y,f)-niveau(x,f)) for f in freqs))
