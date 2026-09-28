#pragma once

#include <JuceHeader.h>
#include "PluginProcessor.h"
#include "UiParts.h"
using prismeParams::U8;

// Courbe de correction + spectre + nœuds des 5 bandes (maquette v1) : glisser un nœud = fréquence et gain, molette = Q, double-clic = bande active / coupée.
class CurveDisplay : public juce::Component, public prismeUi::HelpProvider, private juce::Timer
{
public:
    CurveDisplay (PrismeProcessor& p, std::function<int()> getSel, std::function<void (int)> setSel);
    ~CurveDisplay() override { stopTimer(); proc.setAnalyserActive (false); }

    void paint (juce::Graphics&) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDrag (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;
    void mouseDoubleClick (const juce::MouseEvent&) override;
    void mouseWheelMove (const juce::MouseEvent&, const juce::MouseWheelDetails&) override;
    void setShowSpectrum (bool b) { showSpec = b; repaint(); }
    juce::String helpAt (juce::Point<int> p) const override;

private:
    void timerCallback() override;
    float xOf (float f) const;
    float fOf (float x) const;
    float yOf (float g) const;
    float gOf (float y) const;
    static float response (int shape, float f0, float q, float gain, float f);
    float magFiltre (int band, float f) const;                 // module des filtres de la bande (Linkwitz-Riley)
    float effectif (int band, int shape, float f0, float q, float gain, float f) const;   // effet de la bande, filtres compris
    float fyDb (float db) const;
    int triangleAt (juce::Point<int> p) const;                 // 0 coupe-bas, 1 coupe-haut, −1 aucun
    juce::Rectangle<int> autresRect() const;
    void setFiltre (int k, bool on, float f);
    void setParam (const juce::String& id, float denormalised, bool gesture);

    PrismeProcessor& proc;
    std::function<int()> selGet;
    std::function<void (int)> selSet;
    bool showSpec = true;
    int dragBand = -1, dragFilt = -1;

    juce::dsp::FFT fft { 11 };
    juce::dsp::WindowingFunction<float> window { 2048, juce::dsp::WindowingFunction<float>::hann };
    std::vector<float> ring = std::vector<float> (2048, 0.0f);
    std::vector<float> fftData = std::vector<float> (4096, 0.0f);
    std::vector<float> specDb = std::vector<float> (1024, -120.0f);
    int ringPos = 0, sinceFft = 0;

    struct Ana { std::vector<float> ring = std::vector<float> (2048, 0.0f), spec = std::vector<float> (1024, -120.0f); int pos = 0, since = 0; };
    std::array<Ana, prismeParams::nBands> wetAna;              // spectre du delta de chaque bande (le wet à la couleur du traitement)
    void runFft (Ana& a);
};

// Les 5 onglets de bande (couleur du type, canal, forme · fréquence · gain).
class BandTabs : public juce::Component, public prismeUi::HelpProvider
{
public:
    BandTabs (PrismeProcessor& p, std::function<int()> getSel, std::function<void (int)> setSel) : proc (p), selGet (std::move (getSel)), selSet (std::move (setSel)) {}
    void paint (juce::Graphics&) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDoubleClick (const juce::MouseEvent&) override;
    juce::String helpAt (juce::Point<int> p) const override;

private:
    juce::Rectangle<int> cell (int i) const { const int gap = 8, w = (getWidth() - gap * 4) / 5; return { i * (w + gap), 0, w, getHeight() }; }
    PrismeProcessor& proc;
    std::function<int()> selGet;
    std::function<void (int)> selSet;
};

// Fiche de la bande sélectionnée : 3 colonnes × 2 rangées (type + forme | position + canal | réglages du type + note).
class BandCard : public juce::Component
{
public:
    explicit BandCard (PrismeProcessor& p) : proc (p) {}
    void rebuild (int band);
    void paint (juce::Graphics&) override;
    void resized() override;

private:
    struct Label { juce::String text; juce::Rectangle<int> r; };
    PrismeProcessor& proc;
    int band = 0;
    juce::Colour colour { prismeUi::col::exc };
    std::unique_ptr<prismeUi::TypeButtons> types;
    std::unique_ptr<prismeUi::PillButton> onButton;
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> onAttach;
    std::unique_ptr<prismeUi::Seg> forme, canal;
    std::vector<std::unique_ptr<prismeUi::Knob>> posKnobs;                 // fréquence, Q, gain
    std::vector<std::unique_ptr<prismeUi::Knob>> typeKnobs;
    std::vector<std::unique_ptr<prismeUi::Seg>> typeSegs;
    std::vector<juce::String> typeSegTitles;
    std::unique_ptr<juce::Slider> linkSlider;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> linkAttach;
    std::vector<Label> labels;
};

// Bandeau d'aide (bas de la fenêtre) : décrit ce que la souris survole. Écoute les événements souris de tous les composants du contenu.
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

// Contenu de l'editeur, dessine a une taille de base fixe puis mis a l'echelle (le redimensionnement garde les proportions de tous les elements).
class EditorContent : public juce::Component, public prismeUi::HelpProvider
{
public:
    juce::String helpAt (juce::Point<int> p) const override { return juce::Rectangle<int> (10, 8, 190, 42).contains (p) ? prismeParams::U8 ("PRISME : un clic sur le titre active / désactive le bypass (le titre s'assombrit).") : juce::String(); }
    std::function<void (juce::Graphics&)> onPaint;
    std::function<void (const juce::MouseEvent&)> onMouseDown;
    void paint (juce::Graphics& g) override { if (onPaint) onPaint (g); }
    void mouseDown (const juce::MouseEvent& e) override { if (onMouseDown) onMouseDown (e); }
};

class PrismeEditor : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit PrismeEditor (PrismeProcessor&);
    ~PrismeEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

    static constexpr int baseW = 1120, baseH = 816;                    // taille de CONCEPTION (mise a l'echelle ensuite)
    static constexpr int defaultW = 1040;                              // taille a l'ouverture (retour de llg53) ; la derniere taille utilisee est memorisee

private:
    void timerCallback() override;
    void select (int b);
    void layoutContent();
    int uiWidth = 0, lastUiWidth = 0;
    bool uiDirty = false;

    PrismeProcessor& proc;
    int sel = 2;
    EditorContent content;
    CurveDisplay display;
    BandTabs tabs;
    BandCard card;
    HelpBar helpBar;
    juce::Slider scaleSlider;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> scaleAttach;
    prismeUi::PillButton deltaBtn { U8 ("Écouter le delta"), U8 ("Écouter le delta") }, specBtn { "Spectre", "Spectre" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> deltaAttach;
    juce::Slider outSlider;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> outAttach;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PrismeEditor)
};
