"""PRISME — Exciter en FLUX (2026-09-25) : la recette « Iron Auto flanc raide » traitée bloc par bloc, états conservés.

Reproduit EXACTEMENT `excite_band` (source Auto ou Bande, gain adaptatif, suréchantillonnage ×2, ADAA, de-emphasis par projection sur la réponse
linéaire de la même chaîne, filtre de sortie à `out_sections` sections, normalisation par la zone) : mêmes filtres, mêmes constantes.

LATENCE : le suréchantillonnage ×2 (FIR de 41 coefficients, le même que `resample_poly`) retarde la chaîne de D_OS = 20 échantillons de base.
Tout ce qui se combine avec elle (gain adaptatif, source, zone) est retardé d'autant ; `process` renvoie le DELTA aligné sur l'entrée retardée
de D_OS : sortie du plugin = entrée retardée de D_OS + Σ deltas. Latence à déclarer à l'hôte : D_OS échantillons (≈ 0,42 ms à 48 kHz).
"""
import numpy as np
from scipy.signal import lfilter, firwin
from prisme_dsp import MODES, rect_curves
from prisme_band import zone_filter, H_DOMINANT, AGC_TAU, AGC_GMIN, AGC_GMAX_DB, rbj_shelf, tilt_pivot, TILT_DB

H0 = firwin(41, 0.5, window=("kaiser", 5.0))          # filtre de `resample_poly(x, 2, 1)` et `resample_poly(x, 1, 2)`
H_UP, H_DN = 2.0 * H0, H0
D_OS = 20                                              # (40 échantillons à ×2) / 2
EPS_ADAA = 1e-6


def _courbe(mode, drive=1.5):
    if mode == "lin":
        return (lambda v: v), (lambda v: 0.5 * v * v)
    if mode == "rect":                       # le Rectifier est homogène (|x|) : « Saturation » agit sur le coude, eps ∝ 1/drive² (0,05 à drive 1,5)
        return rect_curves(0.05 * (1.5 / drive) ** 2)
    f, F, _ = MODES[mode]
    return f, F


def _adaa(v, courbe, x1):
    f, F = courbe
    xp = np.concatenate(([x1], v[:-1]))
    dx = v - xp
    petit = np.abs(dx) < EPS_ADAA
    sur = np.where(petit, 1.0, dx)
    return np.where(petit, f(0.5 * (v + xp)), (F(v) - F(xp)) / sur), v[-1]


class Delai:
    def __init__(self, n, init=0.0):
        self.n, self.buf = n, np.full(n, init)

    def push(self, x):
        if self.n == 0:
            return x
        ext = np.concatenate([self.buf, x])
        self.buf = ext[len(x):]
        return ext[:len(x)]


def _un_pole(a, x, zi):
    return lfilter([1 - a], [1, -a], x, zi=zi)


class ExciterStream:
    latence = D_OS

    def __init__(self, fs, shape="bell", f0=12000.0, q=2.0, gain_db=5.0, mode="iron", source="auto", drive=1.5,
                 out_sections=3, src_q=2.0, floor_ratio=0.05, norm_tau=0.2, null_tau=0.03, env_tau=AGC_TAU, gmin=AGC_GMIN, gmax_db=AGC_GMAX_DB, tilt=0.0):
        self.fs, self.mode, self.source, self.drive = fs, mode, source, drive
        self.sign, self.amount = (1.0 if gain_db >= 0 else -1.0), 10.0 ** (abs(gain_db) / 20.0) - 1.0
        self.floor_ratio, self.out_sections = floor_ratio, out_sections
        self.focus = source != "band"
        self.courbe, self.courbe_lin = _courbe(mode, drive), _courbe("lin")
        if source == "auto":
            self.zf = zone_filter(shape, fs, max(f0 / H_DOMINANT[mode], 60.0), max(q, src_q))
            self.z_src = [np.zeros(2), np.zeros(2)]
        else:                                                              # « Bande »
            self.zf = zone_filter(shape, fs, f0, q)
            self.z_src = [np.zeros(2)]
        # Tilt (mode Bande seulement) : bascule de tonalité de la source AVANT la saturation → décide quelle partie de la zone sature le plus (le « profil »)
        self.tilt_f = None
        if source != "auto" and abs(tilt) > 1e-9:
            pv = tilt_pivot(shape, f0, fs)
            self.tilt_f = [rbj_shelf(fs, pv, -0.5 * TILT_DB * tilt, False), rbj_shelf(fs, pv, +0.5 * TILT_DB * tilt, True)]
            self.z_tilt = [np.zeros(2), np.zeros(2)]
        self.count = 0                                                     # échantillons de base déjà traités
        self.a_env = np.exp(-1.0 / (env_tau * fs))
        self.gmin, self.gmax = gmin, 10.0 ** (gmax_db / 20.0)
        self.z_env = np.zeros(1)
        self.z_up, self.z_dn, self.z_dl = np.zeros(40), np.zeros(40), np.zeros(40)
        self.x1, self.x1l = 0.0, 0.0
        self.d_g, self.d_s, self.d_x = Delai(D_OS, 1.0), Delai(D_OS), Delai(D_OS)      # le gain adaptatif vaut ≥ 1 : jamais de division par 0
        self.a_null = np.exp(-1.0 / (null_tau * fs))
        self.z_num, self.z_den = np.zeros(1), np.zeros(1)
        self.r_dc = 1.0 - 2.0 * np.pi * 20.0 / fs
        self.z_dc = np.zeros(1)
        self.zo = zone_filter(shape, fs, f0, q)
        self.z_out = [np.zeros(2) for _ in range(out_sections)]
        self.a_norm = np.exp(-1.0 / (norm_tau * fs))
        self.z_rs, self.z_rz, self.z_rr = np.zeros(1), np.zeros(1), np.zeros(1)
        self.zb_filtre = zone_filter(shape, fs, f0, q)
        self.z_zb = np.zeros(2)
        self.zr = zone_filter(shape, fs, max(f0 / H_DOMINANT[mode], 60.0), max(q, src_q))
        self.z_ref = [np.zeros(2), np.zeros(2)]

    def process(self, x):
        n = len(x)
        # source
        s0 = x
        for i in range(len(self.z_src)):
            s0, self.z_src[i] = lfilter(*self.zf, s0, zi=self.z_src[i])
        if self.tilt_f is not None:
            for i in range(2):
                s0, self.z_tilt[i] = lfilter(*self.tilt_f[i], s0, zi=self.z_tilt[i])
        # gain adaptatif (AGC : 0,05 … +40 dB)
        env, self.z_env = _un_pole(self.a_env, np.abs(s0), self.z_env)
        g = np.clip(self.drive / np.maximum(env * (np.pi / 2), 1e-9), self.gmin, self.gmax)
        sin = s0 * g
        # suréchantillonnage ×2, ADAA sur la courbe et sur la courbe linéaire, retour ×1 (latence D_OS)
        zs = np.zeros(2 * n)
        zs[::2] = sin
        v, self.z_up = lfilter(H_UP, [1.0], zs, zi=self.z_up)
        # démarrage : la version hors ligne (zéro-phase) n'a jamais vu la montée en régime des FIR ; on l'écarte pour être identique dès t = 0
        v = np.where(np.arange(2 * n) + 2 * self.count >= D_OS, v, 0.0)
        y2, self.x1 = _adaa(v, self.courbe, self.x1)
        yl2, self.x1l = _adaa(v, self.courbe_lin, self.x1l)
        y, self.z_dn = lfilter(H_DN, [1.0], y2, zi=self.z_dn)
        yl, self.z_dl = lfilter(H_DN, [1.0], yl2, zi=self.z_dl)
        y, yl = y[::2], yl[::2]
        depuis_debut = np.arange(n) + self.count >= D_OS
        y, yl = np.where(depuis_debut, y, 0.0), np.where(depuis_debut, yl, 0.0)
        # tout ce qui se combine avec y est retardé de D_OS
        g_d, s0_d, x_d = self.d_g.push(g), self.d_s.push(s0), self.d_x.push(x)
        # de-emphasis exact : projection sur la réponse linéaire de la même chaîne
        num, self.z_num = _un_pole(self.a_null, y * yl, self.z_num)
        den, self.z_den = _un_pole(self.a_null, yl * yl, self.z_den)
        res = (y - (num / (den + 1e-12)) * yl) / g_d
        res, self.z_dc = lfilter([1.0, -1.0], [1.0, -self.r_dc], res, zi=self.z_dc)
        if self.focus:
            for i in range(self.out_sections):
                res, self.z_out[i] = lfilter(*self.zo, res, zi=self.z_out[i])
        # normalisation par la zone
        if self.source == "auto":
            s_ref = s0_d
        else:
            s_ref = x_d
            for i in range(2):
                s_ref, self.z_ref[i] = lfilter(*self.zr, s_ref, zi=self.z_ref[i])
        zb, self.z_zb = lfilter(*self.zb_filtre, x_d, zi=self.z_zb)
        rs2, self.z_rs = _un_pole(self.a_norm, s_ref * s_ref, self.z_rs)
        rz2, self.z_rz = _un_pole(self.a_norm, zb * zb, self.z_rz)
        rr2, self.z_rr = _un_pole(self.a_norm, res * res, self.z_rr)
        cible = self.amount * np.maximum(np.sqrt(rz2), self.floor_ratio * np.sqrt(rs2))
        res = res * np.clip(cible / np.maximum(np.sqrt(rr2), 1e-9), 0.0, 100.0)
        self.count += n
        return self.sign * res


def exciter_stream(x, fs, block=8192, **kw):
    """Traite tout `x` par blocs ; renvoie le delta aligné sur l'entrée retardée de D_OS."""
    e = ExciterStream(fs, **kw)
    out = np.empty(len(x))
    for i in range(0, len(x), block):
        out[i:i + block] = e.process(x[i:i + block])
    return out
