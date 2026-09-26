"""PRISME — assemblage des 5 bandes EN FLUX (2026-09-25) : bloc par bloc, états conservés, latence fixe compensée.

Même architecture que `prisme_engine` : sortie = entrée + Σ deltas (parallèle, ordre indifférent), modes de canal Stéréo / Mid / Side / Left / Right.

LATENCE : fixe = D_OS = 20 échantillons de base (0,42 ms à 48 kHz), imposée par le suréchantillonnage de l'Exciter. L'entrée sèche ET les deltas du
Tame et du Shape (qui n'ont aucune latence propre) sont retardés d'autant pour rester alignés sur les deltas de l'Exciter.
→ à déclarer à l'hôte (`setLatencySamples(20)`) ; constante, que des Exciters soient actifs ou non (les hôtes n'aiment pas une latence qui change).
"""
import numpy as np
from prisme_exciter_v2_stream import ExciterV2Stream
from prisme_exciter_stream import Delai, D_OS
from prisme_tame import Tame
from prisme_shape import Shape
from prisme_lift import Lift
from prisme_link import PAIRES

LATENCE = D_OS


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
            self.bandes.append((spec, canal, [self._creer(spec) for _ in range(n_inst)], [Delai(LATENCE) for _ in range(n_inst)]))

    def _creer(self, spec):
        t, sh, f0, q, g = spec["type"], spec["shape"], spec["f0"], spec["q"], spec["gain_db"]
        if t == "exciter":
            return ExciterV2Stream(self.fs, shape=sh, f0=f0, q=q, gain_db=g, profil=spec.get("profil", "mordant_chaud"), source=spec.get("source", "auto"),
                                   drive=spec.get("drive", 2.5), tilt=spec.get("tilt", 0.0))
        if t == "tame":
            return Tame(self.fs, sh, f0, q, g, spec.get("width", 0.5))
        if t == "shape":
            return Shape(self.fs, spec.get("cible", "transitoires"), sh, f0, q, g, None, spec.get("time_ms"), spec.get("sens", 0.85))
        if t == "lift":
            return Lift(self.fs, sh, f0, q, g, spec.get("amount", 50.0), spec.get("release_ms", 150.0))
        raise ValueError(t)

    @staticmethod
    def _delta(spec, obj, delai, z):
        """Delta de la bande sur le signal z, aligné sur l'entrée retardée de LATENCE."""
        if spec["type"] == "exciter":
            return obj.process(z)                                   # déjà aligné (porte la latence)
        return delai.push(obj.process(z) - z)                       # Tame / Shape : zéro latence propre → on retarde le delta

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
