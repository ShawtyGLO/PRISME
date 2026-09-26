"""Exciter v2 : porte plus régulière (mesuré : écart-type du niveau du wet 66,8 dB → 7,7 dB, fenêtres muettes 37 % → 0 %) — seuil −3 dB, largeur 12 dB, plancher 0,3, relâchement 100 ms."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "PRISME")


def rd(p, base=HERE):
    return open(os.path.join(base, p), encoding="utf-8").read()


def wr(p, s, base=HERE):
    open(os.path.join(base, p), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:80]
    return s.replace(old, new, 1)


# ---------------------------------------------------------------- Python (référence)
s = rd("prisme_exciter_v2_stream.py")
s = sub(s, "SEUIL_DB = 3.0\nTAU_LENT, TAU_RAPIDE = 0.4, 0.003",
        "# Porte de niveau RELATIF, réglée pour une détection RÉGULIÈRE (retour d'écoute : « ça pompe parfois fort, parfois plus du tout ») : ouverture douce sur 12 dB, plancher de 0,3,\n# relâchement de 100 ms (attaque immédiate). Mesuré sur la prod : écart-type du niveau du wet par fenêtre de 100 ms 66,8 dB → 7,7 dB ; fenêtres muettes 37 % → 0 %.\nSEUIL_DB, LARGEUR_DB, PLANCHER, TAU_PORTE = -3.0, 12.0, 0.3, 0.1\nTAU_LENT, TAU_RAPIDE = 0.4, 0.003")
s = sub(s, "from prisme_exciter_stream import Delai, _adaa, H_UP, H_DN, D_OS", "from prisme_exciter_stream import Delai, _adaa, H_UP, H_DN, D_OS\nfrom prisme_shape import _tient_relache")
s = sub(s, "        self.z_S, self.z_E = np.zeros(1), np.zeros(1)", "        self.z_S, self.z_E = np.zeros(1), np.zeros(1)\n        self.c_porte, self.y_porte = np.exp(-1.0 / (TAU_PORTE * fs)), 0.0")
s = sub(s, "        v = np.clip((rel - self.seuil) / 6.0, 0.0, 1.0)\n        porte = v * v * (3.0 - 2.0 * v)",
        "        v = np.clip((rel - self.seuil) / LARGEUR_DB, 0.0, 1.0)\n        porte = PLANCHER + (1.0 - PLANCHER) * (v * v * (3.0 - 2.0 * v))\n        porte, self.y_porte = _tient_relache(porte, self.c_porte, self.y_porte)          # attaque immédiate, relâchement 100 ms")
s = sub(s, "      → niveau lent S (τ 400 ms) et niveau rapide e (τ 3 ms) ; porte = smoothstep((20·log10(e/S) − seuil)/6)   (seuil RELATIF : pics au-dessus du niveau courant)",
        "      → niveau lent S (τ 400 ms) et niveau rapide e (τ 3 ms) ; porte = 0,3 + 0,7·smoothstep((20·log10(e/S) + 3)/12), relâchement 100 ms (seuil RELATIF au niveau courant, détection régulière)")
wr("prisme_exciter_v2_stream.py", s)

t = rd("tests_exciter_v2.py")
i = t.index("    t = np.arange(int(fs * 4)) / fs")
j = t.index("    ok5, pire = True, 0.0")
new = '''    ww = int(0.1 * fs)
    r = ref[int(fs):]
    nw = len(r) // ww
    lw = 10 * np.log10((r[: nw * ww].reshape(nw, ww) ** 2).mean(axis=1) + 1e-20)
    muet = 100 * np.mean(lw < np.median(lw) - 25)
    check("V04", "détection RÉGULIÈRE sur la musique : fenêtres de 100 ms muettes ≤ 5 %, écart-type du niveau ≤ 12 dB", f"muettes {muet:.0f} % ; écart-type {np.std(lw):.1f} dB", muet <= 5 and np.std(lw) <= 12)
'''
t = t[:i] + new + t[j:]
t = t.replace("  V04 seuil      signal STABLE (sans pic au-dessus de son niveau courant) → wet ≤ −60 dB sous la zone ; même signal avec des pics +6 dB → wet clairement plus haut", "  V04 régularité fenêtres de 100 ms muettes ≤ 5 %, écart-type du niveau du wet ≤ 12 dB (mesuré avant réglage de la porte : 37 % et 66,8 dB)")
wr("tests_exciter_v2.py", t)

# ---------------------------------------------------------------- C++
c = rd("Source/Dsp/ExciterV2.h", ROOT)
c = sub(c, "        const double v = std::clamp ((rel - seuilDb) / 6.0, 0.0, 1.0);\n        const double porte = v * v * (3.0 - 2.0 * v);",
        "        const double v = std::clamp ((rel - seuilDb) / largeurDb, 0.0, 1.0);\n        yPorte = std::max (plancher + (1.0 - plancher) * (v * v * (3.0 - 2.0 * v)), cPorte * yPorte);      // attaque immédiate, relâchement 100 ms\n        const double porte = yPorte;")
c = sub(c, "    static constexpr double seuilDb = 3.0, tiltDb = 9.0;", "    static constexpr double seuilDb = -3.0, largeurDb = 12.0, plancher = 0.3, tiltDb = 9.0;      // porte régulière (voir prisme_exciter_v2_stream.py)")
c = sub(c, "        cE = std::exp (-1.0 / (0.003 * fs));", "        cE = std::exp (-1.0 / (0.003 * fs));\n        cPorte = std::exp (-1.0 / (0.1 * fs));")
c = sub(c, "        zS = zE = 0.0;\n        x1 = 0.0;", "        zS = zE = 0.0;\n        yPorte = 0.0;\n        x1 = 0.0;")
c = sub(c, "    double cS = 0, cE = 0, rDc = 0,", "    double cPorte = 0, yPorte = 0;\n    double cS = 0, cE = 0, rDc = 0,")
c = sub(c, "// Profils : Doux", "// Porte de niveau relatif RÉGULIÈRE (ouverture douce sur 12 dB, plancher 0,3, relâchement 100 ms) : sinon le wet pompe (mesuré : écart-type 66,8 dB → 7,7 dB).\n// Profils : Doux")
wr("Source/Dsp/ExciterV2.h", c, ROOT)
print("ok")
