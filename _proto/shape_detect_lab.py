"""Laboratoire Shape (2026-10-01) : plusieurs détecteurs de percussion, comparés à iso-faux-déclenchements, avec et sans anticipation (lookahead).

Chaque détecteur renvoie une « force » s(t) (dB, débit plein) ; poids = clip((s − m0)/largeur) → tenue/relâchement → décalage d'anticipation → attaque bornée.
  A  différentiel   : montée de l'enveloppe rapide de la zone sur un retard (= Shape v4 actuel)
  B  flux léger     : 3 bandes/octave, SuperFlux (référence = max sur 3 bandes voisines), montée moyenne des bandes de contexte ou de tout le spectre
  C  résidu         : prédicteur adaptatif NLMS (16 coefs) du signal de zone ; force = enveloppe rapide / lente du résidu
  D  C × B          : le résidu de prédiction doit éclater ET la montée doit être large (produit géométrique des poids)
"""
import numpy as np
from scipy.signal import lfilter, freqz
from scipy.ndimage import maximum_filter1d
from prisme_band import zone_filter
from prisme_dsp import rbj_bandpass0db
from prisme_shape import _tient_relache
from prisme_tame5 import _zone_lo_hi

DEC = 16


def env(sig_abs, tau, fs):
    c = np.exp(-1.0 / (tau * fs))
    return lfilter([1 - c], [1, -c], sig_abs)


def zone_signal(x, fs, shape, f0, q):
    b, a = zone_filter(shape, fs, f0, q)
    return lfilter(b, a, x)


def strength_A(x, fs, shape, f0, q):
    b = zone_signal(x, fs, shape, f0, q)
    tf = float(np.clip(3.0 / f0, 0.002, 0.03))
    Ef = env(np.abs(b), tf, fs)
    D = max(1, int(round(tf * fs)))
    Ed = np.concatenate([np.full(D, 1e-12), Ef[:-D]])
    m = 20 * np.log10((Ef + 1e-12) / (Ed + 1e-12))
    return m * np.clip((20 * np.log10(Ef * np.pi / 2 + 1e-12) + 95) / 10, 0, 1), b


def bands_B(x, fs, per_oct=3):
    f = 30.0 * 2 ** (np.arange(0, 100) / per_oct)
    f = f[f < 0.45 * fs]
    q = 1.0 / (2 ** (1 / (2 * per_oct)) - 2 ** (-1 / (2 * per_oct)))
    idx = np.arange(0, len(x), DEC)
    L = np.empty((len(f), len(idx)))
    for k, fk in enumerate(f):
        bk = lfilter(*rbj_bandpass0db(fs, fk, q), x)
        ef = env(np.abs(bk), max(0.002, 2.0 / fk), fs)
        L[k] = 20 * np.log10(ef[idx] * np.pi / 2 + 1e-12)
    return f, idx, L


def strength_B(x, fs, shape, f0, q, cache=None):
    f, idx, L = cache if cache is not None else bands_B(x, fs)
    lo, hi = _zone_lo_hi(shape, f0, q, fs, 1.5)
    c = np.where((f >= lo) & (f <= hi))[0]
    if len(c) < 3:
        c = np.argsort(np.abs(np.log2(f / f0)))[:3]
    tf = float(np.clip(3.0 / f0, 0.005, 0.03))
    lag = max(2, int(round(tf * fs / DEC)))
    ref = np.concatenate([np.repeat(L[:, :1], lag, axis=1), L[:, :-lag]], axis=1)
    ref = maximum_filter1d(ref, size=3, axis=0, mode="nearest")             # SuperFlux : référence = max sur les bandes voisines
    up = np.maximum(L - ref, 0.0)
    s_ctx = up[c].mean(axis=0)
    s_glob = up[np.searchsorted(f, 60.0):].mean(axis=0)
    s = np.maximum(s_ctx, s_glob) * np.clip((L[c].max(axis=0) + 95) / 10, 0, 1)
    return np.interp(np.arange(len(x)), idx, s)


def strength_C(x, fs, shape, f0, q, b=None, order=16, mu=0.2):
    if b is None:
        b = zone_signal(x, fs, shape, f0, q)
    n = len(b)
    w = np.zeros(order)
    e = np.zeros(n)
    buf = np.zeros(order)
    en = 1e-6
    for i in range(n):
        err = b[i] - w @ buf
        e[i] = err
        w += (mu / (buf @ buf + 1e-9)) * err * buf                       # NLMS standard
        buf[1:] = buf[:-1]
        buf[0] = b[i]
    tf = float(np.clip(2.0 / f0, 0.002, 0.01))
    Ef = env(np.abs(e), tf, fs)
    Es = env(np.abs(e), 0.05, fs)
    return 20 * np.log10((Ef + 1e-12) / (Es + 1e-12)) * np.clip((20 * np.log10(Ef * np.pi / 2 + 1e-12) + 95) / 10, 0, 1)


def weights(s, fs, m0, width, f0, time_ms=None, look_ms=0.0, B=None):
    """force → poids final (0…1) : seuil, tenue, anticipation, attaque."""
    T = np.clip((s - m0) / width, 0.0, 1.0)
    tf = float(np.clip(3.0 / f0, 0.002, 0.03))
    tau_rel = (time_ms / 1000.0) / 3.0 if time_ms else tf
    Th, _ = _tient_relache(T, np.exp(-1.0 / (tau_rel * fs)), 0.0)
    L = int(round(look_ms * fs / 1000.0))
    if L > 0:
        Th = np.concatenate([Th[L:], np.zeros(L)])                       # le poids arrive L échantillons avant l'événement détecté
    att = float(np.clip(0.45 + 0.35 * np.log2(f0 / 60.0) / np.log2(250.0 / 60.0), 0.45, 0.8))
    c = np.exp(-1.0 / (max(att / f0, 1.0 / fs) * fs))
    return lfilter([1 - c], [1, -c], Th)
