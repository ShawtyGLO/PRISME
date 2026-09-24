"""PRISME — type de bande « Shape » (2026-09-24) : gain sur les TRANSITOIRES ou sur le SUSTAIN de la bande, bipolaire.

Squelette additif, comme l'Exciter et le Tame :

    sortie = entrée + (g(t) − 1) · b(t),     b = signal de la bande (passe-bande / passe-haut / passe-bas de la courbe)

  - deux enveloppes de b : rapide E_f et lente E_s ; mesure de transitoire  T(t) = clip(E_f/E_s − 1, 0, 1)
    (≈ 1 juste après une attaque, → 0 quand l'enveloppe rapide rejoint la lente) ;
  - cible « transitoires » : g = 1 + (A − 1)·T          ;  cible « sustain » : g = 1 + (A − 1)·(1 − T) ;
  - A = 10^(gain_db/20) : gain_db > 0 renforce, < 0 atténue (bipolaire) ;
  - les constantes de temps suivent la fréquence de la bande (une basse a besoin d'enveloppes plus lentes) ;
  - deux bandes à la même fréquence s'additionnent : transitoires +6 dB et sustain −6 dB donnent un kick net et un grondement réduit.
"""
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter


def _env(a, tau, fs):
    c = np.exp(-1.0 / (tau * fs))
    return lfilter([1 - c], [1, -c], a)


def shape_band(x, fs, cible="transitoires", shape="bell", f0=60.0, q=1.0, gain_db=6.0, diag=False):
    if gain_db == 0.0:
        return x.copy()
    b = lfilter(*zone_filter(shape, fs, f0, q), x)
    ab = np.abs(b)
    tf = float(np.clip(1.5 / f0, 0.002, 0.03))               # rapide : 2 ms (aigu) … 30 ms (grave)
    ts = 10.0 * tf                                            # lente : 20 ms … 300 ms
    Ef, Es = _env(ab, tf, fs), _env(ab, ts, fs)
    # seuil : en régime établi ou en décroissance E_f/E_s reste ≈ 1 (ondulation de |b|) ; on ne compte comme transitoire
    # que ce qui dépasse 1,15 (pleine échelle à 1,75) → pas de fuite du mode « transitoires » dans le sustain
    T = np.clip((Ef / (Es + 1e-9) - 1.15) / 0.6, 0.0, 1.0)
    A = 10.0 ** (gain_db / 20.0)
    poids = T if cible == "transitoires" else 1.0 - T
    g = 1.0 + (A - 1.0) * poids
    y = x + (g - 1.0) * b
    return (y, dict(T=T, g=g)) if diag else y
