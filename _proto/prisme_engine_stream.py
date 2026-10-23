"""PRISME — assemblage des 5 bandes EN FLUX (2026-09-25) : bloc par bloc, états conservés, latence fixe compensée.

Même architecture que `prisme_engine` : sortie = entrée + Σ deltas (parallèle, ordre indifférent), modes de canal Stéréo / Mid / Side / Left / Right.

LATENCE : fixe = 192 échantillons (4,0 ms à 48 kHz) depuis le Shape v5, qui ANTICIPE (le poids calculé à l'instant n s'applique à b(n − 192)).
L'entrée sèche ET les deltas du Tame et du Lift (latence propre nulle) sont retardés de 192 ; l'Exciter porte sa propre latence de 20 (FIR) et reçoit 172 de plus ;
le Shape porte déjà les 192 (retard interne de b). → à déclarer à l'hôte (`setLatencySamples(192)`) ; constante (les hôtes n'aiment pas une latence qui change).
"""
import numpy as np
from prisme_exciter_v3_stream import ExciterV3Stream
from prisme_exciter_stream import Delai, D_OS
from prisme_tame import Tame
from prisme_shape5 import Shape5, LOOK
from prisme_lift import Lift
from prisme_link import PAIRES

LATENCE = LOOK


class EngineStream:
    latence = LATENCE

    def __init__(self, fs, bandes):
        self.fs = fs
        self.sec = [Delai(LATENCE), Delai(LATENCE)]
        self.bandes = []
        for spec in bandes:
            if not spec.get("on", True) or spec["gain_db"] == 0.0:
                continue
            canal = spec.get("canal", "stereo")
            n_inst = 2 if (canal == "stereo" and spec["type"] != "exciter") else 1          # Exciter v2 : une seule chaîne (lié)
            self.bandes.append((spec, canal, [self._creer(spec) for _ in range(n_inst)], [Delai(self._retard(spec)) for _ in range(n_inst)]))

    @staticmethod
    def _retard(spec):
        t = spec["type"]
        return LATENCE - D_OS if t == "exciter" else (0 if t == "shape" else LATENCE)

    def _creer(self, spec):
        t, sh, f0, q, g = spec["type"], spec["shape"], spec["f0"], spec["q"], spec["gain_db"]
        if t == "exciter":
            return ExciterV3Stream(self.fs, shape=sh, f0=f0, q=q, gain_db=g, profil=spec.get("profil", "mordant_chaud"),
                                   drive=spec.get("drive", 2.5), tilt=spec.get("tilt", 0.0), purete=spec.get("purete", 0.0))
        if t == "tame":
            return Tame(self.fs, sh, f0, q, g, spec.get("width", 0.5))
        if t == "shape":
            return Shape5(self.fs, spec.get("cible", "transitoires"), sh, f0, q, g, None, spec.get("time_ms"), spec.get("sens", 0.85), LATENCE)
        if t == "lift":
            return Lift(self.fs, sh, f0, q, g, spec.get("amount", 50.0), spec.get("release_ms", 150.0))
        raise ValueError(t)

    @staticmethod
    def _delta(spec, obj, delai, z):
        """Delta de la bande sur le signal z, aligné sur l'entrée retardée de LATENCE."""
        if spec["type"] == "exciter":
            return delai.push(obj.process(z))                       # aligné sur 20 → complété jusqu'à LATENCE
        return delai.push(obj.process(z) - z)                       # Tame / Lift : zéro latence propre → on retarde le delta ; Shape : déjà aligné (retard nul)

    def process(self, x):
        """x : (n, 2) → (n, 2), retardé de LATENCE échantillons."""
        L, R = x[:, 0], x[:, 1]
        out = np.stack([self.sec[0].push(L), self.sec[1].push(R)], axis=1)
        for spec, canal, objs, dels in self.bandes:
            if canal == "stereo" and spec["type"] == "exciter":
                dm = self._delta(spec, objs[0], dels[0], (L + R) / 2)
                d = np.stack([dm, dm], axis=1)
            elif canal == "stereo":
                lam = float(spec.get("link", 0.5))                    # liaison partielle des détecteurs L/R (Tame, Shape, Lift)
                if lam > 0.0:
                    yL, yR = PAIRES[spec["type"]](objs[0], objs[1], L, R, lam)
                    d = np.stack([dels[0].push(yL - L), dels[1].push(yR - R)], axis=1)
                else:
                    d = np.stack([self._delta(spec, objs[0], dels[0], L), self._delta(spec, objs[1], dels[1], R)], axis=1)
                stw = float(spec.get("st_width", 1.0))                 # largeur stéréo de la bande : Side du delta × stw (0 = mono, 2 = Side doublé)
                if stw != 1.0:
                    M, S = (d[:, 0] + d[:, 1]) / 2, (d[:, 0] - d[:, 1]) / 2 * stw
                    d = np.stack([M + S, M - S], axis=1)
            elif canal == "mid":
                dm = self._delta(spec, objs[0], dels[0], (L + R) / 2)
                d = np.stack([dm, dm], axis=1)
            elif canal == "side":
                ds = self._delta(spec, objs[0], dels[0], (L - R) / 2)
                d = np.stack([ds, -ds], axis=1)
            elif canal == "left":
                d = np.stack([self._delta(spec, objs[0], dels[0], L), np.zeros(len(L))], axis=1)
            else:
                d = np.stack([np.zeros(len(R)), self._delta(spec, objs[0], dels[0], R)], axis=1)
            out = out + d
        return out


def traite(x, fs, bandes, block=8192):
    e = EngineStream(fs, bandes)
    out = np.empty_like(x)
    for i in range(0, len(x), block):
        out[i:i + block] = e.process(x[i:i + block])
    return out
