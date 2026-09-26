"""Exciter v2 : réglage « Densité » (régularité de la porte, en direct) ; paramètre global « Intensité » (échelle proportionnelle du gain de toutes les bandes) ; tests."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "PRISME")


def rd(p, base=ROOT):
    return open(os.path.join(base, p), encoding="utf-8").read()


def wr(p, s, base=ROOT):
    open(os.path.join(base, p), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:90]
    return s.replace(old, new, 1)


# ---------------------------------------------------------------- Python : Densité
s = rd("prisme_exciter_v2_stream.py", HERE)
s = sub(s, "largeur_db=LARGEUR_DB, plancher=PLANCHER, tau_porte=TAU_PORTE):", "largeur_db=LARGEUR_DB, plancher=PLANCHER, tau_porte=TAU_PORTE, dens=None):")
s = sub(s, "        self.c_porte, self.y_porte = np.exp(-1.0 / (max(tau_porte, 1e-6) * fs)), 0.0\n        self.largeur, self.plancher = largeur_db, plancher",
        "        if dens is not None:                                   # « Densité » 0 … 1 : de la porte creuse (pics seulement, peut pomper) à la porte régulière (wet continu)\n            self.seuil, largeur_db, plancher, tau_porte = 3.0 - 6.0 * dens, 6.0 + 6.0 * dens, 0.3 * dens, 0.1 * dens\n        self.c_porte, self.y_porte = np.exp(-1.0 / (max(tau_porte, 1e-6) * fs)), 0.0\n        self.largeur, self.plancher = largeur_db, plancher")
wr("prisme_exciter_v2_stream.py", s, HERE)

# ---------------------------------------------------------------- C++ : ExciterV2
c = rd("Source/Dsp/ExciterV2.h")
c = sub(c, "ProfilExc profil_, SourceExc source_, double drive_ = 2.5, double tilt = 0.0)", "ProfilExc profil_, SourceExc source_, double drive_ = 2.5, double tilt = 0.0, double dens = 1.0)")
c = sub(c, "        cPorte = std::exp (-1.0 / (0.1 * fs));\n        rDc", "        setDensite (dens);\n        rDc")
c = sub(c, "    void setDrive (double d) { drive = d; }                                                   // en direct", "    void setDrive (double d) { drive = d; }                                                   // en direct\n\n    // Densité 0 … 1 (en direct) : porte creuse (pics seulement, peut pomper) → porte régulière (wet continu) ; 1 = réglage validé (−3 dB / 12 dB / 0,3 / 100 ms)\n    void setDensite (double d)\n    {\n        seuilDb = 3.0 - 6.0 * d;\n        largeurDb = 6.0 + 6.0 * d;\n        plancher = 0.3 * d;\n        cPorte = std::exp (-1.0 / (std::max (0.1 * d, 1e-6) * fsHz));\n    }")
c = sub(c, "    static constexpr double seuilDb = -3.0, largeurDb = 12.0, plancher = 0.3, tiltDb = 9.0;      // porte régulière (voir prisme_exciter_v2_stream.py)", "    static constexpr double tiltDb = 9.0;\n    double seuilDb = -3.0, largeurDb = 12.0, plancher = 0.3;                                      // porte (voir prisme_exciter_v2_stream.py et setDensite)")
wr("Source/Dsp/ExciterV2.h", c)

# ---------------------------------------------------------------- C++ : Engine.h
g = rd("Source/Dsp/Engine.h")
g = sub(g, "    double tilt = 0.0;", "    double dens = 1.0;                                      // « Densité » de la porte de l'Exciter (0 creuse … 1 régulière)\n    double tilt = 0.0;")
g = sub(g, "&& drive == o.drive && tilt == o.tilt", "&& drive == o.drive && tilt == o.tilt && dens == o.dens")
g = sub(g, "s.profil, s.source, s.drive, s.tilt); break;", "s.profil, s.source, s.drive, s.tilt, s.dens); break;")
g = sub(g, "    void setLink (double l) { spec.link = l; }", "    void setLink (double l) { spec.link = l; }\n    void setDens (double d)\n    {\n        spec.dens = d;\n        for (int i = 0; i < n; ++i)\n            if (exc[(size_t) i]) exc[(size_t) i]->setDensite (d);\n    }")
wr("Source/Dsp/Engine.h", g)

# ---------------------------------------------------------------- Params.h : densité, intensité globale
p = rd("Source/Params.h")
p = sub(p, '        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "link"), 1 }', '        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "dens"), 1 }, n + "densité (Exciter)", juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.5f));\n        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "link"), 1 }')
p = sub(p, '    layout.add (std::make_unique<juce::AudioParameterBool>  (P { "bypass", 1 }, "Bypass", false));', '    layout.add (std::make_unique<juce::AudioParameterBool>  (P { "bypass", 1 }, "Bypass", false));\n    layout.add (std::make_unique<juce::AudioParameterFloat> (P { "scale", 1 }, "Intensité (échelle du gain de toutes les bandes)", juce::NormalisableRange<float> (0.0f, 2.0f, 0.01f), 1.0f));')
p = sub(p, '    sp.gainDb  = raw (s, pid (b, "gain"));', '    sp.gainDb  = juce::jlimit (-30.0f, 30.0f, raw (s, pid (b, "gain")) * raw (s, "scale"));      // Intensité globale : échelle proportionnelle du gain de toutes les bandes')
p = sub(p, '    sp.link    = raw (s, pid (b, "link"));', '    sp.link    = raw (s, pid (b, "link"));\n    sp.dens    = raw (s, pid (b, "dens"));')
wr("Source/Params.h", p)

# ---------------------------------------------------------------- PluginProcessor : densité en direct
h = rd("Source/PluginProcessor.h")
h = sub(h, "        double lastLink = 0.5;", "        double lastLink = 0.5;\n        std::atomic<double> densTarget { 1.0 };\n        double lastDens = 1.0;")
wr("Source/PluginProcessor.h", h)
pc = rd("Source/PluginProcessor.cpp")
pc = sub(pc, "        structure.link = 0.0;", "        structure.link = 0.0;\n        structure.dens = 0.0;")
pc = sub(pc, "            s.linkTarget.store (spec.link);\n            s.lastLink = spec.link;", "            s.linkTarget.store (spec.link);\n            s.lastLink = spec.link;\n            s.densTarget.store (spec.dens);\n            s.lastDens = spec.dens;")
pc = sub(pc, "        s.linkTarget.store (spec.link);\n        if (! s.msgAlive", "        s.linkTarget.store (spec.link);\n        s.densTarget.store (spec.dens);\n        if (! s.msgAlive")
pc = sub(pc, "                        s.lastLink = s.linkTarget.load();", "                        s.lastLink = s.linkTarget.load();\n                        s.warm->setDens (s.densTarget.load());\n                        s.lastDens = s.densTarget.load();")
pc = sub(pc, "            if (s.cur && lk != s.lastLink) { s.cur->setLink (lk); s.lastLink = lk; }", "            if (s.cur && lk != s.lastLink) { s.cur->setLink (lk); s.lastLink = lk; }\n            const double dn = s.densTarget.load();\n            if (s.cur && dn != s.lastDens) { s.cur->setDens (dn); s.lastDens = dn; }")
wr("Source/PluginProcessor.cpp", pc)

# ---------------------------------------------------------------- tests : références avec densité
x = rd("export_refs.py", HERE)
x = sub(x, '("mordant", "band", "highshelf", 8000.0, 0.71, 6.0, 4.0, -0.5)]\nfor fs, nom_sig, sig in', '("mordant", "band", "highshelf", 8000.0, 0.71, 6.0, 4.0, -0.5),\n         ("mordant_chaud", "auto", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0, 0.0), ("mordant_chaud", "auto", "bell", 3000.0, 0.71, 6.0, 2.5, 0.0, 0.5), ("doux", "auto", "highshelf", 9600.0, 0.71, 6.0, 2.0, 0.0, 0.25)]\nfor fs, nom_sig, sig in')
x = sub(x, "    for i, (pr, so, sh, f0, q, g, dr, tl) in enumerate(E2CFG):\n        nom = f\"exc2_{nom_sig}_{i}\"", "    for i, cfg in enumerate(E2CFG):\n        pr, so, sh, f0, q, g, dr, tl = cfg[:8]\n        dn = cfg[8] if len(cfg) > 8 else 1.0\n        nom = f\"exc2_{nom_sig}_{i}\"")
x = sub(x, "profil=pr, source=so, drive=dr, tilt=tl)\n        dump(nom, sig, y)\n        man.append(f\"exciter2 {nom} {fs} {sh} {f0} {q} {g} {pr} {so} {dr} {tl}\")", "profil=pr, source=so, drive=dr, tilt=tl, dens=dn)\n        dump(nom, sig, y)\n        man.append(f\"exciter2 {nom} {fs} {sh} {f0} {q} {g} {pr} {so} {dr} {tl} {dn}\")")
wr("export_refs.py", x, HERE)
t = rd("tests/test_refs.cpp")
t = sub(t, "            double g, dr, tl;\n            std::string pr, so;\n            is >> g >> pr >> so >> dr >> tl;", "            double g, dr, tl, dn = 1.0;\n            std::string pr, so;\n            is >> g >> pr >> so >> dr >> tl >> dn;")
t = sub(t, "so == \"auto\" ? SourceExc::Auto : SourceExc::Bande, dr, tl);\n            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process", "so == \"auto\" ? SourceExc::Auto : SourceExc::Bande, dr, tl, dn);\n            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (ex.process")
wr("tests/test_refs.cpp", t)
print("ok")
