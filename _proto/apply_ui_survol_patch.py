"""Patch UI 2026-10-24 (VALIDÉ par llg53 le 2026-10-24 : « 1 tel quel, 2 oui, 3 parfait ») : pastilles qui s'ouvrent au survol — « filtres des autres bandes » (œil, coin bas droit de l'écran)
et « autogain » (témoin, à gauche de « Sortie ») ; le curseur Sortie est grisé quand l'autogain est actif (et ignoré par le moteur)."""
import os
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PRISME", "Source")


def edit(path, pairs):
    p = os.path.join(SRC, path)
    s = open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert a in s, (path, a[:90])
        s = s.replace(a, b, 1)
    open(p, "w", encoding="utf-8").write(s)


PASTILLE = '''
// Pastille ronde qui s'ouvre au survol et affiche son libellé (maquette « survol » validée) ; cliquable ; seule la zone dessinée reçoit la souris.
class PastilleSurvol : public juce::Component, private juce::Timer
{
public:
    std::function<void (juce::Graphics&, juce::Rectangle<float>, bool)> icone;      // dessine l'icône dans un carré de 16 px ; bool = état allumé
    std::function<juce::String()> libelle;                                          // texte affiché une fois ouverte
    std::function<bool()> actif;                                                    // état allumé (fond plus clair)
    std::function<void()> clic;

    bool hitTest (int x, int y) override { return rectCourant().contains ((float) x, (float) y); }

    void paint (juce::Graphics& g) override
    {
        const auto r = rectCourant();
        const bool on = actif ? actif() : true;
        g.setColour (juce::Colours::black.withAlpha (0.35f));
        g.fillRoundedRectangle (r.translated (0.0f, 1.5f), r.getHeight() / 2.0f);
        g.setColour (on ? juce::Colour (0xff232830) : col::panel);
        g.fillRoundedRectangle (r, r.getHeight() / 2.0f);
        g.setColour (on ? juce::Colour (0xff4a5568) : col::line);
        g.drawRoundedRectangle (r.reduced (0.5f), r.getHeight() / 2.0f, 1.0f);
        if (icone) icone (g, { r.getX() + 7.0f, r.getCentreY() - 8.0f, 16.0f, 16.0f }, on);
        if (ouv > 0.35f && libelle)
        {
            g.setColour ((on ? col::txt : col::mut).withAlpha (juce::jlimit (0.0f, 1.0f, (ouv - 0.35f) / 0.65f)));
            g.setFont (12.0f);
            g.drawText (libelle(), juce::Rectangle<float> (r.getX() + 31.0f, r.getY(), r.getWidth() - 31.0f, r.getHeight()), juce::Justification::centredLeft);
        }
    }

    void mouseEnter (const juce::MouseEvent&) override { cible = 1.0f; startTimerHz (60); }
    void mouseExit (const juce::MouseEvent&) override { cible = 0.0f; startTimerHz (60); }
    void mouseUp (const juce::MouseEvent& e) override { if (e.mouseWasClicked() && rectCourant().contains (e.position) && clic) { clic(); repaint(); } }

private:
    float largeurOuverte() const
    {
        const auto t = libelle ? libelle() : juce::String();
        return 31.0f + (float) textWidth (juce::Font (juce::FontOptions (12.0f)), t) + 14.0f;
    }
    juce::Rectangle<float> rectCourant() const
    {
        const float w = 30.0f + (largeurOuverte() - 30.0f) * ouv;
        return { (float) getWidth() - w, ((float) getHeight() - 30.0f) / 2.0f, w, 30.0f };      // ancrée à droite : elle s'ouvre vers la gauche
    }
    void timerCallback() override
    {
        ouv += (cible - ouv) * 0.35f;
        if (std::abs (cible - ouv) < 0.01f) { ouv = cible; stopTimer(); }
        repaint();
    }
    float ouv = 0.0f, cible = 0.0f;
};
'''

s = open(os.path.join(SRC, "UiParts.h"), encoding="utf-8").read()
k = s.rindex("\n}")
s = s[:k] + "\n" + PASTILLE + s[k:]
open(os.path.join(SRC, "UiParts.h"), "w", encoding="utf-8").write(s)

edit("PluginEditor.h", [
    ("    void paint (juce::Graphics&) override;\n    void mouseDown (const juce::MouseEvent&) override;\n    void mouseDrag",
     "    void paint (juce::Graphics&) override;\n    void resized() override;\n    void mouseDown (const juce::MouseEvent&) override;\n    void mouseDrag"),
    ("    juce::Rectangle<int> autresRect() const;\n", "    prismeUi::PastilleSurvol pastilleAutres;                   // « filtres des autres bandes » : œil, s'ouvre au survol\n"),
    ("    prismeUi::PillButton deltaPosBtn", "    prismeUi::PastilleSurvol autogainPill;                     // autogain : témoin, s'ouvre au survol sur « Autogain −x,x dB »\n    prismeUi::PillButton deltaPosBtn"),
])

edit("PluginEditor.cpp", [
    # ancien libellé et ancien bouton : retirés
    ("""        g.setColour (col::mut.withAlpha (0.8f));
        g.setFont (10.0f);
        g.drawText (autres ? U8 ("autres filtres : visibles") : U8 ("autres filtres : masqués"), autresRect(), juce::Justification::centred);
""", ""),
    ("""    if (autresRect().contains (p)) return U8 ("Clic : afficher (en pointillés) ou masquer les filtres des autres bandes.");
""", ""),
    ("""    if (autresRect().contains (e.getPosition()))
    {
        proc.apvts.state.setProperty ("filtresAutres", ! (bool) proc.apvts.state.getProperty ("filtresAutres", true), nullptr);
        repaint();
        return;
    }
""", ""),
    ("""// Hors de la zone des triangles de filtres (bande du haut) : un bouton posé sur leur course les rendrait inatteignables.
juce::Rectangle<int> CurveDisplay::autresRect() const { return { getWidth() - 190, getHeight() - 34, 184, 16 }; }
""", ""),
    # construction de la pastille dans l'écran
    ("""    : proc (p), selGet (std::move (getSel)), selSet (std::move (setSel))
{""", """    : proc (p), selGet (std::move (getSel)), selSet (std::move (setSel))
{
    pastilleAutres.icone = [] (juce::Graphics& g, juce::Rectangle<float> r, bool on)          // œil (barré quand les filtres des autres bandes sont masqués)
    {
        const float cx = r.getCentreX(), cy = r.getCentreY();
        juce::Path oeil;
        oeil.startNewSubPath (cx - 8.0f, cy);
        oeil.quadraticTo (cx, cy - 9.0f, cx + 8.0f, cy);
        oeil.quadraticTo (cx, cy + 9.0f, cx - 8.0f, cy);
        g.setColour (on ? col::txt : col::mut);
        g.strokePath (oeil, juce::PathStrokeType (1.6f));
        g.drawEllipse (cx - 2.6f, cy - 2.6f, 5.2f, 5.2f, 1.6f);
        if (! on) g.drawLine (cx - 7.0f, cy + 8.0f, cx + 7.0f, cy - 8.0f, 1.6f);
    };
    pastilleAutres.actif = [this] { return (bool) proc.apvts.state.getProperty ("filtresAutres", true); };
    pastilleAutres.libelle = [this] { return (bool) proc.apvts.state.getProperty ("filtresAutres", true) ? U8 ("Filtres des autres bandes : visibles") : U8 ("Filtres des autres bandes : masqués"); };
    pastilleAutres.clic = [this] { proc.apvts.state.setProperty ("filtresAutres", ! (bool) proc.apvts.state.getProperty ("filtresAutres", true), nullptr); repaint(); };
    aide (pastilleAutres, U8 ("Clic : afficher (en pointillés) ou masquer les filtres des autres bandes."));
    addAndMakeVisible (pastilleAutres);"""),
    ("""void CurveDisplay::timerCallback()""", """void CurveDisplay::resized()
{
    pastilleAutres.setBounds (getWidth() - 10 - 330, getHeight() - 9 - 30, 330, 30);          // coin bas droit : hors de la bande des triangles
}

void CurveDisplay::timerCallback()"""),
    # autogain dans l'éditeur
    ("""    deltaPosAttach = std::make_unique""", """    content.addAndMakeVisible (autogainPill);
    autogainPill.icone = [] (juce::Graphics& g, juce::Rectangle<float> r, bool on)             // témoin rond (vert allumé quand l'autogain est actif)
    {
        const auto c = r.getCentre();
        if (on)
        {
            for (int i = 3; i >= 1; --i) { g.setColour (juce::Colour (0xff7ddc6a).withAlpha (0.10f)); g.fillEllipse (c.x - 4.5f - (float) i * 1.4f, c.y - 4.5f - (float) i * 1.4f, 9.0f + (float) i * 2.8f, 9.0f + (float) i * 2.8f); }
            g.setColour (juce::Colour (0xff7ddc6a));
        }
        else g.setColour (juce::Colour (0xff3a414c));
        g.fillEllipse (c.x - 4.5f, c.y - 4.5f, 9.0f, 9.0f);
    };
    autogainPill.actif = [this] { return pp::raw (proc.apvts, "sonie") > 0.5f; };
    autogainPill.libelle = [this]
    {
        if (pp::raw (proc.apvts, "sonie") < 0.5f) return U8 ("Autogain : inactif");
        const float g = proc.sonieGainDb.load();
        return U8 ("Autogain  ") + (g > 0.0f ? juce::String ("+") : juce::String()) + juce::String (g, 1).replace ("-", U8 ("−")) + " dB";
    };
    autogainPill.clic = [this]
    {
        if (auto* p = proc.apvts.getParameter ("sonie"))
        {
            p->beginChangeGesture();
            p->setValueNotifyingHost (pp::raw (proc.apvts, "sonie") > 0.5f ? 0.0f : 1.0f);
            p->endChangeGesture();
        }
    };
    aide (autogainPill, U8 ("Autogain : recale en continu le signal traité sur la sonie du signal d'entrée, pour comparer (bypass) à volume égal. Le curseur Sortie est alors inactif. Cliquer pour activer ou couper."));
    deltaPosAttach = std::make_unique"""),
    ("""    tabs.repaint();
    content.repaint (0, 0, 260, 50);""", """    tabs.repaint();
    content.repaint (0, 0, 260, 50);
    const bool ag = pp::raw (proc.apvts, "sonie") > 0.5f;                                    // Sortie grisé quand l'autogain est actif
    if (outSlider.isEnabled() == ag) { outSlider.setEnabled (! ag); outSlider.setAlpha (ag ? 0.45f : 1.0f); }
    autogainPill.repaint();"""),
    ("""    header.removeFromRight (56);
    scaleSlider.setBounds""", """    autogainPill.setBounds (outSlider.getX() - 50 - 320, outSlider.getY() - 2, 320, 30);        // à gauche de « Sortie » ; s'ouvre vers la gauche
    header.removeFromRight (56);
    scaleSlider.setBounds"""),
])

# moteur : le curseur Sortie est ignoré quand l'autogain est actif
edit("PluginProcessor.cpp", [
    ("""    outGain.setTargetValue (juce::Decibels::decibelsToGain (prismeParams::raw (apvts, "output")));
    const bool sonieOn""", """    outGain.setTargetValue (prismeParams::raw (apvts, "sonie") > 0.5f ? 1.0f : juce::Decibels::decibelsToGain (prismeParams::raw (apvts, "output")));      // autogain actif : Sortie ignoré
    const bool sonieOn"""),
])
print("ok")
