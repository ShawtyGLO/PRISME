"""PRISME — modes de canal discrets par bande : Stéréo / Mid / Side / Left / Right (décision llg53, 2026-09-24).

  stereo : chaque canal traité séparément (delta L et delta R indépendants)
  mid    : traite (L+R)/2 ; le même delta est ajouté aux deux canaux
  side   : traite (L−R)/2 ; delta ajouté à L et retranché à R (élargit sans toucher au centre)
  left / right : traite un seul canal, delta ajouté à ce canal seulement
Aucune version intermédiaire (pas de curseur de largeur).
"""
import numpy as np
from prisme_band import excite_band

CANAUX = ("stereo", "mid", "side", "left", "right")


def process_channels(x, fs, canal, **kw):
    L, R = x[:, 0], x[:, 1]
    if canal == "stereo":
        return np.stack([excite_band(L, fs, **kw), excite_band(R, fs, **kw)], axis=1)
    if canal == "mid":
        M = (L + R) / 2
        d = excite_band(M, fs, **kw) - M
        return x + np.stack([d, d], axis=1)
    if canal == "side":
        S = (L - R) / 2
        d = excite_band(S, fs, **kw) - S
        return x + np.stack([d, -d], axis=1)
    if canal == "left":
        return np.stack([excite_band(L, fs, **kw), R], axis=1)
    if canal == "right":
        return np.stack([L, excite_band(R, fs, **kw)], axis=1)
    raise ValueError(canal)
