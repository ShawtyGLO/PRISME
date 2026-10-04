import sys, os, numpy as np
sys.path.append("_libs")
import soundfile as sf
from prisme_lift import lift_band
from prisme_lift_rel import lift_rel_band
D = "C:/Users/llg53/Desktop/FL Studio/FL Studio/Audio/Rendered/"
OUT = "renders/lift_rel"; os.makedirs(OUT, exist_ok=True)
FILES = {"Track1": "Track 1 (consolidated)_35.wav", "Track3": "Track 3 (consolidated)_12.wav", "Track5": "Track 5 (consolidated)_7.wav"}
BANDES = [("bell", 3000.0, 0.7, 9.0), ("bell", 250.0, 0.7, 6.0)]            # « détail » aigu-médium et corps grave, Amount 50 %
for tag, nm in FILES.items():
    x, fs = sf.read(D + nm); x = x[:int(20 * fs)]
    outs = {"original": x}
    for nom, fn in (("lift_absolu_v4", lambda s, sh, f0, q, g: lift_band(s, fs, sh, f0, q, g, 50.0, 150.0)),
                    ("lift_relatif", lambda s, sh, f0, q, g: lift_rel_band(s, fs, sh, f0, q, g, 50.0, 150.0))):
        y = x.copy()
        for sh, f0, q, g in BANDES:
            for c in range(2):
                y[:, c] += fn(x[:, c], sh, f0, q, g) - x[:, c]
        outs[nom] = y
    peak = max(np.abs(o).max() for o in outs.values()); k = 0.95 / peak if peak > 0.95 else 1.0
    for nom, o in outs.items():
        sf.write("%s/%s_%s.wav" % (OUT, tag, nom), (o * k).astype(np.float32), fs, subtype="FLOAT")
    da, dr = outs["lift_absolu_v4"] - x, outs["lift_relatif"] - x
    e = lambda d: 20 * np.log10(np.sqrt(np.mean(d ** 2)) / np.sqrt(np.mean(x ** 2)))
    print(tag, "ajout (dB sous le signal) : absolu %.1f | relatif %.1f ; gain commun %.3f" % (e(da), e(dr), k))
