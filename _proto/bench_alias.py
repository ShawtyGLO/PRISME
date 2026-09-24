"""Bancs d'étape 0 : (1) identité cloche = 1 + (A²-1)·BP, (2) repliement naïf / ADAA / ×2 / ×4.

Repliement = énergie du résidu hors des multiples de f0 sous Nyquist, rapportée au fondamental
d'entrée (dB). Signal périodique, fenêtre centrale de 1 s (nombre entier de périodes).
"""
import sys
import numpy as np
from scipy.signal import freqz, lfilter
from prisme_dsp import MODES, excite_residual, rbj_peaking, rbj_bandpass0db

sys.stdout.reconfigure(encoding="utf-8")


def check_identity():
    fs = 48000.0
    worst = 0.0
    for gain_db in (-9.0, 6.0, 12.0):
        for q in (0.5, 1.0, 4.0):
            A = 10.0 ** (gain_db / 40.0)
            bp, ap = rbj_peaking(fs, 3000.0, gain_db, q)
            bb, ab = rbj_bandpass0db(fs, 3000.0, A * q)
            w, Hp = freqz(bp, ap, worN=4096, fs=fs)
            _, Hb = freqz(bb, ab, worN=4096, fs=fs)
            worst = max(worst, np.max(np.abs(Hp - (1.0 + (A * A - 1.0) * Hb))))
    print(f"Identité cloche = 1 + (A²-1)·BP : écart max |ΔH| = {worst:.2e}")


def alias_db(res, fs, f0):
    n = int(fs)
    seg = res[n : 2 * n]                     # 1 s, entier de périodes
    S = np.abs(np.fft.rfft(seg)) ** 2
    k_h = [m * int(f0) for m in range(1, int(fs / 2 / f0) + 1)]
    mask = np.ones_like(S, dtype=bool)
    for k in k_h:
        mask[max(k - 1, 0): k + 2] = False
    mask[:30] = False                        # continu résiduel
    fund_pow = (n / 2.0) ** 2                # sinus d'amplitude 1 -> |X|² = (n/2)²
    return 10 * np.log10(S[mask].sum() / fund_pow + 1e-30)


def bench(fs=44100.0, f0=6000, effs=(1.0, 3.0)):
    n = int(fs) * 3
    t = np.arange(n) / fs
    x = np.sin(2 * np.pi * f0 * t)
    print(f"\nRepliement du résidu (dB rel. fondamental d'entrée) — fs={fs:.0f} Hz, source {f0} Hz")
    head = f"{'mode':8s}{'niveau':>7s}" + "".join(f"{c:>13s}" for c in ("naïf", "ADAA", "naïf ×2", "ADAA ×2", "naïf ×8 (réf)"))
    print(head)
    for name in MODES:
        for eff in effs:
            row = []
            for adaa, ov in ((False, 1), (True, 1), (False, 2), (True, 2), (False, 8)):
                r = excite_residual(x, name, eff, fs, adaa=adaa, oversample=ov)
                row.append(alias_db(r, fs, f0))
            print(f"{name:8s}{eff:7.1f}" + "".join(f"{v:13.1f}" for v in row))


if __name__ == "__main__":
    check_identity()
    bench()
    bench(f0=9000)
