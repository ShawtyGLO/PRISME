"""Rendus n°3 : modes de canal, sur Auto « flanc raide » (référence validée), +5 dB."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, lfilter
from prisme_channels import process_channels, CANAUX
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")

fs, x = load(SRC)
seg = x[int(30 * fs): int(50 * fs)]
out_dir = os.path.join("renders", "canaux_5dB_30s")
os.makedirs(out_dir, exist_ok=True)
pad = 10 ** (-9 / 20)
kw = dict(source="auto", out_sections=3, f0=12000.0, q=2.0, gain_db=5.0, drive=1.5, oversample=2, norm="zone", mode="iron")
def kwl(z):
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585], z, axis=0)
    y = lfilter([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621], y, axis=0)
    return -0.691 + 10 * np.log10(np.sum(np.mean(y ** 2, axis=0)))
sos = butter(4, [8500, 17000], btype="band", fs=fs, output="sos")
def sm(z):
    zz = sosfiltfilt(sos, z, axis=0); M = (zz[:, 0] + zz[:, 1]) / 2; S = (zz[:, 0] - zz[:, 1]) / 2
    return 10 * np.log10(np.sum(S ** 2) / np.sum(M ** 2))
def cor(z):
    zz = sosfiltfilt(sos, z, axis=0); return np.corrcoef(zz[:, 0], zz[:, 1])[0, 1]
wavfile.write(os.path.join(out_dir, "00_dry.wav"), int(fs), (seg * pad).astype(np.float32))
print(f"{'canal':10s}{'Δ sonie K':>11s}{'Δ Side/Mid 8–17k':>19s}{'corr. L/R 8–17k':>17s}{'Δ niveau L':>12s}{'Δ niveau R':>12s}")
print(f"{'sec':10s}{'':>11s}{'':>19s}{cor(seg):17.2f}")
for i, c in enumerate(CANAUX, 1):
    y = process_channels(seg, fs, c, **kw)
    wavfile.write(os.path.join(out_dir, f"{i:02d}_iron_auto_{c.upper()}.wav"), int(fs), (y * pad).astype(np.float32))
    bl = sosfiltfilt(sos, y - seg, axis=0)
    print(f"{c:10s}{kwl(y) - kwl(seg):+11.2f}{sm(y) - sm(seg):+19.2f}{cor(y):17.2f}"
          f"{10*np.log10(np.sum(sosfiltfilt(sos, y[:,0])**2)/np.sum(sosfiltfilt(sos, seg[:,0])**2)):+12.2f}"
          f"{10*np.log10(np.sum(sosfiltfilt(sos, y[:,1])**2)/np.sum(sosfiltfilt(sos, seg[:,1])**2)):+12.2f}")
print(f"\nRendus dans {out_dir}/ (abaissés de 9 dB)")
