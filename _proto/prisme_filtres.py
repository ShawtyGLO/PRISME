"""PRISME — filtres coupe-bas / coupe-haut PAR BANDE, à phase compensée (2026-09-28). Référence des tests C++ (FiltresBandes.h).

Problème mesuré : un filtre ordinaire sur le signal ajouté (delta) d'une bande décale sa phase par rapport au sec → l'effet réel s'écarte de l'effet affiché
de 5 à 16 dB (une cloche +6 dB filtrée en 24 dB/oct devient une coupe de −10,9 dB).
Solution : filtres Linkwitz-Riley sur le delta + le PASSE-TOUT correspondant sur le sec et sur les deltas des autres bandes :
    y = Π AP · (x + Σ m_i · delta_i)       (m_i réel ≥ 0 = module du filtre de la bande i)   → effet réel = effet affiché, zéro latence.
  · 24 dB/oct (LR4) : filtre = Butterworth ordre 2 (RBJ, Q = √½) au carré ; passe-tout = RBJ passe-tout Q = √½  (= LP² + HP²)
  · 12 dB/oct (LR2) : filtre = Butterworth ordre 1 (bilinéaire) au carré, coupe-bas en polarité INVERSÉE ; passe-tout ordre 1 (= LP² − HP²)
Version STATIQUE vectorisée (réglages fixes) : le plugin ajoute des fondus à l'activation / désactivation.
"""
import numpy as np
from scipy.signal import lfilter

Q_BW = 1.0 / np.sqrt(2.0)


def bw1(fs, fc, haut):
    K = np.tan(np.pi * fc / fs)
    a = np.array([1.0, (K - 1.0) / (K + 1.0)])
    b = np.array([1.0, -1.0]) / (K + 1.0) if haut else np.array([K, K]) / (K + 1.0)
    return b, a


def ap1(fs, fc):
    K = np.tan(np.pi * fc / fs)
    c = (K - 1.0) / (K + 1.0)
    return np.array([c, 1.0]), np.array([1.0, c])


def rbj(fs, fc, kind, q=Q_BW):
    w0 = 2 * np.pi * fc / fs
    al, c = np.sin(w0) / (2 * q), np.cos(w0)
    if kind == "lp":
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]
    elif kind == "hp":
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    else:                                                     # passe-tout
        b = [1 - al, -2 * c, 1 + al]
    a = np.array([1 + al, -2 * c, 1 - al])
    return np.array(b) / a[0], a / a[0]


def etages(fs, kind, fc, pente):
    """(liste des étages du filtre LR, signe, étage passe-tout). kind : 'lc' (coupe-bas) ou 'hc' (coupe-haut)."""
    fc = float(np.clip(fc, 10.0, 0.45 * fs))
    if pente == 24:
        k = "hp" if kind == "lc" else "lp"
        return [rbj(fs, fc, k), rbj(fs, fc, k)], 1.0, rbj(fs, fc, "ap")
    return [bw1(fs, fc, kind == "lc"), bw1(fs, fc, kind == "lc")], (-1.0 if kind == "lc" else 1.0), ap1(fs, fc)


def applique(dry, deltas, filtres, fs):
    """dry : (n, 2) ; deltas : {bande: (n, 2)} ; filtres : {bande: [('lc', f, pente) | None, ('hc', f, pente) | None]} (bandes actives seulement).
    Renvoie la sortie (n, 2)."""
    actifs = [(b, spec) for b, lst in filtres.items() for spec in lst if spec is not None]

    def ap_de(sig, sauf=None):
        for b, (kind, f, p) in actifs:
            if b == sauf:
                continue
            _, _, ap = etages(fs, kind, f, p)
            sig = lfilter(*ap, sig, axis=0)
        return sig

    y = ap_de(dry)
    for b, d in deltas.items():
        s = d
        for kind, f, p in [sp for sp in filtres.get(b, []) if sp is not None]:
            et, sgn, _ = etages(fs, kind, f, p)
            for e in et:
                s = lfilter(*e, s, axis=0)
            s = sgn * s
        y = y + ap_de(s, sauf=b)
    return y
