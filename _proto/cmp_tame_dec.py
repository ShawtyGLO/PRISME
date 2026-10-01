import sys, numpy as np
sys.path.append("_libs")
import soundfile as sf
import prisme_tame as a, prisme_tame_d32 as b
D="C:/Users/llg53/Desktop/FL Studio/FL Studio/Audio/Rendered/"
for tag,nm in (("Track1","Track 1 (consolidated)_35.wav"),("Track5","Track 5 (consolidated)_7.wav")):
    x,fs=sf.read(D+nm); m=x.mean(1)[int(2*fs):int(12*fs)]
    for sh,f0,q,g,wd in (("bell",3000.0,0.7,-9.0,0.5),("bell",120.0,4.0,-9.0,0.5),("highshelf",8000.0,0.7,-6.0,0.3),("lowshelf",150.0,0.7,-9.0,0.8)):
        ya=a.tame_band(m,fs,sh,f0,q,g,wd); yb=b.tame_band(m,fs,sh,f0,q,g,wd)
        da,db=ya-m,yb-m
        print(tag,sh,f0,q,wd,": delta v16 rms %.1f dBFS ; écart v32−v16 : %.1f dB sous le delta"%(20*np.log10(np.sqrt(np.mean(da**2))),20*np.log10(np.sqrt(np.mean((db-da)**2))/np.sqrt(np.mean(da**2)))))
