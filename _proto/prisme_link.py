"""Liaison stéréo partielle des détecteurs (Tame, Shape, Lift) : voir apply_link_patch_py.py pour le principe.  λ = 0 : indépendants ; 1 : mêmes décisions."""
import numpy as np


def _mix(a, b, lam, lie):
    """a_c' = (1 − λ)·a_c + λ·a_lié, calculé en double puis ramené au type de a (float32 pour le Tame)."""
    return ((1.0 - lam) * a.astype(np.float64) + lam * lie.astype(np.float64)).astype(a.dtype)


def tame_pair(tL, tR, xL, xR, lam):
    nL, idx, m, rL = tL._detect1(xL)
    nR, _, _, rR = tR._detect1(xR)
    if m > 0 and lam > 0.0:
        lie = np.maximum(rL, rR)
        rL, rR = _mix(rL, rR, lam, lie), _mix(rR, rL, lam, lie)
    return tL.process(xL, pre=tL._detect2(nL, idx, m, rL)), tR.process(xR, pre=tR._detect2(nR, idx, m, rR))


def shape_pair(sL, sR, xL, xR, lam):
    bL, aL = sL.detecte(xL)
    bR, aR = sR.detecte(xR)
    lie = np.maximum(aL, aR)
    return sL.applique(xL, bL, _mix(aL, aR, lam, lie)), sR.applique(xR, bR, _mix(aR, aL, lam, lie))


def lift_pair(lL, lR, xL, xR, lam):
    bL, aL = lL.detecte(xL)
    bR, aR = lR.detecte(xR)
    lie = np.minimum(aL, aR)                                   # le canal le plus fort commande (moins de relevé)
    return lL.applique(xL, bL, _mix(aL, aR, lam, lie)), lR.applique(xR, bR, _mix(aR, aL, lam, lie))


PAIRES = {"tame": tame_pair, "shape": shape_pair, "lift": lift_pair}
