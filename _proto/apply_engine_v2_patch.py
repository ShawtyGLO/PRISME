"""Branche l'Exciter v2 (lié en stéréo) dans les assemblages Python (hors ligne et en flux)."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))


def rd(n):
    return open(os.path.join(HERE, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(HERE, n), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:80]
    return s.replace(old, new, 1)


# ---------------- hors ligne
e = rd("prisme_engine.py")
e = sub(e, "from prisme_lift import lift_band", "from prisme_lift import lift_band\nfrom prisme_exciter_v2_stream import excite_v2_aligne")
e = sub(e, '''        return lambda z: excite_band(z, fs, shape=sh, f0=f0, q=q, gain_db=g, mode=spec.get("mode", "iron"), source=spec.get("source", "auto"),
                                     out_sections=3, drive=1.5, oversample=2, norm="zone")''',
        '''        # Exciter v2 : seuil relatif, wet sans normalisation ; entrée MONO (lié : voir delta_bande)
        return lambda z: z + excite_v2_aligne(z, fs, shape=sh, f0=f0, q=q, gain_db=g, profil=spec.get("profil", "mordant_chaud"), source=spec.get("source", "auto"),
                                              drive=spec.get("drive", 2.5), tilt=spec.get("tilt", 0.0))''')
e = sub(e, '    fn, canal = _fn(spec, fs), spec.get("canal", "stereo")', '    fn, canal = _fn(spec, fs), spec.get("canal", "stereo")\n    if spec["type"] == "exciter" and canal == "stereo":\n        canal = "mid"                                         # Exciter v2 : non-linéarité LIÉE (source = milieu, même wet sur L et R)')
wr("prisme_engine.py", e)

# ---------------- flux
s = rd("prisme_engine_stream.py")
s = sub(s, "from prisme_exciter_stream import ExciterStream, Delai, D_OS", "from prisme_exciter_v2_stream import ExciterV2Stream\nfrom prisme_exciter_stream import Delai, D_OS")
s = sub(s, '            n_inst = 2 if canal == "stereo" else 1', '            n_inst = 2 if (canal == "stereo" and spec["type"] != "exciter") else 1          # Exciter v2 : une seule chaîne (lié)')
s = sub(s, '            return ExciterStream(self.fs, shape=sh, f0=f0, q=q, gain_db=g, mode=spec.get("mode", "iron"), source=spec.get("source", "auto"))',
        '            return ExciterV2Stream(self.fs, shape=sh, f0=f0, q=q, gain_db=g, profil=spec.get("profil", "mordant_chaud"), source=spec.get("source", "auto"),\n                                   drive=spec.get("drive", 2.5), tilt=spec.get("tilt", 0.0))')
s = sub(s, '            if canal == "stereo":\n                d = np.stack', '            if canal == "stereo" and spec["type"] == "exciter":\n                dm = self._delta(spec, objs[0], dels[0], (L + R) / 2)\n                d = np.stack([dm, dm], axis=1)\n            elif canal == "stereo":\n                d = np.stack')
wr("prisme_engine_stream.py", s)
print("ok")
