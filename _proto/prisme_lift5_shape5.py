"""PRISME — Lift v5 et Shape v5 lisant l'ANALYSE PARTAGÉE (prisme_tame5.AnalysePartagee) — essai du 2026-10-01.

  Lift v5 : seuil RELATIF. Niveau de la zone relatif à son spectre long terme (rel = Ls − lt − décalage, en dB, moyenne pondérée par la zone) ;
            s = smoothstep((Th − rel)/W), Th = −(2 + 0,13·Amount) dB (0 % → −2 dB, 100 % → −15 dB sous l'habituel) ;
            porte de souffle : niveau absolu de la zone (Lp) < −80 dBFS → rien ; relâchement ADAPTATIF (50 ms si le niveau chute vite, 300 ms si lent), coupure rapide (5 ms).
  Shape v5 : détection de PERCUSSION. Montée rapide (dB) de chaque bande de la grille sur un retard de 5–30 ms ; montée de la zone (poids de zone) ET « étendue » B
            = fraction des bandes (autour de la zone ±1,5 oct, ou de tout le spectre) qui montent ensemble de plus de 3 dB : une attaque de percussion
            fait monter beaucoup de bandes à la fois, une note qui commence n'en fait monter que quelques-unes (harmoniques). Seuil d'étendue 40 %.
  Les deux appliquent leur gain, comme les versions v4 (prisme_lift / prisme_shape), sur le signal de zone b au débit plein (poids interpolés linéairement depuis fs/16).
"""
import numpy as np
from scipy.signal import lfilter, freqz
from scipy.ndimage import uniform_filter1d
from prisme_band import zone_filter
from prisme_shape import _tient_relache
from prisme_tame5 import DEC, RA, _zone_lo_hi


def smoothstep(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _zone(fg, shape, f0, q, fs, ctx=1.0, mini=8):
    lo, hi = _zone_lo_hi(shape, f0, q, fs, ctx)
    sel = np.where((fg >= lo * 0.999) & (fg <= hi * 1.001))[0]
    if len(sel) < mini:
        c = int(np.argmin(np.abs(np.log2(fg / f0))))
        sel = np.arange(max(0, c - mini // 2), min(len(fg), c + mini // 2))
    b, a = zone_filter(shape, fs, f0, q)
    w = np.abs(freqz(b, a, worN=2 * np.pi * fg[sel] / fs)[1])
    return int(sel[0]), int(sel[-1]) + 1, w, (b, a)


class _Interp:
    """Valeurs à fs/16 → débit plein (interpolation linéaire, état conservé entre blocs)."""
    def __init__(self, v0=0.0):
        self.v, self.p = v0, 0

    def __call__(self, n, idx, vals):
        if len(idx) == 0:
            return np.full(n, self.v)
        xs = np.concatenate([[self.p], idx])
        vs = np.concatenate([[self.v], vals])
        out = np.interp(np.arange(n), xs, vs)
        self.v, self.p = float(vals[-1]), int(idx[-1]) - n
        return out


class Lift5:
    def __init__(self, fs, fg, shape="bell", f0=1000.0, q=1.0, gain_db=6.0, amount=50.0):
        self.fs, self.G = fs, float(gain_db)
        self.i0, self.i1, self.w, (self.b, self.a) = _zone(fg, shape, f0, q, fs)
        self.w2 = (self.w ** 2) / np.sum(self.w ** 2)
        self.W = max(1.667 * abs(self.G), 6.0)
        self.Th = -(2.0 + 0.13 * float(np.clip(amount, 0.0, 100.0)))
        d = DEC / fs
        self.c_cut, self.c_fast, self.c_slow = (np.exp(-d / t) for t in (0.005, 0.05, 0.30))
        self.zc, self.zf, self.zs, self.zb = np.zeros(1), np.zeros(1), np.zeros(1), np.zeros(2)
        self.prev_rel = None
        self.itp = _Interp()
        self.lag = max(1, int(round(0.05 * fs / DEC)))
        self.hist = None

    def process(self, x, ana_out, ana, keep=False):
        n, idx, m, Lp, e = ana_out
        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)
        if m > 0:
            sl = slice(self.i0, self.i1)
            rel = self.w2 @ ana.rel[sl]                                    # niveau relatif de la zone
            Lz = self.w2 @ Lp[sl]
            s0 = smoothstep((self.Th - rel) / self.W) * smoothstep((Lz + 80.0) / 10.0)
            if self.G < 0:
                s0 = smoothstep((self.Th - rel) / self.W)                  # expandeur : pas besoin de porte
            ext = rel if self.hist is None else np.concatenate([self.hist, rel])
            if self.hist is None:
                ext = np.concatenate([np.full(self.lag, rel[0]), rel])
            vit = np.abs(ext[self.lag:] - ext[:-self.lag]) if len(ext) > self.lag else np.zeros(m)
            vit = vit[-m:]
            self.hist = ext[-self.lag:]
            a = np.clip(vit / 6.0, 0.0, 1.0)                               # chute rapide → relâchement court
            sf, self.zf = lfilter([1 - self.c_fast], [1, -self.c_fast], s0, zi=self.zf)
            ss, self.zs = lfilter([1 - self.c_slow], [1, -self.c_slow], s0, zi=self.zs)
            s_up = a * sf + (1 - a) * ss                                   # montée lente (chute rapide du niveau → montée plus vive)
            s_min = np.minimum(s0, s_up)                                   # le gain ne dépasse jamais le besoin courant
            s_pts, self.zc = lfilter([1 - self.c_cut], [1, -self.c_cut], s_min, zi=self.zc)
            s_full = self.itp(n, idx, s_pts)
        else:
            s_full = self.itp(n, idx, np.empty(0))
        g = 10.0 ** (self.G * s_full / 20.0)
        y = x + (g - 1.0) * b
        return (y, g) if keep else y


class Shape5:
    def __init__(self, fs, fg, cible="transitoires", shape="bell", f0=60.0, q=1.0, gain_db=6.0, time_ms=None, sens=0.85):
        self.fs, self.cible, self.A = fs, cible, 10.0 ** (gain_db / 20.0)
        self.i0, self.i1, self.w, (self.b, self.a) = _zone(fg, shape, f0, q, fs)
        self.wn = self.w / self.w.max()
        lo, hi = _zone_lo_hi(shape, f0, q, fs, 1.5)
        self.c0, self.c1 = int(np.searchsorted(fg, lo * 0.999)), int(np.searchsorted(fg, hi * 1.001))
        self.g0 = int(np.searchsorted(fg, 60.0))
        tf = float(np.clip(3.0 / f0, 0.005, 0.03))
        self.lag = max(2, int(round(tf * fs / DEC)))
        self.m0 = 10.0 - 9.0 * sens
        self.hist = None
        tau_rel = (time_ms / 1000.0) / 3.0 if time_ms else 1.0 * tf
        self.c_rel = np.exp(-DEC / (tau_rel * fs))
        att_periods = float(np.clip(0.45 + 0.35 * np.log2(f0 / 60.0) / np.log2(250.0 / 60.0), 0.45, 0.8))
        self.c_att = np.exp(-1.0 / (max(att_periods / f0, 1.0 / fs) * fs))
        self.zb, self.z_att, self.y_hold = np.zeros(2), np.zeros(1), 0.0
        self.itp = _Interp()

    def process(self, x, ana_out, ana, keep=False):
        n, idx, m, Lp, e = ana_out
        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)
        if m > 0:
            Lf = ana.Lf
            ext = np.concatenate([self.hist, Lf], axis=1) if self.hist is not None else np.concatenate([np.repeat(Lf[:, :1], self.lag, axis=1), Lf], axis=1)
            self.hist = ext[:, -self.lag:]
            rise = ext[:, self.lag:] - ext[:, :-self.lag]                  # montée en dB sur le retard
            up = np.maximum(rise, 0.0)
            Rz = (self.wn[:, None] * up[self.i0:self.i1]).max(axis=0)       # montée de pointe de la zone (pondérée par la zone)
            ctx = (rise[self.c0:self.c1] > 3.0).mean(axis=0)               # étendue locale
            glob = (rise[self.g0:] > 3.0).mean(axis=0)                     # étendue sur tout le spectre
            B = np.maximum(ctx, glob)
            T = np.clip((Rz - self.m0) / 4.0, 0.0, 1.0) * smoothstep((B - 0.5) / 0.25)
            T *= np.clip((Lf[self.i0:self.i1].max(axis=0) + 95.0) / 10.0, 0.0, 1.0)
            Th, self.y_hold = _tient_relache(T, self.c_rel, self.y_hold)
            T_full = self.itp(n, idx, Th)
        else:
            T_full = self.itp(n, idx, np.empty(0))
        Tl, self.z_att = lfilter([1 - self.c_att], [1, -self.c_att], T_full, zi=self.z_att)
        poids = Tl if self.cible == "transitoires" else 1.0 - Tl
        g = 1.0 + (self.A - 1.0) * poids
        y = x + (g - 1.0) * b
        return (y, g) if keep else y
