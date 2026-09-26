"""PRISME — assemblage des 5 bandes (2026-09-25).

Chaque bande est un traitement ADDITIF sur le signal sec : sortie = entrée + Σᵢ deltaᵢ, deltaᵢ = traitéᵢ(entrée) − entrée.
Les bandes lisent toutes le sec (parallèle) : l'ordre est indifférent et une bande ne perturbe jamais la détection d'une autre.

Une bande = { type: 'exciter' | 'tame' | 'shape' | 'lift', shape: 'bell' | 'lowshelf' | 'highshelf', f0, q, gain_db,
              canal: 'stereo' | 'mid' | 'side' | 'left' | 'right', on: True/False, + paramètres du type }
  exciter : mode (iron/triode/diode/classa/rect), source ('auto' | 'band')
  tame    : width (0 large … 1 fin)
  lift    : amount (0…100 %, seuil absolu −60…−12 dBFS), release_ms (20–1000, défaut 150)
  shape   : cible ('transitoires' | 'sustain'), time_ms (5–200), sens (0…1)

⚠️ État du prototype : Tame et Shape sont en flux (par blocs, causaux, latence nulle) ; l'Exciter est encore hors ligne (signal entier).
"""
import numpy as np
from prisme_band import excite_band
from prisme_tame import tame_band
from prisme_shape import shape_band
from prisme_lift import lift_band
from prisme_exciter_v2_stream import excite_v2_aligne
from prisme_link import PAIRES
from prisme_tame import Tame
from prisme_shape import Shape
from prisme_lift import Lift

FREQS_DEFAUT = (42.0, 164.0, 632.0, 2800.0, 9600.0)                      # points de départ de Spectre : 5 bandes réparties sur le spectre
FORMES_DEFAUT = ("lowshelf", "bell", "bell", "bell", "highshelf")


def bandes_defaut():
    return [dict(type="exciter", shape=f, f0=fr, q=0.71, gain_db=0.0, canal="stereo", on=True) for f, fr in zip(FORMES_DEFAUT, FREQS_DEFAUT)]


def _fn(spec, fs):
    t, sh, f0, q, g = spec["type"], spec["shape"], spec["f0"], spec["q"], spec["gain_db"]
    if t == "exciter":
        # Exciter v2 : seuil relatif, wet sans normalisation ; entrée MONO (lié : voir delta_bande)
        return lambda z: z + excite_v2_aligne(z, fs, shape=sh, f0=f0, q=q, gain_db=g, profil=spec.get("profil", "mordant_chaud"), source=spec.get("source", "auto"),
                                              drive=spec.get("drive", 2.5), tilt=spec.get("tilt", 0.0))
    if t == "tame":
        return lambda z: tame_band(z, fs, shape=sh, f0=f0, q=q, gain_db=g, width=spec.get("width", 0.5))
    if t == "shape":
        return lambda z: shape_band(z, fs, cible=spec.get("cible", "transitoires"), shape=sh, f0=f0, q=q, gain_db=g,
                                    time_ms=spec.get("time_ms"), sens=spec.get("sens", 0.85))
    if t == "lift":
        return lambda z: lift_band(z, fs, shape=sh, f0=f0, q=q, gain_db=g, amount=spec.get("amount", 50.0), release_ms=spec.get("release_ms", 150.0))
    raise ValueError(t)


def delta_bande(x, fs, spec):
    """Delta (n, 2) d'une bande selon son mode de canal. Aucune bande active → zéro exact."""
    if not spec.get("on", True) or spec["gain_db"] == 0.0:
        return np.zeros_like(x)
    fn, canal = _fn(spec, fs), spec.get("canal", "stereo")
    if spec["type"] == "exciter" and canal == "stereo":
        canal = "mid"                                         # Exciter v2 : non-linéarité LIÉE (source = milieu, même wet sur L et R)
    L, R = x[:, 0], x[:, 1]
    z = np.zeros(len(L))
    if canal == "stereo":
        lam = float(spec.get("link", 0.5))                        # liaison partielle des détecteurs L/R (Tame, Shape, Lift) ; 0 = indépendants
        if lam > 0.0 and spec["type"] in PAIRES:
            t, sh, f0, q, g = spec["type"], spec["shape"], spec["f0"], spec["q"], spec["gain_db"]
            mk = {"tame": lambda: Tame(fs, sh, f0, q, g, spec.get("width", 0.5)),
                  "shape": lambda: Shape(fs, spec.get("cible", "transitoires"), sh, f0, q, g, None, spec.get("time_ms"), spec.get("sens", 0.85)),
                  "lift": lambda: Lift(fs, sh, f0, q, g, spec.get("amount", 50.0), spec.get("release_ms", 150.0))}[t]
            oL, oR = mk(), mk()
            yL, yR = np.empty(len(L)), np.empty(len(L))
            for i in range(0, len(L), 8192):
                yL[i:i + 8192], yR[i:i + 8192] = PAIRES[t](oL, oR, L[i:i + 8192], R[i:i + 8192], lam)
            return np.stack([yL - L, yR - R], axis=1)
        return np.stack([fn(L) - L, fn(R) - R], axis=1)
    if canal == "mid":
        M = (L + R) / 2
        d = fn(M) - M
        return np.stack([d, d], axis=1)
    if canal == "side":
        S = (L - R) / 2
        d = fn(S) - S
        return np.stack([d, -d], axis=1)
    if canal == "left":
        return np.stack([fn(L) - L, z], axis=1)
    if canal == "right":
        return np.stack([z, fn(R) - R], axis=1)
    raise ValueError(canal)


def process(x, fs, bandes):
    """sortie = entrée + Σ deltas (parallèle, ordre indifférent)."""
    out = x.copy()
    for spec in bandes:
        out = out + delta_bande(x, fs, spec)
    return out
