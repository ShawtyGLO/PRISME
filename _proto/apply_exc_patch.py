"""Patch C++ de l'Exciter v0.5 : AGC élargie (10 ms, 0,05 … +40 dB), Tilt (mode Bande), coude du Rectifier réglé par Saturation ; paramètres, interface."""
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def rd(n):
    return open(os.path.join(ROOT, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(ROOT, n), "w", encoding="utf-8").write(s)


def sub(s, old, new, count=1):
    assert old in s, old[:70]
    return s.replace(old, new, count)


# ---------------------------------------------------------------- Biquad.h : shelf RBJ
b = rd("Dsp/Biquad.h")
b = sub(b, "// Forme de la zone d'une bande", '''// Shelf RBJ (pente S = 1) : haut = true → shelf aigu. Mêmes formules que `rbj_shelf` du prototype.
inline BiquadCoefs rbjShelf (double fs, double f0, double gainDb, bool haut)
{
    const double A = std::pow (10.0, gainDb / 40.0), w0 = 2.0 * kPi * f0 / fs, c = std::cos (w0), s = std::sin (w0);
    const double al = s / 2.0 * std::sqrt ((A + 1.0 / A) * (1.0 / 1.0 - 1.0) + 2.0), t = 2.0 * std::sqrt (A) * al;
    double b0, b1, b2, a0, a1, a2;
    if (haut)
    {
        b0 = A * ((A + 1) + (A - 1) * c + t);  b1 = -2 * A * ((A - 1) + (A + 1) * c);  b2 = A * ((A + 1) + (A - 1) * c - t);
        a0 = (A + 1) - (A - 1) * c + t;        a1 = 2 * ((A - 1) - (A + 1) * c);       a2 = (A + 1) - (A - 1) * c - t;
    }
    else
    {
        b0 = A * ((A + 1) - (A - 1) * c + t);  b1 = 2 * A * ((A - 1) - (A + 1) * c);   b2 = A * ((A + 1) - (A - 1) * c - t);
        a0 = (A + 1) + (A - 1) * c + t;        a1 = -2 * ((A - 1) + (A + 1) * c);      a2 = (A + 1) + (A - 1) * c - t;
    }
    return { b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0 };
}

// Forme de la zone d'une bande''')
wr("Dsp/Biquad.h", b)

# ---------------------------------------------------------------- Exciter.h
e = rd("Dsp/Exciter.h")
# courbes : eps du Rectifier variable
e = sub(e, "constexpr double B = 0.18, EPS_R = 0.05;", "constexpr double B = 0.18, EPS_R = 0.05;               // EPS_R : coude du Rectifier à drive 1,5 (varie avec « Saturation » : eps = 0,05 · (1,5 / drive)²)")
e = sub(e, "inline double f (ModeSat m, double x)\n{", "inline double f (ModeSat m, double x, double eps = EPS_R)\n{")
e = sub(e, "        case ModeSat::Rect:   return std::sqrt (x * x + EPS_R * EPS_R) - EPS_R;", "        case ModeSat::Rect:   return std::sqrt (x * x + eps * eps) - eps;")
e = sub(e, "inline double F (ModeSat m, double x)                      // primitive (ADAA d'ordre 1)\n{", "inline double F (ModeSat m, double x, double eps = EPS_R)         // primitive (ADAA d'ordre 1)\n{")
e = sub(e, "        case ModeSat::Rect:   return 0.5 * (x * std::sqrt (x * x + EPS_R * EPS_R) + EPS_R * EPS_R * std::asinh (x / EPS_R)) - EPS_R * x;",
        "        case ModeSat::Rect:   return 0.5 * (x * std::sqrt (x * x + eps * eps) + eps * eps * std::asinh (x / eps)) - eps * x;")
e = sub(e, "courbes::f (mode, 0.5 * (v + xp))", "courbes::f (mode, 0.5 * (v + xp), epsR)")
e = sub(e, "(courbes::F (mode, v) - courbes::F (mode, xp)) / dxv", "(courbes::F (mode, v, epsR) - courbes::F (mode, xp, epsR)) / dxv")
# AGC + tilt + drive
e = sub(e, "        aEnv = std::exp (-1.0 / (0.02 * fs));", "        aEnv = std::exp (-1.0 / (agcTau * fs));")
e = sub(e, "1.0, 15.848931924611136);", "agcGmin, agcGmax);")
e = sub(e, "    static constexpr double floorRatio = 0.05;", "    static constexpr double floorRatio = 0.05;\n    // AGC d'entrée : enveloppe 10 ms, gain de 0,05 à +40 dB (l'ancien plafond de +24 dB était atteint presque tout le temps : « Saturation » sans effet, delta pointu)\n    static constexpr double agcTau = 0.01, agcGmin = 0.05, agcGmax = 100.0, tiltDb = 9.0;\n    double epsR = courbes::EPS_R;\n    Forme forme = Forme::Cloche;\n    double f0 = 1000.0, fsHz = 48000.0;\n    bool tiltOn = false;\n    Biquad tiltLo, tiltHi;")
e = sub(e, "    void setDrive (double d) { drive = d; }                     // en direct, sans réinitialiser",
        '''    void setDrive (double d)                                  // en direct, sans réinitialiser
    {
        drive = d;
        epsR = courbes::EPS_R * (1.5 / d) * (1.5 / d);       // Rectifier : « Saturation » règle le coude (homogène en amplitude, le niveau n'y change rien)
    }

    // Tilt −1 … +1 (mode Bande seulement) : bascule de tonalité de la source avant la saturation ; en direct, l'état des filtres est conservé.
    void setTilt (double t)
    {
        if (source != SourceExc::Bande) return;
        if (std::abs (t) <= 1e-9 && ! tiltOn) return;
        const double pv = forme == Forme::ShelfAigu ? std::min (0.4 * fsHz, f0 * 2.5) : forme == Forme::ShelfGrave ? std::max (40.0, f0 / 2.5) : f0;
        tiltLo.set (rbjShelf (fsHz, pv, -0.5 * tiltDb * t, false));
        tiltHi.set (rbjShelf (fsHz, pv, +0.5 * tiltDb * t, true));
        tiltOn = true;
    }''')
e = sub(e, "        mode = mode_;\n        source = source_;", "        mode = mode_;\n        source = source_;\n        forme = forme_;\n        f0 = f0_;\n        fsHz = fs;\n        tiltOn = false;\n        tiltLo.reset(); tiltHi.reset();")
e = sub(e, "    void prepare (double fs, Forme forme, double f0, double q, double gainDb, ModeSat mode_, SourceExc source_)", "    void prepare (double fs, Forme forme_, double f0_, double q, double gainDb, ModeSat mode_, SourceExc source_)")
# dans prepare, les appels utilisent forme / f0 (paramètres) : ils portent maintenant les noms forme_ / f0_
i0 = e.index("    void prepare (double fs, Forme forme_")
i1 = e.index("    void setDrive")
body = e[i0:i1]
body2 = body.replace("zoneFilter (forme, fs,", "zoneFilter (forme_, fs,").replace("f0 / courbes::harmoniqueDominant", "f0_ / courbes::harmoniqueDominant")
body2 = body2.replace("fs, fsrc, qsrc", "fs, fsrc, qsrc").replace("zoneFilter (forme_, fs, f0, q)", "zoneFilter (forme_, fs, f0_, q)").replace("fs, f0, q)", "fs, f0_, q)")
e = e[:i0] + body2 + e[i1:]
# le tilt s'applique après le filtre de source (Bande)
e = sub(e, "        // gain adaptatif (montée seulement, jusqu'à +24 dB)", "        if (tiltOn) s0 = tiltHi.process (tiltLo.process (s0));       // Tilt (mode Bande) avant l'AGC et la saturation\n        // gain adaptatif (AGC : 0,05 … +40 dB)")
wr("Dsp/Exciter.h", e)

# ---------------------------------------------------------------- Engine.h : tilt dans la spec
g = rd("Dsp/Engine.h")
g = sub(g, "    double drive = 1.5;", "    double tilt = 0.0;                                      // −1 … +1, mode Bande seulement\n    double drive = 1.5;")
g = sub(g, "&& drive == o.drive", "&& drive == o.drive && tilt == o.tilt")
g = sub(g, "exc[k]->setDrive (s.drive); break;", "exc[k]->setDrive (s.drive); exc[k]->setTilt (s.tilt); break;")
g = sub(g, "    void setDrive (double d)\n    {\n        spec.drive = d;", "    void setTilt (double t)\n    {\n        spec.tilt = t;\n        for (int i = 0; i < n; ++i)\n            if (exc[(size_t) i]) exc[(size_t) i]->setTilt (t);\n    }\n\n    void setDrive (double d)\n    {\n        spec.drive = d;")
wr("Dsp/Engine.h", g)

# ---------------------------------------------------------------- Params.h
p = rd("Params.h")
p = sub(p, '        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "drive"), 1 }',
        '        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "tilt"), 1 }, n + "tilt (mode Bande)", juce::NormalisableRange<float> (-1.0f, 1.0f, 0.01f), 0.0f));\n        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "drive"), 1 }')
p = sub(p, "    sp.drive   = driveFromKnob", "    sp.tilt    = raw (s, pid (b, \"tilt\"));\n    sp.drive   = driveFromKnob")
wr("Params.h", p)

# ---------------------------------------------------------------- PluginProcessor : tilt en direct
h = rd("PluginProcessor.h")
h = sub(h, "        double lastDrive = 1.5;", "        double lastDrive = 1.5;\n        std::atomic<double> tiltTarget { 0.0 };\n        double lastTilt = 0.0;")
wr("PluginProcessor.h", h)
c = rd("PluginProcessor.cpp")
c = sub(c, "        structure.drive = 0.0;", "        structure.drive = 0.0;\n        structure.tilt = 0.0;")
c = sub(c, "            s.driveTarget.store (spec.drive);\n            s.lastDrive = spec.drive;", "            s.driveTarget.store (spec.drive);\n            s.lastDrive = spec.drive;\n            s.tiltTarget.store (spec.tilt);\n            s.lastTilt = spec.tilt;")
c = sub(c, "        s.driveTarget.store (spec.drive);\n        if (! s.msgAlive", "        s.driveTarget.store (spec.drive);\n        s.tiltTarget.store (spec.tilt);\n        if (! s.msgAlive")
c = sub(c, "                        s.lastDrive = s.driveTarget.load();", "                        s.lastDrive = s.driveTarget.load();\n                        s.warm->setTilt (s.tiltTarget.load());\n                        s.lastTilt = s.tiltTarget.load();")
c = sub(c, "            if (s.cur && dv != s.lastDrive) { s.cur->setDrive (dv); s.lastDrive = dv; }", "            if (s.cur && dv != s.lastDrive) { s.cur->setDrive (dv); s.lastDrive = dv; }\n            const double tv = s.tiltTarget.load();\n            if (s.cur && tv != s.lastTilt) { s.cur->setTilt (tv); s.lastTilt = tv; }")
wr("PluginProcessor.cpp", c)

# ---------------------------------------------------------------- Interface : Tilt visible en mode Bande ; changement de source → reconstruction de la fiche
u = rd("UiParts.h")
u = sub(u, "    Seg (juce::AudioProcessorValueTreeState& apvts, const juce::String& paramId, const juce::StringArray& names_, juce::Colour c)\n        : names (names_), colour (c), param (apvts.getParameter (paramId))\n    {\n        attachment = std::make_unique<juce::ParameterAttachment> (*param, [this] (float v) { index = juce::roundToInt (v); repaint(); });",
        "    Seg (juce::AudioProcessorValueTreeState& apvts, const juce::String& paramId, const juce::StringArray& names_, juce::Colour c, std::function<void()> onChange_ = {})\n        : names (names_), colour (c), param (apvts.getParameter (paramId)), onChange (std::move (onChange_))\n    {\n        index = juce::roundToInt (param->convertFrom0to1 (param->getValue()));\n        attachment = std::make_unique<juce::ParameterAttachment> (*param, [this] (float v)\n        {\n            const int nv = juce::roundToInt (v);\n            const bool changed = nv != index;\n            index = nv;\n            repaint();\n            if (changed && onChange) juce::MessageManager::callAsync ([fn = onChange] { fn(); });\n        });")
u = sub(u, "    juce::RangedAudioParameter* param;\n    int index = 0;\n    std::unique_ptr<juce::ParameterAttachment> attachment;\n};\n\n// Les 4 types", "    juce::RangedAudioParameter* param;\n    std::function<void()> onChange;\n    int index = 0;\n    std::unique_ptr<juce::ParameterAttachment> attachment;\n};\n\n// Les 4 types")
wr("UiParts.h", u)
ed = rd("PluginEditor.cpp")
ed = sub(ed, "    auto addSeg = [&] (const char* id, const juce::String& title, const juce::StringArray& names)\n    {\n        typeSegs.push_back (std::make_unique<Seg> (ap, pp::pid (b, id), names, colour));",
         "    auto addSeg = [&] (const char* id, const juce::String& title, const juce::StringArray& names)\n    {\n        typeSegs.push_back (std::make_unique<Seg> (ap, pp::pid (b, id), names, colour, [safe = juce::Component::SafePointer<BandCard> (this)] { if (safe != nullptr) safe->rebuild (safe->band); }));")
ed = sub(ed, 'addKnob ("drive", "Saturation", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; }); }',
         'addKnob ("drive", "Saturation", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });\n                          if (juce::roundToInt (pp::raw (proc.apvts, pp::pid (b, "source"))) == 1) addKnob ("tilt", "Tilt", [] (double v) { return (v > 0 ? juce::String ("+") : juce::String()) + juce::String (v, 2); }); }')
ed = sub(ed, "        for (auto& k : typeKnobs) k->setBounds (x3 + maxW + 24, yTop + 24, Knob::preferredWidth(), Knob::preferredHeight());\n    }",
         "        int kx2 = x3 + maxW + 24;\n        for (auto& k : typeKnobs) { k->setBounds (kx2, yTop + 24, Knob::preferredWidth(), Knob::preferredHeight()); kx2 += Knob::preferredWidth() + 8; }\n    }")
ed = sub(ed, "Ajoute des harmoniques dans la zone (gain de 0 à +15 dB). Saturation : de doux à très saturé.", "Ajoute des harmoniques dans la zone (gain de 0 à +15 dB). Saturation : de doux à très saturé. En mode Bande, Tilt penche la source : plus de saturation dans les graves (−) ou les aigus (+).")
wr("PluginEditor.cpp", ed)
print("ok")
