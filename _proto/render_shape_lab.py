import sys, os, numpy as np
sys.path.append("_libs")
import soundfile as sf
import shape_detect_lab as lab
D = "C:/Users/llg53/Desktop/FL Studio/FL Studio/Audio/Rendered/"
OUT = "renders/shape_lab"; os.makedirs(OUT, exist_ok=True)
FILES = {"Track1": "Track 1 (consolidated)_35.wav", "Track3": "Track 3 (consolidated)_12.wav", "Track5": "Track 5 (consolidated)_7.wav"}
ZONES = [(200.0, 9.0), (5000.0, 9.0)]            # deux bandes « Transitoires » +9 dB (cloches 200 Hz et 5 kHz, Q 0,7)
A = lambda g: 10 ** (g / 20)
for tag, nm in FILES.items():
    x, fs = sf.read(D + nm); x = x[:int(16 * fs)]
    m = x.mean(1)
    cache = lab.bands_B(m, fs)
    variants = {"A_v4_defaut": None, "A_v4_tenue30ms": None, "B_flux_anticip4ms": None}
    for v in variants: variants[v] = np.zeros_like(x)
    for f0, g in ZONES:
        sA, bz = lab.strength_A(m, fs, "bell", f0, 0.7); sB = lab.strength_B(m, fs, "bell", f0, 0.7, cache=cache)
        from prisme_band import zone_filter
        from scipy.signal import lfilter
        bs = np.stack([lfilter(*zone_filter("bell", fs, f0, 0.7), x[:, c]) for c in range(2)], axis=1)
        ws = {"A_v4_defaut": lab.weights(sA, fs, 2.35, 4.0, f0, time_ms=None),
              "A_v4_tenue30ms": lab.weights(sA, fs, 2.35, 4.0, f0, time_ms=30.0),
              "B_flux_anticip4ms": lab.weights(sB, fs, 2.0, 2.0, f0, time_ms=30.0, look_ms=4.0)}
        for v, w in ws.items():
            variants[v] += ((A(g) - 1.0) * w)[:, None] * bs
    outs = {"original": x, **{v: x + d for v, d in variants.items()}}
    peak = max(np.abs(o).max() for o in outs.values()); k = 0.95 / max(peak, 1e-9) if peak > 0.95 else 1.0
    for v, o in outs.items():
        sf.write("%s/%s_%s.wav" % (OUT, tag, v), (o * k).astype(np.float32), fs, subtype="FLOAT")
    print(tag, "ok, gain commun %.3f" % k)
