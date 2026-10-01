"""PRISME — Tame v5 « analyse partagée » (2026-10-01).

Idée de llg53 : la détection par courbe de référence (Tame v4) ne doit pas être répétée dans chaque bande ; on la calcule UNE fois, en amont, sur tout le spectre,
et chaque bande (Tame aujourd'hui ; Lift et Shape ensuite) y lit ce dont elle a besoin.

  AnalysePartagee (une par signal analysé : L, R, et M / S si une bande les utilise)
    grille fixe 24 bandes/octave de 20 Hz à 0,45·fs (Q 14) ; niveau de bande = max(enveloppe lente, rapide − 6 dB) en dB ; Lp = tenue sur 3 bandes ; Ls = lissage 3 bandes
    spectre long terme lt (moyenne cumulative puis τ 3 s) ;
    courbe de référence = pour chaque bande, droite locale de lt (moindres carrés sur ±2 oct) retirée, puis percentile bas 15 % des écarts sur la même fenêtre
        → neutre pour toute pente locale (blanc, rose, grave montant…), les pics ne la font pas monter ;
        recalculée toutes les 32 trames décimées, lissée τ 20 ms ;
    décalage de niveau d'ensemble = médiane (Ls − lt) sur tout le spectre ;
    excès e = Ls − (courbe + décalage)        (dB, par bande de la grille, à fs/16)
  TameP (une par bande et par canal) : prend la tranche de la grille couvrant sa zone, puis sa propre chaîne : lissage selon la Largeur, seuil, genou, cœur des excès,
    porte −95 dBFS, ratio, plateau, poids de zone, attaque/relâchement, normalisation locale, synthèse (gains interpolés à fs/16) — comme le Tame v4.
"""
import numpy as np
from scipy.signal import lfilter, freqz
from scipy.ndimage import uniform_filter1d, maximum_filter1d, convolve1d, percentile_filter
from prisme_dsp import rbj_bandpass0db
from prisme_band import zone_filter

RA, QA, QS, JK, DEC = 24, 14.0, 20.0, 18, 16
F_MIN = 20.0
PCT, SIZE_REF, TAU_LT, PAS, TAU_COURBE = 15.0, 4 * RA + 1, 3.0, 32, 0.02          # fenêtre de 97 bandes (±2 octaves), comme le Tame v4


def grille(fs):
    n = int(np.floor(np.log2(0.45 * fs / F_MIN) * RA)) + 1
    f = F_MIN * 2 ** (np.arange(n) / RA)
    return f[f < 0.45 * fs]


class AnalysePartagee:
    def __init__(self, fs):
        self.fs = fs
        self.f = f = grille(fs)
        N = self.N = len(f)
        self.ca = [rbj_bandpass0db(fs, fk, QA) for fk in f]
        self.za = [np.zeros(2) for _ in range(N)]
        tf = np.maximum.reduce([np.full(N, 0.004), 3.0 / f, QA / (np.pi * f)])
        ts = np.maximum(0.10, 10.0 / f)
        self.cf, self.cs_env = np.exp(-1.0 / (tf * fs)), np.exp(-1.0 / (ts * fs))
        self.zef, self.zes = np.zeros((N, 1)), np.zeros((N, 1))
        self.c_lt = np.exp(-DEC / (TAU_LT * fs))
        self.a_cs = np.exp(-DEC / (TAU_COURBE * fs))
        self.v_lt, self.n_lt = None, 0
        self.courbe_c, self.courbe_s = None, None
        h = SIZE_REF // 2
        self.idx_w = np.clip(np.arange(N)[:, None] + np.arange(-h, h + 1)[None, :], 0, N - 1)    # fenêtres « nearest »
        Xw = self.idx_w / RA                                                                   # abscisses en octaves
        self.Xc = Xw - Xw.mean(axis=1, keepdims=True)
        self.XX = (self.Xc ** 2).sum(axis=1)
        self.Xk = Xw - (np.arange(N) / RA)[:, None]                                            # écart à la bande centrale
        self.rang = int(SIZE_REF * PCT / 100.0)
        self.count = 0

    def process(self, x):
        """Renvoie (n, idx, m, Lp, e) — Lp, e : float32 (N × m) aux points décimés."""
        n, N = len(x), self.N
        idx = np.arange((-self.count) % DEC, n, DEC)
        m = len(idx)
        ef_s = np.empty((N, m)); es_s = np.empty((N, m))
        for k in range(N):
            bk, self.za[k] = lfilter(*self.ca[k], x, zi=self.za[k])
            ab = np.abs(bk)
            ef, self.zef[k] = lfilter([1 - self.cf[k]], [1, -self.cf[k]], ab, zi=self.zef[k])
            es, self.zes[k] = lfilter([1 - self.cs_env[k]], [1, -self.cs_env[k]], ab, zi=self.zes[k])
            ef_s[k], es_s[k] = ef[idx], es[idx]
        self.count += n
        if m == 0:
            z = np.empty((N, 0), dtype=np.float32)
            return n, idx, m, z, z
        L = (20.0 * np.log10(np.maximum(es_s, 0.5 * ef_s) * (np.pi / 2) + 1e-12)).astype(np.float32)
        Lp = maximum_filter1d(L, size=3, axis=0, mode="nearest")
        Ls = uniform_filter1d(Lp, size=3, axis=0, mode="nearest").astype(np.float64)
        e = np.empty((N, m), dtype=np.float32)
        rel = np.empty((N, m), dtype=np.float32)
        for j in range(m):
            self.n_lt += 1
            c = max(1.0 - 1.0 / self.n_lt, 0.0) if self.n_lt * DEC / self.fs < TAU_LT else self.c_lt
            self.v_lt = Ls[:, j].copy() if self.v_lt is None else c * self.v_lt + (1.0 - c) * Ls[:, j]
            if (self.n_lt - 1) % PAS == 0:
                # pour chaque bande : droite locale (moindres carrés sur ±2 oct, bords « nearest ») retirée, puis percentile bas 15 % des écarts
                Y = self.v_lt[self.idx_w]
                a = ((self.Xc * (Y - Y.mean(axis=1, keepdims=True))).sum(axis=1)) / self.XX
                D = Y - a[:, None] * self.Xk
                self.courbe_c = np.partition(D, self.rang, axis=1)[:, self.rang]
            self.courbe_s = self.courbe_c.copy() if self.courbe_s is None else self.a_cs * self.courbe_s + (1.0 - self.a_cs) * self.courbe_c
            decal = np.median(Ls[:, j] - self.v_lt)
            e[:, j] = (Ls[:, j] - (self.courbe_s + decal)).astype(np.float32)
            rel[:, j] = Ls[:, j] - self.v_lt                     # niveau relatif à l habituel (sans le décalage d ensemble : un passage globalement faible doit compter pour le Lift)
        # sorties additionnelles pour Lift / Shape (lues par prisme_lift5_shape5) : niveau relatif au spectre long terme, niveau rapide (dBFS)
        self.rel = rel
        self.Lf = (20.0 * np.log10(ef_s * (np.pi / 2) + 1e-12)).astype(np.float32)
        return n, idx, m, Lp, e


def _zone_lo_hi(shape, f0, q, fs, ctx=1.0):
    if shape == "bell":
        sq3 = np.sqrt(3.0) / q
        demi = np.log2((sq3 + np.sqrt(sq3 ** 2 + 4)) / 2)
        lo, hi = f0 / 2 ** (demi + ctx), f0 * 2 ** (demi + ctx)
    elif shape == "highshelf":
        lo, hi = f0 / 2 ** ctx, 0.45 * fs
    else:
        lo, hi = 25.0, f0 * 2 ** ctx
    return max(lo, 20.0), min(hi, 0.45 * fs)


class TameP:
    def __init__(self, fs, fg, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=0.5, thresh_db=4.5):
        self.fs, self.sign, self.depth = fs, (1.0 if gain_db > 0 else -1.0), abs(gain_db)
        lo, hi = _zone_lo_hi(shape, f0, q, fs)
        sel = np.where((fg >= lo * 0.999) & (fg <= hi * 1.001))[0]
        if len(sel) < 8:                                           # au moins 8 bandes (comme le Tame v4)
            c = int(np.argmin(np.abs(np.log2(fg / f0))))
            sel = np.arange(max(0, c - 4), min(len(fg), c + 4))
        self.i0, self.i1 = int(sel[0]), int(sel[-1]) + 1
        self.f = f = fg[self.i0:self.i1]
        N = self.N = len(f)
        b, a = zone_filter(shape, fs, f0, q)
        self.w = np.abs(freqz(b, a, worN=2 * np.pi * f / fs)[1])
        self.act = np.where(self.w >= 0.02)[0]
        self.ratio = float(np.clip(self.depth / 4.5, 1.0, 3.0))
        self.seuil = thresh_db
        p = 0.04 + 0.66 * (1.0 - width) ** 1.5
        self.n_p = int(round(RA * p))
        sm = 0.0 if width >= 0.999 else 0.6 * p
        self.size_sm = max(3, 2 * int(round(RA * sm)) + 1)
        self.size_s = max(3, 2 * (self.n_p // 2) + 1)
        self.marge = 1.5 + 30.0 * (1.0 - width) ** 2
        self.cs = {k: rbj_bandpass0db(fs, f[k], QS) for k in self.act}
        self.zs = {k: np.zeros(2) for k in self.act}
        self.c_att, self.c_rel = np.exp(-DEC / (0.004 * fs)), np.exp(-DEC / (0.08 * fs))
        self.zra, self.zrr = np.zeros((N, 1)), np.zeros((N, 1))
        self.count = 0
        fc = 3000.0 * 2 ** (np.arange(-JK, JK + 1) / RA)
        pts = 2 * np.pi * 3000.0 / fs
        self.K = np.array([freqz(*rbj_bandpass0db(fs, fj, QS), worN=[pts])[1][0].real for fj in fc])
        self.c_prev, self.c_cur = np.zeros(len(self.act)), np.zeros(len(self.act))
        self.r_prev, self.r_cur = np.zeros(len(self.act)), np.zeros(len(self.act))

    def detect1(self, Lp_all, e_all, m):
        """Réduction par bande `red` (float32, N × m) à partir de l'analyse partagée — c'est ici qu'agit la liaison stéréo."""
        if m == 0:
            return None
        Lp, e0 = Lp_all[self.i0:self.i1], e_all[self.i0:self.i1]
        e = uniform_filter1d(e0, size=self.size_sm, axis=0, mode="nearest") - np.float32(self.seuil)
        ep = np.where(e >= 1.0, e, np.where(e <= -1.0, 0.0, 0.25 * (e + 1.0) ** 2)).astype(np.float32)
        cime = maximum_filter1d(ep, size=2 * self.n_p + 3, axis=0, mode="nearest")
        ep = np.where(ep >= cime - np.float32(self.marge), ep, 0.0).astype(np.float32)
        gate = np.clip((Lp + 95.0) / 10.0, 0.0, 1.0)
        red = np.minimum(self.ratio * ep * gate, self.depth)
        red = maximum_filter1d(red, size=2 * self.n_p + 1, axis=0, mode="nearest")
        red = uniform_filter1d(red, size=self.size_s, axis=0, mode="nearest")
        return (red * self.w[:, None]).astype(np.float32)

    def detect2(self, red, m):
        N = self.N
        if m == 0:
            z = np.empty((N, 0), dtype=np.float32)
            return z, z
        ra, self.zra = lfilter([1 - self.c_att], [1, -self.c_att], red, axis=1, zi=self.zra)
        rr, self.zrr = lfilter([1 - self.c_rel], [1, -self.c_rel], red, axis=1, zi=self.zrr)
        red_d = np.maximum(ra, rr)
        actif = (red_d > 0.25).astype(np.float32)
        S_d = np.maximum(convolve1d(actif, self.K.astype(np.float32), axis=0, mode="constant"), 1.0)
        return red_d, S_d

    def synth(self, x, idx, m, red_d, S_d, keep=False):
        n, N = len(x), self.N
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

    def process(self, x, ana_out, keep=False, red=None):
        n, idx, m, Lp, e = ana_out
        if red is None:
            red = self.detect1(Lp, e, m)
        red_d, S_d = self.detect2(red, m)
        return self.synth(x, idx, m, red_d, S_d, keep)


def tame_band(x, fs, shape="bell", f0=3000.0, q=0.7, gain_db=-9.0, width=0.5, thresh_db=4.5, block=8192, diag=False, **_):
    """Même interface que prisme_tame.tame_band (une analyse partagée dédiée au signal x)."""
    if gain_db == 0.0:
        return x.copy()
    ana = AnalysePartagee(fs)
    t = TameP(fs, ana.f, shape, f0, q, gain_db, width, thresh_db)
    y = np.empty(len(x))
    reds = []
    for i in range(0, len(x), block):
        out = t.process(x[i:i + block], ana.process(x[i:i + block]), keep=diag)
        if diag:
            y[i:i + block], r = out
            reds.append(r)
        else:
            y[i:i + block] = out
    if diag:
        return y, dict(f=t.f, w=t.w, red_full=np.concatenate(reds, axis=1))
    return y
