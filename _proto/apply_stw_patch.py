"""Patch 2026-10-23 : « Largeur stéréo » par bande (mode Stéréo, Tame / Shape / Lift) : le Side du delta de la bande est multiplié (0 = delta mono … 2 = Side doublé, 1 = inchangé).
Paramètre `stw` (défaut 1,0 = neutre : presets et projets inchangés), réglable EN DIRECT, AUCUNE interface (le visuel est soumis à validation)."""
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME")
PROTO = os.path.dirname(os.path.abspath(__file__))


def edit(path, pairs, base=ROOT):
    p = os.path.join(base, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:90])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


# ---- Python (référence)
edit("prisme_engine_stream.py", [
    ('''            elif canal == "stereo":
                lam = float(spec.get("link", 0.5))                    # liaison partielle des détecteurs L/R (Tame, Shape, Lift)
                if lam > 0.0:
                    yL, yR = PAIRES[spec["type"]](objs[0], objs[1], L, R, lam)
                    d = np.stack([dels[0].push(yL - L), dels[1].push(yR - R)], axis=1)
                else:
                    d = np.stack([self._delta(spec, objs[0], dels[0], L), self._delta(spec, objs[1], dels[1], R)], axis=1)''',
     '''            elif canal == "stereo":
                lam = float(spec.get("link", 0.5))                    # liaison partielle des détecteurs L/R (Tame, Shape, Lift)
                if lam > 0.0:
                    yL, yR = PAIRES[spec["type"]](objs[0], objs[1], L, R, lam)
                    d = np.stack([dels[0].push(yL - L), dels[1].push(yR - R)], axis=1)
                else:
                    d = np.stack([self._delta(spec, objs[0], dels[0], L), self._delta(spec, objs[1], dels[1], R)], axis=1)
                stw = float(spec.get("st_width", 1.0))                 # largeur stéréo de la bande : Side du delta × stw (0 = mono, 2 = Side doublé)
                if stw != 1.0:
                    M, S = (d[:, 0] + d[:, 1]) / 2, (d[:, 0] - d[:, 1]) / 2 * stw
                    d = np.stack([M + S, M - S], axis=1)'''),
], base=PROTO)

# ---- C++
edit("Source/Dsp/Engine.h", [
    ("    double zonePente = 1.0;", "    double stWidth = 1.0;                                   // largeur stéréo (mode Stéréo, Tame / Shape / Lift) : Side du delta ×stWidth ; réglé en direct, hors de l'égalité\n    double zonePente = 1.0;"),
    ("    void setLink (double l) { spec.link = l; }",
     "    void setLink (double l) { spec.link = l; }\n    void setStWidth (double w) { spec.stWidth = w; stw = w; }                  // largeur stéréo, en direct"),
    ("""                else if (spec.link > 0.0 && spec.type != TypeBande::Exciter) pair (L, R, dL, dR);
                else { dL = delta (0, L); dR = delta (1, R); }
                break;""",
     """                else if (spec.link > 0.0 && spec.type != TypeBande::Exciter) pair (L, R, dL, dR);
                else { dL = delta (0, L); dR = delta (1, R); }
                if (spec.type != TypeBande::Exciter && stw != 1.0)                // largeur stéréo de la bande : Side du delta × stw
                {
                    const double M = 0.5 * (dL + dR), S = 0.5 * (dL - dR) * stw;
                    dL = M + S;
                    dR = M - S;
                }
                break;"""),
    ("    BandeSpec spec;\n    int n = 1;", "    BandeSpec spec;\n    double stw = 1.0;\n    int n = 1;"),
    ("        spec = s;\n        n = (s.canal", "        spec = s;\n        stw = s.stWidth;\n        n = (s.canal"),
])
edit("Source/Params.h", [
    ("""        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "zone"), 1 }""",
     """        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "stw"), 1 }, n + U8 ("largeur stéréo (mode Stéréo)"), juce::NormalisableRange<float> (0.0f, 2.0f, 0.01f), 1.0f));
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "zone"), 1 }"""),
    ("""    sp.zonePente = juce::roundToInt""", """    sp.stWidth = raw (s, pid (b, "stw"));
    sp.zonePente = juce::roundToInt"""),
])
edit("Source/PluginProcessor.h", [
    ("        std::atomic<double> widthTarget { 0.5 };               // Largeur du Tame en direct\n        double lastWidth = 0.5;\n",
     "        std::atomic<double> widthTarget { 0.5 };               // Largeur du Tame en direct\n        double lastWidth = 0.5;\n        std::atomic<double> stwTarget { 1.0 };                 // largeur stéréo de la bande, en direct\n        double lastStw = 1.0;\n"),
])
edit("Source/PluginProcessor.cpp", [
    ("            s.widthTarget.store (spec.width);\n            s.lastWidth = spec.width;\n",
     "            s.widthTarget.store (spec.width);\n            s.lastWidth = spec.width;\n            s.stwTarget.store (spec.stWidth);\n            s.lastStw = spec.stWidth;\n"),
    ("        s.widthTarget.store (spec.width);\n        if (! s.msgAlive", "        s.widthTarget.store (spec.width);\n        s.stwTarget.store (spec.stWidth);\n        if (! s.msgAlive"),
    ("                        s.warm->setWidth (s.widthTarget.load());\n                        s.lastWidth = s.widthTarget.load();\n",
     "                        s.warm->setWidth (s.widthTarget.load());\n                        s.lastWidth = s.widthTarget.load();\n                        s.warm->setStWidth (s.stwTarget.load());\n                        s.lastStw = s.stwTarget.load();\n"),
    ("            if (s.cur && wd != s.lastWidth) { s.cur->setWidth (wd); s.lastWidth = wd; }\n",
     "            if (s.cur && wd != s.lastWidth) { s.cur->setWidth (wd); s.lastWidth = wd; }\n            const double sw = s.stwTarget.load();\n            if (s.cur && sw != s.lastStw) { s.cur->setStWidth (sw); s.lastStw = sw; }\n"),
])
print("ok")
