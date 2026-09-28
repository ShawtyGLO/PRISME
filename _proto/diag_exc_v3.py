"""Exciter v3 « Aural » : mesures contre v2 et petit jeu de rendus (peu de fichiers : écoute économe)."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter
from prisme_exciter_v3 import exc_v3
import prisme_exciter_v2_stream as V2
from prisme_band import zone_filter
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
fs, X = load(SRC)
X = X[int(30 * fs): int(48 * fs)]
mid = np.ascontiguousarray(0.5 * (X[:, 0] + X[:, 1]))
zone = lfilter(*zone_filter("bell", fs, 3000.0, 0.71), mid)
rms = lambda v: 20 * np.log10(np.sqrt(np.mean(v[int(fs):] ** 2)) + 1e-12)


def stats(w):
    w = w[int(fs):]
    e = np.sort(w ** 2)[::-1]
    return np.max(np.abs(w)) / np.sqrt(np.mean(w ** 2)), 100 * e[: len(e) // 100].sum() / e.sum()


def harm(w, f0=3000.0):                      # part du wet HORS de la bande [f0/√2 ; f0·√2] (= contenu nouveau, harmoniques)
    w = w[int(fs):]
    P = np.abs(np.fft.rfft(w * np.hanning(len(w)))) ** 2
    f = np.fft.rfftfreq(len(w), 1 / fs)
    dans = P[(f > f0 / 1.414) & (f < f0 * 1.414)].sum()
    return 100 * (1 - dans / P[f > 200].sum())


print(f"{'moteur':44s} crête/RMS   1 % forts   contenu hors bande")
w2 = V2.exciter_v2_stream(mid, fs, shape="bell", f0=3000.0, q=0.71, gain_db=6.0, profil="mordant_chaud", dens=0.0)
c, t = stats(w2); print(f"{'v2 mordant chaud (harmoniques pures)':44s} {c:7.1f}   {t:6.0f} %    {harm(w2):6.0f} %")
for pr in ("doux", "chaud", "mordant", "mordant_chaud"):
    for pu in (0.0, 0.5):
        w = exc_v3(mid, fs, 3000.0, profil=pr, purete=pu)
        c, t = stats(w)
        print(f"{'v3 ' + pr + f' pureté {pu:.1f}':44s} {c:7.1f}   {t:6.0f} %    {harm(w):6.0f} %")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_v3")
os.makedirs(out, exist_ok=True)
peak = np.max(np.abs(X))


def ecrit(nom, w, cible):
    w = w * 10 ** ((cible + rms(zone) - rms(w)) / 20)
    y = X + w[:, None]
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


ecrit("00_sec", np.zeros(len(mid)), 0.0)
ecrit("01_v3_mordant_chaud_purete0_-10dB", exc_v3(mid, fs, 3000.0, profil="mordant_chaud", purete=0.0), -10)
ecrit("02_v3_mordant_chaud_purete0.5_-10dB", exc_v3(mid, fs, 3000.0, profil="mordant_chaud", purete=0.5), -10)
ecrit("03_v3_doux_purete0_-10dB", exc_v3(mid, fs, 3000.0, profil="doux", purete=0.0), -10)
ecrit("04_v3_mordant_chaud_purete0_drive6_-10dB", exc_v3(mid, fs, 3000.0, profil="mordant_chaud", purete=0.0, drive=6.0), -10)
ecrit("05_v2_actuel_mordant_chaud_-10dB", np.concatenate([w2[V2.D_OS:], np.zeros(V2.D_OS)]), -10)
print(sorted(os.listdir(out)))
