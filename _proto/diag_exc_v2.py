"""Exciter v2 : mesures (deux sons purs, musique) et rendus dans renders/exciter_v2."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter
import prisme_exciter_stream as ES
from prisme_exciter_v2 import exc_v2
from prisme_band import zone_filter
from diag_exc_diffuse import dispersion
from render import load
from bench_leak import SRC

sys.stdout.reconfigure(encoding="utf-8")
rmsdb = lambda v, a=0: 20 * np.log10(np.sqrt(np.mean(v[a:] ** 2)) + 1e-12)

# ---- deux sons : part de l'énergie sur les raies d'harmoniques
fs = 48000
t = np.arange(fs * 4) / fs
tw = 0.05 * np.sin(2 * np.pi * 900 * t) + 0.05 * np.sin(2 * np.pi * 1100 * t)
for nom, w in (("v1 actuel (+2,4 dB)", ES.exciter_stream(tw, fs, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode="iron", source="auto")),
               ("v2 seuil 3 dB, drive 1,5", exc_v2(tw, fs, 3000.0, seuil_db=3.0, drive=1.5)),
               ("v2 seuil 0 dB, drive 3", exc_v2(tw, fs, 3000.0, seuil_db=0.0, drive=3.0))):
    d = w[fs:]
    P = np.abs(np.fft.rfft(d * np.hanning(len(d)))) ** 2
    f = np.fft.rfftfreq(len(d), 1 / fs)
    harm = sum(P[(f > v - 15) & (f < v + 15)].sum() for v in (2700, 3300, 3000))
    tot = P[(f > 500) & (f < 8000)].sum()
    print(f"deux sons — {nom:26s}: {100 * harm / tot:5.1f} % de l'énergie sur les harmoniques ; niveau {rmsdb(d):6.1f} dBFS")

# ---- musique
fs0, X = load(SRC)
X = X[int(30 * fs0): int(48 * fs0)]
mid = np.ascontiguousarray(0.5 * (X[:, 0] + X[:, 1]))
zone = lfilter(*zone_filter("bell", fs0, 3000.0, 0.71), mid)
print(f"\ncontenu de la zone 3 kHz (milieu) : {rmsdb(zone, int(fs0)):.1f} dBFS")


def stats(y):
    y = y[int(fs0):]
    e = np.sort(y ** 2)[::-1]
    return np.max(np.abs(y)) / np.sqrt(np.mean(y ** 2)), 100 * e[: len(e) // 100].sum() / e.sum()


for nom, kw in (("doux seuil 3 dB", dict(curve="doux", seuil_db=3.0)), ("doux seuil 0 dB", dict(curve="doux", seuil_db=0.0)), ("doux seuil 6 dB", dict(curve="doux", seuil_db=6.0)),
                ("chaud seuil 3 dB", dict(curve="chaud", seuil_db=3.0)), ("mordant seuil 3 dB", dict(curve="mordant", seuil_db=3.0, drive=2.5))):
    w = exc_v2(mid, fs0, 3000.0, niveau_db=0.0, **kw)
    c, t1 = stats(w)
    print(f"v2 {nom:20s}: wet à niveau 0 dB = {rmsdb(w, int(fs0)) - rmsdb(zone, int(fs0)):6.1f} dB sous la zone ; crête/RMS {c:5.1f} ; 1 % forts {t1:4.0f} %")

# ---- rendus
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_v2")
os.makedirs(out, exist_ok=True)
peak = np.max(np.abs(X))
D = ES.D_OS
dry = np.concatenate([np.zeros((D, 2)), X[:-D]])
sec = np.concatenate([np.zeros(D), mid[:-D]])


def ecrit(nom, y):
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs0), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))


def calibre(w, cible_db):                                               # ramène le wet à `cible_db` sous la zone
    return w * 10 ** ((cible_db + (rmsdb(zone, int(fs0)) - rmsdb(w, int(fs0)))) / 20)


ecrit("00_sec", dry)
# (a) l'Exciter v1 actuel mais LIÉ (source = milieu, même wet sur L et R) : teste à lui seul le problème de spatialisation
w1 = ES.exciter_stream(mid, fs0, shape="bell", f0=3000.0, q=0.71, gain_db=2.4, mode="iron", source="auto")
for c in (-20, -14):
    ecrit(f"a_v1_lie_{c}dB_sous_la_zone", dry + calibre(w1, c)[:, None])
# (b) v2 : profils et niveaux
for nom, kw in (("doux", dict(curve="doux", seuil_db=3.0)), ("chaud", dict(curve="chaud", seuil_db=3.0)), ("mordant", dict(curve="mordant", seuil_db=3.0, drive=2.5))):
    w = exc_v2(mid, fs0, 3000.0, niveau_db=0.0, **kw)
    for c in (-26, -20, -14):
        ecrit(f"b_v2_{nom}_{c}dB_sous_la_zone", dry + calibre(w, c)[:, None])
# (c) v2 + diffusion COHÉRENTE (même passe-tout sur les deux canaux : ne touche pas la spatialisation)
w = exc_v2(mid, fs0, 3000.0, niveau_db=0.0, curve="doux", seuil_db=3.0)
ecrit("c_v2_doux_-20dB_diffus_coherent", dry + calibre(dispersion(w, fs0, n=12, q=0.7), -20)[:, None])
print(sorted(os.listdir(out)))
