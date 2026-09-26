"""Liaison stéréo partielle des détecteurs en C++ (Tame, Shape, Lift) + paramètre « Liaison », interface, tests. Principe : apply_link_patch_py.py."""
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME")
PY = os.path.dirname(os.path.abspath(__file__))


def rd(p, base=ROOT):
    return open(os.path.join(base, p), encoding="utf-8").read()


def wr(p, s, base=ROOT):
    open(os.path.join(base, p), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:90]
    return s.replace(old, new, 1)


# ---------------------------------------------------------------- Lift.h : detect / apply
l = rd("Source/Dsp/Lift.h")
l = sub(l, "    inline double process (double x, double* gOut = nullptr)\n    {\n        const double b = band.process (x), ab = std::abs (b);",
        "    inline double process (double x, double* gOut = nullptr)\n    {\n        double b;\n        const double s = detect (x, b);\n        return apply (x, b, s, gOut);\n    }\n\n    // Détection : renvoie la courbe de relevé s (0 … 1, porte de souffle comprise) et le signal de la zone b ; la liaison stéréo agit sur s.\n    inline double detect (double x, double& bOut)\n    {\n        const double b = band.process (x), ab = std::abs (b);\n        bOut = b;")
l = sub(l, "            s *= smoothstep ((Ls - N - marge) / 6.0);\n        }\n        const double g = std::pow (10.0, G * s / 20.0);\n        if (gOut) *gOut = g;\n        return x + (g - 1.0) * b;\n    }",
        "            s *= smoothstep ((Ls - N - marge) / 6.0);\n        }\n        return s;\n    }\n\n    inline double apply (double x, double b, double s, double* gOut = nullptr) const\n    {\n        const double g = std::pow (10.0, G * s / 20.0);\n        if (gOut) *gOut = g;\n        return x + (g - 1.0) * b;\n    }")
wr("Source/Dsp/Lift.h", l)

# ---------------------------------------------------------------- Shape.h
s = rd("Source/Dsp/Shape.h")
s = sub(s, "    inline double process (double x, double* gOut = nullptr)\n    {\n        const double b = band.process (x);",
        "    inline double process (double x, double* gOut = nullptr)\n    {\n        double b;\n        const double Tl = detect (x, b);\n        return apply (x, b, Tl, gOut);\n    }\n\n    // Détection : renvoie le poids « transitoire » lissé Tl (avant le choix transitoires / sustain) et le signal de la zone b ; la liaison stéréo agit sur Tl.\n    inline double detect (double x, double& bOut)\n    {\n        const double b = band.process (x);\n        bOut = b;")
s = sub(s, "        zAtt = (1.0 - cAtt) * yHold + cAtt * zAtt;                 // attaque du gain bornée\n        const double poids = cible == Cible::Transitoires ? zAtt : 1.0 - zAtt;",
        "        zAtt = (1.0 - cAtt) * yHold + cAtt * zAtt;                 // attaque du gain bornée\n        return zAtt;\n    }\n\n    inline double apply (double x, double b, double Tl, double* gOut = nullptr) const\n    {\n        const double poids = cible == Cible::Transitoires ? Tl : 1.0 - Tl;")
wr("Source/Dsp/Shape.h", s)

# ---------------------------------------------------------------- Tame.h : analyse / stage1 / stage2 / synth
t = rd("Source/Dsp/Tame.h")
t = sub(t, "    inline double process (double x)\n    {\n        const bool point = (count % DEC) == 0;\n        const int n = N;",
        "    inline bool isPoint() const { return (count % DEC) == 0; }\n\n    inline double process (double x)\n    {\n        analyse (x);\n        if (isPoint()) { stage1(); stage2(); }\n        return synth (x);\n    }\n\n    // Analyse : N biquads + 2 enveloppes par bande (à appeler avant stage1 / synth)\n    inline void analyse (double x)\n    {\n        const int n = N;")
t = sub(t, "        if (point) decimatedStep();\n        const int na = (int) act.size();", "    }\n\n    // Synthèse (après stage2 aux points décimés)\n    inline double synth (double x)\n    {\n        const bool point = isPoint();\n        const int na = (int) act.size();")
t = sub(t, "    void decimatedStep()\n    {", "public:\n    // Détection aux points décimés en deux temps : stage1 (jusqu'à la réduction par bande `redu`, où agit la liaison stéréo) puis stage2 (lissage temporel, normalisation locale)\n    float* reduData() { return redu.data(); }\n    int bandCount() const { return N; }\n\n    void stage1()\n    {")
t = sub(t, "        for (int k = 0; k < N; ++k) redu[(size_t) k] = (float) ((double) redu[(size_t) k] * w[(size_t) k]);\n        // lissage temporel", "        for (int k = 0; k < N; ++k) redu[(size_t) k] = (float) ((double) redu[(size_t) k] * w[(size_t) k]);\n    }\n\n    void stage2()\n    {\n        // lissage temporel")
t = sub(t, "        lastRed = redD;\n        lastS = SD;\n    }\n", "        lastRed = redD;\n        lastS = SD;\n    }\n\nprivate:\n")
wr("Source/Dsp/Tame.h", t)

# ---------------------------------------------------------------- Engine.h
g = rd("Source/Dsp/Engine.h")
g = sub(g, "    double amount = 50.0, releaseMs = 150.0;\n", "    double amount = 50.0, releaseMs = 150.0;\n    // Liaison stéréo PARTIELLE des détecteurs L/R (Tame, Shape, Lift ; canal Stéréo) : 0 = indépendants, 1 = mêmes décisions (défaut 0,5)\n    double link = 0.5;\n")
g = sub(g, "&& amount == o.amount && releaseMs == o.releaseMs;", "&& amount == o.amount && releaseMs == o.releaseMs && link == o.link;")
g = sub(g, "    void setTilt (double t)\n    {\n        spec.tilt = t;", "    void setLink (double l) { spec.link = l; }                                       // en direct\n\n    void setTilt (double t)\n    {\n        spec.tilt = t;")
g = sub(g, "                else { dL = delta (0, L); dR = delta (1, R); }\n                break;",
        "                else if (spec.link > 0.0 && spec.type != TypeBande::Exciter) pair (L, R, dL, dR);\n                else { dL = delta (0, L); dR = delta (1, R); }\n                break;")
g = sub(g, "private:\n    inline double delta (int i, double z)", '''private:
    // Canal Stéréo de Tame / Shape / Lift : détecteurs L/R liés PARTIELLEMENT au niveau de l'activité :  a_c' = (1 − λ)·a_c + λ·a_lié
    //   Tame : a = réduction par bande (max des deux) · Shape : poids transitoire (max) · Lift : courbe s (MIN : le canal le plus fort commande)
    inline void pair (double L, double R, double& dL, double& dR)
    {
        const double lam = spec.link;
        double yL = 0, yR = 0;
        switch (spec.type)
        {
            case TypeBande::Tame:
            {
                auto &a = *tame[0], &b = *tame[1];
                a.analyse (L);
                b.analyse (R);
                if (a.isPoint())
                {
                    a.stage1(); b.stage1();
                    float *ra = a.reduData(), *rb = b.reduData();
                    for (int k = 0; k < a.bandCount(); ++k)
                    {
                        const float xa = ra[k], xb = rb[k], mx = std::max (xa, xb);
                        ra[k] = (float) ((1.0 - lam) * (double) xa + lam * (double) mx);
                        rb[k] = (float) ((1.0 - lam) * (double) xb + lam * (double) mx);
                    }
                    a.stage2(); b.stage2();
                }
                yL = a.synth (L);
                yR = b.synth (R);
                break;
            }
            case TypeBande::Shape:
            {
                double bL, bR;
                const double aL = shape[0]->detect (L, bL), aR = shape[1]->detect (R, bR), lie = std::max (aL, aR);
                yL = shape[0]->apply (L, bL, (1.0 - lam) * aL + lam * lie);
                yR = shape[1]->apply (R, bR, (1.0 - lam) * aR + lam * lie);
                break;
            }
            case TypeBande::Lift:
            {
                double bL, bR;
                const double aL = lift[0]->detect (L, bL), aR = lift[1]->detect (R, bR), lie = std::min (aL, aR);
                yL = lift[0]->apply (L, bL, (1.0 - lam) * aL + lam * lie);
                yR = lift[1]->apply (R, bR, (1.0 - lam) * aR + lam * lie);
                break;
            }
            default: break;
        }
        dL = retard[0].push (yL - L);
        dR = retard[1].push (yR - R);
    }

    inline double delta (int i, double z)''')
wr("Source/Dsp/Engine.h", g)

# ---------------------------------------------------------------- Params.h
p = rd("Source/Params.h")
p = sub(p, '        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "drive"), 1 }', '        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "link"), 1 }, n + "liaison L/R (Tame, Shape, Lift)", juce::NormalisableRange<float> (0.0f, 1.0f, 0.01f), 0.5f));\n        layout.add (std::make_unique<juce::AudioParameterFloat>  (P { pid (b, "drive"), 1 }')
p = sub(p, '    sp.tilt    = raw (s, pid (b, "tilt"));', '    sp.tilt    = raw (s, pid (b, "tilt"));\n    sp.link    = raw (s, pid (b, "link"));')
wr("Source/Params.h", p)

# ---------------------------------------------------------------- PluginProcessor : liaison en direct
h = rd("Source/PluginProcessor.h")
h = sub(h, "        double lastTilt = 0.0;", "        double lastTilt = 0.0;\n        std::atomic<double> linkTarget { 0.5 };\n        double lastLink = 0.5;")
wr("Source/PluginProcessor.h", h)
c = rd("Source/PluginProcessor.cpp")
c = sub(c, "        structure.tilt = 0.0;", "        structure.tilt = 0.0;\n        structure.link = 0.0;")
c = sub(c, "            s.tiltTarget.store (spec.tilt);\n            s.lastTilt = spec.tilt;", "            s.tiltTarget.store (spec.tilt);\n            s.lastTilt = spec.tilt;\n            s.linkTarget.store (spec.link);\n            s.lastLink = spec.link;")
c = sub(c, "        s.tiltTarget.store (spec.tilt);\n        if (! s.msgAlive", "        s.tiltTarget.store (spec.tilt);\n        s.linkTarget.store (spec.link);\n        if (! s.msgAlive")
c = sub(c, "                        s.lastTilt = s.tiltTarget.load();", "                        s.lastTilt = s.tiltTarget.load();\n                        s.warm->setLink (s.linkTarget.load());\n                        s.lastLink = s.linkTarget.load();")
c = sub(c, "            if (s.cur && tv != s.lastTilt) { s.cur->setTilt (tv); s.lastTilt = tv; }", "            if (s.cur && tv != s.lastTilt) { s.cur->setTilt (tv); s.lastTilt = tv; }\n            const double lk = s.linkTarget.load();\n            if (s.cur && lk != s.lastLink) { s.cur->setLink (lk); s.lastLink = lk; }")
wr("Source/PluginProcessor.cpp", c)

# ---------------------------------------------------------------- Interface : curseur « Liaison L/R » (Tame, Shape, Lift, canal Stéréo) ; changer de canal reconstruit la fiche
e = rd("Source/PluginEditor.cpp")
e = sub(e, "    canal = std::make_unique<Seg> (ap, pp::pid (b, \"canal\"), pp::canalNames(), colour);", "    canal = std::make_unique<Seg> (ap, pp::pid (b, \"canal\"), pp::canalNames(), colour, [safe = juce::Component::SafePointer<BandCard> (self)] { if (safe != nullptr) safe->rebuild (safe->band); });")
e = sub(e, "    note = notes[type];", '''    note = notes[type];
    linkSlider.reset(); linkAttach.reset();
    if (type != 0 && juce::roundToInt (pp::raw (ap, pp::pid (b, "canal"))) == 0)         // liaison des détecteurs L/R : Tame, Shape, Lift en canal Stéréo
    {
        linkSlider = std::make_unique<juce::Slider> (juce::Slider::LinearHorizontal, juce::Slider::TextBoxRight);
        linkSlider->setTextBoxStyle (juce::Slider::TextBoxRight, false, 50, 22);
        linkSlider->setNumDecimalPlacesToDisplay (0);
        linkSlider->textFromValueFunction = [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; };
        linkSlider->setColour (juce::Slider::trackColourId, colour);
        linkSlider->setColour (juce::Slider::thumbColourId, col::txt);
        linkSlider->setColour (juce::Slider::textBoxTextColourId, col::txt);
        linkSlider->setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
        linkAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (ap, pp::pid (b, "link"), *linkSlider);
        addAndMakeVisible (*linkSlider);
    }''')
e = sub(e, "    noteRect = { x3, yBot, w3, bottomH };", '''    if (linkSlider)
    {
        labels.push_back ({ U8 ("LIAISON L/R"), { x3, yBot, 200, 16 } });
        linkSlider->setBounds (x3, yBot + 22, 215, 26);
        noteRect = { x3 + 232, yBot, w3 - 232, bottomH };
    }
    else
        noteRect = { x3, yBot, w3, bottomH };''')
e = sub(e, "    g.drawFittedText (note, noteRect, juce::Justification::topLeft, 3);", "    g.drawFittedText (note, noteRect, juce::Justification::topLeft, 5);")
wr("Source/PluginEditor.cpp", e)
hh = rd("Source/PluginEditor.h")
hh = sub(hh, "    juce::String note;\n", "    juce::String note;\n    std::unique_ptr<juce::Slider> linkSlider;\n    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> linkAttach;\n")
wr("Source/PluginEditor.h", hh)

# ---------------------------------------------------------------- Tests : cfg d'assemblage avec « link »
x = rd("export_refs.py", PY)
x = sub(x, 's.get("amount", 50.0), s.get("release_ms", 150.0))) + "\\n")', 's.get("amount", 50.0), s.get("release_ms", 150.0), s.get("link", 0.5))) + "\\n")') if 's.get("amount", 50.0), s.get("release_ms", 150.0))) + "\\n")' in x else x
wr("export_refs.py", x, PY)
print("ok")
