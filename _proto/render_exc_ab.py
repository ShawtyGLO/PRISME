"""A/B : le prototype d'écoute (Mordant chaud −14 dB, préféré) contre ce que fait le plugin ; mêmes niveaux (−14 dB sous la zone), même source (milieu → L et R)."""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter
import prisme_exciter_v2_stream as V2
from prisme_exciter_v2 import exc_v2
import prisme_exciter_v2 as P2
from prisme_band import zone_filter
from render import load
from bench_leak import SRC
sys.stdout.reconfigure(encoding="utf-8")
P2.CURVES["mordant_chaud"] = lambda u: (lambda c: c - c ** 3 / 3.0)(np.clip(u + 0.25, -1.0, 1.0))
fs, X = load(SRC)
X = X[int(30 * fs): int(48 * fs)]
mid = np.ascontiguousarray(0.5 * (X[:, 0] + X[:, 1]))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "exciter_proto_vs_plugin")
peak = np.max(np.abs(X))
D = V2.D_OS
dry = np.concatenate([np.zeros((D, 2)), X[:-D]])
zone = lfilter(*zone_filter("bell", fs, 3000.0, 0.71), mid)
rms = lambda v: 20 * np.log10(np.sqrt(np.mean(v[int(fs):] ** 2)) + 1e-12)


def ecrit(nom, w, cible=-14.0):
    w = w * 10 ** ((cible + rms(zone) - rms(w)) / 20)
    y = dry + w[:, None]
    wavfile.write(os.path.join(out, nom + ".wav"), int(fs), (y / max(peak, np.max(np.abs(y))) * 0.9 * 32767).astype(np.int16))
    return w


ecrit("00_sec_ref", np.zeros(len(mid)) + 1e-12)
wp = ecrit("A_prototype_aime_mordant_chaud", exc_v2(mid, fs, 3000.0, curve="mordant_chaud", seuil_db=3.0, drive=2.5, niveau_db=0.0))
kw = dict(shape="bell", f0=3000.0, q=0.71, gain_db=6.0, source="auto", drive=2.5)
wb = ecrit("B_plugin_actuel_porte_reguliere", V2.exciter_v2_stream(mid, fs, profil="mordant_chaud", **kw)[:len(mid)])
wc = ecrit("C_plugin_ancienne_porte_creuse", V2.exciter_v2_stream(mid, fs, profil="mordant_chaud", seuil_db=3.0, largeur_db=6.0, plancher=0.0, tau_porte=1e-6, **kw))
wd = ecrit("D_plugin_porte_intermediaire", V2.exciter_v2_stream(mid, fs, profil="mordant_chaud", seuil_db=0.0, largeur_db=9.0, plancher=0.1, tau_porte=0.03, **kw))
for pr in ("doux", "chaud", "mordant"):
    ecrit(f"E_plugin_actuel_{pr}", V2.exciter_v2_stream(mid, fs, profil=pr, **kw))


def corr(a, b):
    a, b = a[int(fs):], b[int(fs):]
    n = min(len(a), len(b))
    return float(np.corrcoef(a[:n], b[:n])[0, 1])


def crete(v):
    v = v[int(fs):]
    return np.max(np.abs(v)) / np.sqrt(np.mean(v ** 2))


print("Corrélation avec le prototype aimé (même niveau) :  B", round(corr(wp, np.concatenate([wb[D:], np.zeros(D)])), 2), "  C", round(corr(wp, np.concatenate([wc[D:], np.zeros(D)])), 2), "  D", round(corr(wp, np.concatenate([wd[D:], np.zeros(D)])), 2))
print("Crête/RMS : prototype", round(crete(wp), 1), " B", round(crete(wb), 1), " C", round(crete(wc), 1), " D", round(crete(wd), 1))
print(sorted(os.listdir(out)))
