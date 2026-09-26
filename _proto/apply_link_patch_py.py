"""Liaison stéréo PARTIELLE des détecteurs (Tame, Shape, Lift), au niveau de l'ACTIVITÉ (pas du signal : mélanger les signaux de détection ne donne pas une liaison partielle
— un seuil s'ouvre dès qu'un demi-poids de la résonance arrive, mesuré : parasite −8,6 dB à λ = 0,5 comme à λ = 1).

   activité du canal c :  a_c' = (1 − λ)·a_c + λ·a_lié       λ = 0 : indépendants (historique) ; λ = 1 : mêmes décisions ; défaut du plugin λ = 0,5
   Tame  : a = réduction par bande (avant lissage temporel), a_lié = max des deux canaux
   Shape : a = poids « transitoire » (avant choix transitoires / sustain), a_lié = max
   Lift  : a = courbe s (0 … 1, porte de souffle comprise), a_lié = MIN (le canal le plus fort commande : moins de relevé)
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))


def rd(n):
    return open(os.path.join(HERE, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(HERE, n), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:80]
    return s.replace(old, new, 1)


# ---------------------------------------------------------------- Tame : détection en deux temps
t = rd("prisme_tame.py")
t = sub(t, '''    def _detect(self, x):
        """Analyse, niveaux, excès, réduction et normalisation aux points décimés ; renvoie (n, idx, m, red_d, S_d)."""
        n, N = len(x), self.N''', '''    def _detect(self, x):
        """Analyse, niveaux, excès, réduction et normalisation aux points décimés ; renvoie (n, idx, m, red_d, S_d)."""
        return self._detect2(*self._detect1(x))

    def _detect1(self, x):
        """Premier temps : analyse jusqu'à la réduction par bande `red` (float32, N × m ; None si aucun point) — c'est ICI que la liaison stéréo agit."""
        n, N = len(x), self.N''')
t = sub(t, '''            red = (red * self.w[:, None]).astype(np.float32)
            ra, self.zra''', '''            red = (red * self.w[:, None]).astype(np.float32)
        else:
            red = None
        return n, idx, m, red

    def _detect2(self, n, idx, m, red):
        """Second temps : lissage attaque / relâchement à cadence décimée puis normalisation locale ; renvoie (n, idx, m, red_d, S_d)."""
        N = self.N
        if m > 0:
            ra, self.zra''')
t = sub(t, "    def process(self, x, keep=False):\n        n, idx, m, red_d, S_d = self._detect(x)", "    def process(self, x, keep=False, pre=None):\n        n, idx, m, red_d, S_d = self._detect(x) if pre is None else pre")
wr("prisme_tame.py", t)

# ---------------------------------------------------------------- Shape
s = rd("prisme_shape.py")
s = sub(s, "    def process(self, x, keep=False):\n        n = len(x)\n        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)",
        "    def process(self, x, keep=False):\n        b, Tl = self.detecte(x)\n        return self.applique(x, b, Tl, keep)\n\n    def detecte(self, x):\n        \"\"\"Renvoie (b, Tl) : signal de la zone et poids « transitoire » lissé (avant le choix transitoires / sustain) — la liaison stéréo agit sur Tl.\"\"\"\n        n = len(x)\n        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)")
s = sub(s, "        Tl, self.z_att = lfilter([1 - self.c_att], [1, -self.c_att], Th, zi=self.z_att)         # attaque du gain bornée\n        poids",
        "        Tl, self.z_att = lfilter([1 - self.c_att], [1, -self.c_att], Th, zi=self.z_att)         # attaque du gain bornée\n        return b, Tl\n\n    def applique(self, x, b, Tl, keep=False):\n        poids")
wr("prisme_shape.py", s)

# ---------------------------------------------------------------- Lift
l = rd("prisme_lift.py")
l = sub(l, "    def process(self, x, keep=False):\n        n = len(x)\n        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)",
        "    def process(self, x, keep=False):\n        b, s = self.detecte(x)\n        return self.applique(x, b, s, keep)\n\n    def detecte(self, x):\n        \"\"\"Renvoie (b, s) : signal de la zone et courbe de relevé s (0 … 1, porte de souffle comprise) — la liaison stéréo agit sur s.\"\"\"\n        n = len(x)\n        b, self.zb = lfilter(self.b, self.a, x, zi=self.zb)")
l = sub(l, "        self.last_L = L\n        lift = self.G * s", "        self.last_L = L\n        return b, s\n\n    def applique(self, x, b, s, keep=False):\n        lift = self.G * s")
wr("prisme_lift.py", l)

# ---------------------------------------------------------------- module de liaison
wr("prisme_link.py", '''"""Liaison stéréo partielle des détecteurs (Tame, Shape, Lift) : voir apply_link_patch_py.py pour le principe.  λ = 0 : indépendants ; 1 : mêmes décisions."""
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
''')

# ---------------------------------------------------------------- assemblage en flux
g = rd("prisme_engine_stream.py")
g = sub(g, "from prisme_lift import Lift", "from prisme_lift import Lift\nfrom prisme_link import PAIRES")
g = sub(g, '            elif canal == "stereo":\n                d = np.stack([self._delta(spec, objs[0], dels[0], L), self._delta(spec, objs[1], dels[1], R)], axis=1)',
        '            elif canal == "stereo":\n                lam = float(spec.get("link", 0.5))                    # liaison partielle des détecteurs L/R (Tame, Shape, Lift)\n                if lam > 0.0:\n                    yL, yR = PAIRES[spec["type"]](objs[0], objs[1], L, R, lam)\n                    d = np.stack([dels[0].push(yL - L), dels[1].push(yR - R)], axis=1)\n                else:\n                    d = np.stack([self._delta(spec, objs[0], dels[0], L), self._delta(spec, objs[1], dels[1], R)], axis=1)')
wr("prisme_engine_stream.py", g)

# ---------------------------------------------------------------- assemblage hors ligne
e = rd("prisme_engine.py")
e = sub(e, "from prisme_exciter_v2_stream import excite_v2_aligne", "from prisme_exciter_v2_stream import excite_v2_aligne\nfrom prisme_link import PAIRES\nfrom prisme_tame import Tame\nfrom prisme_shape import Shape\nfrom prisme_lift import Lift")
e = sub(e, '''    if canal == "stereo":
        return np.stack([fn(L) - L, fn(R) - R], axis=1)''', '''    if canal == "stereo":
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
        return np.stack([fn(L) - L, fn(R) - R], axis=1)''')
wr("prisme_engine.py", e)
print("ok")
