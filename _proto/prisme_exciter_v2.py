"""PRISME — Exciter v2 (PROTOTYPE hors ligne, 2026-09-26) : « à seuil relatif », lié en stéréo, wet à niveau proportionnel aux harmoniques réellement produites.

Retour de llg53 : le wet actuel « grouille » et manque du côté « parallèle » d'un Aural Exciter. Causes mesurées de l'Exciter v1 : l'AGC remonte tout au même niveau (aucun
seuil), la normalisation gonfle en signal continu des harmoniques minuscules et rares, la non-linéarité est indépendante sur L et R (elle décorrèle le centre).

v2 :
  · source (bande f0/h ou zone), niveau lent S (τ 400 ms) et niveau rapide e (τ 3 ms) ;
  · SEUIL RELATIF : la porte ne s'ouvre que si e dépasse S de `seuil_db` (pics et attaques au-dessus du niveau courant, comme le « transient discriminate » d'Aphex) → indépendant du niveau d'entrée ;
  · saturation d'un signal normalisé u = drive · s / S (sans mémoire, oversamplée ×4) ; résidu = y − u (le fondamental est retiré EXACTEMENT : courbe sans mémoire) ;
  · wet = résidu · S · porte · niveau (pas de normalisation par la zone) : il n'existe que s'il y a des harmoniques ;
  · filtre de sortie de la zone (3 sections) ; sortie LIÉE : la source vient du milieu (L+R)/2, le même wet est ajouté aux deux canaux.
"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, resample_poly
from prisme_band import zone_filter, H_DOMINANT

CURVES = {
    "doux": lambda u: np.tanh(u),                                           # impair, doux : 3e harmonique
    "chaud": lambda u: np.tanh(u + 0.35) - np.tanh(0.35) * 1.0,               # asymétrique : 2e harmonique (le résidu retire la partie linéaire ci-dessous)
    "mordant": lambda u: np.clip(u, -1.0, 1.0) - np.clip(u, -1.0, 1.0) ** 3 / 3.0 + 0.0,   # cubique borné
}


def env(a, tau, fs):
    c = np.exp(-1.0 / (tau * fs))
    return lfilter([1 - c], [1, -c], a) * (np.pi / 2)


def smoothstep(v):
    v = np.clip(v, 0.0, 1.0)
    return v * v * (3 - 2 * v)


def exc_v2(x, fs, f0, shape="bell", q=0.71, mode_h=3, curve="doux", seuil_db=3.0, drive=1.5, niveau_db=-20.0, src_q=2.0, out_sections=3):
    """x : mono. Renvoie le wet (mono) ; niveau_db : niveau du wet relatif au niveau lent de la source (−20 = discret)."""
    fs_src = max(f0 / mode_h, 60.0)
    zf = zone_filter(shape, fs, fs_src, max(q, src_q))
    s = lfilter(*zf, lfilter(*zf, x))
    S = env(np.abs(s), 0.4, fs) + 1e-7
    e = env(np.abs(s), 0.003, fs)
    rel = 20 * np.log10((e + 1e-12) / S)
    porte = smoothstep((rel - seuil_db) / 6.0)
    u = drive * s / S
    v = resample_poly(u, 4, 1)
    f = CURVES[curve]
    y = resample_poly(f(v), 1, 4)[: len(x)]
    if curve == "chaud":
        y = y - (1.0 - np.tanh(0.35) ** 2) * u                              # retire la partie linéaire (pente en 0 de la courbe décalée)
    else:
        y = y - u
    res = y * S * porte * 10 ** (niveau_db / 20)
    zo = zone_filter(shape, fs, f0, q)
    for _ in range(out_sections):
        res = lfilter(*zo, res)
    c = 1.0 - 2 * np.pi * 20.0 / fs
    return lfilter([1.0, -1.0], [1.0, -c], res)
