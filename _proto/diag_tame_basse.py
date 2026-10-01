import sys, numpy as np
sys.path.append("_libs")
import soundfile as sf
from scipy.signal import welch
import prisme_tame as t4
D="C:/Users/llg53/Desktop/FL Studio/FL Studio/Audio/Rendered/"
for tag,nm in (("Track5","Track 5 (consolidated)_7.wav"),("Track3","Track 3 (consolidated)_12.wav")):
    x,fs=sf.read(D+nm); m=x.mean(1)[int(2*fs):int(14*fs)]
    for f0,q,wd in ((120.0,12.0,0.5),(120.0,12.0,0.1),(120.0,8.0,0.5),(1000.0,12.0,0.5)):
        y=t4.tame_band(m,fs,"bell",f0,q,-9.0,wd)
        fr,Px=welch(m,fs,nperseg=16384); _,Pd=welch(y-m,fs,nperseg=16384)
        out=[]
        for fc in (30,40,60,80,120,160,240,320,480,700,1000,1500,2200):
            k=(fr>=fc/2**(1/6))&(fr<fc*2**(1/6))
            out.append("%d:%+.0f"%(fc,10*np.log10(Pd[k].sum()/Px[k].sum()+1e-12)))
        print(tag,"bell %d Hz Q %.0f largeur %.1f — niveau du delta par rapport à l'entrée (dB, tiers d'octave) : %s"%(f0,q,wd," ".join(out)))
