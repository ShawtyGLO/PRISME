"""PRISME — Exciter v2 en FLUX (2026-09-26) : référence des tests C++. Voir prisme_exciter_v2.py (prototype d'écoute) pour le principe.

    source (Auto : bande f0/h Q ≥ 2 sur 2 sections ; Bande : la zone) [+ Tilt en mode Bande]
      → niveau lent S (τ 400 ms) et niveau rapide e (τ 3 ms) ; porte = 0,3 + 0,7·smoothstep((20·log10(e/S) + 3)/12), relâchement 100 ms (seuil RELATIF au niveau courant, détection régulière)
      → u = drive · s / S ; ×2 (FIR 41) → courbe ADAA ordre 1 → ×1 ; résidu = y − pente·u (fondamental retiré)
      → wet = résidu · S · porte · niveau → filtre de sortie de la zone (3 sections) → coupe-continu 20 Hz.
    Profils : 0 doux (tanh), 1 chaud (tanh décalé, harmoniques paires), 2 mordant (cubique borné), 3 mordant chaud (cubique borné décalé) — préféré de llg53.
    Entrée MONO (le plugin alimente le milieu (L+R)/2 et ajoute le même wet aux deux canaux : la non-linéarité est LIÉE, elle ne décorrèle pas le centre).
LATENCE : 20 échantillons (FIR ×2), comme l'Exciter v1 ; `process` renvoie le wet aligné sur l'entrée retardée de 20.
Gain de bande g (dB, ≥ 0) → niveau du wet = 10^((g − 3)/20) × (niveau lent de la source).
"""
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_libs"))
import numpy as np
from scipy.signal import lfilter
from prisme_dsp import triode_f, iron_f, classa_f, classa_F
from prisme_band import zone_filter, H_DOMINANT, rbj_shelf, tilt_pivot, TILT_DB
from prisme_exciter_stream import Delai, _adaa, H_UP, H_DN, D_OS
from prisme_shape import _tient_relache

# Porte de niveau RELATIF, réglée pour une détection RÉGULIÈRE (retour d'écoute : « ça pompe parfois fort, parfois plus du tout ») : ouverture douce sur 12 dB, plancher de 0,3,
# relâchement de 100 ms (attaque immédiate). Mesuré sur la prod : écart-type du niveau du wet par fenêtre de 100 ms 66,8 dB → 7,7 dB ; fenêtres muettes 37 % → 0 %.
SEUIL_DB, LARGEUR_DB, PLANCHER, TAU_PORTE = -3.0, 12.0, 0.3, 0.1
TAU_LENT, TAU_RAPIDE = 0.4, 0.003
PROFILS = ("doux", "chaud", "mordant", "mordant_chaud")
H_PROFIL = {"doux": 3, "chaud": 2, "mordant": 3, "mordant_chaud": 3}       # harmonique dominant : centre de la source = f0 / h


def _logcosh(u):
    a = np.abs(u)
    return a + np.log1p(np.exp(-2.0 * a)) - np.log(2.0)


def courbe(profil):
    """(f, F, pente_en_0) — F primitive pour l'ADAA."""
    if profil == "doux":
        return (lambda x: np.tanh(x)), (lambda x: _logcosh(x)), 1.0
    if profil == "chaud":
        b = 0.35
        return (lambda x: np.tanh(x + b)), (lambda x: _logcosh(x + b)), 1.0 - np.tanh(b) ** 2
    if profil == "mordant":
        return classa_f, classa_F, 1.0
    if profil == "mordant_chaud":
        a = 0.25
        return (lambda x: classa_f(x + a)), (lambda x: classa_F(x + a)), 1.0
    raise ValueError(profil)


def _un_pole(c, x, zi):
    return lfilter([1 - c], [1, -c], x, zi=zi)


class ExciterV2Stream:
    latence = D_OS

    def __init__(self, fs, shape="bell", f0=3000.0, q=0.71, gain_db=6.0, profil="mordant_chaud", source="auto", drive=2.5, tilt=0.0, seuil_db=SEUIL_DB, src_q=2.0, out_sections=3):
        self.fs, self.profil, self.source, self.drive, self.seuil = fs, profil, source, drive, seuil_db
        self.niveau = 10.0 ** ((gain_db - 3.0) / 20.0)
        self.f, self.F, self.pente = courbe(profil)[0], courbe(profil)[1], courbe(profil)[2]
        if source == "auto":
            self.zf = zone_filter(shape, fs, max(f0 / H_PROFIL[profil], 60.0), max(q, src_q))
            self.z_src = [np.zeros(2), np.zeros(2)]
        else:
            self.zf = zone_filter(shape, fs, f0, q)
            self.z_src = [np.zeros(2)]
        self.tilt_f = None
        if source != "auto" and abs(tilt) > 1e-9:
            pv = tilt_pivot(shape, f0, fs)
            self.tilt_f = [rbj_shelf(fs, pv, -0.5 * TILT_DB * tilt, False), rbj_shelf(fs, pv, +0.5 * TILT_DB * tilt, True)]
            self.z_tilt = [np.zeros(2), np.zeros(2)]
        self.cS, self.cE = np.exp(-1.0 / (TAU_LENT * fs)), np.exp(-1.0 / (TAU_RAPIDE * fs))
        self.z_S, self.z_E = np.zeros(1), np.zeros(1)
        self.c_porte, self.y_porte = np.exp(-1.0 / (TAU_PORTE * fs)), 0.0
        self.z_up, self.z_dn = np.zeros(40), np.zeros(40)
        self.x1 = 0.0
        self.d_u, self.d_S, self.d_p = Delai(D_OS), Delai(D_OS, 1e-7), Delai(D_OS)
        self.zo = zone_filter(shape, fs, f0, q)
        self.out_sections = out_sections
        self.z_out = [np.zeros(2) for _ in range(out_sections)]
        self.r_dc = 1.0 - 2.0 * np.pi * 20.0 / fs
        self.z_dc = np.zeros(1)

    def process(self, x):
        n = len(x)
        s = x
        for i in range(len(self.z_src)):
            s, self.z_src[i] = lfilter(*self.zf, s, zi=self.z_src[i])
        if self.tilt_f is not None:
            for i in range(2):
                s, self.z_tilt[i] = lfilter(*self.tilt_f[i], s, zi=self.z_tilt[i])
        a = np.abs(s)
        S, self.z_S = _un_pole(self.cS, a, self.z_S)
        S = S * (np.pi / 2) + 1e-7
        e, self.z_E = _un_pole(self.cE, a, self.z_E)
        e = e * (np.pi / 2)
        rel = 20.0 * np.log10((e + 1e-12) / S)
        v = np.clip((rel - self.seuil) / LARGEUR_DB, 0.0, 1.0)
        porte = PLANCHER + (1.0 - PLANCHER) * (v * v * (3.0 - 2.0 * v))
        porte, self.y_porte = _tient_relache(porte, self.c_porte, self.y_porte)          # attaque immédiate, relâchement 100 ms
        u = self.drive * s / S
        zs = np.zeros(2 * n)
        zs[::2] = u
        w, self.z_up = lfilter(H_UP, [1.0], zs, zi=self.z_up)
        y2, self.x1 = _adaa(w, (self.f, self.F), self.x1)
        y, self.z_dn = lfilter(H_DN, [1.0], y2, zi=self.z_dn)
        y = y[::2]
        u_d, S_d, p_d = self.d_u.push(u), self.d_S.push(S), self.d_p.push(porte)
        res = (y - self.pente * u_d) * S_d * p_d * self.niveau
        for i in range(self.out_sections):
            res, self.z_out[i] = lfilter(*self.zo, res, zi=self.z_out[i])
        res, self.z_dc = lfilter([1.0, -1.0], [1.0, -self.r_dc], res, zi=self.z_dc)
        return res


def exciter_v2_stream(x, fs, block=8192, **kw):
    e = ExciterV2Stream(fs, **kw)
    out = np.empty(len(x))
    for i in range(0, len(x), block):
        out[i:i + block] = e.process(x[i:i + block])
    return out


def excite_v2_aligne(x, fs, **kw):
    """Version hors ligne : wet aligné sur l'entrée NON retardée (décalé de −D_OS ; les D_OS derniers échantillons valent 0)."""
    w = exciter_v2_stream(x, fs, block=len(x), **kw)
    return np.concatenate([w[D_OS:], np.zeros(D_OS)])
