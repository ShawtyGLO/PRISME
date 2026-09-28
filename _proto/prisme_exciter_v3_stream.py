"""PRISME — Exciter v3 « Aural » en FLUX (2026-09-28) : référence des tests C++. Principe : prisme_exciter_v3.py (prototype validé à l'oreille par llg53 : « précis et naturel »).

    source = zone de la bande (cloche / shelf) [+ Tilt] → niveau lent S (τ 400 ms) → u = drive · b / S
      → ×2 (FIR 41) → courbe ADAA ordre 1 → ×1 ; y0 = y − f(0)
      → wet = (y0 − pureté · c1 · u) · S / (drive · c1)   (c1 = gain du fondamental de la courbe pour un sinus d'amplitude drive : le fondamental du wet ≈ b)
      → filtre de la zone (1 section) → coupe-continu 20 Hz → × k,  k = 10^(g/20) − 1  (sur un signal propre, « +g dB » ≈ renfort de g dB de la zone).
    Entrée MONO (milieu : non-linéarité liée). LATENCE 20 échantillons ; `process` renvoie le wet aligné sur l'entrée retardée de 20.
"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
from prisme_band import zone_filter, rbj_shelf, tilt_pivot, TILT_DB
from prisme_exciter_stream import Delai, _adaa, H_UP, H_DN, D_OS
from prisme_exciter_v2_stream import courbe, PROFILS

TAU_LENT = 0.4
N_C1 = 256


def c1_courbe(f, drive):
    """Coefficient du fondamental de f(drive·sin θ) − f(0), divisé par drive (somme sur N_C1 points, même ordre qu'en C++)."""
    f0v = float(f(np.array([0.0]))[0])
    acc = 0.0
    for i in range(N_C1):
        th = 2.0 * np.pi * i / N_C1
        s = np.sin(th)
        acc += (float(f(np.array([drive * s]))[0]) - f0v) * s
    return max(2.0 * acc / N_C1 / drive, 1e-6)


class ExciterV3Stream:
    latence = D_OS

    def __init__(self, fs, shape="bell", f0=3000.0, q=0.71, gain_db=6.0, profil="mordant_chaud", drive=2.5, tilt=0.0, purete=0.0):
        self.fs, self.drive, self.purete = fs, drive, purete
        self.k = 10.0 ** (gain_db / 20.0) - 1.0
        self.f, self.F, self.pente = courbe(profil)
        self.fz = float(self.f(np.array([0.0]))[0])
        self.c1 = c1_courbe(self.f, drive)
        self.zf = zone_filter(shape, fs, f0, q)
        self.z_src, self.z_out = np.zeros(2), np.zeros(2)
        self.tilt_f = None
        if abs(tilt) > 1e-9:
            pv = tilt_pivot(shape, f0, fs)
            self.tilt_f = [rbj_shelf(fs, pv, -0.5 * TILT_DB * tilt, False), rbj_shelf(fs, pv, +0.5 * TILT_DB * tilt, True)]
            self.z_tilt = [np.zeros(2), np.zeros(2)]
        self.cS = np.exp(-1.0 / (TAU_LENT * fs))
        self.z_S = np.zeros(1)
        self.z_up, self.z_dn = np.zeros(40), np.zeros(40)
        self.x1 = 0.0
        self.d_u, self.d_S = Delai(D_OS), Delai(D_OS, 1e-7)
        self.r_dc = 1.0 - 2.0 * np.pi * 20.0 / fs
        self.z_dc = np.zeros(1)

    def process(self, x):
        n = len(x)
        b, self.z_src = lfilter(*self.zf, x, zi=self.z_src)
        if self.tilt_f is not None:
            for i in range(2):
                b, self.z_tilt[i] = lfilter(*self.tilt_f[i], b, zi=self.z_tilt[i])
        S, self.z_S = lfilter([1 - self.cS], [1, -self.cS], np.abs(b), zi=self.z_S)
        S = S * (np.pi / 2) + 1e-7
        u = self.drive * b / S
        zs = np.zeros(2 * n)
        zs[::2] = u
        w, self.z_up = lfilter(H_UP, [1.0], zs, zi=self.z_up)
        y2, self.x1 = _adaa(w, (self.f, self.F), self.x1)
        y, self.z_dn = lfilter(H_DN, [1.0], y2, zi=self.z_dn)
        y = y[::2]
        u_d, S_d = self.d_u.push(u), self.d_S.push(S)
        res = (y - self.fz - self.purete * self.c1 * u_d) * S_d / (self.drive * self.c1)      # pureté : retire le fondamental RÉEL de la courbe (c1·u), pas la pente
        res, self.z_out = lfilter(*self.zf, res, zi=self.z_out)
        res, self.z_dc = lfilter([1.0, -1.0], [1.0, -self.r_dc], res, zi=self.z_dc)
        return self.k * res


def exciter_v3_stream(x, fs, block=8192, **kw):
    e = ExciterV3Stream(fs, **kw)
    out = np.empty(len(x))
    for i in range(0, len(x), block):
        out[i:i + block] = e.process(x[i:i + block])
    return out


def excite_v3_aligne(x, fs, **kw):
    w = exciter_v3_stream(x, fs, block=len(x), **kw)
    return np.concatenate([w[D_OS:], np.zeros(D_OS)])
