import sys, numpy as np
sys.path.append("_libs")
import soundfile as sf
from scipy.signal import butter, sosfilt, lfilter
R="renders/shape_lab/"
for tag in ("Track1","Track3","Track5"):
    o,fs=sf.read(R+tag+"_original.wav"); lo=sosfilt(butter(4,[40,250],"band",fs=fs,output="sos"),o.mean(1))
    w=int(.01*fs); env=np.sqrt(np.convolve(lo**2,np.ones(w)/w,"same")); db=20*np.log10(env+1e-9)
    # reprises après silence : niveau < max-45 dB pendant >=120 ms puis remontée
    low=db<db.max()-45; ons=[]; i=0
    while i<len(db)-int(.5*fs):
        if low[i:i+int(.12*fs)].all():
            j=i+int(.12*fs)
            while j<len(db) and low[j]: j+=1
            if j<len(db)-int(.5*fs): ons.append(j)
            i=j+int(.3*fs)
        else: i+=int(.01*fs)
    print("\n##",tag,"reprises de basse après silence :",len(ons),"(à %s s)"%", ".join("%.1f"%(k/fs) for k in ons[:8]))
    for v in ("A_v4_defaut","A_v4_tenue30ms","B_flux_anticip4ms"):
        y,_=sf.read(R+"%s_%s.wav"%(tag,v)); ly=sosfilt(butter(4,[40,250],"band",fs=fs,output="sos"),y.mean(1))
        ey=np.sqrt(np.convolve(ly**2,np.ones(w)/w,"same")); g=20*np.log10((ey+1e-9)/(env+1e-9))
        rows=[]
        for t0,t1 in ((0,.01),(.01,.03),(.03,.08),(.08,.2),(.2,.5)):
            rows.append(np.mean([g[k+int(t0*fs):k+int(t1*fs)].mean() for k in ons]) if ons else np.nan)
        print("  %-18s écart de niveau (dB, 40–250 Hz) après la reprise : 0–10 ms %+.1f | 10–30 %+.1f | 30–80 %+.1f | 80–200 %+.1f | 200–500 %+.1f"%((v,)+tuple(rows)))
