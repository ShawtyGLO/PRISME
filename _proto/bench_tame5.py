import time, numpy as np, prisme_tame as v4, prisme_tame5 as v5
fs=48000; rng=np.random.default_rng(1); x=rng.standard_normal(fs*8)*0.1
cfg=[dict(f0=f,q=0.7,gain_db=-9.0,width=0.5) for f in (120,400,1200,3500,9000)]
t=time.time(); ana=v5.AnalysePartagee(fs); outs=[]
for i in range(0,len(x),8192): outs.append(ana.process(x[i:i+8192]))
ta=time.time()-t; print("analyse partagée: %.2f s"%ta)
bands=[v5.TameP(fs,ana.f,"bell",c['f0'],c['q'],c['gain_db'],c['width'],4.5) for c in cfg]
tb=[]
for b in bands:
    t=time.time()
    ana2=None
    for k,i in enumerate(range(0,len(x),8192)): b.process(x[i:i+8192],outs[k])
    tb.append(time.time()-t)
print("TameP par bande: ",["%.2f"%v for v in tb])
t4=[]
for c in cfg:
    t=time.time(); v4.tame_band(x,fs,"bell",c['f0'],c['q'],c['gain_db'],c['width']); t4.append(time.time()-t)
print("v4 par bande:    ",["%.2f"%v for v in t4])
for n in (1,3,5): print(n,"bandes : v4 %.2f s | v5 %.2f s"%(sum(t4[:n]),ta+sum(tb[:n])))
y4=v4.tame_band(x,fs,"bell",1200,0.7,-9.0,0.5); y5=v5.tame_band(x,fs,"bell",1200,0.7,-9.0,0.5)
print("écart v5-v4 / RMS delta v4 : %.1f dB"%(20*np.log10(np.sqrt(np.mean((y5-y4)**2))/np.sqrt(np.mean((y4-x)**2)))))
