"""PRISME — type de bande « Shape » v4 (flux, 2026-09-25) : gain sur les TRANSITOIRES ou le SUSTAIN de la bande, bipolaire.

    sortie = entrée + (g(t) − 1) · b(t),       b = signal de la bande (passe-bande / passe-haut / passe-bas de la courbe)

  - enveloppe rapide E_f de |b| (τ_f = 3/f0, bornée à 2–30 ms : au moins trois périodes, sinon l'ondulation de |b| déclenche) ;
  - MONTÉE  m(t) = 20·log10(E_f(t) / E_f(t − τ_f)) en dB : nulle en régime établi et en décroissance, grande à une attaque ;
  - SENSIBILITÉ (0 … 1) : T = clip((m − m0)/4, 0, 1), m0 = 10 − 9·sens dB (1 = toutes les attaques, 0 = seulement les plus vives) ;
    elle mesure la VIVACITÉ de la montée, pas le niveau ; porte absolue −95 dBFS ;
  - DURÉE `time_ms` (5–200 ms ; None = 1 τ_f) : le poids d'un transitoire retombe en « durée » (suiveur de crête : attaque immédiate,
    relâchement exponentiel, 95 % à t = durée) ; pour le corps (sustain) c'est le temps qu'il met à revenir ;
  - l'attaque du gain est bornée (0,45 période à 60 Hz … 0,8 période à 250 Hz et plus) : un gain qui change plus vite que la bande ne
    peut suivre créerait un clic hors bande ;
  - cible « transitoires » : poids = T ; cible « sustain » : poids = 1 − T (partition de l'unité : transitoires(A) + sustain(A) = gain statique A) ;
  - g = 1 + (A − 1)·poids, A = 10^(gain_db/20) ; deux bandes à la même fréquence s'additionnent ; état conservé entre blocs ; causal ; latence nulle.
"""
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter


def _tient_relache(T, c, y_prev):
    """y[n] = max(T[n], c·y[n−1]) : attaque immédiate, relâchement exponentiel (vectorisé par blocs, état conservé)."""
    n = len(T)
    y = np.empty(n)
    tau = -1.0 / np.log(c)
    L = max(1, int(500 * tau))                                    # c**(−idx) reste < e^500
    i = 0
    while i < n:
        seg = T[i:i + L]
        idx = np.arange(1, len(seg) + 1)
        z = np.maximum(np.maximum.accumulate(seg * c ** (-idx)), y_prev)
        yb = c ** idx * z
        y[i:i + len(seg)] = yb
        y_prev = yb[-1]
        i += len(seg)
    return y, y_prev


class Shape:
    def __init__(self, fs, cible="transitoires", shape="bell", f0=60.0, q=1.0, gain_db=6.0, att_periods=None, time_ms=None, sens=0.85):
        self.fs, self.cible, self.A = fs, cible, 10.0 ** (gain_db / 20.0)
        self.b, self.a = zone_filter(shape, fs, f0, q)
        tf = float(np.clip(3.0 / f0, 0.002, 0.03))
        self.D = max(1, int(round(tf * fs)))
        self.cf = np.exp(-1.0 / (tf * fs))
        if att_periods is None:                      # attaque du gain : 0,45 période (≤ 60 Hz) … 0,8 période (≥ 250 Hz), interpolée en log
            att_periods = float(np.clip(0.45 + 0.35 * np.log2(f0 / 60.0) / np.log2(250.0 / 60.0), 0.45, 0.8))
        self.c_att = np.exp(-1.0 / (max(att_periods / f0, 1.0 / fs) * fs))
        tau_rel = (time_ms / 1000.0) / 3.0 if time_ms else 1.0 * tf                # 3 constantes → 95 % à t = durée
        self.c_rel = np.exp(-1.0 / (tau_rel * fs))
        self.m0 = 10.0 - 9.0 * sens
        self.zb, self.zf, self.z_att = np.zeros(2), np.zeros(1), np.zeros(1)
        self.hist = np.full(self.D, 1e-12)
        self.y_hold = 0.0

    def process(self, x, keep=False):
        n = len(x)
        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)
        Ef, self.zf = lfilter([1 - self.cf], [1, -self.cf], np.abs(b), zi=self.zf)
        ext = np.concatenate([self.hist, Ef])
        Ef_d = ext[:n]                                             # E_f retardée de D échantillons (= τ_f)
        self.hist = ext[-self.D:]
        m = 20.0 * np.log10((Ef + 1e-12) / (Ef_d + 1e-12))
        T = np.clip((m - self.m0) / 4.0, 0.0, 1.0)
        T *= np.clip((20.0 * np.log10(Ef * (np.pi / 2) + 1e-12) + 95.0) / 10.0, 0.0, 1.0)     # porte absolue −95 dBFS
        Th, self.y_hold = _tient_relache(T, self.c_rel, self.y_hold)                            # tient et relâche sur la durée choisie
        Tl, self.z_att = lfilter([1 - self.c_att], [1, -self.c_att], Th, zi=self.z_att)         # attaque du gain bornée
        poids = Tl if self.cible == "transitoires" else 1.0 - Tl
        g = 1.0 + (self.A - 1.0) * poids
        y = x + (g - 1.0) * b
        return (y, g) if keep else y


def shape_band(x, fs, cible="transitoires", shape="bell", f0=60.0, q=1.0, gain_db=6.0, block=8192, diag=False,
               att_periods=None, time_ms=None, sens=0.85):
    if gain_db == 0.0:
        return x.copy()
    s = Shape(fs, cible, shape, f0, q, gain_db, att_periods, time_ms, sens)
    y = np.empty(len(x))
    gs = []
    for i in range(0, len(x), block):
        out = s.process(x[i:i + block], keep=diag)
        if diag:
            y[i:i + block], g = out
            gs.append(g)
        else:
            y[i:i + block] = out
    return (y, dict(g=np.concatenate(gs))) if diag else y
