"""Tame sur ta prod (vrai mix) : que fait-il, où, avec quels effets de bord ? Zone 3 kHz Q 0,7, profondeur −6 dB."""
import sys, os, time
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import welch, find_peaks
from scipy.ndimage import uniform_filter1d
from prisme_tame import tame_band
from render import load
from bench_leak import SRC
from bench_quality import rugosite
sys.stdout.reconfigure(encoding="utf-8")
fs, x = load(SRC)
m = x.mean(axis=1)[int(30 * fs): int(42 * fs)]
kw = dict(shape="bell", f0=3000.0, q=0.7)
fr, Px = welch(m, fs, nperseg=16384, noverlap=8192)
dbx = 10 * np.log10(Px + 1e-30)
lisse = uniform_filter1d(dbx, size=int(400 / (fs / 16384)))
zone = (fr > 1500) & (fr < 6000)
pk, pr = find_peaks(np.where(zone, dbx - lisse, -99), prominence=6.0, distance=8)
top = pk[np.argsort(pr["prominences"])[-6:][::-1]]
print(f"prod 30–42 s, zone bell 3 kHz Q 0,7 (≈ 1,4–6,4 kHz), −6 dB ; rugosité de la zone avant : {rugosite(m, fs, 1500, 6000):.2f} dB")
print(f"{len(pk)} pics saillants (> 6 dB au-dessus de la moyenne locale) dans la zone ; les 6 plus marqués : " + ", ".join(f"{fr[i]:.0f} Hz (+{dbx[i]-lisse[i]:.0f})" for i in top) + "\n")
print(f"{'largeur':>8s}{'rugosité':>10s}{'6 pics : réduction moyenne':>28s}{'pics (par pic)':>40s}{'niveau global':>15s}{'SNR':>9s}{'temps':>8s}")
for wd in (0.0, 0.5, 1.0):
    t0 = time.time()
    y = tame_band(m, fs, gain_db=-6.0, width=wd, **kw)
    dt = time.time() - t0
    _, Py = welch(y, fs, nperseg=16384, noverlap=8192)
    dby = 10 * np.log10(Py + 1e-30)
    red = [dby[i] - dbx[i] for i in top]
    snr = 10 * np.log10(np.sum(m ** 2) / np.sum((y - m) ** 2))
    print(f"{wd:8.1f}{rugosite(y, fs, 1500, 6000):10.2f}{np.mean(red):+28.1f}{' '.join(f'{r:+.1f}' for r in red):>40s}"
          f"{10*np.log10(np.sum(y**2)/np.sum(m**2)):+15.2f}{snr:8.1f} dB{dt:7.1f}s")
