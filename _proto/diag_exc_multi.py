"""Essai « multibande » de l'Exciter : K chaînes à sources étroites (Q élevé) réparties sur la zone-source, deltas sommés (÷√K)."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
import prisme_exciter_stream as ES
from prisme_band import H_DOMINANT
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")


def multi(x, fs, K, f0=3000.0, mode="iron", gain=2.4, shape="bell", q=0.71, span=1.0):
    h = H_DOMINANT[mode]
    fc = max(f0 / h, 60.0)
    if K == 1:
        return ES.exciter_stream(x, fs, shape=shape, f0=f0, q=q, gain_db=gain, mode=mode, source="auto")
    qs = 1.0 / (2 ** (span / K / 2) - 2 ** (-span / K / 2)) * 1.3        # Q donnant des sous-bandes jointives
    out = 0.0
    for k in range(K):
        c = fc * 2 ** (span * ((k + 0.5) / K - 0.5))
        out = out + ES.exciter_stream(x, fs, shape=shape, f0=f0, q=q, gain_db=gain, mode=mode, source="auto", src_f0=c, src_q=qs)
    return out / np.sqrt(K)


if __name__ == "__main__":
    fs = 48000
    t = np.arange(int(fs * 4)) / fs
    tw = 0.05 * np.sin(2 * np.pi * 900 * t) + 0.05 * np.sin(2 * np.pi * 1100 * t)
    print("DEUX SONS (900 + 1100 Hz), Iron, bell 3 kHz : part de l'énergie du delta sur les raies d'harmoniques (2700, 3300, 3000) contre le reste (intermodulation)")
    for K in (1, 2, 4, 8):
        d = multi(tw, fs, K)[fs:]
        P = np.abs(np.fft.rfft(d * np.hanning(len(d)))) ** 2
        f = np.fft.rfftfreq(len(d), 1 / fs)
        def raie(fr): return P[(f > fr - 15) & (f < fr + 15)].sum()
        harm = sum(raie(v) for v in (2700, 3300, 3000)); tot = P[(f > 500) & (f < 8000)].sum()
        print(f"  K = {K} : harmoniques {100 * harm / tot:5.1f} % de l'énergie 0,5–8 kHz ; niveau delta {10 * np.log10(np.mean(d ** 2)):6.1f} dB")
    fs0, x = load(SRC)
    x = np.ascontiguousarray(x[int(30 * fs0): int(38 * fs0), 0])
    print("\nMUSIQUE (bell 3 kHz +2,4 dB Iron) : crête/RMS et énergie des 1 % les plus forts")
    for K in (1, 4, 8):
        y = multi(x, fs0, K)[int(fs0):]
        e = np.sort(y ** 2)[::-1]
        print(f"  K = {K} : crête/RMS {np.max(np.abs(y)) / np.sqrt(np.mean(y ** 2)):5.1f} ; 1 % forts {100 * e[: len(e) // 100].sum() / e.sum():5.1f} % ; niveau {20 * np.log10(np.sqrt(np.mean(y ** 2))):6.1f} dB")
