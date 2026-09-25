"""PRISME — Tame « allégé » (variantes de test, 2026-09-25) : v3 + `ra` (bandes/octave) + `interp` (gain interpolé à fs/16 au lieu de ZOH + lissage plein débit).
TAME_RA / TAME_INTERP dans l'environnement fixent les défauts (pour rejouer tests_tame.py sur une variante).

PRISME — type de bande « Tame » v3 (moteur temporel en FLUX, 2026-09-25) : bipolaire, largeur de traitement, plafond garanti.

    sortie = entrée + Σₖ cₖ(t) · BPˢₖ(entrée),      cₖ = (gₖ(t) − 1) / S_eff,k(t)

  ANALYSE   24 bandes/octave (Q 14) sur la zone ± 1 octave ; niveau de chaque bande (dB) = max(enveloppe lente, enveloppe rapide − 6 dB) ;
            tenue de crête + lissage sur 3 bandes (supprime l'ondulation de grille et la fluctuation du bruit).
  DÉTECTION excès = niveau − moyenne des voisines (fenêtre extérieure ±0,5 à ±1,5 oct, hors une zone intérieure ±(p + 0,05 oct)) ;
            genou quadratique (nul sous le seuil → transparence) ; porte absolue −95 dBFS.
  LARGEUR   `width` ∈ [0, 1] règle la demi-largeur p du plateau de correction (0,08 oct = fin … 0,5 oct = large) ET l'échelle de détection.
  PLAFOND   réduction bornée bande par bande, étendue en plateau, puis NORMALISÉE LOCALEMENT : S_eff,k = Σⱼ aⱼ·Re Hⱼ(fₖ) (aⱼ = bande active),
            noyau invariant sur la grille logarithmique → l'effet au centre d'un plateau vaut exactement le gain, quelle que soit sa largeur.
            Bandes de synthèse SIMPLES (24/oct, Q 20 : ondulation 3 %) — pas de cascade (la phase dépasserait ±90° et inverserait le sens).
  DYNAMIQUE réduction lissée attaque 4 ms / relâchement 80 ms ; état conservé entre blocs (résultat indépendant de la taille des blocs) ;
            latence nulle ; causal.
  BIPOLAIRE gain < 0 supprime les excès (jusqu'à |gain|), gain > 0 les réhausse.
"""
import os
import numpy as np
from scipy.signal import lfilter, freqz
from scipy.ndimage import uniform_filter1d, maximum_filter1d, convolve1d
from prisme_dsp import rbj_bandpass0db
from prisme_band import zone_filter

RA0, QA0, QS0, JK0 = 24, 14.0, 20.0, 18      # référence v3 : 24 bandes/octave, Q 14 (analyse) / 20 (synthèse), noyau ±18 bandes
RA_DEFAULT = int(os.environ.get('TAME_RA', '24'))
INTERP_DEFAULT = os.environ.get('TAME_INTERP', '1') == '1'
DEC = 16         # la détection (niveaux, excès, lissage) tourne à fs/16 : les niveaux de bande varient lentement (τ ≥ 4 ms)


def _grille(shape, f0, q, fs, ctx, RA=24):
    if shape == "bell":
        sq3 = np.sqrt(3.0) / q
        demi = np.log2((sq3 + np.sqrt(sq3 ** 2 + 4)) / 2)
        lo, hi = f0 / 2 ** (demi + ctx), f0 * 2 ** (demi + ctx)
    elif shape == "highshelf":
        lo, hi = f0 / 2 ** ctx, 0.45 * fs
    else:
        lo, hi = 25.0, f0 * 2 ** ctx
    lo = max(lo, 20.0)
    hi = min(hi, 0.45 * fs)
    n = max(int(np.ceil(np.log2(hi / lo) * RA)) + 1, 8)
    f = lo * 2 ** (np.arange(n) / RA)
    return f[f < 0.45 * fs]


class Tame:
    def __init__(self, fs, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=0.5, thresh_db=4.5, ratio=None, ctx=1.0, ra=None, interp=None):
        RA = self.RA = RA_DEFAULT if ra is None else ra
        self.interp = INTERP_DEFAULT if interp is None else interp
        QA, QS, JK = self.QA, self.QS, self.JK = QA0 * RA / RA0, QS0 * RA / RA0, max(2, int(round(JK0 * RA / RA0)))
        self.fs, self.sign, self.depth = fs, (1.0 if gain_db > 0 else -1.0), abs(gain_db)
        self.f = f = _grille(shape, f0, q, fs, ctx, RA)
        N = self.N = len(f)
        b, a = zone_filter(shape, fs, f0, q)
        self.w = np.abs(freqz(b, a, worN=2 * np.pi * f / fs)[1])
        self.act = np.where(self.w >= 0.02)[0]
        self.ratio = float(np.clip(self.depth / 4.5, 1.0, 3.0)) if ratio is None else ratio
        self.seuil = thresh_db - 1.0 * (1.0 - width)
        p = 0.08 + 0.42 * (1.0 - width) ** 1.5                       # demi-largeur du plateau (octaves)
        self.n_p = int(round(RA * p))
        sm = 0.0 if width >= 0.999 else 0.6 * p
        self.size_sm = max(3, 2 * int(round(RA * sm)) + 1)
        self.size_o = 2 * int(round(RA * (0.5 + (1.0 - width)))) + 1
        self.size_i = 2 * int(round(RA * (p + 0.05))) + 1
        self.size_o = max(self.size_o, self.size_i + 2)
        self.size_s = max(3, 2 * (self.n_p // 2) + 1)
        self.ca = [rbj_bandpass0db(fs, fk, QA) for fk in f]
        self.cs = {k: rbj_bandpass0db(fs, f[k], QS) for k in self.act}
        self.za = [np.zeros(2) for _ in range(N)]
        self.zs = {k: np.zeros(2) for k in self.act}
        tf = np.maximum.reduce([np.full(N, 0.004), 3.0 / f, QA / (np.pi * f)])
        ts = np.maximum(0.10, 10.0 / f)
        self.cf, self.cs_env = np.exp(-1.0 / (tf * fs)), np.exp(-1.0 / (ts * fs))
        self.zef, self.zes = np.zeros((N, 1)), np.zeros((N, 1))
        self.c_att, self.c_rel = np.exp(-DEC / (0.004 * fs)), np.exp(-DEC / (0.08 * fs))        # à cadence décimée
        self.zra, self.zrr = np.zeros((N, 1)), np.zeros((N, 1))
        self.count = 0
        self.last_red, self.last_S = np.zeros(N), np.ones(N)
        self.c_fin = np.exp(-1.0 / (0.0006 * fs))                                                # lissage plein débit des seules bandes actives
        self.zfin = np.zeros((len(self.act), 1))
        # noyau de normalisation : K[δ] = Re H_{k+δ}(f_k), invariant sur la grille logarithmique
        fc = 3000.0 * 2 ** (np.arange(-JK, JK + 1) / RA)
        pts = 2 * np.pi * 3000.0 / fs
        self.K = np.array([freqz(*rbj_bandpass0db(fs, fj, QS), worN=[pts])[1][0].real for fj in fc])

    def _detect(self, x):
        """Analyse, niveaux, excès, réduction et normalisation aux points décimés ; renvoie (n, idx, m, red_d, S_d)."""
        n, N = len(x), self.N
        idx = np.arange((-self.count) % DEC, n, DEC)                       # points de décimation alignés sur l'indice absolu
        m = len(idx)
        ef_s = np.empty((N, m)); es_s = np.empty((N, m))
        for k in range(N):
            bk, self.za[k] = lfilter(*self.ca[k], x, zi=self.za[k])
            ab = np.abs(bk)
            ef, self.zef[k] = lfilter([1 - self.cf[k]], [1, -self.cf[k]], ab, zi=self.zef[k])
            es, self.zes[k] = lfilter([1 - self.cs_env[k]], [1, -self.cs_env[k]], ab, zi=self.zes[k])
            ef_s[k], es_s[k] = ef[idx], es[idx]
        if m > 0:
            L = (20.0 * np.log10(np.maximum(es_s, 0.5 * ef_s) * (np.pi / 2) + 1e-12)).astype(np.float32)
            Lp = maximum_filter1d(L, size=3, axis=0, mode="nearest")
            Ls = uniform_filter1d(Lp, size=self.size_sm, axis=0, mode="nearest")
            mo = uniform_filter1d(Ls, size=self.size_o, axis=0, mode="nearest")
            mi = uniform_filter1d(Ls, size=self.size_i, axis=0, mode="nearest")
            ref = (mo * self.size_o - mi * self.size_i) / (self.size_o - self.size_i)
            e = Ls - ref - self.seuil
            ep = np.where(e >= 1.0, e, np.where(e <= -1.0, 0.0, 0.25 * (e + 1.0) ** 2))          # genou quadratique
            gate = np.clip((Lp + 95.0) / 10.0, 0.0, 1.0)                                          # rien sous −95 dBFS
            red = np.minimum(self.ratio * ep * gate, self.depth)
            red = maximum_filter1d(red, size=2 * self.n_p + 1, axis=0, mode="nearest")            # plateau
            red = uniform_filter1d(red, size=self.size_s, axis=0, mode="nearest")
            red = (red * self.w[:, None]).astype(np.float32)
            ra, self.zra = lfilter([1 - self.c_att], [1, -self.c_att], red, axis=1, zi=self.zra)
            rr, self.zrr = lfilter([1 - self.c_rel], [1, -self.c_rel], red, axis=1, zi=self.zrr)
            red_d = np.maximum(ra, rr)
            actif = (red_d > 0.25).astype(np.float32)                                              # normalisation locale (cadence décimée)
            S_d = np.maximum(convolve1d(actif, self.K.astype(np.float32), axis=0, mode="constant"), 1.0)
        else:
            red_d = np.empty((N, 0), dtype=np.float32); S_d = np.empty((N, 0), dtype=np.float32)
        return n, idx, m, red_d, S_d

    def process(self, x, keep=False):
        n, idx, m, red_d, S_d = self._detect(x)
        N = self.N
        if self.interp:
            return self._sortie_interp(x, n, idx, m, red_d, S_d, keep)
        # maintien d'ordre zéro jusqu'au point suivant, puis lissage court plein débit sur les bandes actives
        pos = np.full(n, -1); pos[idx] = np.arange(m)
        ff = np.maximum.accumulate(pos) + 1
        red_ext = np.concatenate([self.last_red[self.act, None], red_d[self.act]], axis=1)
        S_ext = np.concatenate([self.last_S[self.act, None], S_d[self.act]], axis=1)
        red_full, self.zfin = lfilter([1 - self.c_fin], [1, -self.c_fin], red_ext[:, ff], axis=1, zi=self.zfin)
        S_full = S_ext[:, ff]
        if m > 0:
            self.last_red, self.last_S = red_d[:, -1].astype(np.float64), S_d[:, -1].astype(np.float64)
        self.count += n
        y = np.asarray(x, dtype=np.float64).copy()
        for j, k in enumerate(self.act):
            bs, self.zs[k] = lfilter(*self.cs[k], x, zi=self.zs[k])
            y += ((10.0 ** (self.sign * red_full[j].astype(np.float64) / 20.0) - 1.0) / S_full[j]) * bs
        if keep:
            full = np.zeros((N, n), dtype=np.float32); full[self.act] = red_full
            return y, full
        return y

    def _sortie_interp(self, x, n, idx, m, red_d, S_d, keep):
        """Variante allégée : le coefficient c = (g − 1)/S n'est calculé (exp, division) qu'aux points décimés (fs/16) ; entre deux points il monte
        linéairement de l'ancienne cible vers la nouvelle (retard de 16 échantillons, causal). Plus de lissage plein débit."""
        N = self.N
        if not hasattr(self, "c_prev"):
            self.c_prev, self.c_cur = np.zeros(len(self.act)), np.zeros(len(self.act))
            self.r_prev, self.r_cur = np.zeros(len(self.act)), np.zeros(len(self.act))
        pos = np.full(n, -1); pos[idx] = np.arange(m)
        ff = np.maximum.accumulate(pos) + 1
        ph = ((self.count + np.arange(n)) % DEC) / DEC
        r_pts = red_d[self.act].astype(np.float64)
        c_pts = (10.0 ** (self.sign * r_pts / 20.0) - 1.0) / S_d[self.act].astype(np.float64)
        c_ext = np.concatenate([self.c_prev[:, None], self.c_cur[:, None], c_pts], axis=1)
        r_ext = np.concatenate([self.r_prev[:, None], self.r_cur[:, None], r_pts], axis=1)
        c_full = c_ext[:, ff] * (1 - ph) + c_ext[:, ff + 1] * ph
        r_full = r_ext[:, ff] * (1 - ph) + r_ext[:, ff + 1] * ph
        if m > 0:
            self.c_prev, self.c_cur = c_ext[:, -2].copy(), c_ext[:, -1].copy()
            self.r_prev, self.r_cur = r_ext[:, -2].copy(), r_ext[:, -1].copy()
        self.count += n
        y = np.asarray(x, dtype=np.float64).copy()
        for j, k in enumerate(self.act):
            bs, self.zs[k] = lfilter(*self.cs[k], x, zi=self.zs[k])
            y += c_full[j] * bs
        if keep:
            full = np.zeros((N, n), dtype=np.float32); full[self.act] = r_full
            return y, full
        return y


class TameStereo:
    """Détection LIÉE : l'analyse, les niveaux et les gains sont calculés une fois sur le milieu (L+R)/2 ; les deux canaux reçoivent la même correction
    (chacun garde ses propres filtres de synthèse). Coût ≈ 1 × la détection + 2 × la synthèse au lieu de 2 × tout."""
    def __init__(self, fs, *a, **k):
        self.t = Tame(fs, *a, **k)
        self.t2 = None

    def process(self, L, R):
        t = self.t
        n, idx, m, red_d, S_d = t._detect(0.5 * (L + R))
        if self.t2 is None:
            self.t2 = {kk: np.zeros(2) for kk in t.act}
        if not hasattr(t, "c_prev"):
            t.c_prev, t.c_cur = np.zeros(len(t.act)), np.zeros(len(t.act))
        pos = np.full(n, -1); pos[idx] = np.arange(m)
        ff = np.maximum.accumulate(pos) + 1
        ph = ((t.count + np.arange(n)) % DEC) / DEC
        c_pts = (10.0 ** (t.sign * red_d[t.act].astype(np.float64) / 20.0) - 1.0) / S_d[t.act].astype(np.float64)
        c_ext = np.concatenate([t.c_prev[:, None], t.c_cur[:, None], c_pts], axis=1)
        c_full = c_ext[:, ff] * (1 - ph) + c_ext[:, ff + 1] * ph
        if m > 0:
            t.c_prev, t.c_cur = c_ext[:, -2].copy(), c_ext[:, -1].copy()
        t.count += n
        yL, yR = np.asarray(L, dtype=np.float64).copy(), np.asarray(R, dtype=np.float64).copy()
        for j, k in enumerate(t.act):
            bl, t.zs[k] = lfilter(*t.cs[k], L, zi=t.zs[k])
            br, self.t2[k] = lfilter(*t.cs[k], R, zi=self.t2[k])
            yL += c_full[j] * bl
            yR += c_full[j] * br
        return yL, yR


def tame_stereo(x, fs, block=8192, **kw):
    """x : (n, 2). Détection liée sur le milieu, correction identique sur L et R."""
    t = TameStereo(fs, **kw)
    y = np.empty_like(x)
    for i in range(0, len(x), block):
        y[i:i + block, 0], y[i:i + block, 1] = t.process(x[i:i + block, 0], x[i:i + block, 1])
    return y


def tame_band(x, fs, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=0.5, thresh_db=4.5, ratio=None, ctx=1.0,
              block=8192, diag=False, ra=None, interp=None):
    """Tame bipolaire. gain_db < 0 : supprime les résonances ; > 0 : les réhausse. width : 0 large … 1 fin."""
    if gain_db == 0.0:
        return x.copy()
    t = Tame(fs, shape, f0, q, gain_db, width, thresh_db, ratio, ctx, ra, interp)
    y = np.empty(len(x))
    reds = []
    for i in range(0, len(x), block):
        out = t.process(x[i:i + block], keep=diag)
        if diag:
            y[i:i + block], r = out
            reds.append(r)
        else:
            y[i:i + block] = out
    if diag:
        return y, dict(f=t.f, w=t.w, red_full=np.concatenate(reds, axis=1))
    return y
