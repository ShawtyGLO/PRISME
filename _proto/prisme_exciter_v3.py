"""PRISME — Exciter v3 « Aural » (prototype hors ligne, 2026-09-28).

Retour de llg53 : le moteur v2 (harmoniques PURES : fondamental retiré) est la cause du grouillement — son wet est rare et pointu.
v3 suit le principe des exciters « Aural » MAIS sans leurs limites matérielles :
  · la zone (cloche / shelf de la bande, ou passe-haut) est saturée ENTIÈRE et ajoutée au sec : fondamental + harmoniques (renfort HF + grain) ;
  · niveau d'attaque de la courbe INDÉPENDANT du niveau d'entrée : u = drive · b / S (S = niveau lent 400 ms) → même caractère à −30 dB qu'à −6 dB ;
  · « Pureté » 0 … 1 : 0 = zone saturée entière (Aural), 1 = harmoniques seules (v2) — continu, pas deux positions ;
  · suréchantillonnage ×4, courbe sans mémoire, filtre de sortie de la zone (les harmoniques qui sortent de la zone sont gardées en partie : 1 section) ;
  · stéréo LIÉE (source = milieu).
Wet = (y − pureté · pente · u) · S · niveau.
"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter, resample_poly
from prisme_band import zone_filter

CURVES = {
    "doux": (lambda u: np.tanh(u), 1.0),
    "chaud": (lambda u: np.tanh(u + 0.35) - np.tanh(0.35), 1.0 - np.tanh(0.35) ** 2),
    "mordant": (lambda u: (lambda c: c - c ** 3 / 3.0)(np.clip(u, -1.0, 1.0)), 1.0),
    "mordant_chaud": (lambda u: (lambda c: c - c ** 3 / 3.0)(np.clip(u + 0.25, -1.0, 1.0)) - (0.25 - 0.25 ** 3 / 3.0), 1.0 - 0.25 ** 2),
}


def env(a, tau, fs):
    c = np.exp(-1.0 / (tau * fs))
    return lfilter([1 - c], [1, -c], a) * (np.pi / 2)


def exc_v3(x, fs, f0, shape="bell", q=0.71, profil="mordant_chaud", drive=2.5, purete=0.0, out_sections=1):
    """x : mono. Renvoie le wet (à ajouter au sec), niveau brut (à calibrer par l'appelant)."""
    zf = zone_filter(shape, fs, f0, q)
    b = lfilter(*zf, x)
    S = env(np.abs(b), 0.4, fs) + 1e-7
    u = drive * b / S
    f, pente = CURVES[profil]
    y = resample_poly(f(resample_poly(u, 4, 1)), 1, 4)[: len(x)]
    res = (y - purete * pente * u) * S / drive                  # ÷ drive : le fondamental garde ~ son niveau quel que soit le drive
    for _ in range(out_sections):
        res = lfilter(*zf, res)
    c = 1.0 - 2 * np.pi * 20.0 / fs
    return lfilter([1.0, -1.0], [1.0, -c], res)
