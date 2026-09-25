"""Les 5 modes de l'Exciter avec la nouvelle AGC : effet de « Saturation » (différence relative entre drive 0,5 et 4) et crête/RMS du delta ; effet du Tilt en mode Bande."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
import prisme_exciter_stream as ES
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
x = np.ascontiguousarray(x[int(30 * fs): int(38 * fs), 0])
rms = lambda v: np.sqrt(np.mean(v[int(fs):] ** 2))
print("Mode      | Auto bell 3 kHz : effet Saturation (0,5 → 4) | crête/RMS (0,5 / 1,5 / 4)")
for mode in ("iron", "triode", "diode", "classa", "rect"):
    d = {dr: ES.exciter_stream(x, fs, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode=mode, source="auto", drive=dr) for dr in (0.5, 1.5, 4.0)}
    diff = 20 * np.log10(rms(d[0.5] - d[4.0]) / rms(d[0.5]))
    cr = [np.max(np.abs(d[k][int(fs):])) / rms(d[k]) for k in (0.5, 1.5, 4.0)]
    print(f"{mode:9s} | écart relatif {diff:6.1f} dB (0 dB = totalement différent, −40 dB = identique) | {cr[0]:5.1f} / {cr[1]:5.1f} / {cr[2]:5.1f}")
print("\nTilt en mode Bande (bell 3 kHz Q 0,71, Iron) : barycentre spectral du delta")
def centroid(y):
    y = y[int(fs):]
    P = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2; f = np.fft.rfftfreq(len(y), 1 / fs)
    return np.exp(np.sum(P * np.log(f + 1)) / np.sum(P))
for t in (-1.0, 0.0, 1.0):
    y = ES.exciter_stream(x, fs, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode="iron", source="band", tilt=t)
    print(f"  tilt {t:+.1f} : barycentre {centroid(y):7.0f} Hz ; niveau {20 * np.log10(rms(y)):6.1f} dB")
