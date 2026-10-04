"""Patch 2026-10-04 : zone « raide » (option, Tame) — exposant du poids de zone ; paramètre « zone » par bande (Normale par défaut), AUCUNE interface."""
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME")


def edit(path, pairs):
    p = os.path.join(ROOT, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:90])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


edit("Source/Dsp/Tame.h", [
    ("    void prepare (double fs_, Forme forme, double f0, double q, double gainDb, double width)",
     "    void prepare (double fs_, Forme forme, double f0, double q, double gainDb, double width, double zonePente = 1.0)"),
    ("""            if (f[(size_t) k] < zoneLo * 0.999 || f[(size_t) k] > zoneHi * 1.001) w[(size_t) k] = 0.0;""",
     """            if (f[(size_t) k] < zoneLo * 0.999 || f[(size_t) k] > zoneHi * 1.001) w[(size_t) k] = 0.0;
        if (zonePente != 1.0)                                         // zone « raide » (option) : poids élevé à une puissance, flancs plus raides (2 : 12 dB/oct au lieu de 6)
            for (int k = 0; k < N; ++k) w[(size_t) k] = std::pow (w[(size_t) k], zonePente);"""),
])
edit("Source/Dsp/Engine.h", [
    ("    double width = 0.5;\n", "    double width = 0.5;\n    double zonePente = 1.0;                                 // Tame : 1 = zone normale, 2 = zone « raide » (option)\n"),
    ("cible == o.cible && timeMs == o.timeMs", "cible == o.cible && zonePente == o.zonePente && timeMs == o.timeMs"),
    ("tame[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.width);", "tame[k]->prepare (fs, s.forme, s.f0, s.q, s.gainDb, s.width, s.zonePente);"),
])
edit("Source/Params.h", [
    ("""        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "cible"), 1 }""",
     """        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "zone"), 1 }, n + U8 ("zone (Tame) : normale / raide"), sa ({ "Normale", "Raide" }), 0));
        layout.add (std::make_unique<juce::AudioParameterChoice> (P { pid (b, "cible"), 1 }"""),
    ("""    sp.width   = raw (s, pid (b, "width"));""",
     """    sp.width   = raw (s, pid (b, "width"));
    sp.zonePente = juce::roundToInt (raw (s, pid (b, "zone"))) == 1 ? 2.0 : 1.0;"""),
])
edit("tests/test_refs.cpp", [
    ("""            double g, wd;
            is >> g >> wd;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;""",
     """            double g, wd, zp = 1.0;
            is >> g >> wd >> zp;                                              // zp : exposant de zone (facultatif, 1 par défaut)
            if (! is) zp = 1.0;
            const auto xs = lire (dir + "/" + nom + ".in.f64"), ref = lire (dir + "/" + nom + ".out.f64");
            ++total;"""),
    ("            t.prepare (fs, forme (sh), f0, q, g, wd);\n            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (t.process (xs[i]) - ref[i]));",
     "            t.prepare (fs, forme (sh), f0, q, g, wd, zp);\n            for (size_t i = 0; i < xs.size(); ++i) e = std::max (e, std::abs (t.process (xs[i]) - ref[i]));"),
])
print("ok")
