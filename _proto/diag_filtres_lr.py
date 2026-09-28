"""Filtres de bande à phase COMPENSÉE : Linkwitz-Riley sur le delta + le passe-tout correspondant sur le sec et sur les deltas des autres bandes.
   y = AP(x) + Σ_i [ LR_i(delta_i) · Π_{j≠i} AP_j ]  = Π AP · (x + Σ m_i · delta_i)   → module exact, phase globale = passe-tout."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import freqz, butter, sosfreqz
from prisme_dsp import rbj_peaking
sys.stdout.reconfigure(encoding="utf-8")
fs = 48000
f = np.geomspace(30, 20000, 800)
w = 2 * np.pi * f / fs


def lr(kind, fc, ordre):                       # Linkwitz-Riley = Butterworth d'ordre ordre/2 au carré
    sos = butter(ordre // 2, fc, btype="highpass" if kind == "bas" else "lowpass", fs=fs, output="sos")
    H = sosfreqz(sos, worN=w)[1] ** 2
    Lsos = butter(ordre // 2, fc, btype="lowpass" if kind == "bas" else "highpass", fs=fs, output="sos")
    Lc = sosfreqz(Lsos, worN=w)[1] ** 2
    sgn = -1.0 if ordre == 4 and False else 1.0
    AP = H + Lc if ordre == 4 else H - Lc     # LR2 : HP − LP = passe-tout ; LR4 : HP + LP = passe-tout
    return (H if ordre == 4 else H), AP, (1.0 if ordre == 4 else 1.0)


for g in (+6.0, -9.0):
    b, a = rbj_peaking(fs, 1000.0, g, 0.71)
    D = freqz(b, a, worN=w)[1] - 1.0
    for kind, fc in (("bas", 1000.0), ("haut", 1000.0), ("bas", 500.0)):
        for ordre, pente in ((2, 12), (4, 24)):
            H, AP, _ = lr(kind, fc, ordre)
            if ordre == 2:
                H = H if kind == "haut" else H    # LR2 : on garde la polarité telle que H/AP soit réel positif
                r = H / AP
                if np.median(r.real) < 0: H = -H
            reel = np.abs(AP + H * D)                        # |AP·x + LR(delta)| pour x = 1
            m = np.abs(H / AP)
            ideal = np.abs(1 + D * m)
            print(f"  bande {g:+.0f} dB à 1 kHz, coupe-{kind} {fc:.0f} Hz {pente} dB/oct : écart réel − idéal {np.max(np.abs(20*np.log10(reel) - 20*np.log10(ideal))):.3f} dB ; H/AP réel ? {np.max(np.abs((H/AP).imag)):.1e}")
