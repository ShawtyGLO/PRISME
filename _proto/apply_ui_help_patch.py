"""Interface v1.1 : bandeau d'aide en bas (ce que la souris survole), plus de texte de note, Intensité globale, Densité de l'Exciter, courbes à l'échelle."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def rd(n):
    return open(os.path.join(SRC, n), encoding="utf-8").read()


def wr(n, s):
    open(os.path.join(SRC, n), "w", encoding="utf-8").write(s)


def sub(s, old, new):
    assert old in s, old[:90]
    return s.replace(old, new, 1)


NL = chr(10)

# ============================================================ UiParts.h : fournisseurs d'aide
u = rd("UiParts.h")
u = sub(u, "// Dessin des boutons rotatifs", '''// Un composant qui décrit lui-même ce que la souris survole (bandeau d'aide du bas) : sinon la propriété « aide » du composant ou d'un de ses parents est utilisée.
struct HelpProvider
{
    virtual ~HelpProvider() = default;
    virtual juce::String helpAt (juce::Point<int>) const { return {}; }
};

// Dessin des boutons rotatifs''')
# Seg : aide par option
u = sub(u, "class Seg : public juce::Component\n{", "class Seg : public juce::Component, public HelpProvider\n{")
u = sub(u, "    int preferredWidth (float fontH = 13.0f) const", '''    void setOptionHelp (juce::StringArray h) { optHelp = std::move (h); }

    juce::String helpAt (juce::Point<int> p) const override
    {
        juce::Font f { juce::FontOptions (13.0f) };
        int total = 0;
        for (auto& n : names) total += prismeUi::textWidth (f, n) + 24;
        const float scale = (float) getWidth() / (float) juce::jmax (1, total);
        float x = 0.0f;
        for (int i = 0; i < names.size(); ++i)
        {
            x += (float) (prismeUi::textWidth (f, names[i]) + 24) * scale;
            if ((float) p.x < x) return i < optHelp.size() ? optHelp[i] : juce::String();
        }
        return {};
    }

    int preferredWidth (float fontH = 13.0f) const''')
u = sub(u, "    juce::RangedAudioParameter* param;\n    std::function<void()> onChange;\n    int index = 0;\n    std::unique_ptr<juce::ParameterAttachment> attachment;\n};\n\n// Les 4 types", "    juce::RangedAudioParameter* param;\n    std::function<void()> onChange;\n    juce::StringArray optHelp;\n    int index = 0;\n    std::unique_ptr<juce::ParameterAttachment> attachment;\n};\n\n// Les 4 types")
u = sub(u, "class TypeButtons : public juce::Component\n{", "class TypeButtons : public juce::Component, public HelpProvider\n{")
u = sub(u, "    void mouseDown (const juce::MouseEvent& e) override\n    {\n        for (int i = 0; i < 4; ++i)\n            if (cell (i).contains (e.getPosition())) { attachment->setValueAsCompleteGesture ((float) i); return; }\n    }",
        '''    juce::String helpAt (juce::Point<int> p) const override
    {
        const char* aide[4] = { "Exciter : ajoute des harmoniques dans la zone, en parallèle (le signal d'origine n'est pas modifié).",
                                "Tame : atténue les résonances qui ressortent dans la zone (gain −) ou accentue les pics déjà forts (gain +).",
                                "Shape : agit sur les transitoires ou sur le sustain de la zone, dans les deux sens.",
                                "Lift : relève ce qui est faible dans la zone (gain +) ou l'abaisse (gain −), selon le niveau." };
        for (int i = 0; i < 4; ++i)
            if (cell (i).contains (p)) return prismeParams::U8 (aide[i]);
        return {};
    }

    void mouseDown (const juce::MouseEvent& e) override
    {
        for (int i = 0; i < 4; ++i)
            if (cell (i).contains (e.getPosition())) { attachment->setValueAsCompleteGesture ((float) i); return; }
    }''')
wr("UiParts.h", u)

# ============================================================ PluginEditor.h
h = rd("PluginEditor.h")
h = sub(h, "class CurveDisplay : public juce::Component, private juce::Timer\n{", "class CurveDisplay : public juce::Component, public prismeUi::HelpProvider, private juce::Timer\n{")
h = sub(h, "    void setShowSpectrum (bool b) { showSpec = b; repaint(); }", "    void setShowSpectrum (bool b) { showSpec = b; repaint(); }\n    juce::String helpAt (juce::Point<int> p) const override;")
h = sub(h, "class BandTabs : public juce::Component\n{", "class BandTabs : public juce::Component, public prismeUi::HelpProvider\n{")
h = sub(h, "    void mouseDoubleClick (const juce::MouseEvent&) override;\n\nprivate:\n    juce::Rectangle<int> cell", "    void mouseDoubleClick (const juce::MouseEvent&) override;\n    juce::String helpAt (juce::Point<int> p) const override;\n\nprivate:\n    juce::Rectangle<int> cell")
h = sub(h, "    juce::String note;\n", "")
h = sub(h, "    juce::Rectangle<int> noteRect;\n", "")
h = sub(h, "// Contenu de l'editeur", '''// Bandeau d'aide (bas de la fenêtre) : décrit ce que la souris survole. Écoute les événements souris de tous les composants du contenu.
class HelpBar : public juce::Component, public juce::MouseListener
{
public:
    void paint (juce::Graphics& g) override
    {
        const auto r = getLocalBounds().toFloat();
        g.setColour (prismeUi::col::panel);
        g.fillRoundedRectangle (r, 8.0f);
        g.setColour (prismeUi::col::line);
        g.drawRoundedRectangle (r.reduced (0.5f), 8.0f, 1.0f);
        g.setColour (text.isEmpty() ? prismeUi::col::mut.withAlpha (0.6f) : prismeUi::col::txt);
        g.setFont (13.0f);
        g.drawFittedText (text.isEmpty() ? U8 ("Survolez un réglage pour afficher son rôle.") : text, getLocalBounds().reduced (12, 2), juce::Justification::centredLeft, 2);
    }

    void mouseMove (const juce::MouseEvent& e) override { update (e); }
    void mouseEnter (const juce::MouseEvent& e) override { update (e); }
    void mouseDown (const juce::MouseEvent& e) override { update (e); }
    void mouseExit (const juce::MouseEvent&) override { setText ({}); }

private:
    void update (const juce::MouseEvent& e)
    {
        juce::String t;
        for (auto* p = e.eventComponent; p != nullptr && p != getParentComponent(); p = p->getParentComponent())
        {
            if (auto* hp = dynamic_cast<prismeUi::HelpProvider*> (p))
            {
                t = hp->helpAt (e.getEventRelativeTo (p).getPosition());
                if (t.isNotEmpty()) break;
            }
            if (p->getProperties().contains ("aide"))
            {
                t = p->getProperties()["aide"].toString();
                if (t.isNotEmpty()) break;
            }
        }
        setText (t);
    }

    void setText (const juce::String& t) { if (t != text) { text = t; repaint(); } }
    juce::String text;
};

// Contenu de l'editeur''')
h = sub(h, "class EditorContent : public juce::Component\n{\npublic:", "class EditorContent : public juce::Component, public prismeUi::HelpProvider\n{\npublic:\n    juce::String helpAt (juce::Point<int> p) const override { return juce::Rectangle<int> (10, 8, 190, 42).contains (p) ? prismeParams::U8 (\"PRISME : un clic sur le titre active / désactive le bypass (le titre s'assombrit).\") : juce::String(); }")
h = sub(h, "static constexpr int baseW = 1120, baseH = 780; ", "static constexpr int baseW = 1120, baseH = 816; ")
h = sub(h, "    BandCard card;\n", "    BandCard card;\n    HelpBar helpBar;\n    juce::Slider scaleSlider;\n    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> scaleAttach;\n")
wr("PluginEditor.h", h)

# ============================================================ PluginEditor.cpp
e = rd("PluginEditor.cpp")
e = sub(e, "static constexpr float kFMin = 20.0f, kFMax = 20000.0f, kGMax = 15.0f;", '''static constexpr float kFMin = 20.0f, kFMax = 20000.0f, kGMax = 15.0f;

static float scaleOf (PrismeProcessor& p) { return pp::raw (p.apvts, "scale"); }                              // Intensité globale (échelle du gain de toutes les bandes)
static void aide (juce::Component& c, const juce::String& t) { c.getProperties().set ("aide", t); }''')
# courbes / nœuds à l'échelle
e = sub(e, 'pp::raw (proc.apvts, pp::pid (i, "q")), pp::raw (proc.apvts, pp::pid (i, "gain")) };', 'pp::raw (proc.apvts, pp::pid (i, "q")), juce::jlimit (-kGMax, kGMax, pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)) };')
e = sub(e, 'y = yOf (pp::raw (proc.apvts, pp::pid (i, "gain")));', 'y = yOf (juce::jlimit (-kGMax, kGMax, pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)));')
e = sub(e, '    setParam (pp::pid (dragBand, "gain"), g, false);', '    const float sc = scaleOf (proc);                                                    // g est le gain EFFECTIF (affiché) : le réglage de la bande est g / Intensité\n    const float gBase = sc > 0.05f ? std::round (juce::jlimit (-kGMax, kGMax, g / sc) * 10.0f) / 10.0f : pp::raw (proc.apvts, pp::pid (dragBand, "gain"));\n    setParam (pp::pid (dragBand, "gain"), gBase, false);')
e = sub(e, 'fmtGain (pp::raw (proc.apvts, pp::pid (i, "gain"))),', 'fmtGain (pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)),')

# aide : courbe et onglets
e = sub(e, "void CurveDisplay::mouseDown (const juce::MouseEvent& e)", '''juce::String CurveDisplay::helpAt (juce::Point<int> p) const
{
    const auto ord = pp::bandOrder (proc.apvts);
    for (int i = 0; i < pp::nBands; ++i)
    {
        const float x = xOf (pp::raw (proc.apvts, pp::pid (i, "freq"))), y = yOf (juce::jlimit (-kGMax, kGMax, pp::raw (proc.apvts, pp::pid (i, "gain")) * scaleOf (proc)));
        if (std::hypot (x - (float) p.x, y - (float) p.y) < 18.0f)
            return U8 ("Bande ") + juce::String (ord.rankOf[i] + 1) + U8 (" (") + pp::typeNames()[juce::roundToInt (pp::raw (proc.apvts, pp::pid (i, "type")))]
                 + U8 (") : glisser = fréquence et gain, molette = Q, double-clic = activer / couper.");
    }
    return U8 ("Courbe : glisser un nœud (fréquence, gain), molette = Q de la bande sélectionnée. La zone colorée derrière montre le signal ajouté (wet) de chaque bande.");
}

void CurveDisplay::mouseDown (const juce::MouseEvent& e)''')
e = sub(e, "void BandTabs::mouseDoubleClick (const juce::MouseEvent& e)", '''juce::String BandTabs::helpAt (juce::Point<int> p) const
{
    for (int rank = 0; rank < pp::nBands; ++rank)
        if (cell (rank).contains (p)) return U8 ("Bande ") + juce::String (rank + 1) + U8 (" : clic = sélectionner, double-clic = activer / couper. Les bandes sont numérotées selon leur fréquence.");
    return {};
}

void BandTabs::mouseDoubleClick (const juce::MouseEvent& e)''')

# fiche : Densité + aides + plus de note
e = sub(e, '''addKnob ("drive", "Harmoniques", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });''', '''addKnob ("drive", "Harmoniques", [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });
                          addKnob ("dens", U8 ("Densité"), [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; });''')
i0 = e.index("    juce::String notes[4] = {")
i1 = e.index("    linkSlider.reset(); linkAttach.reset();")
aides = '''    // ---- aides du bandeau ----
    aide (*onButton, U8 ("Delta de la bande : n'écoute que le signal ajouté (wet) par cette bande."));
    forme->setOptionHelp ({ U8 ("Shelf grave : la bande agit en dessous de la fréquence (le Q est fixe)."), U8 ("Cloche : la bande agit autour de la fréquence, avec la largeur donnée par Q."), U8 ("Shelf aigu : la bande agit au-dessus de la fréquence (le Q est fixe).") });
    canal->setOptionHelp ({ U8 ("Stéréo : la bande traite les deux canaux (Exciter : source prise sur le milieu, même wet à gauche et à droite)."), U8 ("Mid : ne traite que le milieu (L+R)/2."), U8 ("Side : ne traite que les côtés (L−R)/2."),
                            U8 ("L : ne traite que le canal gauche."), U8 ("R : ne traite que le canal droit.") });
    aide (*posKnobs[0], U8 ("Fréquence de la bande (pour un shelf : fréquence de coupure). Maj = réglage fin, double-clic = valeur par défaut."));
    aide (*posKnobs[1], U8 ("Q : largeur de la cloche (plus élevé = plus étroit). Sans effet sur les shelfs."));
    const juce::String aideGain[4] = { U8 ("Gain de l'Exciter (0 à +15 dB) : dose du signal ajouté (wet). Toutes les bandes sont multipliées par Intensité (en haut)."),
                                       U8 ("Gain du Tame : négatif = atténue les résonances jusqu'à cette profondeur, positif = accentue les pics déjà forts."),
                                       U8 ("Gain du Shape : appliqué aux transitoires ou au sustain (selon Cible), dans les deux sens."),
                                       U8 ("Gain du Lift : positif = relève ce qui est faible, négatif = l'abaisse (expandeur).") };
    aide (*posKnobs[2], aideGain[type]);
    if (type == 0)
    {
        typeSegs[0]->setOptionHelp ({ U8 ("Doux : distorsion douce (tanh), harmoniques impaires discrètes : brillance sans agressivité."), U8 ("Chaud : distorsion asymétrique, harmoniques paires : chaleur et épaisseur."),
                                      U8 ("Mordant : écrêtage plus dur, harmoniques impaires : mordant et présence."), U8 ("Mordant chaud : écrêtage dur asymétrique : mordant et chaleur (profil de référence).") });
        typeSegs[1]->setOptionHelp ({ U8 ("Auto : la saturation est alimentée par une bande centrée à f0/3 : ses harmoniques tombent dans la zone réglée."), U8 ("Bande : la saturation est alimentée par la zone elle-même (permet le Tilt).") });
        aide (*typeKnobs[0], U8 ("Harmoniques : dureté de la saturation, de douce à dure (plus dur = plus d'harmoniques élevées)."));
        aide (*typeKnobs[1], U8 ("Densité : 0 % = le wet ne réagit qu'aux pics (salves nettes, peut pomper) ; 100 % = wet continu et régulier (halo)."));
        if (typeKnobs.size() > 2) aide (*typeKnobs[2], U8 ("Tilt : penche la source avant la saturation : négatif = plus de saturation dans les graves de la zone, positif = dans les aigus."));
    }
    else if (type == 1)
        aide (*typeKnobs[0], U8 ("Largeur de traitement : de fin (résonances étroites) à large (bosses larges)."));
    else if (type == 2)
    {
        typeSegs[0]->setOptionHelp ({ U8 ("Transitoires : le gain s'applique aux attaques de la zone."), U8 ("Sustain : le gain s'applique au corps du son, entre les attaques.") });
        aide (*typeKnobs[0], U8 ("Durée : combien de temps l'effet dure après une attaque (5 à 200 ms)."));
        aide (*typeKnobs[1], U8 ("Sensibilité : à 100 % toutes les attaques déclenchent, à 0 % seulement les plus vives."));
    }
    else
    {
        aide (*typeKnobs[0], U8 ("Amount : seuil absolu du relevé (−60 à −12 dBFS). Plus il monte, plus de matière est relevée."));
        aide (*typeKnobs[1], U8 ("Relâchement : vitesse à laquelle le gain revient (20 à 1000 ms)."));
    }
'''
e = e[:i0] + aides + e[i1:]
e = sub(e, "        addAndMakeVisible (*linkSlider);\n    }", "        addAndMakeVisible (*linkSlider);\n        aide (*linkSlider, U8 (\"Liaison L/R des détecteurs : 0 % = indépendants (précis par canal, l'image peut bouger), 100 % = mêmes décisions (image stable). 50 % = compromis.\"));\n    }")
e = sub(e, "        noteRect = { x3 + 232, yBot, w3 - 232, bottomH };\n    }\n    else\n        noteRect = { x3, yBot, w3, bottomH };", "    }")
e = sub(e, "    g.setFont (12.0f);\n    g.drawFittedText (note, noteRect, juce::Justification::topLeft, 5);\n", "")
e = sub(e, "kx2 += Knob::preferredWidth() + 8; }", "kx2 += Knob::preferredWidth() + 2; }")

# éditeur : Intensité, bandeau d'aide
e = sub(e, "    for (auto* c : std::initializer_list<juce::Component*> { &display, &tabs, &card, &deltaBtn, &specBtn, &outSlider })\n        content.addAndMakeVisible (c);",
        "    for (auto* c : std::initializer_list<juce::Component*> { &display, &tabs, &card, &deltaBtn, &specBtn, &outSlider, &scaleSlider, &helpBar })\n        content.addAndMakeVisible (c);\n    content.addMouseListener (&helpBar, true);")
e = sub(e, "    outAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (p.apvts, \"output\", outSlider);", '''    outAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (p.apvts, "output", outSlider);
    scaleSlider.setSliderStyle (juce::Slider::LinearHorizontal);
    scaleSlider.setTextBoxStyle (juce::Slider::TextBoxRight, false, 56, 22);
    scaleSlider.textFromValueFunction = [] (double v) { return juce::String (juce::roundToInt (v * 100.0)) + " %"; };
    scaleSlider.setColour (juce::Slider::trackColourId, col::mut);
    scaleSlider.setColour (juce::Slider::thumbColourId, col::txt);
    scaleSlider.setColour (juce::Slider::textBoxTextColourId, col::txt);
    scaleSlider.setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    scaleAttach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (p.apvts, "scale", scaleSlider);
    aide (scaleSlider, U8 ("Intensité : multiplie proportionnellement le gain de TOUTES les bandes. 100 % = vos réglages ; moins = traitement réduit ; plus (jusqu'à 200 %) = poussé à l'extrême."));
    aide (outSlider, U8 ("Niveau de sortie du plugin (−12 à +12 dB)."));
    aide (deltaBtn, U8 ("Écouter le delta : n'écoute que ce que les bandes ajoutent ou retirent (toutes les bandes)."));
    aide (specBtn, U8 ("Affiche ou masque le spectre de fond dans la courbe."))''' + ";")
e = sub(e, "        g.drawText (\"P R I S M E\", 16, 14, 240, 30, juce::Justification::left);\n", "        g.drawText (\"P R I S M E\", 16, 14, 240, 30, juce::Justification::left);\n        g.setColour (col::mut);\n        g.setFont (12.0f);\n        g.drawText (U8 (\"Intensité\"), scaleSlider.getX() - 66, scaleSlider.getY() + 2, 64, 22, juce::Justification::centredRight);\n        g.drawText (\"Sortie\", outSlider.getX() - 46, outSlider.getY() + 2, 44, 22, juce::Justification::centredRight);\n")
e = sub(e, "    outSlider.setBounds (header.removeFromRight (190).withTrimmedTop (10).withHeight (26));\n    header.removeFromRight (8);", "    outSlider.setBounds (header.removeFromRight (190).withTrimmedTop (10).withHeight (26));\n    header.removeFromRight (56);\n    scaleSlider.setBounds (header.removeFromRight (190).withTrimmedTop (10).withHeight (26));\n    header.removeFromRight (80);")
e = sub(e, "    const int cardH = 262, tabsH = 64;\n", "    helpBar.setBounds (a.removeFromBottom (30));\n    a.removeFromBottom (8);\n    const int cardH = 262, tabsH = 64;\n")
wr("PluginEditor.cpp", e)
print("ok")
